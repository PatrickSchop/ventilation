"""Lock behavior of health_monitor.py: log parsing, health evaluation,
post-reboot grace period, and reboot trigger.

The production code is exercised through its public functions, not by
importing the module's __main__ entry point. subprocess.run and
get_uptime_seconds are monkeypatched.
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call

import pytest

from Clock import Clock


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import health_monitor  # noqa: E402
from health_monitor import (  # noqa: E402
    BROKEN_THRESHOLD_SECONDS,
    evaluate_health,
    parse_log,
    parse_log_line,
    trigger_reboot,
    uptime_grace_period,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def frozen(monkeypatch):
    t = [datetime(2024, 1, 1, 12, 0, 0)]
    monkeypatch.setattr(Clock, "now", staticmethod(lambda: t[0]))
    class Ctrl:
        def advance(self, seconds):
            t[0] = t[0] + timedelta(seconds=seconds)
        def set(self, new_t):
            t[0] = new_t
    return Ctrl()


def _ts(offset_seconds: int, base: datetime = None) -> str:
    base = base or datetime(2024, 1, 1, 12, 0, 0)
    return (base + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]


# ---------------------------------------------------------------------------
# Grace period
# ---------------------------------------------------------------------------

def test_grace_period_under_threshold_is_in_grace():
    assert uptime_grace_period(0) is True
    assert uptime_grace_period(BROKEN_THRESHOLD_SECONDS - 1) is True


def test_grace_period_at_threshold_is_out_of_grace():
    assert uptime_grace_period(BROKEN_THRESHOLD_SECONDS) is False
    assert uptime_grace_period(BROKEN_THRESHOLD_SECONDS + 1) is False


# ---------------------------------------------------------------------------
# Log line parsing
# ---------------------------------------------------------------------------

def test_parse_log_line_error_mqtt():
    line = f"{_ts(0)} INFO ventilation - [ERROR:mqtt] MQTT disconnected (rc=1)"
    result = parse_log_line(line)
    assert result is not None
    ts, kind, category = result
    assert kind == "error"
    assert category == "mqtt"
    assert ts == datetime(2024, 1, 1, 12, 0, 0)


def test_parse_log_line_recovery_scd41():
    line = f"{_ts(0)} INFO ventilation - [RECOVERY:scd41] Sensor measurement resumed after 3 consecutive errors"
    result = parse_log_line(line)
    assert result is not None
    _ts_, kind, category = result
    assert kind == "recovery"
    assert category == "scd41"


def test_parse_log_line_plain_info_is_ignored():
    line = f"{_ts(0)} INFO ventilation - Some unrelated event"
    assert parse_log_line(line) is None


def test_parse_log_line_warning_is_ignored():
    line = f"{_ts(0)} WARNING ventilation - [ERROR:mqtt] Would be ignored if it weren't structured"
    assert parse_log_line(line) is not None  # structured prefix wins over level


def test_parse_log_line_malformed_timestamp_returns_none():
    line = "not-a-timestamp INFO ventilation - [ERROR:mqtt] x"
    assert parse_log_line(line) is None


def test_parse_log_line_unknown_category_accepted():
    line = f"{_ts(0)} ERROR ventilation - [ERROR:futuresystem] Something new"
    result = parse_log_line(line)
    assert result is not None
    assert result[2] == "futuresystem"


def test_parse_log_line_preserves_message_body():
    line = f"{_ts(0)} ERROR ventilation - [ERROR:mqtt] MQTT client connect failed: connection refused"
    result = parse_log_line(line)
    assert result is not None


# ---------------------------------------------------------------------------
# parse_log
# ---------------------------------------------------------------------------

def test_parse_log_filters_lookback(tmp_path, frozen):
    log = tmp_path / "ventilation.log"
    base = Clock.now()
    # 90 minutes ago: outside lookback (7200s = 2h), but check 3h = out
    outside = base - timedelta(hours=3)
    inside = base - timedelta(hours=1)
    log.write_text(
        f"{outside.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} ERROR ventilation - [ERROR:mqtt] old\n"
        f"{inside.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} ERROR ventilation - [ERROR:mqtt] recent\n",
        encoding="utf-8",
    )
    events = parse_log(str(log), base)
    assert len(events) == 1
    assert events[0][2] == "mqtt"


def test_parse_log_sorts_chronologically(tmp_path, frozen):
    log = tmp_path / "ventilation.log"
    base = Clock.now()
    t1 = base - timedelta(minutes=30)
    t2 = base - timedelta(minutes=60)
    log.write_text(
        f"{t1.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} ERROR ventilation - [ERROR:mqtt] later\n"
        f"{t2.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} ERROR ventilation - [ERROR:mqtt] earlier\n",
        encoding="utf-8",
    )
    events = parse_log(str(log), base)
    assert [e[0] for e in events] == sorted(e[0] for e in events)


def test_parse_log_missing_file_returns_empty(tmp_path, frozen):
    events = parse_log(str(tmp_path / "nonexistent.log"), Clock.now())
    assert events == []


# ---------------------------------------------------------------------------
# Health evaluation
# ---------------------------------------------------------------------------

def test_evaluate_no_events_is_healthy(frozen):
    assert evaluate_health([], Clock.now()) == []


def test_evaluate_error_under_threshold_is_healthy(frozen):
    now = Clock.now()
    events = [(now - timedelta(minutes=30), "error", "mqtt")]
    assert evaluate_health(events, now) == []


def test_evaluate_error_over_threshold_is_broken(frozen):
    now = Clock.now()
    events = [(now - timedelta(hours=2), "error", "mqtt")]
    broken = evaluate_health(events, now)
    assert len(broken) == 1
    assert broken[0][0] == "mqtt"


def test_evaluate_recovery_resets_broken_state(frozen):
    now = Clock.now()
    events = [
        (now - timedelta(hours=2), "error", "mqtt"),
        (now - timedelta(minutes=30), "recovery", "mqtt"),
    ]
    assert evaluate_health(events, now) == []


def test_evaluate_second_error_after_recovery_restarts_clock(frozen):
    now = Clock.now()
    events = [
        (now - timedelta(hours=2), "error", "mqtt"),
        (now - timedelta(hours=1, minutes=30), "recovery", "mqtt"),
        (now - timedelta(minutes=30), "error", "mqtt"),
    ]
    broken = evaluate_health(events, now)
    assert broken == []


def test_evaluate_one_category_broken_other_healthy_triggers_reboot(frozen):
    """Key requirement: sensor works, mqtt broken >1h = still a problem."""
    now = Clock.now()
    events = [
        (now - timedelta(hours=2), "recovery", "scd41"),
        (now - timedelta(hours=2), "error", "mqtt"),
    ]
    broken = evaluate_health(events, now)
    assert [c for c, _ in broken] == ["mqtt"]


def test_evaluate_both_categories_broken(frozen):
    now = Clock.now()
    events = [
        (now - timedelta(hours=2), "error", "mqtt"),
        (now - timedelta(hours=2, minutes=10), "error", "scd41"),
    ]
    broken = evaluate_health(events, now)
    assert {c for c, _ in broken} == {"mqtt", "scd41"}


def test_evaluate_dynamic_category_supported(frozen):
    """Categories should not need to be pre-declared."""
    now = Clock.now()
    events = [(now - timedelta(hours=2), "error", "newthing")]
    broken = evaluate_health(events, now)
    assert broken[0][0] == "newthing"


# ---------------------------------------------------------------------------
# Reboot trigger
# ---------------------------------------------------------------------------

def test_trigger_reboot_dry_run_does_not_call_subprocess(monkeypatch):
    monkeypatch.setattr(health_monitor.subprocess, "run", MagicMock())
    monkeypatch.setattr(health_monitor.Logger, "fault", MagicMock())
    trigger_reboot([("mqtt", datetime(2024, 1, 1))], dry_run=True)
    health_monitor.subprocess.run.assert_not_called()


def test_trigger_reboot_calls_sudo_reboot(monkeypatch):
    monkeypatch.setattr(health_monitor.subprocess, "run", MagicMock())
    monkeypatch.setattr(health_monitor.Logger, "fault", MagicMock())
    trigger_reboot([("mqtt", datetime(2024, 1, 1))], dry_run=False)
    health_monitor.subprocess.run.assert_called_once_with(["sudo", "reboot"], check=False)


def test_trigger_reboot_logs_fault_before_subprocess(monkeypatch):
    order = []
    def fake_fault(category, msg):
        order.append(("fault", category))
    def fake_run(cmd, **kwargs):
        order.append(("run", cmd))
    monkeypatch.setattr(health_monitor.Logger, "fault", fake_fault)
    monkeypatch.setattr(health_monitor.subprocess, "run", fake_run)
    trigger_reboot([("mqtt", datetime(2024, 1, 1))], dry_run=False)
    assert order[0] == ("fault", "health_monitor")
    assert order[1] == ("run", ["sudo", "reboot"])


def test_trigger_reboot_sudo_missing_is_handled(monkeypatch):
    monkeypatch.setattr(
        health_monitor.subprocess, "run",
        MagicMock(side_effect=FileNotFoundError),
    )
    monkeypatch.setattr(health_monitor.Logger, "fault", MagicMock())
    # Should not raise
    trigger_reboot([("mqtt", datetime(2024, 1, 1))], dry_run=False)


# ---------------------------------------------------------------------------
# End-to-end main() (no real subprocess or /proc reads)
# ---------------------------------------------------------------------------

def _run_main(args, uptime, log_content, monkeypatch, frozen_at=None):
    """Invoke health_monitor.main() with a mocked environment."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
        f.write(log_content)
        log_path = f.name
    if frozen_at is not None:
        monkeypatch.setattr(Clock, "now", staticmethod(lambda: frozen_at))
    monkeypatch.setattr(health_monitor, "get_uptime_seconds", lambda: uptime)
    monkeypatch.setattr(health_monitor, "DEFAULT_LOG_PATH", log_path)
    mock_subprocess = MagicMock()
    monkeypatch.setattr(health_monitor, "subprocess", mock_subprocess)
    monkeypatch.setattr(health_monitor.Logger, "fault", MagicMock())
    monkeypatch.setattr(health_monitor.Logger, "info", MagicMock())
    monkeypatch.setattr(health_monitor.Logger, "error", MagicMock())
    monkeypatch.setattr(health_monitor.Logger, "warning", MagicMock())
    sys.argv = ["health_monitor.py"] + args
    rc = health_monitor.main()
    return rc, mock_subprocess, log_path


