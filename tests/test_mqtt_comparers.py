"""Lock current behavior of BaseComparer and IntComparer."""

import pytest
from Mqtt import BaseComparer, IntComparer, shouldPublish


class TestBaseComparer:
    def test_none_original_returns_2(self):
        assert BaseComparer().compare(None, 5) == 2

    def test_equal_returns_0(self):
        assert BaseComparer().compare(7, 7) == 0

    def test_differ_returns_2(self):
        assert BaseComparer().compare(5, 7) == 2


class TestIntComparer:
    def test_none_original_returns_2(self):
        assert IntComparer(1).compare(None, 5) == 2

    def test_equal_returns_0(self):
        assert IntComparer(1).compare(5, 5) == 0

    def test_diff_below_minchange_returns_1(self):
        # minChange=5: |100-103|=3 < 5 → 1
        assert IntComparer(5).compare(100, 103) == 1

    def test_diff_at_minchange_returns_2(self):
        # |100-105|=5, not strictly less than 5 → 2
        assert IntComparer(5).compare(100, 105) == 2

    def test_diff_above_minchange_returns_2(self):
        assert IntComparer(5).compare(100, 200) == 2

    def test_diff_in_either_direction(self):
        assert IntComparer(5).compare(200, 100) == 2


class TestShouldPublish:
    # Lock the boolean expression extracted from __publishTopic (Phase 3 R4).
    # Phase 8 (M2) will switch the source from `.seconds` to `.total_seconds()`;
    # dTime is still in seconds; this test remains correct.

    def test_dvalue_2_publishes_immediately(self):
        # any dTime works
        assert shouldPublish(2, 0, 10, 60) is True
        assert shouldPublish(2, 5, 10, 60) is True

    def test_dvalue_1_within_publish_interval_skips(self):
        # dValue=1, dTime=5 < publishInterval=10 → False
        assert shouldPublish(1, 5, 10, 60) is False

    def test_dvalue_1_beyond_publish_interval_publishes(self):
        # dValue=1, dTime=15 > publishInterval=10 → True
        assert shouldPublish(1, 15, 10, 60) is True

    def test_dvalue_0_within_force_publish_interval_skips(self):
        # dValue=0, dTime=30, not beyond force=60 → False
        assert shouldPublish(0, 30, 10, 60) is False

    def test_dvalue_0_beyond_force_publish_interval_publishes(self):
        # dValue=0, dTime=120 > force=60 → True
        assert shouldPublish(0, 120, 10, 60) is True

    def test_boundary_force_publish_exclusive(self):
        # dTime == forcePublishInterval: not strictly greater → False (when dValue=0)
        assert shouldPublish(0, 60, 10, 60) is False
        # dTime just over
        assert shouldPublish(0, 61, 10, 60) is True
        # dValue=1 at dTime==forcePublishInterval still publishes (publishInterval branch hits)
        assert shouldPublish(1, 60, 10, 60) is True
