from datetime import datetime
import Timer
import Mqtt
import Ventilator


def on_demand(value):
    if ((value < 0) | (value > 255)):
        return
    demandCalculator.externalDemand(value)

def on_demandChanged(demand):
    print(f"Demand changed to {demand}")
    mqtt.publishState("state/level", demand)


demandCalculator = Ventilator.DemandCalculator()
demandCalculator.onDemandChanged = on_demandChanged

timer = Timer.Timer()

mqtt = Mqtt.MqttConnection(timer, "homeassistant.local", 1883, "mqtt", "mqtt", baseTopic="ventilation")

mqtt.subscribe("state/demand", on_demand, int)
mqtt.register("state/level", Mqtt.IntComparer(5))
mqtt.register("environment/humidity", Mqtt.IntComparer(2))
mqtt.register("environment/co2", Mqtt.IntComparer(25))


ct = Timer.CancellationToken()
timer.run(ct)
