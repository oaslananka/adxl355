"""Initialization and standby configuration contract tests."""

from __future__ import annotations

import pytest

from adxl355 import ADXL355, ODR, PowerMode, Range
from adxl355.errors import BusError, DeviceStateError
from adxl355.registers import Register
from adxl355.testing import MockTransport


class ConfigurationTransport(MockTransport):
    def __init__(self) -> None:
        super().__init__()
        self.fail_write_reg: int | None = None
        self.fail_write_occurrence = 0
        self._matching_writes = 0

    def write_register(self, reg: int, data: bytes) -> None:
        if self.fail_write_reg == reg:
            self._matching_writes += 1
            if (
                self.fail_write_occurrence == 0
                or self._matching_writes == self.fail_write_occurrence
            ):
                raise BusError(f"injected write failure at register 0x{reg:02X}")
        super().write_register(reg, data)

    def register(self, reg: int) -> int:
        return self._regs[reg]


def probed_device() -> tuple[ADXL355, ConfigurationTransport]:
    transport = ConfigurationTransport()
    transport.set_identity_ok()
    device = ADXL355(transport)
    device.probe()
    return device, transport


def write_registers(transport: ConfigurationTransport) -> list[int]:
    return [call["reg"] for call in transport.calls if call["is_write"]]


def test_pre_probe_operations_fail_without_bus_access() -> None:
    transport = ConfigurationTransport()
    device = ADXL355(transport)

    with pytest.raises(DeviceStateError):
        device.set_range(Range.G4)
    with pytest.raises(DeviceStateError):
        device.read_status()
    with pytest.raises(DeviceStateError):
        device.reset()

    assert transport.calls == []


def test_range_configuration_restores_measurement_mode() -> None:
    device, transport = probed_device()
    transport.set_register(Register.POWER_CTL, PowerMode.MEASUREMENT)
    transport.clear_call_log()

    device.set_range(Range.G4)

    assert transport.register(Register.POWER_CTL) == PowerMode.MEASUREMENT
    assert transport.register(Register.RANGE) == Range.G4
    assert device._range == Range.G4
    assert write_registers(transport) == [Register.POWER_CTL, Register.RANGE, Register.POWER_CTL]


def test_range_configuration_in_standby_avoids_power_writes() -> None:
    device, transport = probed_device()
    transport.clear_call_log()

    device.set_range(Range.G8)

    assert write_registers(transport) == [Register.RANGE]


def test_target_write_failure_restores_measurement_and_preserves_cache() -> None:
    device, transport = probed_device()
    transport.set_register(Register.POWER_CTL, PowerMode.MEASUREMENT)
    transport.fail_write_reg = Register.RANGE

    with pytest.raises(BusError):
        device.set_range(Range.G4)

    assert transport.register(Register.POWER_CTL) == PowerMode.MEASUREMENT
    assert transport.register(Register.RANGE) == Range.G2
    assert device._range == Range.G2


def test_restore_failure_keeps_successful_range_cache_consistent() -> None:
    device, transport = probed_device()
    transport.set_register(Register.POWER_CTL, PowerMode.MEASUREMENT)
    transport.fail_write_reg = Register.POWER_CTL
    transport.fail_write_occurrence = 2

    with pytest.raises(BusError):
        device.set_range(Range.G4)

    assert transport.register(Register.POWER_CTL) == PowerMode.STANDBY
    assert transport.register(Register.RANGE) == Range.G4
    assert device._range == Range.G4


def test_odr_configuration_restores_measurement_mode() -> None:
    device, transport = probed_device()
    transport.set_register(Register.POWER_CTL, PowerMode.MEASUREMENT)
    transport.set_register(Register.FILTER, 0x50)
    transport.clear_call_log()

    device.set_odr(ODR.HZ_125)

    assert transport.register(Register.POWER_CTL) == PowerMode.MEASUREMENT
    assert transport.register(Register.FILTER) == 0x55
    assert write_registers(transport) == [Register.POWER_CTL, Register.FILTER, Register.POWER_CTL]
