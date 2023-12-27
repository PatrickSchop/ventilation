from Scd41 import Scd41
from Timer import Timer
from Mqtt import MqttPublisher

class Environment:
    co2: int
    temperature: float
    relativeHumidity: float


class EnvironmentMonitor:
    _scd41: Scd41
    _timer: Timer
    _mqttPublisher: MqttPublisher
    onMeasurement: any

    def __init__(self, timer, mqttPublisher):
        self._timer = timer
        self._mqttPublisher = mqttPublisher
        self._scd41 = Scd41(timer)
        self.onMeasurement = None

        self._resetScd41()
        timer.add(self._readData, 10)
        timer.add(self._resetScd41, 60*60)

    

    def _readData(self):
        def onDataReady():
            self._scd41.measure(self._onMeasurement)

        self._scd41.onDataReady(onDataReady)


    def _onMeasurement(self, co2, temperature, relativeHumidity):
        json = "{" + \
            f"\"co2\":{co2}, " + \
            f"\"temperature\":{temperature}, " + \
            f"\"relativeHumidity\":{relativeHumidity} " + \
            "}"
        
        self._mqttPublisher.publish("environment", json)


    def _resetScd41(self):
        self._scd41.stopPeriodicMeasurement()
        self._timer.execute(self._scd41.reset, delay=0.2)        
        self._timer.execute(self._scd41.startPeriodicMeasurement, delay=1)