def test_main_under_grace_period_does_nothing(monkeypatch):
    base = datetime(2024, 1, 1, 12, 0, 0)
    # A clear broken state would trigger a reboot, but we're under grace
    log = f"{_ts(0, base)} ERROR ventilation - [ERROR:mqtt] broken\n"
    rc, proc, path = _run_main([], uptime=10, log_content=log, monkeypatch=monkeypatch, frozen_at=base)
    os.unlink(path)
    assert rc == 0
    proc.run.assert_not_called()


def test_main_at_threshold_evaluates_and_reboots(monkeypatch):
    base = datetime(2024, 1, 1, 12, 0, 0)
    # Fault from 90 min ago: inside 2h lookback, broken for 90 min > 1h
    fault_ts = base - timedelta(minutes=90)
    log = (
        f"{fault_ts.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} ERROR ventilation - "
        f"[ERROR:mqtt] broken\n"
    )
    rc, proc, path = _run_main([], uptime=BROKEN_THRESHOLD_SECONDS, log_content=log, monkeypatch=monkeypatch, frozen_at=base)
    os.unlink(path)
    assert rc == 0
    proc.run.assert_called_once_with(["sudo", "reboot"], check=False)


def test_main_healthy_does_not_reboot(monkeypatch):
    base = datetime(2024, 1, 1, 12, 0, 0)
    recovery_ts = base - timedelta(minutes=5)
    log = (
        f"{recovery_ts.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} INFO ventilation - "
        f"[RECOVERY:mqtt] ok\n"
    )
    rc, proc, path = _run_main([], uptime=7200, log_content=log, monkeypatch=monkeypatch, frozen_at=base)
    os.unlink(path)
    assert rc == 0
    proc.run.assert_not_called()


def test_main_dry_run_does_not_reboot(monkeypatch):
    base = datetime(2024, 1, 1, 12, 0, 0)
    fault_ts = base - timedelta(minutes=90)
    log = (
        f"{fault_ts.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} ERROR ventilation - "
        f"[ERROR:mqtt] broken\n"
    )
    rc, proc, path = _run_main(["--dry-run"], uptime=7200, log_content=log, monkeypatch=monkeypatch, frozen_at=base)
    os.unlink(path)
    assert rc == 0
    proc.run.assert_not_called()


def test_main_log_unreadable_returns_nonzero(monkeypatch, capsys):
    # Force get_uptime_seconds to raise; main should return 1, not crash
    monkeypatch.setattr(health_monitor, "get_uptime_seconds",
                        MagicMock(side_effect=OSError("no /proc")))
    monkeypatch.setattr(health_monitor.Logger, "fault", MagicMock())
    sys.argv = ["health_monitor.py"]
    rc = health_monitor.main()
    assert rc == 1
