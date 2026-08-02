"""Initialization and standby configuration contract tests."""

from __future__ import annotations

import pytest

from adxl355 import ADXL355, ODR, PowerMode, Range
from adxl355.errors import BusError, DeviceStateError
from adxl355.registers import Register
from adxl355.testing import MockTransport


def probed_device() -> tuple[ADXL355, MockTransport]:
    transport = MockTransport()
    transport.set_identity_ok()
    device = ADXL355(transport)
    device.probe()
    return device, transport


def write_registers(transport: MockTransport) -> list[int]:
    return [call["reg"] for call in transport.calls if call["is_write"]]


def test_pre_probe_operations_fail_without_bus_access() -> None:
    transport = MockTransport()
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
    transport.inject_write_error(Register.RANGE)

    with pytest.raises(BusError):
        device.set_range(Range.G4)

    assert transport.register(Register.POWER_CTL) == PowerMode.MEASUREMENT
    assert transport.register(Register.RANGE) == Range.G2
    assert device._range == Range.G2


def test_restore_failure_keeps_successful_range_cache_consistent() -> None:
    device, transport = probed_device()
    transport.set_register(Register.POWER_CTL, PowerMode.MEASUREMENT)
    transport.inject_write_error(Register.POWER_CTL, occurrence=2)

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
