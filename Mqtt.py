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
    __mqtt: mqtt.Client
    _outstanding: dict
    _pingId: int
    _consecutiveFailures = 0
    _maxFailures = 3
    _pingInterval = 30
    _pingTimeout = 90
    _recentInFlight = 2
    _host: str
    _port: int
    _username: str
    _password: str

    def __init__(self, timer, mqtt, subscriber, host, port, username=None, password=None):
        self.__timer = timer
        self.__mqtt = mqtt
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._outstanding = {}
        self._pingId = 0

        subscriber.subscribe("health/echo", self._handleEcho)
        self._startEchoClient()

        timer.add(self._check, self._pingInterval)

    def _startEchoClient(self):
        # MQTT does not deliver a client's own publishes back to its subscriptions
        # (no loopback). To verify that subscriptions work, we use a second
        # lightweight client that simply echoes every ping back to the same topic.
        # When the main client receives the echo, both publish and subscribe
        # paths are confirmed working.
        self._echoClient = mqtt.Client()

        def on_echo(client, userdata, msg):
            client.publish("ventilation/health/echo", msg.payload)

        if self._username:
            self._echoClient.username_pw_set(self._username, self._password)
        self._echoClient.on_message = on_echo
        self._echoClient.connect(self._host, self._port)
        self._echoClient.subscribe("ventilation/health/echo")
        self._echoClient.loop_start()

    def _handleEcho(self, value):
        try:
            pingId = int(value)
            if pingId in self._outstanding:
                del self._outstanding[pingId]
        except ValueError:
            pass

    def _check(self):
        if not self._echoClient.is_connected():
            try:
                Logger.warning("MQTT echo client disconnected, reconnecting")
                self._echoClient.reconnect()
            except Exception as e:
                Logger.error(f"MQTT echo client reconnect failed: {e}")

        now = datetime.now()
        oldPings = [
            pid for pid, ts in self._outstanding.items()
            if (now - ts).total_seconds() > self._pingTimeout
        ]
        for pid in oldPings:
            Logger.warning(f"MQTT ping {pid} expired ({self._pingTimeout}s), discarding")
            del self._outstanding[pid]

        self._pingId += 1
        pingId = self._pingId
        self._outstanding[pingId] = now
        self.__mqtt.publish("ventilation/health/echo", str(pingId))

        outstandingCount = len(self._outstanding)
        unreturned = max(0, outstandingCount - self._recentInFlight)

        if unreturned > 0:
            self._consecutiveFailures += 1
            Logger.warning(
                f"MQTT subscription: {unreturned} pings unreturned "
                f"({self._consecutiveFailures}/{self._maxFailures})"
            )
            if self._consecutiveFailures >= self._maxFailures:
                Logger.warning("MQTT reconnecting after subscription ping failures")
                try:
                    self.__mqtt.reconnect()
                    self._consecutiveFailures = 0
                except Exception as e:
                    Logger.error(f"MQTT reconnect failed: {e}")
        else:
            if self._consecutiveFailures > 0:
                Logger.info("MQTT connection and subscriptions restored")
                try:
                    self.__mqtt.publish("ventilation/status", "online", retain=True)
                except Exception as e:
                    Logger.error(f"MQTT status publish failed: {e}")
            self._consecutiveFailures = 0
    