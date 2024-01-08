from Mqtt import MqttPublisher, MqttSubscriber, IntComparer
from Timer import Timer
from EnvironmentMonitor import EnvironmentMonitor
from datetime import datetime
from Configuration import Configuration


CO2_AVERAGE_TIME = 5
HUMIDITY_AVERAGE_TIME = 240
HUMIDITY_RELIABLE_TIME = 5


class DemandCalculator:
    _CO2_DEMAND_MAP = {400:0, 500:1, 600:5, 700:20, 800:45, 900:63, 1000:72, 1200:77, 1500:82, 2000:85}
    _HUMIDITY_DEMAND_MAP = {0:0, 1:0, 2:10, 3:45, 4:62, 5:73, 6:80, 7:85, 8:88, 9:90, 10:92, 15:95, 20:100}
    
    onDemandChanged = None
    _demands: dict
    demand = 0

    def __init__(self):
        self._demands = {}


    def updateCo2(self, co2):
        print(f"CO2: {co2}")
        self._demands["co2"] = self._mapValue(co2, self._CO2_DEMAND_MAP)
        self._updateDemand()


    def updateHumidity(self, humidity, averageHumidity):
        print(f"Humidity: {humidity}, average: {averageHumidity}")
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
        print(f"Ventilation demand:{self._demands}")
        demand = 0
        for d in self._demands.values():
            demand = max(d, demand)
        self.demand = demand

        if self.onDemandChanged is not None:
            self.onDemandChanged(demand)

    
    def _mapValue(self, value, map: dict):
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
    _mqttPublisher: MqttPublisher
    _states = []
    
    onDemandChanged = None
    level = 0


    def __init__(self, mqttPublisher, mqttSubscriber, timer):
        self._mqttPublisher = mqttPublisher

        self._stateButtonCount = Configuration.getValue("ventilation.stateButtons.count")
        self._stateLevels = {"normal": 0, "medium": Configuration.getValue("ventilation.stateButtons.medium"), "high": Configuration.getValue("ventilation.stateButtons.high"), "max": 100}

        for i in range(0, self._stateButtonCount):
            self._states.append("normal")
            mqttSubscriber.subscribe(f"state/demand/{i}/set", lambda v: self._mqttDemand(i, v))
        
        timer.add(self._publishAllStates, 60)
        self._demandChanged()
    

    def setupConfiguration(config):
        config.addElementGroup("stateButtons") \
            .addElement("count", defaultValue=1) \
            .addElement("medium", defaultValue=40) \
            .addElement("high", defaultValue=75)
    

    def _mqttDemand(self, stateNr, value):
        if (stateNr < 0) or (stateNr >= self._stateButtonCount):
            return
        
        value = value.lower()
        if not self._validateStateValue(value):
            return

        self._states[stateNr] = value
        self._publishState(stateNr)
        self._demandChanged()

    
    def _validateStateValue(self, value):
        for state in self._stateLevels.keys():
            if value == state:
                return True
        return False
    

    def _publishState(self, stateNr):
        state = self._states[stateNr]
        self._mqttPublisher.publishState(f"state/demand/{stateNr}", state)
    

    def _publishAllStates(self):
        for i in range(0, self._stateButtonCount):
            self._publishState(i)

    
    def _demandChanged(self):
        maxLevel = 0
        for s in self._states:
            l = self._stateLevels[s]
            maxLevel = max(l, maxLevel)
        self.level = maxLevel

        if self.onDemandChanged is not None:
            self.onDemandChanged(maxLevel)


class _Average:
    class _Sample:
        time: datetime
        value: float

    _timeRange: int
    _minreliableTime: int
    _samples: list
    _totalValue: float

    def __init__(self, maxTimeRange, minReliableTime=None):
        self._timeRange = maxTimeRange * 60
        if minReliableTime is None:
            self._minReliableTime = self._timeRange / 10
        else:
            self._minReliableTime = minReliableTime * 60
    
        self._samples = []
        self._totalValue = None


    @property
    def average(self):
        n = len(self._samples)
        if n == 0:
            return 0
        return self._totalValue / n
    
    @property
    def reliable(self):
        self._checkLastSampleCurrent()
            
        if len(self._samples) < 2:
            print("Average unreliable: not enough samples")
            return False

        reliable = (datetime.now() - self._samples[0].time).total_seconds() > self._minReliableTime
        if not reliable:
            print(f"Average unreliable: current time: {datetime.now()}  first sample time: {self._samples[0].time}  min reliable time: {self._minReliableTime}")

        return reliable
    

    def append(self, value):
        t = datetime.now()

        self._checkLastSampleCurrent()

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
            return (t - self._samples[0].time).total_seconds() > self._timeRange

        while firstSampleOutOfTimeRange():
            s = self._samples[0]
            self._totalValue -= s.value
            self._samples.remove(s)
    

    def _checkLastSampleCurrent(self):
        if len(self._samples) > 0:
            lastSample = self._samples[-1]
            if (datetime.now() - lastSample.time).total_seconds() > self._minReliableTime:
                print(f"Last sample too old. Discarding samples. count: {len(self._samples)} last sample time: {lastSample.time}  min reliable time: {self._minReliableTime}")
                self._samples.clear()



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
        self._humidityAverage = _Average(HUMIDITY_AVERAGE_TIME, HUMIDITY_RELIABLE_TIME)

        self._mqttPublisher.register(self._MQTT_LEVEL, IntComparer(5))
        self._mqttPublisher.register(self._MQTT_ITHO_LEVEL, IntComparer(5))

        environmentMonitor.onMeasurement = self._environmentMeasurement

        self._demandCalculator.onDemandChanged = self._demandChanged
        self._externalDemand.onDemandChanged = self._externalDemandChanged


    def setupConfiguration():
        ventilation = Configuration.addElementGroup("ventilation")
        ExternalDemand.setupConfiguration(ventilation)

    
    def _environmentMeasurement(self, env):
        self._co2Average.append(env.co2)
        self._humidityAverage.append(env.relativeHumidity)
        
        if self._co2Average.reliable:
            self._demandCalculator.updateCo2(self._co2Average.average)
        
        if self._humidityAverage.reliable:
            self._demandCalculator.updateHumidity(env.relativeHumidity, self._humidityAverage.average)


    def _demandChanged(self, demand):
        demand = int(demand)
        self._mqttPublisher.publishState(self._MQTT_LEVEL, demand)

        ithoLevel = int(min((demand/100)*254, 254))
        self._mqttPublisher.publishState(self._MQTT_ITHO_LEVEL, ithoLevel)

        print(f"Current demand: {demand} Itho: {ithoLevel}")

    def _externalDemandChanged(self, demand):
        self._demandCalculator.externalDemand(demand)