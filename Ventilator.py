from Mqtt import MqttPublisher, MqttSubscriber, IntComparer
from Timer import Timer
from EnvironmentMonitor import EnvironmentMonitor
from datetime import datetime

CO2_AVERAGE_TIME = 5
HUMIDITY_AVERAGE_TIME = 120


class DemandCalculator:
    _CO2_DEMAND_MAP = {400:0, 500:5, 600:20, 700:42, 800:55, 900:63, 1000:72, 1200:77, 1500:82, 2000:85}
    _HUMIDITY_DEMAND_MAP = {0:0, 1:0, 2:10, 3:45, 4:62, 5:73, 6:80, 7:85, 8:88, 9:90, 10:92, 15:95, 20:100}
    
    onDemandChanged = None
    _demands: dict
    demand = 0

    def __init__(self):
        self._demands = {}


    def updateCo2(self, co2):
        self._demands["co2"] = self._mapValue(co2, self._CO2_DEMAND_MAP)


    def updateHumidity(self, humidity, averageHumidity):
        diff = humidity - averageHumidity
        self._demands["humidity"] = self._mapValue(diff, self._HUMIDITY_DEMAND_MAP)
        self._updateDemand()


    def externalDemand(self, value, key=""):
        if value < 0:
            value = 0
        if value > 100:
            value = 100

        self._demands[f"external_{key}"] = value
        self._updateDemand()


    def _updateDemand(self):
        demand = 0
        for d in self._demands.values():
            d = max(d, demand)
        self.demand = demand

        if self.onDemandChanged is not None:
            self.onDemandChanged(demand)

    
    def _mapValue(value, map: dict):
        keys = list(map.keys())
        values = list(map.values())
        if value < keys[0]:
            return values[0]
        
        for n in range(1, len(keys)):
            k2 = keys[n]
            if (value < k2):
                k1 = keys[n-1]
                v1 = values[n-1]
                v2 = values[n]

                p = (value-k1)/(k2-k1)
                r = v1+((v2-v1)*p)
                return r

        return values[len(values)-1]



class ExternalDemand:
    _STATE_COUNT = 5
    _STATE_LEVELS = {'normal': 0, 'medium': 40, 'high': 75, 'max': 100 }
    _mqttPublisher: MqttPublisher
    _states = []
    
    onDemandChanged = None
    level = 0


    def __init__(self, mqttPublisher, mqttSubscriber, timer):
        self._mqttPublisher = mqttPublisher

        for i in range(0, ExternalDemand._STATE_COUNT-1):
            self._states[i] = "normal"
            mqttSubscriber.subscribe(f"state/demand/{i}/set", lambda v: self._mqttDemand(i, v))
        
        timer.add(self._publishAllStates, 60)
        self._demandChanged()
    
    
    def _mqttDemand(self, stateNr, value):
        if (stateNr < 0) or (stateNr >= ExternalDemand._STATE_COUNT):
            return
        
        value = value.lower()
        if not ExternalDemand._validateStateValue(value):
            return

        self._states[stateNr] = value
        self._publishState(stateNr)
        self._demandChanged()

    
    def _validateStateValue(value):
        for state in ExternalDemand._STATE_LEVELS.keys:
            if value == state:
                return True
        return False
    

    def _publishState(self, stateNr):
        state = self._states[stateNr]
        self._mqttPublisher.publish(f"state/demand/{stateNr}", state)
    

    def _publishAllStates(self):
        for i in range(0, ExternalDemand._STATE_COUNT-1):
            self._publishState(i)

    
    def _demandChanged(self):
        maxLevel = 0
        for s in self._states:
            l = ExternalDemand._STATE_LEVELS[s]
            maxLevel = max(l, maxLevel)
        self.level = maxLevel

        if self.onDemandChanged is not None:
            self.onDemandChanged(maxLevel)


class _Average:
    class _Sample:
        time: datetime
        value: float

    _timeRange: int
    _samples = []
    _totalValue = None

    def __init__(self, maxTimeRange):
        self._timeRange = maxTimeRange * 60


    @property
    def average(self):
        n = len(self._samples)
        if n == 0:
            return 0
        return self._totalValue / n
    

    def append(self, value):
        t = datetime.now()

        s = _Average._Sample()
        s.time = t
        s.value = value
        self._samples.append(s)

        if (self._totalValue is None):
            self._totalValue = value
        else:
            self._totalValue += value
        
        def firstSampleOutOfTimeRange():
            if len(self._samples) == 0:
                return False
            return (t - self._samples[0].time).total_seconds <= self._timeRange
                    
        while firstSampleOutOfTimeRange():
            s = self._samples[0]
            self._totalValue -= s.value
            self._samples.remove(s)



class VentilationController:
    _MQTT_LEVEL = "state/level"
    _MQTT_ITHO_LEVEL = "/itho/cmd"

    _mqttPublisher: MqttPublisher
    _demandCalculator: DemandCalculator
    _externalDemand: ExternalDemand
    _co2Average: _Average
    _humidityAverage: _Average


    def __init__(self, mqttPublisher, mqttSubscriber, environmentMonitor, timer):
        self._mqttPublisher = mqttPublisher
        self._demandCalculator = DemandCalculator()
        self._externalDemand = ExternalDemand(mqttPublisher, mqttSubscriber, timer)

        self._co2Average = _Average(CO2_AVERAGE_TIME)
        self._humidityAverage = _Average(HUMIDITY_AVERAGE_TIME)

        self._mqttPublisher.register(self._MQTT_LEVEL, IntComparer(5))
        self._mqttPublisher.register(self._MQTT_ITHO_LEVEL, IntComparer(5))

        environmentMonitor.onMeasurement = self._environmentMeasurement

        self._demandCalculator.onDemandChanged = self._demandChanged
        self._externalDemand.onDemandChanged = self._externalDemandChanged

    
    def _environmentMeasurement(self, env):
        self._co2Average.append(env.co2)
        self._humidityAverage.append(env.relativeHumidity)
        
        self._demandCalculator.updateCo2(self._co2Average.average)
        self._demandCalculator.updateHumidity(env.relativeHumidity, self._humidityAverage.average)


    def _demandChanged(self, demand):
        self._mqttPublisher.publish(self._MQTT_LEVEL, demand)

        ithoLevel = max((demand/100)*254, 254)
        self._mqttPublisher.publish(self._MQTT_ITHO_LEVEL, ithoLevel)


    def _externalDemandChanged(self, demand):
        self._demandCalculator.externalDemand(demand)