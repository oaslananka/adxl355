"""Shared transport contract scenarios from spec/transport_contract.json."""

from __future__ import annotations

from typing import Optional

import pytest

from adxl355 import ADXL355, Range
from adxl355.errors import BusError
from adxl355.registers import Register
from adxl355.testing import MockTransport


class ContractTransport(MockTransport):
    def __init__(self) -> None:
        super().__init__()
        self.set_identity_ok()
        self.short_reg: Optional[int] = None
        self.short_length = 0
        self.fail_read_reg: Optional[int] = None
        self.fail_write_reg: Optional[int] = None
        self.fail_delay = False

    def read_register(self, reg: int, length: int = 1) -> bytes:
        if self.fail_read_reg == reg:
            raise RuntimeError("native read failure")
        data = super().read_register(reg, length)
        if self.short_reg != reg:
            return data
        if self.short_length <= len(data):
            return data[: self.short_length]
        return data + bytes(self.short_length - len(data))

    def write_register(self, reg: int, data: bytes) -> None:
        if self.fail_write_reg == reg:
            raise RuntimeError("native write failure")
        super().write_register(reg, data)

    def delay_ms(self, ms: int) -> None:
        if self.fail_delay:
            raise RuntimeError("native delay failure")
        super().delay_ms(0)


def probed_device(transport: ContractTransport) -> ADXL355:
    device = ADXL355(transport)
    device.probe()
    return device


@pytest.mark.parametrize("returned_length", [0, 2], ids=["TR-1-ZERO", "TR-1-OVERLONG"])
def test_single_register_requires_exact_length(returned_length: int) -> None:
    transport = ContractTransport()
    transport.short_reg = Register.DEVID_AD
    transport.short_length = returned_length
    with pytest.raises(BusError):
        ADXL355(transport).probe()


@pytest.mark.parametrize("returned_length", [0, 1], ids=["TR-2-ZERO", "TR-2-TRUNCATED"])
def test_temperature_burst_requires_exact_length(returned_length: int) -> None:
    transport = ContractTransport()
    device = probed_device(transport)
    transport.short_reg = Register.TEMP2
    transport.short_length = returned_length
    with pytest.raises(BusError):
        device.read_temperature_raw()


@pytest.mark.parametrize("returned_length", [0, 8], ids=["TR-9-ZERO", "TR-9-TRUNCATED"])
def test_xyz_burst_requires_exact_length(returned_length: int) -> None:
    transport = ContractTransport()
    device = probed_device(transport)
    transport.short_reg = Register.XDATA3
    transport.short_length = returned_length
    with pytest.raises(BusError):
        device.read_raw()


def test_public_mock_can_inject_short_reads() -> None:
    transport = MockTransport()
    transport.set_identity_ok()
    transport.inject_short_read(Register.DEVID_AD, 0)
    with pytest.raises(BusError):
        ADXL355(transport).probe()


def test_native_read_failure_is_normalized() -> None:
    transport = ContractTransport()
    transport.fail_read_reg = Register.DEVID_AD
    with pytest.raises(BusError):
        ADXL355(transport).probe()


def test_native_write_failure_is_normalized() -> None:
    transport = ContractTransport()
    device = probed_device(transport)
    transport.fail_write_reg = Register.RANGE
    with pytest.raises(BusError):
        device.set_range(Range.G4)


def test_native_delay_failure_is_normalized() -> None:
    transport = ContractTransport()
    device = probed_device(transport)
    transport.fail_delay = True
    with pytest.raises(BusError):
        device.reset()
