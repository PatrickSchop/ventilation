"""Indirection for `datetime.now()` so tests can pin/advance time.

Production code uses Clock.now() instead of datetime.now() directly. Tests
monkeypatch this method (e.g. via conftest's frozen_clock fixture) to make
time-dependent behavior (health checks, average windows, deferrals,
scheduling) deterministic.
"""

from datetime import datetime


class Clock:
    @staticmethod
    def now():
        return datetime.now()
