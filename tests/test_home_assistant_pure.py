"""Lock current behavior of HomeAssistant pure helpers:
- _generate_entity_id: deterministic 12-hex hash of name
- add(): object_id derivation (including current `lstrip("_")` no-op behavior on line 39)
"""

import pytest
from HomeAssistant import HomeAssistant


class TestGenerateEntityId:
    def test_deterministic_for_same_name(self):
        a = HomeAssistant._generate_entity_id("Co2")
        b = HomeAssistant._generate_entity_id("Co2")
        assert a == b

    def test_different_names_produce_different_ids(self):
        a = HomeAssistant._generate_entity_id("Co2")
        b = HomeAssistant._generate_entity_id("Humidity")
        assert a != b

    def test_id_format(self):
        eid = HomeAssistant._generate_entity_id("Co2")
        # Format: {_ENTITY_ID_BASE}-{h:0>12X}
        assert eid.startswith(HomeAssistant._ENTITY_ID_BASE + "-")
        suffix = eid[len(HomeAssistant._ENTITY_ID_BASE) + 1:]
        assert len(suffix) == 12
        int(suffix, 16)  # parses as hex

    def test_golden_value(self):
        # Lock the exact hash output for a known name so a refactor that
        # changes the algorithm breaks visibly (entity IDs would change,
        # which would re-register as new entities in Home Assistant).
        eid = HomeAssistant._generate_entity_id("Co2")
        # Recompute algorithmically to assert the locked value:
        h = 0
        for c in "Co2":
            h = (h << 4) + ord(c)
            h %= 0x1000000000000
        expected = f"{HomeAssistant._ENTITY_ID_BASE}-{h:0>12X}"
        assert eid == expected


class TestAddObjectIdDerivation:
    """Tests against the HomeAssistant add() flow.

    These exercise the CURRENT (Phase 1) behavior, including the no-op
    `objectId.lstrip("_")` on HomeAssistant.py:39. Phase 8 (M3) will fix
    the no-op and the test will be updated.
    """

    def _make(self, baseTopic=None):
        # HomeAssistant.__init__ takes (timer, mqtt); timer/mqtt are not used
        # by add() itself beyond baseTopic derivation, so we pass None-like
        # objects via a minimal stub.
        from unittest.mock import MagicMock
        ha = HomeAssistant(MagicMock(), MagicMock())
        ha.baseTopic = baseTopic
        return ha

    def test_state_topic_with_basetopic_strips_basetopic_and_leading_underscore(self):
        # Phase 8 (M3): objectId.lstrip("_") is now correctly assigned back.
        ha = self._make(baseTopic="ventilation")
        ha.add({"name": "Co2", "type": "sensor", "state_topic": "ventilation/state/level"})
        assert ha._entities[-1]["object_id"] == "state_level"

    def test_state_topic_without_basetopic(self):
        ha = self._make(baseTopic=None)
        ha.add({"name": "Co2", "type": "sensor", "state_topic": "ventilation/state/level"})
        assert ha._entities[-1]["object_id"] == "ventilation_state_level"

    def test_name_fallback(self):
        ha = self._make(baseTopic=None)
        ha.add({"name": "My Sensor", "type": "sensor"})
        assert ha._entities[-1]["object_id"] == "my_sensor"

    def test_key_suffix(self):
        ha = self._make(baseTopic=None)
        ha.add({"name": "Co2", "type": "sensor", "state_topic": "ventilation/environment"}, key="co2")
        assert ha._entities[-1]["object_id"] == "ventilation_environment_co2"

    def test_unique_id_default(self):
        ha = self._make()
        ha.add({"name": "Co2", "type": "sensor"})
        assert "unique_id" in ha._entities[-1]
        assert ha._entities[-1]["unique_id"] == HomeAssistant._generate_entity_id("Co2")

    def test_unique_id_preserved(self):
        ha = self._make()
        ha.add({"name": "Co2", "type": "sensor", "unique_id": "my-fixed-id"})
        assert ha._entities[-1]["unique_id"] == "my-fixed-id"

    def test_device_attached(self):
        ha = self._make()
        ha.add({"name": "Co2", "type": "sensor"})
        assert ha._entities[-1]["device"]["identifiers"] == [HomeAssistant._DEVICE_ID]
