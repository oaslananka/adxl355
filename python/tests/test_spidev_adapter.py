"""Transport-level tests for the Linux spidev adapter."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from adxl355.adapters.spidev import SpiDevTransport


class FakeSpi:
    """Record complete xfer2 transactions and return queued responses."""

    def __init__(self, responses: list[list[int]] | None = None) -> None:
        self.max_speed_hz = 0
        self.mode = -1
        self.responses = list(responses or [])
        self.transfers: list[list[int]] = []
        self.closed = False
        self.opened: tuple[int, int] | None = None

    def open(self, bus: int, device: int) -> None:
        self.opened = (bus, device)

    def xfer2(self, payload: list[int]) -> list[int]:
        self.transfers.append(payload.copy())
        if self.responses:
            return self.responses.pop(0)
        return [0] * len(payload)

    def close(self) -> None:
        self.closed = True


class FaultySpi(FakeSpi):
    """Fake SPI device whose clock or mode assignment raises after open."""

    def __init__(self, fail_on: str) -> None:
        self._fail_on = fail_on
        self._max_speed_hz = 0
        self._mode = -1
        # FakeSpi.__init__ assigns speed/mode before ``opened`` exists.
        self.opened = None
        super().__init__()

    @property
    def max_speed_hz(self) -> int:
        return self._max_speed_hz

    @max_speed_hz.setter
    def max_speed_hz(self, value: int) -> None:
        if self._fail_on == "max_speed_hz" and self.opened is not None:
            raise OSError("injected clock configuration failure")
        self._max_speed_hz = value

    @property
    def mode(self) -> int:
        return self._mode

    @mode.setter
    def mode(self, value: int) -> None:
        if self._fail_on == "mode" and self.opened is not None:
            raise OSError("injected mode configuration failure")
        self._mode = value


def test_clock_configuration_failure_closes_new_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faulty = FaultySpi("max_speed_hz")
    monkeypatch.setitem(sys.modules, "spidev", SimpleNamespace(SpiDev=lambda: faulty))
    transport = SpiDevTransport(max_speed_hz=1_000_000)

    with pytest.raises(OSError, match="injected clock configuration failure"):
        transport.read_register(0x08, 1)

    assert faulty.opened == (0, 0)
    assert faulty.closed is True
    assert transport._spi is None


def test_mode_configuration_failure_closes_handle_and_retry_uses_new_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faulty = FaultySpi("mode")
    healthy = FakeSpi()
    devices = iter([faulty, healthy])
    monkeypatch.setitem(sys.modules, "spidev", SimpleNamespace(SpiDev=lambda: next(devices)))
    transport = SpiDevTransport()

    with pytest.raises(OSError, match="injected mode configuration failure"):
        _ = transport.mode

    assert faulty.opened == (0, 0)
    assert faulty.closed is True
    assert transport._spi is None

    # The next operation lazily opens a new SPI device and succeeds.
    payload = transport.read_register(0x08, 1)

    assert healthy.opened == (0, 0)
    assert healthy.mode == 0
    assert healthy.transfers == [[0x11, 0x00]]
    assert payload == bytes([0x00])
    assert not healthy.closed

    transport.close()
    assert healthy.closed is True


def test_read_register_uses_adxl355_command_and_single_transaction() -> None:
    fake = FakeSpi([[0x00, 0xAA, 0xBB, 0xCC]])
    transport = SpiDevTransport()
    transport._spi = fake

    payload = transport.read_register(0x08, 3)

    assert fake.transfers == [[0x11, 0x00, 0x00, 0x00]]
    assert payload == bytes([0xAA, 0xBB, 0xCC])


def test_write_register_uses_adxl355_command_and_single_transaction() -> None:
    fake = FakeSpi()
    transport = SpiDevTransport()
    transport._spi = fake

    transport.write_register(0x2D, bytes([0x12, 0x34]))

    assert fake.transfers == [[0x5A, 0x12, 0x34]]


def test_transport_exposes_verified_mode_and_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSpi()
    monkeypatch.setitem(sys.modules, "spidev", SimpleNamespace(SpiDev=lambda: fake))
    transport = SpiDevTransport(bus=2, device=1, max_speed_hz=2_000_000)

    assert transport.mode == 0
    assert transport.speed_hz == 2_000_000
    assert fake.opened == (2, 1)
