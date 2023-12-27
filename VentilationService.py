#! /bin/python3

import paho.mqtt.client as mqtt 
import Mqtt
from Timer import Timer
from EnvironmentMonitor import EnvironmentMonitor

MQTT_SERVER = "homeassistant.home"
MQTT_USER = "mqtt"
MQTT_PASSWORD = "mqtt"


def setupMqttClient():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected success")
        else:
            print(f"Connected fail with code {rc}")

    def on_pre_connect(client, userdata):
        # Function must be set in mqtt client setup to prevent an error. No implementation needed.
        ()

    client = mqtt.Client() 
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect 
    client.on_pre_connect = on_pre_connect
    client.connect(MQTT_SERVER, 1883) 

    return client



client = setupMqttClient()
timer = Timer()
subscriber = Mqtt.MqttSubscriber(client, "ventilation", timer)
publisher = Mqtt.MqttPublisher(client, "ventilation", timer)

environmentMonitor = EnvironmentMonitor(timer, publisher)

client.loop_start()
timer.run()



