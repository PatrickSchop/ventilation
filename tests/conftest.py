"""Pytest configuration: path setup, fixtures, and shared state reset.

This conftest is intentionally permissive: it does not auto-apply any global
fixtures (autouse) because some tests exercise module-load order. Use the
explicit fixtures below where needed.
"""

import os
import sys
from datetime import datetime, timedelta

# Project root and stub path so imports like `from Mqtt import ...` and
# `from smbus2 import ...` resolve in tests.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
STUB_ROOT = os.path.join(os.path.dirname(__file__), "stubs")

for path in (PROJECT_ROOT, STUB_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FrozenClock:
    def __init__(self, start=None):
        self._now = start or datetime(2024, 1, 1, 0, 0, 0)

    def now(self):
        return self._now

    def advance(self, seconds):
        self._now = self._now + timedelta(seconds=seconds)

    def set(self, t):
        self._now = t


def pytest_configure(config):
    """Register custom markers (pytest.ini handles this too, but make it explicit)."""
