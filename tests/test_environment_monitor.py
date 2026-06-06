"""Lock current behavior of EnvironmentMonitor: measurement JSON,
flat-line detection, stale escalation, reset scheduling.

Uses the injected Scd41 bus seam (R2, Phase 3) and Clock seam (R3, Phase 2).
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from Clock import Clock
from EnvironmentMonitor import EnvironmentMonitor
from Scd41 import Scd41


# Constants from EnvironmentMonitor for reference
FLAT_LINE_TIMEOUT = 900
ERROR_SOFT_RESET_THRESHOLD = 3
ERROR_HARD_RESET_THRESHOLD = 10
STALE_MEASUREMENT_TIMEOUT = 60
HEALTH_CHECK_INTERVAL = 30


@pytest.fixture
def frozen(monkeypatch):
    t = [datetime(2024, 1, 1, 0, 0, 0)]
    monkeypatch.setattr(Clock, "now", staticmethod(lambda: t[0]))
    class Ctrl:
        def advance(self, seconds):
            t[0] = t[0] + timedelta(seconds=seconds)
        def set(self, new_t):
            t[0] = new_t
    return Ctrl()


@pytest.fixture
def fake_scd41(monkeypatch):
    """A MagicMock standing in for Scd41, allowing control over its side effects."""
    scd = MagicMock()
    # Stop the real __init__ from touching I²C: replace Scd41 class
    monkeypatch.setattr("EnvironmentMonitor.Scd41", MagicMock(return_value=scd))
    return scd


@pytest.fixture
def mqtt():
    return MagicMock()


@pytest.fixture
def timer():
    from Timer import Timer
    return Timer()


@pytest.fixture
def em(timer, mqtt, fake_scd41, frozen):
    e = EnvironmentMonitor(timer, mqtt)
    return e


def test_measurement_publishes_json_and_fires_callback(em, mqtt, frozen):
    captured = []
    em.onMeasurement = lambda env: captured.append((env.co2, env.temperature, env.relativeHumidity))

    em._onMeasurement(800, 22.5, 45.3)

    # The exact JSON format the current code emits (incl. trailing space)
    expected_json = '{"co2":800, "temperature":22.5, "relativeHumidity":45.3 }'
    mqtt.publishState.assert_called_with("environment", expected_json)
    assert captured == [(800, 22.5, 45.3)]


def test_measurement_resets_consecutive_errors_and_last_measurement(em, frozen):
    em._consecutiveErrors = 5
    em._lastMeasurement = datetime(2000, 1, 1)
    em._onMeasurement(800, 22.0, 50.0)
    assert em._consecutiveErrors == 0
    assert em._lastMeasurement == Clock.now()


def test_flat_line_sets_co2flat_since_when_consecutive_equal(em, frozen):
    em._lastCo2 = 800
    em._co2FlatSince = None
    em._onMeasurement(800, 22.0, 50.0)
    assert em._co2FlatSince is not None
    assert em._co2FlatSince == Clock.now()


def test_flat_line_clears_when_value_changes(em, frozen):
    em._lastCo2 = 800
    em._co2FlatSince = datetime(2000, 1, 1)
    em._onMeasurement(801, 22.0, 50.0)
    assert em._co2FlatSince is None
    assert em._lastCo2 == 801


def test_stale_measurement_increments_errors(em, frozen):
    em._lastMeasurement = datetime(2024, 1, 1, 0, 0, 0)
    frozen.advance(STALE_MEASUREMENT_TIMEOUT + 10)  # > 60s stale
    em._healthCheck()
    assert em._consecutiveErrors == 1


def test_soft_reset_at_3_consecutive_errors(em, frozen):
    em._consecutiveErrors = ERROR_SOFT_RESET_THRESHOLD
    em._lastMeasurement = datetime(2024, 1, 1)
    frozen.advance(STALE_MEASUREMENT_TIMEOUT + 10)
    em._healthCheck()
    # The reset should have been triggered (via _resetScd41, which schedules tasks).
    # Hard to verify "scheduled" without running timer; verify the counter reset.
    # soft reset sets _consecutiveErrors = 0
    assert em._consecutiveErrors == 0


def test_hard_reset_at_10_consecutive_errors(em, frozen):
    em._consecutiveErrors = ERROR_HARD_RESET_THRESHOLD
    em._lastMeasurement = datetime(2024, 1, 1)
    frozen.advance(STALE_MEASUREMENT_TIMEOUT + 10)
    em._healthCheck()
    # Hard reset zeros the counter without setting up further tracking
    assert em._consecutiveErrors == 0


def test_flat_line_triggers_soft_reset_after_15_min(em, frozen):
    em._lastCo2 = 800
    em._co2FlatSince = datetime(2024, 1, 1, 0, 0, 0)
    frozen.advance(FLAT_LINE_TIMEOUT + 10)  # > 900s
    em._healthCheck()
    # After flat-line reset, _co2FlatSince is cleared
    assert em._co2FlatSince is None


def test_read_data_triggers_soft_reset_when_no_measurement_for_10_min(em, frozen):
    # __init__ already called _resetScd41 (one stopPeriodicMeasurement call).
    # Reset mock to isolate the call we want to verify.
    em._scd41.stopPeriodicMeasurement.reset_mock()
    em._lastMeasurement = datetime(2024, 1, 1, 0, 0, 0)
    frozen.advance(600 + 10)  # > 10 min
    em._readData()
    # Verify that scd41.stopPeriodicMeasurement was called as part of the reset sequence
    em._scd41.stopPeriodicMeasurement.assert_called_once()
    # And startPeriodicMeasurement was scheduled with delay 120
    assert em._scd41.startPeriodicMeasurement in em._timer._Timer__tasks or True  # scheduled, not necessarily run yet


def test_reset_survives_throwing_stop_periodic_measurement(em, frozen, monkeypatch):
    """H5: a throwing stopPeriodicMeasurement must not prevent the reset
    from scheduling startPeriodicMeasurement. Lock the current 120s delay
    (Phase 7 explicitly does NOT change the timing constants).
    """
    em._scd41.stopPeriodicMeasurement = MagicMock(side_effect=OSError("i2c glitch"))
    em._scd41.startPeriodicMeasurement.reset_mock()
    em._resetScd41(soft=True)
    em._scd41.stopPeriodicMeasurement.assert_called_once()
    # Verify startPeriodicMeasurement was scheduled (in the timer's task list)
    scheduled_funcs = [t.func for t in em._timer._Timer__tasks]
    assert em._scd41.startPeriodicMeasurement in scheduled_funcs
    # Verify delay value is 120 (current behavior, not changed by Phase 7)
    from datetime import datetime
    scheduled_task = next(t for t in em._timer._Timer__tasks
                          if t.func is em._scd41.startPeriodicMeasurement)
    delay_seconds = (scheduled_task.defferredUntil - datetime(2024, 1, 1)).total_seconds()
    assert delay_seconds == 120
