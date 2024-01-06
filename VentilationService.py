#! /bin/python3

import paho.mqtt.client as mqtt 
import Mqtt
from Timer import Timer
from EnvironmentMonitor import EnvironmentMonitor
from Ventilator import VentilationController
from HomeAssistant import HomeAssistant
from Configuration import Configuration


MQTT_SERVER = "homeassistant.home"
MQTT_USER = "mqtt"
MQTT_PASSWORD = "mqtt"


Configuration.addElementGroup("mqtt") \
    .addElement("server", defaultValue="homeassistant") \
    .addElement("username", valueType=str) \
    .addElement("password", valueType=str)

VentilationController.setupConfiguration()

Configuration.load("./config.json")


connectCallbacks = []

timer = Timer()


def setupMqttClient():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected success")
            for cb in connectCallbacks:
                timer.execute(cb)
        else:
            print(f"Connected failed with code {rc}")

    def on_pre_connect(client, userdata):
        # Function must be set in mqtt client setup to prevent an error. No implementation needed.
        ()

    client = mqtt.Client() 
    client.username_pw_set(Configuration.getValue("mqtt.username"), Configuration.getValue("mqtt.password"))
    client.on_connect = on_connect 
    client.on_pre_connect = on_pre_connect
    client.connect(Configuration.getValue("mqtt.server"), 1883) 

    return client




client = setupMqttClient()
subscriber = Mqtt.MqttSubscriber(client, "ventilation", timer)
publisher = Mqtt.MqttPublisher(client, "ventilation", timer)

homeAssistant = HomeAssistant(timer, publisher, subscriber)
connectCallbacks.append(homeAssistant.register)

environmentMonitor = EnvironmentMonitor(timer, publisher)
ventilationController = VentilationController(publisher, subscriber, environmentMonitor, timer)

homeAssistant.topic_base="ventilation"
homeAssistant.add({"name":"Level", "type":"sensor", "state_topic":"ventilation/level", "unit_of_measurement": "%"})
homeAssistant.add({"name":"Co2", "type":"sensor", "state_topic":"ventilation/environment", "value_template":"{{ value_json.co2 }}", "unit_of_measurement": "ppm", "device_class":"carbon_dioxide"}, key="co2")
homeAssistant.add({"name":"Humidity", "type":"sensor", "state_topic":"ventilation/environment", "value_template":"{{ value_json.relativeHumidity }}", "unit_of_measurement": "%", "device_class":"humidity"}, key="humidity")
homeAssistant.add({"name":"Temperature", "type":"sensor", "state_topic":"ventilation/environment", "value_template":"{{ value_json.temperature }}", "unit_of_measurement": "°C", "device_class":"temperature"}, key="temperature")

for stateNr in range(0, Configuration.getValue("ventilation.stateButtons.count")):
    homeAssistant.add({"name":f"Level {stateNr} Low", "type":"switch", "state_topic":f"ventilation/state/demand/{stateNr}", "command_topic":f"ventilation/state/demand/{stateNr}/set", "value_template":"{% if value=='normal' %} normal {% else %} _normal {% endif %}", "payload_on":"normal", "payload_off": "_normal"}, key="normal")
    homeAssistant.add({"name":f"Level {stateNr} Medium", "type":"switch", "state_topic":f"ventilation/state/demand/{stateNr}", "command_topic":f"ventilation/state/demand/{stateNr}/set", "value_template":"{% if value=='medium' %} medium {% else %} normal {% endif %}", "payload_on":"medium", "payload_off": "normal"}, key="medium")
    homeAssistant.add({"name":f"Level {stateNr} High", "type":"switch", "state_topic":f"ventilation/state/demand/{stateNr}", "command_topic":f"ventilation/state/demand/{stateNr}/set", "value_template":"{% if value=='high' %} high {% else %} normal {% endif %}", "payload_on":"high", "payload_off": "normal"}, key="high")
    homeAssistant.add({"name":f"Level {stateNr} Max", "type":"switch", "state_topic":f"ventilation/state/demand/{stateNr}", "command_topic":f"ventilation/state/demand/{stateNr}/set", "value_template":"{% if value=='max' %} max {% else %} normal {% endif %}", "payload_on":"max", "payload_off": "normal"}, key="max")


client.loop_start()
timer.run()



