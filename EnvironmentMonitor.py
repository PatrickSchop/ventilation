from Scd41 import Scd41
from Timer import Timer
from Mqtt import MqttConnection
from datetime import datetime
from Logger import Logger
from Clock import Clock

FLAT_LINE_TIMEOUT = 900
ERROR_SOFT_RESET_THRESHOLD = 3
ERROR_HARD_RESET_THRESHOLD = 10
STALE_MEASUREMENT_TIMEOUT = 60
HEALTH_CHECK_INTERVAL = 30

class Environment:
    co2: int
    temperature: float
    relativeHumidity: float


class EnvironmentMonitor:
    _scd41: Scd41
    _timer: Timer
    _mqtt: MqttConnection
    _lastMeasurement: datetime
    onMeasurement: any

    _lastCo2: int
    _co2FlatSince: datetime
    _consecutiveErrors: int

    def __init__(self, timer, mqtt):
        self._timer = timer
        self._mqtt = mqtt
        self._scd41 = Scd41(timer)
        self._lastMeasurement = Clock.now()
        self.onMeasurement = None

        self._lastCo2 = None
        self._co2FlatSince = None
        self._consecutiveErrors = 0

        self._resetScd41()
        timer.add(self._readData, 10)
        timer.add(self._healthCheck, HEALTH_CHECK_INTERVAL)


    def _readData(self):
        if (Clock.now() - self._lastMeasurement).total_seconds() > 600:
            Logger.warning("No measurement for 10 min, soft resetting sensor")
            self._resetScd41(soft = True)

        def onDataReady():
            self._scd41.measure(self._onMeasurement)

        self._scd41.onDataReady(onDataReady)


    def _onMeasurement(self, co2, temperature, relativeHumidity):
        self._consecutiveErrors = 0
        self._lastMeasurement = Clock.now()

        if self._lastCo2 is not None and co2 == self._lastCo2:
            if self._co2FlatSince is None:
                self._co2FlatSince = Clock.now()
                Logger.warning("CO2 flat-line detected, monitoring for 15 min threshold")
        else:
            self._co2FlatSince = None

        self._lastCo2 = co2

        json = "{" + \
            f"\"co2\":{co2}, " + \
            f"\"temperature\":{temperature}, " + \
            f"\"relativeHumidity\":{relativeHumidity} " + \
            "}"
        
        self._mqtt.publishState("environment", json)

        if self.onMeasurement is not None:
            env = Environment()
            env.co2 = co2
            env.temperature = temperature
            env.relativeHumidity = relativeHumidity
            self.onMeasurement(env)


    def _healthCheck(self):
        now = Clock.now()

        secondsSinceLastMeasurement = (now - self._lastMeasurement).total_seconds()
        if secondsSinceLastMeasurement > STALE_MEASUREMENT_TIMEOUT:
            self._consecutiveErrors += 1
            Logger.warning(
                f"Stale measurement ({secondsSinceLastMeasurement:.0f}s), "
                f"consecutive errors: {self._consecutiveErrors}"
            )

        if self._consecutiveErrors >= ERROR_HARD_RESET_THRESHOLD:
            Logger.warning(f"Hard resetting sensor after {self._consecutiveErrors} consecutive errors")
            self._consecutiveErrors = 0
            self._resetScd41(soft=False)
        elif self._consecutiveErrors >= ERROR_SOFT_RESET_THRESHOLD:
            Logger.warning(f"Soft resetting sensor after {self._consecutiveErrors} consecutive errors")
            self._resetScd41(soft=True)
            self._consecutiveErrors = 0

        if self._co2FlatSince is not None:
            flatDuration = (now - self._co2FlatSince).total_seconds()
            if flatDuration > FLAT_LINE_TIMEOUT:
                Logger.warning(f"CO2 flat-line for {flatDuration:.0f}s, soft resetting sensor")
                self._co2FlatSince = None
                self._resetScd41(soft=True)


    def _resetScd41(self, soft=False):
        Logger.info(f"Sensor reset (soft={soft})")
        self._scd41.stopPeriodicMeasurement()
        if not soft:
            self._timer.execute(self._scd41.reset, delay=0.2)
        self._timer.execute(self._scd41.startPeriodicMeasurement, delay=120)


class FakeEnvironmentMonitor():
    def __init__(self):
        self.onMeasurement = None
