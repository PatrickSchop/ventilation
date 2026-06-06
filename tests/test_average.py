"""Lock current behavior of Ventilator._Average.

Time-dependent; uses the Clock seam (Phase 2 R3). Tests pin Clock.now via
monkeypatch.
"""

import pytest
from datetime import datetime, timedelta
from Ventilator import _Average
from Clock import Clock


@pytest.fixture
def frozen(monkeypatch):
    """Pin Clock.now() to a fixed time, returning a controller for advancement."""
    t = [datetime(2024, 1, 1, 0, 0, 0)]
    monkeypatch.setattr(Clock, "now", staticmethod(lambda: t[0]))
    class Ctrl:
        def advance(self, seconds):
            t[0] = t[0] + timedelta(seconds=seconds)
        def set(self, new_t):
            t[0] = new_t
    return Ctrl()


def test_average_with_no_samples_is_zero(frozen):
    a = _Average(5)
    assert a.average == 0


def test_average_with_samples(frozen):
    a = _Average(5)
    a.append(10)
    a.append(20)
    a.append(30)
    assert a.average == 20.0


def test_reliable_requires_at_least_two_samples(frozen):
    a = _Average(5, minReliableTime=0)
    a.append(10)
    # Only one sample
    assert a.reliable is False


def test_reliable_respects_min_reliable_time(frozen):
    # minReliableTime is in MINUTES internally
    a = _Average(maxTimeRange=5, minReliableTime=1)  # minReliableTime=1min → 60s
    a.append(10)
    frozen.advance(30)  # 30s
    a.append(20)        # need ≥2 samples for reliable
    # Now has 2 samples, but (now - first_sample) = 30s < 60s min
    assert a.reliable is False

    frozen.advance(60)  # +60s → first sample is now 90s old, > 60s min
    assert a.reliable is True


def test_window_eviction(frozen):
    # minReliableTime must be > 70s so the stale-clear path does NOT fire first
    a = _Average(maxTimeRange=1, minReliableTime=2)  # timeRange=60s, minReliableTime=120s
    a.append(100)
    frozen.advance(70)  # first sample is now 70s old, > 60s timeRange, < 120s minReliableTime
    a.append(200)        # append triggers eviction; stale-clear does NOT fire
    # 100 evicted, only 200 remains
    assert len(a._samples) == 1
    assert a.average == 200.0


def test_check_last_sample_current_clears_when_stale(frozen):
    a = _Average(maxTimeRange=10, minReliableTime=1)  # minReliableTime=60s
    a.append(10)
    a.append(20)
    # Advance past minReliableTime since the LAST sample
    frozen.advance(120)
    # Trigger the check via append
    a.append(30)
    # All old samples discarded; only the new one remains in `_samples`,
    # but the running `totalValue` is NOT reset (current behavior; this is
    # a known minor bug not in the review findings — `average` reads
    # totalValue / len(samples) and will be wrong after a clear).
    assert len(a._samples) == 1
    # Lock the current behavior: average reflects the un-reset totalValue
    assert a._totalValue == 60  # 10 + 20 + 30
    assert a.average == 60.0  # buggy: should be 30.0
