"""Lock current behavior of ExternalDemand: state mapping, validation.

xfail-strict H4: per-button routing with count>1 binds the final i in all
lambdas (Python late-binding closure). The test asserts the CORRECT
behavior (each button routes to its own index).
"""

import pytest
from unittest.mock import MagicMock
from Ventilator import ExternalDemand
from Configuration import _Configuration


@pytest.fixture
def fresh_config(monkeypatch):
    """Populate the global Configuration singleton in place (Ventilator
    holds a direct reference to it, so we mutate it rather than replacing).
    """
    import Ventilator
    cfg = Ventilator.Configuration  # the singleton
    cfg._items.clear()
    grp = cfg.addElementGroup("ventilation")
    sb = grp.addElementGroup("stateButtons")
    sb.addElement("count", defaultValue=1)
    sb.addElement("medium", defaultValue=40)
    sb.addElement("high", defaultValue=75)
    yield cfg
    cfg._items.clear()


@pytest.fixture
def reset_class_state():
    """ExternalDemand._states is a class attribute; reset for isolation."""
    ExternalDemand._states = []
    yield
    ExternalDemand._states = []


def test_external_demand_validates_state_values(reset_class_state, fresh_config):
    ed = ExternalDemand(MagicMock(), MagicMock())
    assert ed._validateStateValue("normal") is True
    assert ed._validateStateValue("medium") is True
    assert ed._validateStateValue("high") is True
    assert ed._validateStateValue("max") is True
    assert ed._validateStateValue("unknown") is False
    assert ed._validateStateValue("NORMAL") is False  # case-sensitive


def test_external_demand_publishes_initial_state(reset_class_state, fresh_config):
    mqtt = MagicMock()
    ed = ExternalDemand(mqtt, MagicMock())
    # Initial state: each button is "normal"
    # And _demandChanged is called, which sets self.level via _stateLevels lookup
    assert ed.level == 0  # "normal" → 0


def test_external_demand_mqtt_demand_validates_bounds(reset_class_state, fresh_config):
    mqtt = MagicMock()
    ed = ExternalDemand(mqtt, MagicMock())
    # Out-of-bounds stateNr is ignored
    ed._mqttDemand(-1, "high")
    ed._mqttDemand(99, "high")
    # No state change → publishState not called for those
    publishes = [c for c in mqtt.publishState.call_args_list if "demand" in c.args[0]]
    assert publishes == []


def test_external_demand_mqtt_demand_lowercases_and_validates(reset_class_state, fresh_config):
    mqtt = MagicMock()
    ed = ExternalDemand(mqtt, MagicMock())
    ed._mqttDemand(0, "HIGH")  # case-different; will be lowered to "high"
    assert ed._states[0] == "high"
    # _publishState was called → publishState
    publishes = [c for c in mqtt.publishState.call_args_list if "demand/0" in c.args[0]]
    assert len(publishes) == 1


def test_external_demand_mqtt_demand_invalid_value_ignored(reset_class_state, fresh_config):
    mqtt = MagicMock()
    ed = ExternalDemand(mqtt, MagicMock())
    ed._mqttDemand(0, "garbage")
    # State remains "normal", no publish
    assert ed._states[0] == "normal"


@pytest.mark.xfail(reason="H4: all subscribed lambdas bind the final loop variable i", strict=True)
def test_external_demand_routes_each_button_correctly_with_count_2(reset_class_state, monkeypatch):
    """With stateButtons.count=2, each registered callback must use its OWN index.

    Current behavior (bug): all lambdas share the same i, so the last value
    (i=1) is used by every callback. After the fix, button 0's callback
    routes to _mqttDemand(0, ...) and button 1's to _mqttDemand(1, ...).
    """
    cfg = _Configuration()
    cfg._name = "Configuration"
    sb = cfg.addElementGroup("ventilation").addElementGroup("stateButtons")
    sb.addElement("count", defaultValue=2)
    sb.addElement("medium", defaultValue=40)
    sb.addElement("high", defaultValue=75)
    # Patch the reference in BOTH Configuration module and Ventilator module
    monkeypatch.setattr("Configuration.Configuration", cfg)
    monkeypatch.setattr("Ventilator.Configuration", cfg)

    mqtt = MagicMock()
    ed = ExternalDemand(mqtt, MagicMock())

    # Capture the actual subscribed callbacks (and their topics)
    # mqtt.subscribe(topic, callback) — find the call with "state/demand/0/set"
    cb_by_topic = {}
    for c in mqtt.subscribe.call_args_list:
        topic = c.args[0] if c.args else c.kwargs.get("topic")
        if "demand" in (topic or "") and "/set" in (topic or ""):
            cb_by_topic[topic] = c.args[1] if c.args else c.kwargs.get("callback")

    assert "ventilation/state/demand/0/set" in cb_by_topic
    assert "ventilation/state/demand/1/set" in cb_by_topic

    # Drive the button-0 callback; it should mutate _states[0]
    cb_by_topic["ventilation/state/demand/0/set"]("high")
    assert ed._states[0] == "high"
    assert ed._states[1] == "normal"

    # Drive the button-1 callback; it should mutate _states[1]
    cb_by_topic["ventilation/state/demand/1/set"]("max")
    assert ed._states[0] == "high"   # unchanged
    assert ed._states[1] == "max"
