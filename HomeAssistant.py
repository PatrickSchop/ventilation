from Timer import Timer
from datetime import datetime, timedelta
import json
from Mqtt import MqttPublisher, MqttSubscriber


class HomeAssistant:
    _DEVICE_ID = "VENT_B232AB30-6BCA-4E17-A021-5DACEBC075E2"
    _DEVICE_NAME = "Ventilator"
    _ENTITY_ID_BASE = "F9C8F22F-906A-4F7A-B681"
    _HOMEASSISTANT_TOPIC = "/homeassistant"

    _timer: Timer
    _mqttPublisher: MqttPublisher
    _entities: list
    _device: dict
    baseTopic: str


    def __init__(self, timer, mqttPublisher, mqttSubscriber):
        self._timer = timer
        self._mqttPublisher = mqttPublisher
        self._entities = []
        self._device = { "identifiers": [ self._DEVICE_ID ], "name": self._DEVICE_NAME }
        self.baseTopic = None
        mqttSubscriber.subscribe("/homeassistant/status", self._homeAssistant_status)
    

    def add(self, entity, key=None):
        if not "unique_id" in entity:
            entity["unique_id"] = HomeAssistant._generate_entity_id(entity["name"])
        
        if "state_topic" in entity.keys():
            objectId = entity["state_topic"].lower().replace("/", "_")
        else:
            objectId = entity["name"].lower().replace(" ", "_")
        if (self.baseTopic is not None) and objectId.startswith(self.baseTopic):
            objectId = objectId[len(self.baseTopic):]
        objectId.lstrip("_")
        if key is not None:
            objectId += "_" + key
        entity["object_id"] = objectId

        entity["device"] = self._device
        self._entities.append(entity)
        self._registerDelayed()
        

    def register(self):
        for e in self._entities:
            entityJson = json.dumps(e)

            self._mqttPublisher.publish(self._HOMEASSISTANT_TOPIC + "/" + e["type"] + "/" + e["unique_id"] + "/config", entityJson)


    _registerDeferral = None
    def _registerDelayed(self):
        self._registerDeferral = datetime.now() + timedelta(seconds=10)

        def onRegister():
            if self._registerDeferral is None:
                return
            
            d = (self._registerDeferral - datetime.now()).total_seconds()
            if d > 0:
                self._timer.execute(onRegister, defferredUntil=self._registerDeferral)
                return
            
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
    
