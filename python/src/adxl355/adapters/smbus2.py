"""
Linux I2C adapter using the smbus2 package.

Requires:
    pip install adxl355[i2c]

Usage:
    from adxl355.adapters.smbus2 import Smbus2Transport
    transport = Smbus2Transport(bus=1, address=0x1D)
"""

from __future__ import annotations

import importlib
import time
from typing import Callable, Optional, Protocol, cast

from adxl355.transport import Transport


class _SMBus(Protocol):
    """Subset of ``smbus2.SMBus`` required by this adapter."""

    def read_byte_data(self, address: int, reg: int) -> int: ...

    def read_i2c_block_data(self, address: int, reg: int, length: int) -> list[int]: ...

    def write_byte_data(self, address: int, reg: int, value: int) -> None: ...

    def write_i2c_block_data(self, address: int, reg: int, data: list[int]) -> None: ...

    def close(self) -> None: ...


class Smbus2Transport(Transport):
    """
    I2C transport for ADXL355 using smbus2.

    The ADXL355 uses auto-increment addressing: reading from a register
    returns that register and then advances to the next address.
    """

    def __init__(
        self,
        bus: int = 1,
        address: int = 0x1D,
    ) -> None:
        self._bus = bus
        self._address = address
        self._i2c: Optional[_SMBus] = None

    def _ensure_open(self) -> _SMBus:
        if self._i2c is None:
            module = importlib.import_module("smbus2")
            factory = cast(Callable[[int], _SMBus], getattr(module, "SMBus"))
            self._i2c = factory(self._bus)
        return self._i2c

    def read_register(self, reg: int, length: int = 1) -> bytes:
        i2c = self._ensure_open()
        if length == 1:
            val = i2c.read_byte_data(self._address, reg)
            return bytes([val])
        else:
            # smbus2 supports block reads via read_i2c_block_data.
            # The ADXL355 auto-increments after the first byte.
            block = i2c.read_i2c_block_data(self._address, reg, length)
            return bytes(block[:length])

    def write_register(self, reg: int, data: bytes) -> None:
        i2c = self._ensure_open()
        if len(data) == 1:
            i2c.write_byte_data(self._address, reg, data[0])
        else:
            i2c.write_i2c_block_data(self._address, reg, list(data))

    def delay_ms(self, ms: int) -> None:
        time.sleep(ms / 1000.0)

    def close(self) -> None:
        if self._i2c is not None:
            self._i2c.close()
            self._i2c = None
