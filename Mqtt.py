from datetime import datetime
from Timer import Timer
import paho.mqtt.client as mqtt 
from ActionRunner import Runner as runner
from Logger import Logger
from Clock import Clock

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


def shouldPublish(dValue, dTime, publishInterval, forcePublishInterval):
    """Decision: should this topic be published right now?

    Locks the boolean logic in MqttConnection.__publishTopic. dTime is
    expressed in seconds (matching the original .seconds call site; Phase 8
    will change the source to use .total_seconds()).
    """
    return (dValue > 1) | \
           ((dValue > 0) & (dTime > publishInterval)) | \
           (dTime > forcePublishInterval)


class _PublishTopic:
    topic: str
    comparer: BaseComparer
    lastPublishedValue: int
    lastPublishTime: any
    currentValue: int


class _MqttSubscription:
    topic: str
    callback: any
    paramType: any


class MqttConnection:
    __client: mqtt.Client
    __timer: Timer
    __host: str
    __port: int
    __username: str
    __password: str
    __baseTopic: str
    __publishTopics: list
    __subscriptions: list
    __connectCallbacks: list
    __outstandingPings: dict
    __messageId: int
    __lastSuccessfulCommunication: datetime
    __failureThreshold: int
    __publishInterval = 10
    __forcePublishInterval = 60
    __pingInterval = 30

    def __init__(self, timer, host, port, username=None, password=None, baseTopic="", failureThreshold=900, clientFactory=None):
        self.__timer = timer
        self.__host = host
        self.__port = port
        self.__username = username
        self.__password = password
        self.__baseTopic = baseTopic
        if len(self.__baseTopic) > 0:
            self.__baseTopic += "/"
        self.__failureThreshold = failureThreshold
        self.__clientFactory = clientFactory
        self.__client = None
        self.__publishTopics = []
        self.__subscriptions = []
        self.__connectCallbacks = []
        self.__outstandingPings = {}
        self.__messageId = 0
        self.__lastSuccessfulCommunication = Clock.now()
        self.__createClient()
        self.subscribe("health/ping", self.__onHealthPing)
        timer.add(self.__publishLoop, 1)
        timer.add(self.__healthCheck, self.__pingInterval)

    def __createClient(self):
        if self.__client is not None:
            try:
                self.__client.disconnect()
                self.__client.loop_stop()
            except Exception:
                pass

        factory = self.__clientFactory if self.__clientFactory is not None else lambda: mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        client = factory()
        if self.__username:
            client.username_pw_set(self.__username, self.__password)
        client.reconnect_delay_set(min_delay=1, max_delay=120)
        client.will_set(f"{self.__baseTopic}status", "offline", retain=True)
        client.on_connect = self.__on_connect
        client.on_disconnect = self.__on_disconnect
        client.on_message = self.__on_message
        client.on_pre_connect = lambda c, u: ()
        try:
            client.connect(self.__host, self.__port)
            client.loop_start()
        except Exception as e:
            Logger.fault("mqtt", f"MQTT client connect failed: {e}")
        # Always assign so paho's reconnect loop owns the client even on initial failure
        self.__client = client

    def __on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.__lastSuccessfulCommunication = Clock.now()
            Logger.recovery("mqtt", "MQTT connected success")
            client.publish(f"{self.__baseTopic}status", "online", retain=True)
            for s in self.__subscriptions:
                Logger.info(f"Re-subscribing to {s.topic}")
                client.subscribe(s.topic)
            for cb in self.__connectCallbacks:
                self.__timer.execute(cb)
        else:
            Logger.fault("mqtt", f"MQTT connected failed with code {rc}")

    def __on_disconnect(self, client, userdata, rc):
        Logger.fault("mqtt", f"MQTT disconnected (rc={rc})")

    def __on_message(self, client, userdata, msg):
        topic = msg.topic
        value = msg.payload.decode()

        subscription = self.__getSubscription(topic)
        if subscription is None:
            return

        self.__lastSuccessfulCommunication = Clock.now()
        h = lambda: self.__handle(subscription, value)
        self.__timer.execute(h)

    def __handle(self, subscription, value):
        if subscription.paramType == int:
            value = int(value)

        runner.execute(subscription.callback, value)

    def __getSubscription(self, topic):
        for s in self.__subscriptions:
            if s.topic == topic:
                return s
        return None

    def __getPublishTopic(self, topic):
        for t in self.__publishTopics:
            if t.topic == topic:
                return t

        t = _PublishTopic()
        t.topic = topic
        t.comparer = BaseComparer()
        t.lastPublishedValue = None
        t.lastPublishTime = Clock.now()
        t.currentValue = None
        self.__publishTopics.append(t)
        return t

    def publish(self, topic, value):
        if topic.startswith("/"):
            fullTopic = topic[1:]
        else:
            fullTopic = self.__baseTopic + topic

        self.__client.publish(fullTopic, value)

    def publishState(self, topic, value):
        t = self.__getPublishTopic(topic)
        t.currentValue = value

    def register(self, topic, comparer=None):
        if comparer is None:
            comparer = BaseComparer()
        t = self.__getPublishTopic(topic)
        t.comparer = comparer
        self.__timer.execute(lambda: self.__publishTopic(t))

    def subscribe(self, topic, callback, paramType=None):
        if topic.startswith("/"):
            fullTopic = topic[1:]
        else:
            fullTopic = self.__baseTopic + topic

        s = self.__getSubscription(fullTopic)
        if s is None:
            s = _MqttSubscription()
            self.__subscriptions.append(s)

        s.topic = fullTopic
        s.callback = callback
        s.paramType = paramType

        self.__client.subscribe(fullTopic)

    def addConnectCallback(self, fn):
        self.__connectCallbacks.append(fn)

    def __publishLoop(self):
        time = Clock.now()

        for topic in self.__publishTopics:
            self.__publishTopic(topic)

    def __publishTopic(self, topic):
        time = Clock.now()

        if topic.currentValue is None:
            return

        dValue = topic.comparer.compare(topic.lastPublishedValue, topic.currentValue)
        dTime = (time - topic.lastPublishTime).total_seconds()
        if shouldPublish(dValue, dTime, self.__publishInterval, self.__forcePublishInterval):
            self.publish(topic.topic, topic.currentValue)
            topic.lastPublishedValue = topic.currentValue
            topic.lastPublishTime = time

    def __healthCheck(self):
        elapsed = (Clock.now() - self.__lastSuccessfulCommunication).total_seconds()
        if elapsed > self.__failureThreshold:
            Logger.fault("mqtt", f"MQTT no communication for {elapsed:.0f}s, forcing reset")
            self.__aggressiveReset()
            return

        if not self.__client.is_connected():
            Logger.fault("mqtt", "MQTT health check: client disconnected")
            return

        self.__messageId = (self.__messageId + 1) % (2**31)
        msgId = self.__messageId
        self.__outstandingPings[msgId] = Clock.now()
        self.__client.publish(f"{self.__baseTopic}health/ping", str(msgId))

    def __onHealthPing(self, value):
        try:
            msgId = int(value)
            if msgId in self.__outstandingPings:
                del self.__outstandingPings[msgId]
            self.__lastSuccessfulCommunication = Clock.now()
        except (ValueError, TypeError):
            pass

    def __aggressiveReset(self):
        Logger.warning("MQTT aggressive reset")
        self.__outstandingPings.clear()
        self.__createClient()
        # Re-subscription and connect-callback firing happen asynchronously
        # via __on_connect when the new client connects — do not duplicate here.
        self.__lastSuccessfulCommunication = Clock.now()
