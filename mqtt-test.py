from datetime import datetime
import paho.mqtt.client as mqtt 
import sched
import Timer
import Mqtt
from ActionRunner import Runner
import Ventilator


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected success")
    else:
        print(f"Connected fail with code {rc}")

def on_pre_connect(client, userdata):
    # Function must be set in mqtt client setup to prevent an error. No implementation needed.
    ()

def on_demand(value):
    if ((value < 0) | (value > 255)):
        return
    demandCalculator.demand(value)

def on_demandChanged(demand):
    print(f"Demand changed to {demand}")
    publisher.publish("state/level", demand)


demandCalculator = Ventilator.DemandCalculator()
demandCalculator.demandChanged = on_demandChanged

timer = Timer.Timer()


client = mqtt.Client() 
client.username_pw_set("mqtt", "mqtt")
client.on_connect = on_connect 
client.on_pre_connect = on_pre_connect
client.connect("homeassistant.local", 1883) 

subscriber = Mqtt.MqttSubscriber(client, "ventilation", timer)
subscriber.subscribe("state/demand", on_demand, int)

publisher = Mqtt.MqttPublisher(client, "ventilation", timer)
publisher.register("state/level", Mqtt.IntComparer(5))
publisher.register("environment/humidity", Mqtt.IntComparer(2))
publisher.register("environment/co2", Mqtt.IntComparer(25))




client.loop_start()


ct = Timer.CancellationToken()
timer.run(ct)
