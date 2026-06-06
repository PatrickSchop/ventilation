"""Lock current behavior of BaseComparer and IntComparer."""

from Mqtt import BaseComparer, IntComparer


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
