"""Transport-level tests for the Linux spidev adapter."""

from __future__ import annotations

from adxl355.adapters.spidev import SpiDevTransport


class FakeSpi:
    """Record complete xfer2 transactions and return queued responses."""

    def __init__(self, responses: list[list[int]] | None = None) -> None:
        self.max_speed_hz = 0
        self.mode = -1
        self.responses = list(responses or [])
        self.transfers: list[list[int]] = []
        self.closed = False

    def open(self, _bus: int, _device: int) -> None:
        pass

    def xfer2(self, payload: list[int]) -> list[int]:
        self.transfers.append(payload.copy())
        if self.responses:
            return self.responses.pop(0)
        return [0] * len(payload)

    def close(self) -> None:
        self.closed = True


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
