"""Lock current behavior of ActionRunner.Runner.

The crash-containment net: every callback dispatched through here must not
propagate exceptions, so a single broken handler never tears down the service.
"""

import pytest
from ActionRunner import Runner
from Logger import Logger


def test_executes_no_args():
    called = []
    def fn():
        called.append(True)
    Runner.execute(fn)
    assert called == [True]


def test_executes_single_param():
    captured = []
    Runner.execute(lambda v: captured.append(v), 42)
    assert captured == [42]


def test_executes_list_param_arity_1():
    captured = []
    Runner.execute(lambda a: captured.append(a), [7])
    assert captured == [7]


def test_executes_list_param_arity_2():
    captured = []
    Runner.execute(lambda a, b: captured.append((a, b)), [1, 2])
    assert captured == [(1, 2)]


def test_executes_list_param_arity_3():
    captured = []
    Runner.execute(lambda a, b, c: captured.append((a, b, c)), [1, 2, 3])
    assert captured == [(1, 2, 3)]


def test_executes_list_param_arity_4():
    captured = []
    Runner.execute(lambda a, b, c, d: captured.append((a, b, c, d)), [1, 2, 3, 4])
    assert captured == [(1, 2, 3, 4)]


def test_exception_is_caught_and_logged(monkeypatch):
    """The safety net: an exception in fn must not propagate."""
    logged = []
    monkeypatch.setattr(Logger, "error", staticmethod(lambda e: logged.append(e)))
    def boom():
        raise RuntimeError("kaboom")
    # Should NOT raise
    Runner.execute(boom)
    assert len(logged) == 1
    assert "kaboom" in str(logged[0])
