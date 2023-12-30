from Timer import Timer
from datetime import datetime, timedelta
import json
import paho.mqtt.client as mqttClient



class HomeAssistant:
    _DEVICE_ID = "VENT_B232AB30-6BCA-4E17-A021-5DACEBC075E2"
    _DEVICE_NAME = "Ventilator"
    _ENTITY_ID_BASE = "F9C8F22F-906A-4F7A-B681"
    _BASE_TOPIC = "homeassistant"

    _timer: Timer
    _mqttClient: mqttClient
    _entities = []
    _device = { "identifiers": [ _DEVICE_ID ], "name": _DEVICE_NAME }

    # class Entity:
    #     name: None
    #     device_class = ""
    #     state_topic = ""
    #     unique_id = ""
    #     type = "sensor"


    def __init__(self, timer, mqttClient, mqttSubscriber):
        self._timer = timer
        self._mqttClient = mqttClient
        mqttSubscriber.subscribe("/homeassistant/status", self._homeAssistant_status)
    

    def add(self, entity):
        if not "unique_id" in entity:
            entity["unique_id"] = HomeAssistant._generate_entity_id(entity["name"])
        
        entity["object_id"] = entity["name"].lower().replace(" ", "_")

        entity["device"] = HomeAssistant._device
        self._entities.append(entity)
        self._registerDelayed()
        

    def register(self):
        print("register")
        for e in self._entities:
            entityJson = json.dumps(e)
            print(f"registering {entityJson}")

            self._mqttClient.publish(self._BASE_TOPIC + "/" + e["type"] + "/" + e["unique_id"] + "/config", entityJson)


    _registerDeferral = None
    def _registerDelayed(self):
        self._registerDeferral = datetime.now() + timedelta(seconds=10)
        print("Deferred registration until {self._registerDeferral}")

        def onRegister():
            if self._registerDeferral is None:
                return
            
            d = (self._registerDeferral - datetime.now()).total_seconds()
            if d > 0:
                print("deferring registration")
                self._timer.execute(onRegister, defferredUntil=self._registerDeferral)
                return
            
            print("running deferred registration")
            self._registerDeferral = None
            self.register()

        self._timer.execute(onRegister, defferredUntil=self._registerDeferral)



    def _generate_entity_id(name):
        h = 0
        for c in name:
            h <<= 4
            h += ord(c)
            h %= 0x1000000000000

        id = f"{HomeAssistant._ENTITY_ID_BASE}-{h:0>12X}"
        return id
    
    
    def _homeAssistant_status(self, status):
        if status == "online":
            self.register()
    
