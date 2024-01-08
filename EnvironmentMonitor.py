from Scd41 import Scd41
from Timer import Timer
from Mqtt import MqttPublisher
from datetime import datetime

class Environment:
    co2: int
    temperature: float
    relativeHumidity: float


class EnvironmentMonitor:
    _scd41: Scd41
    _timer: Timer
    _mqttPublisher: MqttPublisher
    _lastMeasurement: datetime
    onMeasurement: any

    def __init__(self, timer, mqttPublisher):
        self._timer = timer
        self._mqttPublisher = mqttPublisher
        self._scd41 = Scd41(timer)
        self._lastMeasurement = datetime.now()
        self.onMeasurement = None

        self._resetScd41()
        timer.add(self._readData, 10)
   

    def _readData(self):
        if (datetime.now() - self._lastMeasurement).total_seconds() > 600:
            self._resetScd41(soft = True)

        def onDataReady():
            self._scd41.measure(self._onMeasurement)

        self._scd41.onDataReady(onDataReady)


    def _onMeasurement(self, co2, temperature, relativeHumidity):
        self._lastMeasurement = datetime.now()
        json = "{" + \
            f"\"co2\":{co2}, " + \
            f"\"temperature\":{temperature}, " + \
            f"\"relativeHumidity\":{relativeHumidity} " + \
            "}"
        
        self._mqttPublisher.publishState("environment", json)

        if self.onMeasurement is not None:
            env = Environment()
            env.co2 = co2
            env.temperature = temperature
            env.relativeHumidity = relativeHumidity
            self.onMeasurement(env)


    def _resetScd41(self, soft=False):
        self._scd41.stopPeriodicMeasurement()
        if not soft:
            self._timer.execute(self._scd41.reset, delay=0.2)        
        self._timer.execute(self._scd41.startPeriodicMeasurement, delay=120)


class FakeEnvironmentMonitor():
    def __init__(self):
        self.onMeasurement = None
