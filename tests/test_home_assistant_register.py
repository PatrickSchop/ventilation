"""Lock current behavior of HomeAssistant registration flow.

Pure orchestration tests; no MQTT needed.
"""

from unittest.mock import MagicMock
import pytest
from HomeAssistant import HomeAssistant


@pytest.fixture
def ha():
    return HomeAssistant(MagicMock(), MagicMock())


def test_register_publishes_one_config_per_entity(ha):
    ha.add({"name": "A", "type": "sensor"})
    ha.add({"name": "B", "type": "switch"})
    mqtt = MagicMock()
    ha._mqtt = mqtt

    ha.register()

    assert mqtt.publish.call_count == 2
    topics = [c.args[0] for c in mqtt.publish.call_args_list]
    assert any("/sensor/" in t for t in topics)
    assert any("/switch/" in t for t in topics)


def test_home_assistant_status_online_triggers_register(ha):
    ha.add({"name": "A", "type": "sensor"})
    mqtt = MagicMock()
    ha._mqtt = mqtt

    ha._homeAssistant_status("online")

    assert mqtt.publish.call_count == 1


def test_home_assistant_status_other_does_not_register(ha):
    ha.add({"name": "A", "type": "sensor"})
    mqtt = MagicMock()
    ha._mqtt = mqtt

    ha._homeAssistant_status("offline")

    assert mqtt.publish.call_count == 0
