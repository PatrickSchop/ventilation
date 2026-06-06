import struct
import time
from datetime import datetime, timedelta
from Timer import Timer
from Logger import Logger

from smbus2 import SMBus, i2c_msg

SOFT_RESET = 0x3646
FACTORY_RESET = 0x3632
FORCE_RECALIBRATION = 0x362F
SELF_TEST = 0x3639
DATA_READY = 0xE4B8
STOP_PERIODIC_MEASUREMENT = 0x3F86
START_PERIODIC_MEASUREMENT = 0x21B1
START_LOW_POWER_PERIODIC_MEASUREMENT = 0x21AC
READ_MEASUREMENT = 0xEC05
SERIAL_NUMBER = 0x3682
GET_TEMP_OFFSET = 0x2318
SET_TEMP_OFFSET = 0x241D
GET_ALTITUDE = 0x2322
SET_ALTITUDE = 0x2427
SET_PRESSURE = 0xE000
PERSIST_SETTINGS = 0x3615
GET_ASCE = 0x2313
SET_ASCE = 0x2416

DEFAULT_I2C_ADDRESS = 0x62


class Scd41:
    _address: int
    _timer: Timer
    _bus: SMBus

    def __init__(self, timer, address=None, bus=None):
        self._timer = timer

        if address is None:
            address = DEFAULT_I2C_ADDRESS
        self._address = address

        self._bus = bus if bus is not None else SMBus(1)
    
    def onDataReady(self, onDataReady):
        def handle(response):
            dataReady = (response & 0x07FF) != 0
            if dataReady:
                self._timer.execute(onDataReady)

        self._rdwr(DATA_READY, response_length=1, delay=1, handler=handle)


    def measure(self, onMeasurement):
        def handle(measurement):
            co2 = measurement[0]
            temperature = round(-45 + 175.0 * measurement[1] / (1 << 16), 1)
            relativeHumidity = round(100.0 * measurement[2] / (1 << 16), 1)
            onMeasurement(co2, temperature, relativeHumidity)

        response = self._rdwr(READ_MEASUREMENT, response_length=3, delay=1, handler=handle)


    def startPeriodicMeasurement(self, low_power=False):
        self._rdwr(START_PERIODIC_MEASUREMENT)


    def stopPeriodicMeasurement(self):
        self._rdwr(STOP_PERIODIC_MEASUREMENT)


    def reset(self):
        self._rdwr(SOFT_RESET)


    def _rdwr(self, command, value=None, response_length=0, delay=0, handler=None):
        if value is not None:
            msg_w = i2c_msg.write(
                self._address, struct.pack(">HHB", command, value, self.crc8(value))
            )
        else:
            msg_w = i2c_msg.write(self._address, struct.pack(">H", command))

        try:
            self._bus.i2c_rdwr(msg_w)
        except OSError as e:
            Logger.error(f"SCD41 I2C write failed: {e}")

        if (handler is not None) or (response_length > 0):
            self._timer.execute(lambda: self._handleRdwrResponse(response_length, handler), delay=delay)


    def _handleRdwrResponse(self, response_length, handler):
        data = self._readRdwrResponse(response_length)

        if (handler is not None):
            if response_length > 0:
                self._timer.execute(handler, parameters=[data])
            else:
                self._timer.execute(handler)


    def _readRdwrResponse(self, response_length):
        response_length *= 3

        if response_length > 0:
            msg_r = i2c_msg.read(self._address, response_length)
            try:
                self._bus.i2c_rdwr(msg_r)
            except OSError as e:
                Logger.error(f"SCD41 I2C read failed: {e}")
                return []

            result = list(msg_r)
            data = []
            for chunk in range(0, len(result), 3):
                if self._crc8(result[chunk : chunk + 2]) != result[chunk + 2]:
                    raise ValueError("SCD41: Invalid CRC8 in response.")
                data.append((result[chunk] << 8) | result[chunk + 1])
            if len(data) == 1:
                return data[0]
            else:
                return data

        return []
    
    def _crc8(self, data, polynomial=0x31):
        if isinstance(data, int):
            data = [(data >> 8) & 0xFF, data & 0xFF]
        result = 0xFF
        for byte in data:
            result ^= byte
            for bit in range(8):
                if result & 0x80:
                    result <<= 1
                    result ^= polynomial
                else:
                    result <<= 1
        return result & 0xFF
    