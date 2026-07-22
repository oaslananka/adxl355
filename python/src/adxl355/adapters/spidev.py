"""
Linux SPI adapter using the spidev package.

The ADXL355 uses SPI Mode 0 (CPOL=0, CPHA=0). Command and data bytes are
transferred in one ``xfer2`` call so chip select remains asserted throughout.

Requires:
    pip install adxl355[spi]

Usage:
    from adxl355.adapters.spidev import SpiDevTransport
    transport = SpiDevTransport(bus=0, device=0, max_speed_hz=1000000)
"""

from __future__ import annotations

import time
from typing import Optional, Protocol, cast

from adxl355.registers import spi_read_cmd, spi_write_cmd
from adxl355.transport import Transport


class _SpiDevice(Protocol):
    """Subset of ``spidev.SpiDev`` used by the transport."""

    max_speed_hz: int
    mode: int

    def open(self, bus: int, device: int) -> None: ...

    def xfer2(self, payload: list[int]) -> list[int]: ...

    def close(self) -> None: ...


class SpiDevTransport(Transport):
    """
    SPI transport for ADXL355 using spidev.
    """

    def __init__(
        self,
        bus: int = 0,
        device: int = 0,
        max_speed_hz: int = 1_000_000,
    ) -> None:
        self._bus = bus
        self._device = device
        self._max_speed_hz = max_speed_hz
        self._spi: Optional[_SpiDevice] = None

    def _ensure_open(self) -> _SpiDevice:
        if self._spi is None:
            import spidev  # type: ignore[import-not-found]

            spi = cast(_SpiDevice, spidev.SpiDev())
            spi.open(self._bus, self._device)
            spi.max_speed_hz = self._max_speed_hz
            spi.mode = 0  # CPOL=0, CPHA=0
            self._spi = spi
        return self._spi

    def read_register(self, reg: int, length: int = 1) -> bytes:
        spi = self._ensure_open()
        # ADXL355 command byte: address in bits 7:1, read flag in bit 0.
        header = bytes([spi_read_cmd(reg)])
        dummy = bytes([0x00]) * length
        result = spi.xfer2(list(header + dummy))
        return bytes(result[1:])

    def write_register(self, reg: int, data: bytes) -> None:
        spi = self._ensure_open()
        # ADXL355 command byte: address in bits 7:1, write flag in bit 0.
        header = bytes([spi_write_cmd(reg)])
        payload = list(header + data)
        spi.xfer2(payload)

    def delay_ms(self, ms: int) -> None:
        time.sleep(ms / 1000.0)

    def close(self) -> None:
        if self._spi is not None:
            self._spi.close()
            self._spi = None
