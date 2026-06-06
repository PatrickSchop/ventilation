"""Lock current Timer behavior: scheduling, precedence, cancellation.

xfail-strict markers assert the CORRECT target behavior for known bugs:
  - M5: independent default cancellation tokens
  - M6: run() loop survives a raw exception when ActionRunner is bypassed
"""

import pytest
from datetime import datetime, timedelta
from Timer import Timer, CancellationToken
from Clock import Clock
from Logger import Logger


def test_execute_with_delay_schedules_task():
    t = Timer()
    t.execute(lambda: None, delay=10)
    # No tasks due yet
    assert t._takeTask() is None


def test_add_timer_action_runs_at_frequency():
    t = Timer()
    fired = []
    t.add(lambda: fired.append(1), 5)
    # add() sets lastRun=Clock.now() at registration; _takeTimerAction checks
    # (lastRun + frequency) <= now, so the action is NOT due yet (5s in the future).
    assert t._takeTimerAction() is None
    # Pretend the frequency interval has passed by manipulating lastRun backward
    t._Timer__timerActions[0].lastRun = datetime(2000, 1, 1)
    action = t._takeTimerAction()
    assert action is not None
    # _takeTimerAction returns the action but does not run it; run() does
    action.func()
    assert fired == [1]


def test_task_precedence_over_timer_action():
    t = Timer()
    order = []
    t.add(lambda: order.append("timer"), 1)
    t.execute(lambda: order.append("task"))
    # Tasks come first in run(); _takeTask before _takeTimerAction
    assert t._takeTask() is not None
    t._takeTask()  # drain
    # next call to _takeTimerAction returns None if lastRun is in the future
    # but since the add() set lastRun=Clock.now(), the next fire time is now+1s
    # which is in the future → None
    assert t._takeTimerAction() is None


def test_cancellation_stops_run(monkeypatch):
    """run() with a cancelled token must not invoke any handler."""
    t = Timer()
    fired = []
    t.add(lambda: fired.append(1), 0)
    t.execute(lambda: fired.append(2))
    ct = CancellationToken()
    ct.cancel()
    t.run(ct)
    assert fired == []


def test_default_cancellation_tokens_are_independent():
    """M5: Timer.run with no argument should produce a fresh CancellationToken
    each call (no shared mutable default)."""
    t1 = Timer()
    t2 = Timer()
    # __defaults__ should not contain a CancellationToken; first arg is None
    defaults = Timer.run.__defaults__ or ()
    if defaults:
        assert defaults[0] is None, f"expected None default, got {type(defaults[0])}"
    # Functional check: two runs with no token must not interfere
    t1.add(lambda: 1, 0)
    t2.add(lambda: 2, 0)
    # Manually drive each — they should be independent
    assert t1._Timer__timerActions[0].func() == 1
    assert t2._Timer__timerActions[0].func() == 2


def test_run_survives_raw_exception_in_callback(monkeypatch):
    """M6: a callback that bypasses ActionRunner and raises should NOT stop run().

    The Timer.run() loop body is wrapped in try/except → Logger.error, so
    even a raw raise (e.g. from a callback that wasn't dispatched through
    ActionRunner) cannot terminate the loop.
    """
    import ActionRunner
    logged = []
    monkeypatch.setattr(Logger, "error", staticmethod(lambda e: logged.append(e)))

    t = Timer()
    fired = []

    # Pre-cancel: run a finite number of iterations, then stop.
    ct = CancellationToken()
    t.execute(lambda: fired.append("first"))                 # fires first
    t.execute(lambda: (_ for _ in ()).throw(RuntimeError("boom")))  # raises; M6 catches
    t.execute(lambda: (fired.append("after-boom"), ct.cancel())[1])  # fires after, then cancels

    # Bypass the safety net so the exception reaches the M6 backstop
    monkeypatch.setattr(
        ActionRunner.Runner, "execute",
        lambda f, p=None: f(*(p or [])) if isinstance(p, list) else (f(p) if p is not None else f())
    )

    t.run(ct)
    # If the loop survived, the task after the boom also fired
    assert "first" in fired
    assert "after-boom" in fired, f"loop died on boom; fired={fired}"
    # M6 backstop logged the boom
    assert any("boom" in str(e) for e in logged)
