"""Transport-level tests for the Linux spidev adapter."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import pytest

from adxl355.adapters.spidev import SpiDevTransport
from adxl355.errors import BusError


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


class TestSpiStartupCleanup(TestCase):
    """Failure injection ensures a newly opened SPI handle is always released."""

    def test_clock_configuration_failure_closes_new_handle(self) -> None:
        faulty = FaultySpi("max_speed_hz")
        with patch.dict(sys.modules, {"spidev": SimpleNamespace(SpiDev=lambda: faulty)}):
            transport = SpiDevTransport(max_speed_hz=1_000_000)
            with self.assertRaisesRegex(OSError, "injected clock configuration failure"):
                transport.read_register(0x08, 1)

        self.assertEqual(faulty.opened, (0, 0))
        self.assertTrue(faulty.closed)
        self.assertIsNone(transport._spi)

    def test_mode_configuration_failure_closes_handle_and_retry_uses_new_device(self) -> None:
        faulty = FaultySpi("mode")
        healthy = FakeSpi()
        devices = iter([faulty, healthy])
        with patch.dict(sys.modules, {"spidev": SimpleNamespace(SpiDev=lambda: next(devices))}):
            transport = SpiDevTransport()
            with self.assertRaisesRegex(OSError, "injected mode configuration failure"):
                _ = transport.mode

            self.assertEqual(faulty.opened, (0, 0))
            self.assertTrue(faulty.closed)
            self.assertIsNone(transport._spi)

            # A new device opens successfully on retry.
            payload = transport.read_register(0x08, 1)
            self.assertEqual(healthy.opened, (0, 0))
            self.assertEqual(healthy.mode, 0)
            self.assertEqual(healthy.transfers, [[0x11, 0x00]])
            self.assertEqual(payload, bytes([0x00]))
            self.assertFalse(healthy.closed)
            transport.close()
            self.assertTrue(healthy.closed)

    def test_close_before_first_open_does_not_allocate_spi(self) -> None:
        """Closing an unused transport must not initialize SPI hardware."""
        factory = Mock()
        with patch.dict(sys.modules, {"spidev": SimpleNamespace(SpiDev=factory)}):
            transport = SpiDevTransport()
            transport.close()
            self.assertEqual(factory.call_count, 0)
            self.assertIsNone(transport._spi)

    def test_close_only_once_after_successful_open(self) -> None:
        """Closing twice must not touch an already released Linux SPI handle."""
        fake = FakeSpi()
        with patch.dict(sys.modules, {"spidev": SimpleNamespace(SpiDev=lambda: fake)}):
            transport = SpiDevTransport()
            self.assertEqual(transport.mode, 0)
            with patch.object(fake, "close", wraps=fake.close) as close_spy:
                transport.close()
                transport.close()
                self.assertEqual(close_spy.call_count, 1)
                self.assertIsNone(transport._spi)



def test_read_register_uses_adxl355_command_and_single_transaction() -> None:
    fake = FakeSpi([[0x00, 0xAA, 0xBB, 0xCC]])
    transport = SpiDevTransport()
    transport._spi = fake

    payload = transport.read_register(0x08, 3)

    assert fake.transfers == [[0x11, 0x00, 0x00, 0x00]]
    assert payload == bytes([0xAA, 0xBB, 0xCC])


def test_read_register_accepts_exactly_sized_spi_frame() -> None:
    """A single-byte read accepts only the exact 1 + length response frame."""
    fake = FakeSpi([[0x00, 0x5A]])
    transport = SpiDevTransport()
    transport._spi = fake

    payload = transport.read_register(0x08, 1)

    assert fake.transfers == [[0x11, 0x00]]
    assert payload == bytes([0x5A])


def test_read_register_rejects_truncated_spi_frame() -> None:
    """A response shorter than the requested frame must not be accepted."""
    fake = FakeSpi([[0x00, 0xAA, 0xBB]])
    transport = SpiDevTransport()
    transport._spi = fake

    with pytest.raises(BusError) as exc_info:
        transport.read_register(0x08, 3)

    assert fake.transfers == [[0x11, 0x00, 0x00, 0x00]]
    assert "expected 4, got 3" in str(exc_info.value)


def test_read_register_rejects_overlong_spi_frame() -> None:
    """A response longer than the requested frame must not be accepted."""
    fake = FakeSpi([[0x00, 0xAA, 0xBB, 0xCC, 0xDD]])
    transport = SpiDevTransport()
    transport._spi = fake

    with pytest.raises(BusError) as exc_info:
        transport.read_register(0x08, 3)

    assert fake.transfers == [[0x11, 0x00, 0x00, 0x00]]
    assert "expected 4, got 5" in str(exc_info.value)


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
