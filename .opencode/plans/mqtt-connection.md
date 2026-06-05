# MqttConnection Refactoring Plan

## Goal
Combine `MqttPublisher`, `MqttSubscriber`, and `MqttHealthMonitor` into a single `MqttConnection` class that owns the paho MQTT client internally. No `setClient()` calls needed — the paho client is never exposed.

## Changes

### 1. Mqtt.py — Rewrite (replace everything after `IntComparer`)

**Keep:** `BaseComparer`, `IntComparer`, `_PublishTopic`  
**Add:** `_MqttSubscription` data class, `MqttConnection` class  
**Remove:** `MqttPublisher`, `MqttSubscriber`, `MqttHealthMonitor`

**MqttConnection public API:**
- `publish(topic, value)` — immediate publish with base topic prefixing
- `publishState(topic, value)` — register value for throttled/compared publish
- `register(topic, comparer=BaseComparer())` — register topic with comparer
- `subscribe(topic, callback, paramType=None)` — subscribe + store for re-apply on reset
- `addConnectCallback(fn)` — register callback for reconnect events

**MqttConnection internals:**
- `__client: mqtt.Client` — fully private, never exposed
- `__createClient()` — creates paho client with will, reconnect_delay, on_connect, on_disconnect, on_message
- Health monitoring: every 30s publishes ping with correlation ID; if no ping received for 15 min (`failureThreshold`, default 900s), calls `__aggressiveReset()`
- `__aggressiveReset()` — clears outstanding pings, `__createClient()` (stops old, creates new), re-subscribes all stored subscriptions, fires connect callbacks, resets `__lastSuccessfulCommunication`
- `__on_message` dispatches to subscription callbacks via timer.execute
- Message IDs use modulo `2^31` to prevent overflow

### 2. Ventilator.py

```python
# Current:
from Mqtt import MqttPublisher, MqttSubscriber, IntComparer
# New:
from Mqtt import MqttConnection, IntComparer

# ExternalDemand:
# Current: __init__(self, mqttPublisher, mqttSubscriber, timer)
# New:    __init__(self, mqtt, timer)
# Changes: self._mqttPublisher.x → self._mqtt.x
#          mqttSubscriber.subscribe(...) → self._mqtt.subscribe(...)

# VentilationController:
# Current: __init__(self, mqttPublisher, mqttSubscriber, environmentMonitor, timer)
# New:    __init__(self, mqtt, environmentMonitor, timer)
# Changes: ExternalDemand(mqttPublisher, mqttSubscriber, timer) → ExternalDemand(mqtt, timer)
```

### 3. EnvironmentMonitor.py

```python
# Current:
from Mqtt import MqttPublisher
# New:
from Mqtt import MqttConnection

# __init__(self, timer, mqttPublisher) → __init__(self, timer, mqtt)
# self._mqttPublisher → self._mqtt
```

### 4. HomeAssistant.py

```python
# Current:
from Mqtt import MqttPublisher, MqttSubscriber
# New:
from Mqtt import MqttConnection

# __init__(self, timer, mqttPublisher, mqttSubscriber) → __init__(self, timer, mqtt)
# self._mqttPublisher → self._mqtt
# mqttSubscriber.subscribe(...) → self._mqtt.subscribe(...)
```

### 5. VentilationService.py

```python
# Current (setup):
def setupMqttClient():
    ...  # 27 lines
client = setupMqttClient()
subscriber = MqttSubscriber(client, "ventilation", timer)
publisher = MqttPublisher(client, "ventilation", timer)
healthMonitor = MqttHealthMonitor(timer, subscriber, ..., baseTopic="ventilation")
homeAssistant = HomeAssistant(timer, publisher, subscriber)
connectCallbacks.append(subscriber.on_connect)
connectCallbacks.append(homeAssistant.register)
client.loop_start()
timer.run()

# New:
mqtt = MqttConnection(
    timer,
    Configuration.getValue("mqtt.server"), 1883,
    Configuration.getValue("mqtt.username"),
    Configuration.getValue("mqtt.password"),
    baseTopic="ventilation"
)
homeAssistant = HomeAssistant(timer, mqtt)
mqtt.addConnectCallback(homeAssistant.register)
ventilationController = VentilationController(mqtt, environmentMonitor, timer)
# (moved from _externalDemand constructor)
mqtt.subscribe(f"state/demand/{i}/set", lambda v: ...)
timer.run()
```

**Removed:** `setupMqttClient()`, `connectCallbacks = []`, `import paho.mqtt.client`, `client.loop_start()`

### 6. mqtt-test.py (low priority)
Same pattern: replace separate subscriber/publisher with `MqttConnection`.

## Verification
- Run `python -m py_compile Mqtt.py; python -m py_compile VentilationService.py; python -m py_compile HomeAssistant.py; python -m py_compile Ventilator.py; python -m py_compile EnvironmentMonitor.py` to syntax check all modified files.
