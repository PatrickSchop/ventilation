"""Fake smbus2 module for tests on non-Linux dev machines.

Mirrors the surface used in Scd41.py:
  - SMBus(bus): context manager + .i2c_rdwr(msg)
  - i2c_msg.write(address, payload)   (write direction)
  - i2c_msg.read(address, length)     (read direction)

In real smbus2, `i2c_msg.write` and `i2c_msg.read` are *different* classes
distinguishable by `isinstance`; this stub preserves that so callers' type
checks keep working.
"""

from collections import deque


class _I2cMsgBase:
    def __init__(self, address):
        self._address = address
        self._payload = bytearray()

    def __len__(self):
        return len(self._payload)

    def __getitem__(self, key):
        return self._payload[key]

    def __iter__(self):
        return iter(self._payload)

    def __eq__(self, other):
        return type(self) is type(other) and bytes(self._payload) == bytes(other._payload)


class _WriteI2cMsg(_I2cMsgBase):
    def __init__(self, address, payload):
        super().__init__(address)
        if isinstance(payload, (bytes, bytearray)):
            self._payload = bytearray(payload)
        else:
            self._payload = bytearray(payload)


class _ReadI2cMsg(_I2cMsgBase):
    def __init__(self, address, length):
        super().__init__(address)
        self._length = length
        self._payload = bytearray(length)

    def __len__(self):
        return self._length


class _FakeSMBus:
    def __init__(self, bus):
        self._bus = bus
        self.writes = []   # list of (address, bytes) write payloads
        self.reads = []    # list of (address, length) read requests
        self._read_queue = deque()  # queued byte payloads to return on next read

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def queue_read(self, payload):
        """Schedule a payload (bytes/bytearray/list of ints) for the next i2c_rdwr that includes a read msg."""
        self._read_queue.append(bytearray(payload))

    def i2c_rdwr(self, *msgs):
        for m in msgs:
            if isinstance(m, _WriteI2cMsg):
                self.writes.append((m._address, bytes(m._payload)))
            elif isinstance(m, _ReadI2cMsg):
                self.reads.append((m._address, len(m)))
                if self._read_queue:
                    data = self._read_queue.popleft()
                    needed = len(m)
                    if len(data) < needed:
                        data.extend([0x00] * (needed - len(data)))
                    m._payload = bytearray(data[:needed])
                # else: leave zero-filled
            else:
                raise TypeError(f"Unexpected i2c_msg type: {type(m).__name__}")


# Module-level surface matching the real smbus2.
def i2c_msg_write(address, payload):
    return _WriteI2cMsg(address, payload)


def i2c_msg_read(address, length):
    return _ReadI2cMsg(address, length)


SMBus = _FakeSMBus

# `i2c_msg` is a module alias in real smbus2; expose it as a module-like object
# that callers can use as `i2c_msg.write(...)` / `i2c_msg.read(...)`.
import types
i2c_msg = types.SimpleNamespace(write=i2c_msg_write, read=i2c_msg_read)
