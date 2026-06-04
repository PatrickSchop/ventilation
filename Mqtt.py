from datetime import datetime
from Timer import Timer
import paho.mqtt.client as mqtt 
from ActionRunner import Runner as runner
from Logger import Logger

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
    __timer: Timer

    __publishInterval = 10
    __forcePublishInterval = 60

    def __init__(self, mqtt, baseTopic, timer):
        self.__mqtt = mqtt
        self.__timer = timer
            
        self.__baseTopic = baseTopic
        if len(self.__baseTopic) > 0:
            self.__baseTopic += "/"
        
        timer.add(self.__loop, 1)


    def register(self, topic, comparer = BaseComparer()):
        t = self.__getTopic(topic)
        t.comparer = comparer
        self.__timer.execute(lambda: self.__publishTopic(t))


    def publishState(self, topic, value):
        t = self.__getTopic(topic)
        t.currentValue = value        


    def publish(self, topic, value):
        if topic.startswith("/"):
            fullTopic = topic[1:]
        else:
            fullTopic = self.__baseTopic + topic

        self.__mqtt.publish(fullTopic, value)


    def __loop(self):
        time = datetime.now()
        
        for topic in self.__topics:
            self.__publishTopic(topic)


    def __publishTopic(self, topic):
        time = datetime.now()

        if (topic.currentValue == None):
            return

        dValue = topic.comparer.compare(topic.lastPublishedValue, topic.currentValue)
        dTime = (time-topic.lastPublishTime).seconds
        if  (dValue > 1) | \
            ((dValue > 0) & (dTime > self.__publishInterval)) | \
            (dTime > self.__forcePublishInterval):
            
            self.publish(topic.topic, topic.currentValue)
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

    def on_connect(self):
        Logger.info("MQTT subscriber re-subscribing topics after reconnect")
        for s in self.__subscriptions:
            Logger.info(f"Re-subscribing to {s.topic}")
            self.__mqtt.subscribe(s.topic)

    def subscribe(self, topic, callback, paramType=None):
        if topic.startswith("/"):
            fullTopic = topic[1:]
        else:
            fullTopic = self.__baseTopic + topic

        s = self.__getSubscription(fullTopic)
        if (s == None):
            s = _MqttSubscription()
            self.__subscriptions.append(s)

        s.topic = fullTopic
        s.callback = callback
        s.paramType = paramType
        
        self.__mqtt.subscribe(fullTopic)
    
    def __getSubscription(self, topic: str):
        for s in self.__subscriptions:
            if s.topic == topic:
                return s
        
        return None

    def __on_message(self, client, userdata, msg):
        topic = msg.topic
        value = msg.payload.decode()

        subscription = self.__getSubscription(topic)
        if subscription == None:
            return
        
        h = lambda: self.__handle(subscription, value)
        self.__timer.execute(h)
        

    def __handle(self, subscription, value):
        if subscription.paramType == int:
            value = int(value)
        
        runner.execute(subscription.callback, value)


class MqttHealthMonitor:
    __timer: Timer
    _client: mqtt.Client
    _subscriber: any
    _consecutiveFailures = 0
    _maxFailures = 3
    _pingInterval = 30
    _host: str
    _port: int
    _username: str
    _password: str
    _baseTopic: str
    _messageId = 0
    _outstandingMessages: dict
    _maxTrackedMessages = 100

    def __init__(self, timer, subscriber, host, port, username=None, password=None, baseTopic="", maxFailures=3):
        self.__timer = timer
        self._subscriber = subscriber
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._baseTopic = baseTopic
        if len(self._baseTopic) > 0:
            self._baseTopic += "/"
        self._maxFailures = maxFailures
        self._consecutiveFailures = 0
        self._messageId = 0
        self._outstandingMessages = {}

        self._client = self._connect()
        subscriber.subscribe(f"{self._baseTopic}health/ping", self._onHealthPing)
        timer.add(self._check, self._pingInterval)

    def _connect(self):
        client = mqtt.Client()
        if self._username:
            client.username_pw_set(self._username, self._password)
        client.reconnect_delay_set(min_delay=1, max_delay=120)
        client.connect(self._host, self._port)
        client.loop_start()
        return client

    def _onHealthPing(self, value):
        """Called when a health ping message is received by the subscriber"""
        try:
            msgId = int(value)
            if msgId in self._outstandingMessages:
                del self._outstandingMessages[msgId]
                # Reset failure counter on successful receipt
                if self._consecutiveFailures > 0:
                    Logger.info("MQTT communication restored")
                self._consecutiveFailures = 0
        except (ValueError, TypeError):
            pass

    def _cleanupOldMessages(self):
        """Remove very old messages to prevent unbounded growth"""
        if len(self._outstandingMessages) > self._maxTrackedMessages:
            sortedIds = sorted(self._outstandingMessages.keys())
            # Keep only the most recent maxTrackedMessages
            toDelete = sortedIds[:len(sortedIds) - self._maxTrackedMessages]
            for msgId in toDelete:
                del self._outstandingMessages[msgId]
                Logger.warning(f"MQTT health message {msgId} expired without receipt")

    def _handleFailure(self, reason):
        """Handle a communication failure and attempt reconnect if threshold reached"""
        self._consecutiveFailures += 1
        Logger.warning(
            f"{reason} "
            f"({self._consecutiveFailures}/{self._maxFailures})"
        )
        if self._consecutiveFailures >= self._maxFailures:
            Logger.warning("MQTT health monitor forcing reconnect")
            try:
                self._client.reconnect()
                self._consecutiveFailures = 0
            except Exception as e:
                Logger.error(f"MQTT health monitor reconnect failed: {e}")

    def _handleSuccess(self):
        """Handle successful communication"""
        if self._consecutiveFailures > 0:
            Logger.info("MQTT communication restored")
        self._consecutiveFailures = 0

    def _check(self):
        if not self._client.is_connected():
            self._handleFailure("MQTT health monitor client disconnected")
            return

        # Use modulo to prevent numeric overflow on long-running service
        self._messageId = (self._messageId + 1) % (2**31)
        msgId = self._messageId
        self._outstandingMessages[msgId] = datetime.now()
        self._client.publish(f"{self._baseTopic}health/ping", str(msgId))

        # Check if we have too many unreceived messages
        unreceived = len(self._outstandingMessages)
        if unreceived >= self._maxFailures:
            self._handleFailure(f"MQTT health: {unreceived} messages unreceived")
        else:
            self._handleSuccess()

        self._cleanupOldMessages()
    