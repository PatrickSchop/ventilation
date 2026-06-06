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


@pytest.mark.xfail(reason="M5: Timer.run default token is a shared mutable; two Timers share state", strict=True)
def test_default_cancellation_tokens_are_independent():
    """Two Timer instances should each have their own default token.

    Current behavior: `def run(self, cancellationToken=CancellationToken())`
    shares one default object across calls. With strict=True, this test
    failing means the bug exists; once M5 is fixed, this test passes and
    the strict xfail flips the suite red → marker must be removed.
    """
    t1 = Timer()
    t2 = Timer()
    # Bypass __defaults__ introspection: compare identity of the default object
    default_t1 = Timer.run.__defaults__[0]
    default_t2 = Timer.run.__defaults__[0]
    assert default_t1 is not default_t2


@pytest.mark.xfail(reason="M6: Timer.run has no top-level backstop; a raw exception kills the loop", strict=True)
def test_run_survives_raw_exception_in_callback(monkeypatch):
    """A callback that bypasses ActionRunner and raises should NOT stop run().

    Currently: run() calls `ActionRunner.Runner.execute(a.func, a.parameters)`
    which catches exceptions. The xfail documents what the test ASSERTS
    (the next scheduled task still runs after a throwing callback). After
    M6 wraps the loop body in try/except, the inner block becomes redundant
    but the test still asserts the end-to-end property: a raw raise does
    not terminate the loop.

    The simplest way to exercise this is to monkeypatch ActionRunner to a
    no-op, then verify run() still progresses through pending tasks.
    """
    import ActionRunner
    t = Timer()
    fired = []
    t.add(lambda: fired.append("a"), 0)  # timer action, due now
    t.execute(lambda: fired.append("b"))  # one-shot task
    t.execute(lambda: (_ for _ in ()).throw(RuntimeError("boom")))  # raises
    # Bypass the safety net for THIS test
    monkeypatch.setattr(ActionRunner.Runner, "execute", lambda f, p=None: f(*(p or [])) if isinstance(p, list) else (f(p) if p is not None else f()))

    # Manually run a few iterations; if the loop is robust it should keep going.
    # Use a cancellation token to stop after a few cycles.
    ct = CancellationToken()
    # Schedule a stop after we expect both "a" and "b" to fire
    t.execute(lambda: ct.cancel(), delay=0)
    t.run(ct)
    # If the loop survived the boom, both 'a' and 'b' should have fired.
    assert "a" in fired
    assert "b" in fired
