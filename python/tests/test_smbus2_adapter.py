"""Transport-level tests for the Linux smbus2 adapter."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from adxl355.adapters.smbus2 import Smbus2Transport
from adxl355.errors import BusError


class FakeSMBus:
    """Record SMBus calls and return queued responses."""

    def __init__(self) -> None:
        self.open_bus: int | None = None
        self.read_byte_data_calls: list[tuple[int, int]] = []
        self.read_i2c_block_data_calls: list[tuple[int, int, int]] = []
        self.write_byte_data_calls: list[tuple[int, int, int]] = []
        self.write_i2c_block_data_calls: list[tuple[int, int, list[int]]] = []
        self.closed = False
        self.byte_data_responses: list[int] = []
        self.block_data_responses: list[list[int]] = []

    def read_byte_data(self, address: int, reg: int) -> int:
        self.read_byte_data_calls.append((address, reg))
        if self.byte_data_responses:
            return self.byte_data_responses.pop(0)
        return 0

    def read_i2c_block_data(self, address: int, reg: int, length: int) -> list[int]:
        self.read_i2c_block_data_calls.append((address, reg, length))
        if self.block_data_responses:
            return self.block_data_responses.pop(0)
        return [0] * length

    def write_byte_data(self, address: int, reg: int, value: int) -> None:
        self.write_byte_data_calls.append((address, reg, value))

    def write_i2c_block_data(self, address: int, reg: int, data: list[int]) -> None:
        self.write_i2c_block_data_calls.append((address, reg, list(data)))

    def close(self) -> None:
        self.closed = True


class TestSmbus2Adapter(TestCase):
    def test_single_byte_read_uses_read_byte_data(self) -> None:
        fake = FakeSMBus()
        fake.byte_data_responses = [0xAD]
        with patch.dict(sys.modules, {"smbus2": SimpleNamespace(SMBus=lambda bus: fake)}):
            transport = Smbus2Transport(bus=1, address=0x1D)
            payload = transport.read_register(0x00, 1)

        self.assertEqual(payload, bytes([0xAD]))
        self.assertEqual(fake.read_byte_data_calls, [(0x1D, 0x00)])
        self.assertEqual(fake.read_i2c_block_data_calls, [])

    def test_multi_byte_read_exact_block(self) -> None:
        fake = FakeSMBus()
        fake.block_data_responses = [[0x01, 0x02, 0x03]]
        with patch.dict(sys.modules, {"smbus2": SimpleNamespace(SMBus=lambda bus: fake)}):
            transport = Smbus2Transport(bus=1, address=0x1D)
            payload = transport.read_register(0x08, 3)

        self.assertEqual(payload, bytes([0x01, 0x02, 0x03]))
        self.assertEqual(fake.read_i2c_block_data_calls, [(0x1D, 0x08, 3)])

    def test_multi_byte_read_short_block_raises_bus_error(self) -> None:
        fake = FakeSMBus()
        fake.block_data_responses = [[0x01, 0x02]]
        with patch.dict(sys.modules, {"smbus2": SimpleNamespace(SMBus=lambda bus: fake)}):
            transport = Smbus2Transport(bus=1, address=0x1D)
            with self.assertRaises(BusError):
                transport.read_register(0x08, 3)

        self.assertEqual(fake.read_i2c_block_data_calls, [(0x1D, 0x08, 3)])

    def test_multi_byte_read_overlong_block_raises_bus_error(self) -> None:
        fake = FakeSMBus()
        fake.block_data_responses = [[0x01, 0x02, 0x03, 0x04]]
        with patch.dict(sys.modules, {"smbus2": SimpleNamespace(SMBus=lambda bus: fake)}):
            transport = Smbus2Transport(bus=1, address=0x1D)
            with self.assertRaises(BusError):
                transport.read_register(0x08, 3)

        self.assertEqual(fake.read_i2c_block_data_calls, [(0x1D, 0x08, 3)])

    def test_write_register_byte_and_block(self) -> None:
        fake = FakeSMBus()
        with patch.dict(sys.modules, {"smbus2": SimpleNamespace(SMBus=lambda bus: fake)}):
            transport = Smbus2Transport(bus=1, address=0x1D)
            transport.write_register(0x2D, bytes([0x0E]))
            transport.write_register(0x2C, bytes([0x01, 0x02]))

        self.assertEqual(fake.write_byte_data_calls, [(0x1D, 0x2D, 0x0E)])
        self.assertEqual(fake.write_i2c_block_data_calls, [(0x1D, 0x2C, [0x01, 0x02])])

    def test_close_and_lazy_open(self) -> None:
        fake = FakeSMBus()
        factory = Mock(return_value=fake)
        with patch.dict(sys.modules, {"smbus2": SimpleNamespace(SMBus=factory)}):
            transport = Smbus2Transport(bus=5, address=0x1D)
            transport.close()
            self.assertEqual(factory.call_count, 0)
            self.assertIsNone(transport._i2c)

            transport.read_register(0x00, 1)
            self.assertEqual(factory.call_count, 1)
            transport.close()
            self.assertTrue(fake.closed)
            self.assertIsNone(transport._i2c)
            transport.close()
            self.assertTrue(fake.closed)
