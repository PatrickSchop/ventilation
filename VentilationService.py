#! /bin/python3

import sys
from Timer import Timer
from EnvironmentMonitor import EnvironmentMonitor, FakeEnvironmentMonitor
from Ventilator import VentilationController
from HomeAssistant import HomeAssistant
from Configuration import Configuration
from Logger import Logger
from Mqtt import MqttConnection


print(f"Arguments: {sys.argv}")
noEnvironment = "noenvironment" in sys.argv


Configuration.addElementGroup("mqtt") \
    .addElement("server", defaultValue="homeassistant") \
    .addElement("username", valueType=str) \
    .addElement("password", valueType=str)

VentilationController.setupConfiguration()

Configuration.load("./config.json")


timer = Timer()

mqtt = MqttConnection(
    timer,
    Configuration.getValue("mqtt.server"), 1883,
    Configuration.getValue("mqtt.username"),
    Configuration.getValue("mqtt.password"),
    baseTopic="ventilation"
)

homeAssistant = HomeAssistant(timer, mqtt)
mqtt.addConnectCallback(homeAssistant.register)

if noEnvironment:
    print("Running without environment monitoring")
    environmentMonitor = FakeEnvironmentMonitor()
else:
    environmentMonitor = EnvironmentMonitor(timer, mqtt)

ventilationController = VentilationController(mqtt, environmentMonitor, timer)

homeAssistant.baseTopic = "ventilation"
homeAssistant.add({"name":"Level", "type":"sensor", "state_topic":"ventilation/state/level", "unit_of_measurement": "%"})
homeAssistant.add({"name":"Co2", "type":"sensor", "state_topic":"ventilation/environment", "value_template":"{{ value_json.co2 }}", "unit_of_measurement": "ppm", "device_class":"carbon_dioxide"}, key="co2")
homeAssistant.add({"name":"Humidity", "type":"sensor", "state_topic":"ventilation/environment", "value_template":"{{ value_json.relativeHumidity }}", "unit_of_measurement": "%", "device_class":"humidity"}, key="humidity")
homeAssistant.add({"name":"Temperature", "type":"sensor", "state_topic":"ventilation/environment", "value_template":"{{ value_json.temperature }}", "unit_of_measurement": "°C", "device_class":"temperature"}, key="temperature")

for stateNr in range(0, Configuration.getValue("ventilation.stateButtons.count")):
    homeAssistant.add({"name":f"Level {stateNr} Low", "type":"switch", "state_topic":f"ventilation/state/demand/{stateNr}", "command_topic":f"ventilation/state/demand/{stateNr}/set", "value_template":"{% if value=='normal' %} normal {% else %} _normal {% endif %}", "payload_on":"normal", "payload_off": "_normal"}, key="normal")
    homeAssistant.add({"name":f"Level {stateNr} Medium", "type":"switch", "state_topic":f"ventilation/state/demand/{stateNr}", "command_topic":f"ventilation/state/demand/{stateNr}/set", "value_template":"{% if value=='medium' %} medium {% else %} normal {% endif %}", "payload_on":"medium", "payload_off": "normal"}, key="medium")
    homeAssistant.add({"name":f"Level {stateNr} High", "type":"switch", "state_topic":f"ventilation/state/demand/{stateNr}", "command_topic":f"ventilation/state/demand/{stateNr}/set", "value_template":"{% if value=='high' %} high {% else %} normal {% endif %}", "payload_on":"high", "payload_off": "normal"}, key="high")
    homeAssistant.add({"name":f"Level {stateNr} Max", "type":"switch", "state_topic":f"ventilation/state/demand/{stateNr}", "command_topic":f"ventilation/state/demand/{stateNr}/set", "value_template":"{% if value=='max' %} max {% else %} normal {% endif %}", "payload_on":"max", "payload_off": "normal"}, key="max")


timer.run()



