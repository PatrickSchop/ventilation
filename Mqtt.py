from datetime import datetime
from Timer import Timer
import paho.mqtt.client as mqtt 
from ActionRunner import Runner as runner

class BaseComparer:
    def compare(self, originalValue, newValue):
        if originalValue == None:
            return 2

        if newValue == originalValue:
            return 0
        
        return 2


class IntComparer(BaseComparer):
    __minChange = 0

    def __init__(self, minChange):
        self.__minChange = minChange

    def compare(self, originalValue, newValue):
        if originalValue == None:
            return 2
            
        if newValue == originalValue:
            return 0

        if abs(originalValue - newValue) < self.__minChange:
            return 1
        
        return 2


class _PublishTopic:
    topic: str
    comparer: BaseComparer
    lastPublishedValue: int
    lastPublishTime: any
    currentValue: int


class MqttPublisher:
    __mqtt: mqtt.Client
    __baseTopic: str
    __topics = []

    __publishInterval = 10
    __forcePublishInterval = 60

    def __init__(self, mqtt, baseTopic, timer):
        self.__mqtt = mqtt
        self.__baseTopic = baseTopic
        if len(self.__baseTopic) > 0:
            self.__baseTopic += "/"

        timer.add(self.__loop, 1)

    def register(self, topic, comparer = BaseComparer()):
        t = self.__getTopic(topic)
        t.comparer = comparer

    def publish(self, topic, value):
        t = self.__getTopic(topic)
        t.currentValue = value        

    def __loop(self):
        time = datetime.now()
        
        for topic in self.__topics:
            if (topic.currentValue == None):
                continue

            dValue = topic.comparer.compare(topic.lastPublishedValue, topic.currentValue)
            dTime = (time-topic.lastPublishTime).seconds
            if  (dValue > 1) | \
                ((dValue > 0) & (dTime > self.__publishInterval)) | \
                (dTime > self.__forcePublishInterval):
                
                self.__mqtt.publish(self.__baseTopic + topic.topic, topic.currentValue)
                topic.lastPublishedValue = topic.currentValue
                topic.lastPublishTime = time

    def __getTopic(self, topic: str):
        for t in self.__topics:
            if t.topic == topic:
                return t
            
        t = _PublishTopic()
        t.topic = topic
        t.comparer = BaseComparer()
        t.lastPublishedValue = None
        t.lastPublishTime = datetime.now()
        t.currentValue = None
        self.__topics.append(t)

        return t


class _MqttSubscription:
    topic: str
    callback: any
    paramType: any

class MqttSubscriber:
    __mqtt: mqtt.Client
    __baseTopic: str
    __subscriptions = []
    __timer: Timer

    def __init__(self, mqtt, baseTopic, timer):
        self.__mqtt = mqtt
        self.__timer = timer
        self.__baseTopic = baseTopic
        if len(self.__baseTopic) > 0:
            self.__baseTopic += "/"
        mqtt.on_message = self.__on_message

    def subscribe(self, topic, callback, paramType=None):
        fullTopic = self.__baseTopic + topic

        s = self.__getSubscription(fullTopic)
        if (s == None):
            s = _MqttSubscription()
            self.__subscriptions.append(s)

        s.topic = fullTopic
        s.callback = callback
        s.paramType = paramType
        
        print(f"subscribing to {fullTopic}")
        self.__mqtt.subscribe(fullTopic)
    
    def __getSubscription(self, topic: str):
        for s in self.__subscriptions:
            if s.topic == topic:
                return s
        
        return None

    def __on_message(self, client, userdata, msg):
        topic = msg.topic
        value = msg.payload.decode()

        print(f"Received mqtt message with topic '{topic}' and value '{value}'")

        subscription = self.__getSubscription(topic)
        if subscription == None:
            return
        
        h = lambda: self.__handle(subscription, value)
        print("register task")
        self.__timer.execute(h)
        print("after timer.execute")
        

    def __handle(self, subscription, value):
        print("Handling subscription task")
        if subscription.paramType == int:
            value = int(value)
        
        runner.execute(subscription.callback, value)
    