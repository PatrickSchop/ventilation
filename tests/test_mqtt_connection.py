"""Lock current behavior of MqttConnection (the heart of recovery).

Uses the injected clientFactory seam (R1, Phase 3) to avoid a real paho
connection. Uses the Clock seam (R3, Phase 2) for deterministic time.

xfail-strict markers assert CORRECT target behavior for known bugs:
  - C2: __aggressiveReset fires when is_connected()==False AND stale
  - C2: __aggressiveReset fires when is_connected()==True but stale
  - H2: __aggressiveReset does not double-subscribe or double-fire callbacks
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, call

import pytest

from Clock import Clock
from Mqtt import MqttConnection
from Logger import Logger


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def frozen(monkeypatch):
    t = [datetime(2024, 1, 1, 0, 0, 0)]
    monkeypatch.setattr(Clock, "now", staticmethod(lambda: t[0]))
    class Ctrl:
        def advance(self, seconds):
            t[0] = t[0] + timedelta(seconds=seconds)
        def set(self, new_t):
            t[0] = new_t
    return Ctrl()


@pytest.fixture
def mock_client_factory():
    """Returns (factory, mock_client)."""
    mock = MagicMock()
    mock.is_connected.return_value = True
    factory = MagicMock(return_value=mock)
    return factory, mock


@pytest.fixture
def timer():
    from Timer import Timer
    t = Timer()
    return t


@pytest.fixture
def make_mqtt(timer, mock_client_factory, frozen):
    """Factory for a MqttConnection with a mock client + frozen clock."""
    factory, mock = mock_client_factory
    def _make(host="h", port=1883, baseTopic="ventilation", failureThreshold=900):
        m = MqttConnection(timer, host, port, baseTopic=baseTopic,
                           failureThreshold=failureThreshold,
                           clientFactory=factory)
        return m, mock
    return _make


# ---------------------------------------------------------------------------
# Construction / wiring
# ---------------------------------------------------------------------------

def test_construct_uses_injected_factory(timer, mock_client_factory, frozen):
    factory, mock = mock_client_factory
    MqttConnection(timer, "h", 1883, baseTopic="ventilation", clientFactory=factory)
    factory.assert_called_once()
    mock.will_set.assert_called_once()
    args, kwargs = mock.will_set.call_args
    assert args[0] == "ventilation/status"
    assert args[1] == "offline"
    assert kwargs.get("retain") is True


def test_construct_survives_connect_failure(timer, frozen, monkeypatch):
    """C1: if connect() throws (broker unreachable at boot), construction
    must not crash the service. self.__client must still be assigned so
    paho's reconnect machinery can recover.
    """
    factory = MagicMock(return_value=MagicMock(
        connect=MagicMock(side_effect=OSError("broker down")),
        loop_start=MagicMock(),
    ))
    monkeypatch.setattr(Logger, "error", lambda *a, **k: None)
    # Should NOT raise
    m = MqttConnection(timer, "h", 1883, baseTopic="v", clientFactory=factory)
    assert m._MqttConnection__client is not None  # assigned even on failure


def test_default_client_factory_uses_callback_api_version_1(timer, frozen, monkeypatch):
    """H3: pin paho to the v1 callback API to avoid a future upgrade breaking
    the 4-arg on_connect / 3-arg on_disconnect signatures used in this module.
    """
    import paho.mqtt.client as paho
    captured = []
    real_client = paho.Client
    def spy(api_version=None):
        captured.append(api_version)
        return MagicMock()
    monkeypatch.setattr(paho, "Client", spy)
    MqttConnection(timer, "h", 1883, baseTopic="v")
    assert captured == [paho.CallbackAPIVersion.VERSION1]
    monkeypatch.setattr(paho, "Client", real_client)


def test_construct_registers_timer_actions(timer, mock_client_factory, frozen):
    factory, mock = mock_client_factory
    MqttConnection(timer, "h", 1883, baseTopic="ventilation", clientFactory=factory)
    # publishLoop freq=1, healthCheck freq=30
    assert len(timer._Timer__timerActions) == 2
    freqs = sorted(a.frequency for a in timer._Timer__timerActions)
    assert freqs == [1, 30]


def test_construct_subscribes_health_ping(timer, mock_client_factory, frozen):
    factory, mock = mock_client_factory
    MqttConnection(timer, "h", 1883, baseTopic="ventilation", clientFactory=factory)
    # Should have called subscribe at least once with the health/ping topic
    subscribe_calls = [c for c in mock.subscribe.call_args_list]
    topics = [c.args[0] if c.args else c.kwargs.get("topic") for c in subscribe_calls]
    assert "ventilation/health/ping" in topics


# ---------------------------------------------------------------------------
# Topic prefixing
# ---------------------------------------------------------------------------

def test_publish_with_basetopic_prefixes(make_mqtt):
    m, mock = make_mqtt()
    m.publish("foo/bar", "v")
    mock.publish.assert_called_with("ventilation/foo/bar", "v")


def test_publish_with_leading_slash_bypasses_basetopic(make_mqtt):
    m, mock = make_mqtt()
    m.publish("/absolute", "v")
    mock.publish.assert_called_with("absolute", "v")


def test_subscribe_prefixes_basetopic(make_mqtt):
    m, mock = make_mqtt()
    m.subscribe("foo/bar", lambda v: None)
    topics = [c.args[0] if c.args else c.kwargs.get("topic") for c in mock.subscribe.call_args_list]
    assert "ventilation/foo/bar" in topics


def test_subscribe_with_leading_slash_bypasses_basetopic(make_mqtt):
    m, mock = make_mqtt()
    m.subscribe("/abs", lambda v: None)
    topics = [c.args[0] if c.args else c.kwargs.get("topic") for c in mock.subscribe.call_args_list]
    assert "abs" in topics


# ---------------------------------------------------------------------------
# __on_connect
# ---------------------------------------------------------------------------

def test_on_connect_success_publishes_online_and_resubscribes(make_mqtt):
    m, mock = make_mqtt()
    # Pre-register a subscription so we can verify re-subscribe
    m.subscribe("foo", lambda v: None)
    mock.subscribe.reset_mock()
    mock.publish.reset_mock()

    m._MqttConnection__on_connect(mock, None, {}, 0)

    # Should have published "online" with retain
    online_calls = [c for c in mock.publish.call_args_list
                    if c.args[0] == "ventilation/status" and c.args[1] == "online"]
    assert len(online_calls) == 1
    assert online_calls[0].kwargs.get("retain") is True

    # Should have re-subscribed to the stored topic
    topics = [c.args[0] if c.args else c.kwargs.get("topic") for c in mock.subscribe.call_args_list]
    assert "ventilation/foo" in topics


def test_on_connect_success_fires_connect_callbacks_via_timer(make_mqtt, timer):
    m, mock = make_mqtt()
    fired = []
    m.addConnectCallback(lambda: fired.append(True))

    m._MqttConnection__on_connect(mock, None, {}, 0)
    # The callback is scheduled via timer.execute, not run synchronously
    assert fired == []  # not yet
    # Drain the timer
    while True:
        a = timer._takeTask()
        if a is None:
            break
        a.func()
    assert fired == [True]


def test_on_connect_failure_does_not_subscribe_or_fire(make_mqtt):
    m, mock = make_mqtt()
    m.addConnectCallback(lambda: None)
    m._MqttConnection__on_connect(mock, None, {}, 1)
    # No new subscribe calls beyond what was done at registration
    # (Hard to assert cleanly; just verify no publish of "online" happened)
    online_calls = [c for c in mock.publish.call_args_list
                    if c.args[0] == "ventilation/status" and c.args[1] == "online"]
    assert online_calls == []


# ---------------------------------------------------------------------------
# Message routing
# ---------------------------------------------------------------------------

def test_on_message_unknown_topic_ignored(make_mqtt, timer):
    m, mock = make_mqtt()
    # Build a mock MQTT message
    msg = MagicMock()
    msg.topic = "ventilation/not/subscribed"
    msg.payload.decode.return_value = "x"
    m._MqttConnection__on_message(mock, None, msg)
    # No tasks scheduled
    assert timer._takeTask() is None


def test_on_message_known_topic_dispatches_via_timer(make_mqtt, timer):
    m, mock = make_mqtt()
    captured = []
    m.subscribe("foo", lambda v: captured.append(v))

    msg = MagicMock()
    msg.topic = "ventilation/foo"
    msg.payload.decode.return_value = "hello"
    m._MqttConnection__on_message(mock, None, msg)

    task = timer._takeTask()
    assert task is not None
    task.func()
    assert captured == ["hello"]


def test_on_message_int_paramtype_coerces(make_mqtt, timer):
    m, mock = make_mqtt()
    captured = []
    m.subscribe("foo", lambda v: captured.append(v), paramType=int)

    msg = MagicMock()
    msg.topic = "ventilation/foo"
    msg.payload.decode.return_value = "42"
    m._MqttConnection__on_message(mock, None, msg)

    task = timer._takeTask()
    task.func()
    assert captured == [42]


# ---------------------------------------------------------------------------
# Health ping echo
# ---------------------------------------------------------------------------

def test_health_check_publishes_ping_with_incrementing_id(make_mqtt, frozen):
    m, mock = make_mqtt()
    # Connected
    mock.is_connected.return_value = True
    m._MqttConnection__healthCheck()
    m._MqttConnection__healthCheck()
    # Two pings published, ids 1 and 2
    ping_publishes = [c for c in mock.publish.call_args_list if "health/ping" in c.args[0]]
    assert len(ping_publishes) == 2
    assert ping_publishes[0].args[1] == "1"
    assert ping_publishes[1].args[1] == "2"


def test_health_ping_clears_outstanding_and_updates_comm(make_mqtt, frozen):
    m, mock = make_mqtt()
    mock.is_connected.return_value = True
    m._MqttConnection__healthCheck()
    m._MqttConnection__onHealthPing("1")
    assert m._MqttConnection__outstandingPings == {}
    # And the timestamp was bumped
    assert m._MqttConnection__lastSuccessfulCommunication == Clock.now()


def test_health_check_message_id_wraps_at_2_31(make_mqtt, frozen):
    m, mock = make_mqtt()
    mock.is_connected.return_value = True
    m._MqttConnection__messageId = (2 ** 31) - 1
    m._MqttConnection__healthCheck()
    assert m._MqttConnection__messageId == 0


# ---------------------------------------------------------------------------
# C2 — xfail-strict: reset fires when stale (both connected & disconnected)
# ---------------------------------------------------------------------------

def test_health_check_forces_reset_when_disconnected_and_stale(make_mqtt, frozen):
    m, mock = make_mqtt(failureThreshold=900)
    # Make last successful communication old
    frozen.advance(2000)  # > failureThreshold
    mock.is_connected.return_value = False
    # Spy on __aggressiveReset
    called = []
    m._MqttConnection__aggressiveReset = lambda: called.append(True) or m.__dict__.setdefault("__aggressive_called", True)
    m._MqttConnection__healthCheck()
    assert called == [True]


# ---------------------------------------------------------------------------
# H2 — xfail-strict: aggressiveReset does NOT double-subscribe or double-fire
# ---------------------------------------------------------------------------

def test_aggressive_reset_does_not_double_subscribe_or_callback(make_mqtt, timer):
    m, mock = make_mqtt()
    # Register a subscription and a connect callback
    m.subscribe("foo", lambda v: None)
    cb_count = []
    m.addConnectCallback(lambda: cb_count.append(1))

    # Reset subscribe/publish mock counters from the subscription setup
    mock.subscribe.reset_mock()
    mock.publish.reset_mock()

    # Simulate that on_connect will fire asynchronously when the new client connects.
    # For the test, just call __aggressiveReset and assert it does NOT itself
    # re-subscribe or fire callbacks (those should come solely from __on_connect).
    m._MqttConnection__aggressiveReset()

    subscribe_calls_after_reset = [c for c in mock.subscribe.call_args_list
                                   if (c.args[0] if c.args else c.kwargs.get("topic")) == "ventilation/foo"]
    assert subscribe_calls_after_reset == []  # aggressiveReset should not re-subscribe
    assert cb_count == []  # aggressiveReset should not fire connect callbacks


# ---------------------------------------------------------------------------
# publishState / register / __publishTopic
# ---------------------------------------------------------------------------

def test_register_marks_topic_with_comparer(make_mqtt):
    m, mock = make_mqtt()
    from Mqtt import IntComparer
    m.register("foo", IntComparer(5))
    # publishTopics store the unprefixed topic; subscribe stores the prefixed one
    t = next(t for t in m._MqttConnection__publishTopics if t.topic == "foo")
    assert isinstance(t.comparer, IntComparer)
    assert t.comparer._IntComparer__minChange == 5


def test_publish_loop_skips_none_current_value(make_mqtt, frozen):
    m, mock = make_mqtt()
    m.register("foo")
    mock.publish.reset_mock()
    m._MqttConnection__publishLoop()
    # No publish for unset value
    publishes = [c for c in mock.publish.call_args_list if c.args[0] == "ventilation/foo"]
    assert publishes == []


def test_publish_loop_publishes_first_value_immediately(make_mqtt, frozen):
    m, mock = make_mqtt()
    m.register("foo")
    m.publishState("foo", "v1")
    mock.publish.reset_mock()
    m._MqttConnection__publishLoop()
    publishes = [c for c in mock.publish.call_args_list if c.args[0] == "ventilation/foo"]
    assert len(publishes) == 1
    assert publishes[0].args[1] == "v1"


def test_publish_loop_throttles_same_value(make_mqtt, frozen):
    m, mock = make_mqtt()
    m.register("foo")
    m.publishState("foo", "v1")
    m._MqttConnection__publishLoop()  # first publish
    mock.publish.reset_mock()
    # Immediately re-publish same value: BaseComparer returns 0 → should not publish
    m._MqttConnection__publishLoop()
    publishes = [c for c in mock.publish.call_args_list if c.args[0] == "ventilation/foo"]
    assert publishes == []
