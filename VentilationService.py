#! /bin/python3

import paho.mqtt.client as mqtt 
import Mqtt
from Timer import Timer
from EnvironmentMonitor import EnvironmentMonitor
from HomeAssistant import HomeAssistant

MQTT_SERVER = "homeassistant.home"
MQTT_USER = "mqtt"
MQTT_PASSWORD = "mqtt"

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
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect 
    client.on_pre_connect = on_pre_connect
    client.connect(MQTT_SERVER, 1883) 

    return client



client = setupMqttClient()
subscriber = Mqtt.MqttSubscriber(client, "ventilation", timer)
publisher = Mqtt.MqttPublisher(client, "ventilation", timer)

#environmentMonitor = EnvironmentMonitor(timer, publisher)
homeAssistant = HomeAssistant(timer, client, subscriber)
connectCallbacks.append(homeAssistant.register)


homeAssistant.add({"name":"Level", "type":"sensor", "state_topic":"ventilation/level", "unit_of_measurement": "%"})
homeAssistant.add({"name":"Co2", "type":"sensor", "state_topic":"ventilation/environment", "value_template":"{{ value_json.co2 }}", "unit_of_measurement": "ppm"})
homeAssistant.add({"name":"Humidity", "type":"sensor", "state_topic":"ventilation/environment", "value_template":"{{ value_json.relativeHumidity }}", "unit_of_measurement": "%"})
homeAssistant.add({"name":"Temperature", "type":"sensor", "state_topic":"ventilation/environment", "value_template":"{{ value_json.temperature }}", "unit_of_measurement": "°C"})

for stateNr in range(0, 5):
    homeAssistant.add({"name":f"Level {stateNr} Low", "type":"switch", "state_topic":f"ventilation/state/demand/{stateNr}", "command_topic":f"ventilation/state/demand/{stateNr}/set", "value_template":"{% if value=='normal' %} normal {% else %} _normal {% endif %}", "payload_on":"normal", "payload_off": "_normal"})
    homeAssistant.add({"name":f"Level {stateNr} Medium", "type":"switch", "state_topic":f"ventilation/state/demand/{stateNr}", "command_topic":f"ventilation/state/demand/{stateNr}/set", "value_template":"{% if value=='medium' %} medium {% else %} normal {% endif %}", "payload_on":"medium", "payload_off": "normal"})
    homeAssistant.add({"name":f"Level {stateNr} High", "type":"switch", "state_topic":f"ventilation/state/demand/{stateNr}", "command_topic":f"ventilation/state/demand/{stateNr}/set", "value_template":"{% if value=='high' %} high {% else %} normal {% endif %}", "payload_on":"high", "payload_off": "normal"})
    homeAssistant.add({"name":f"Level {stateNr} Max", "type":"switch", "state_topic":f"ventilation/state/demand/{stateNr}", "command_topic":f"ventilation/state/demand/{stateNr}/set", "value_template":"{% if value=='max' %} max {% else %} normal {% endif %}", "payload_on":"max", "payload_off": "normal"})


client.loop_start()
timer.run()



