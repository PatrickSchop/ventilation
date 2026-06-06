"""Lock current behavior of DemandCalculator pure logic.

- _mapValue interpolation for both CO2 and humidity demand maps.
- aggregation = max across all sources
- externalDemand clamps to [0, 100]
- onDemandChanged fires with the resulting demand (as int)
"""

import pytest
from Ventilator import DemandCalculator


class TestMapValueCO2:
    MAP = {400: 0, 500: 1, 600: 5, 700: 20, 800: 45, 900: 63, 1000: 72, 1200: 77, 1500: 82, 2000: 85}

    def test_below_first_key_returns_first_value(self):
        assert DemandCalculator()._mapValue(300, self.MAP) == 0

    def test_at_first_key_returns_first_value(self):
        # value=400: skips `value < 400`; loop n=1, 400 < 500 → k1=400,v1=0,v2=1, p=0 → 0
        assert DemandCalculator()._mapValue(400, self.MAP) == 0

    def test_midpoint_interpolation(self):
        # value=450 between 400→0 and 500→1, p=0.5 → 0.5
        assert DemandCalculator()._mapValue(450, self.MAP) == 0.5

    def test_at_exact_key_returns_that_key_value(self):
        # value=700: 700 < 700 false; n=3, k2=800, 700 < 800 true → k1=700,v1=20, v2=45, p=0 → 20
        assert DemandCalculator()._mapValue(700, self.MAP) == 20
        # At key 500 exactly: 500 < 500 false, n=2, 500 < 600 true → k1=500,v1=1, v2=5, p=0 → 1
        assert DemandCalculator()._mapValue(500, self.MAP) == 1

    def test_above_last_key_returns_last_value(self):
        assert DemandCalculator()._mapValue(5000, self.MAP) == 85
        assert DemandCalculator()._mapValue(2000, self.MAP) == 85


class TestMapValueHumidity:
    MAP = {0: 0, 1: 0, 2: 10, 3: 45, 4: 62, 5: 73, 6: 80, 7: 85, 8: 88, 9: 90, 10: 92, 15: 95, 20: 100}

    def test_below_first_key(self):
        assert DemandCalculator()._mapValue(-5, self.MAP) == 0

    def test_at_zero(self):
        assert DemandCalculator()._mapValue(0, self.MAP) == 0

    def test_midpoint(self):
        # value=2.5 between 2→10 and 3→45, p=0.5 → 27.5
        assert DemandCalculator()._mapValue(2.5, self.MAP) == 27.5

    def test_above_last_key(self):
        assert DemandCalculator()._mapValue(100, self.MAP) == 100


class TestDemandAggregation:
    def test_no_sources_demand_zero(self):
        dc = DemandCalculator()
        assert dc.demand == 0  # default
        fired = []
        dc.onDemandChanged = lambda d: fired.append(d)
        # No updates: demand remains 0; no callback fired.
        assert fired == []

    def test_single_source(self):
        dc = DemandCalculator()
        fired = []
        dc.onDemandChanged = lambda d: fired.append(d)
        dc.updateCo2(800)  # CO2 map: 800 → 45
        assert dc.demand == 45
        assert fired == [45]

    def test_max_aggregation(self):
        dc = DemandCalculator()
        fired = []
        dc.onDemandChanged = lambda d: fired.append(d)
        dc.updateCo2(800)  # 45
        dc.updateHumidity(humidity=60, averageHumidity=58)  # diff=2 → 10
        dc.externalDemand(70, key="x")
        assert dc.demand == 70
        assert fired[-1] == 70

    def test_external_clamped_below_zero(self):
        dc = DemandCalculator()
        fired = []
        dc.onDemandChanged = lambda d: fired.append(d)
        dc.externalDemand(-50, key="x")
        assert dc.demand == 0
        assert fired == [0]

    def test_external_clamped_above_100(self):
        dc = DemandCalculator()
        fired = []
        dc.onDemandChanged = lambda d: fired.append(d)
        dc.externalDemand(150, key="x")
        assert dc.demand == 100
        assert fired == [100]

    def test_callback_fires_with_demand_value(self):
        # The calculator's onDemandChanged fires with the aggregated demand.
        # Current behavior: the value is whatever `max(...)` returns — a float
        # when the source produced floats (which it does, since _mapValue
        # always returns float). VentilationController._demandChanged casts
        # to int when consuming it. This test locks the calculator's output type.
        dc = DemandCalculator()
        fired = []
        dc.onDemandChanged = lambda d: fired.append(d)
        dc.updateCo2(800)  # 800 maps to 45.0
        assert fired[-1] == 45.0
        assert isinstance(fired[-1], float)  # current behavior; cast happens in controller
