"""Hardware offset and calibration helper tests."""

from __future__ import annotations

import pytest

from adxl355 import ADXL355, Axis, PowerMode, calculate_offset
from adxl355.errors import BusError, DeviceStateError, InvalidConfigurationError
from adxl355.registers import Register
from adxl355.testing import MockTransport


def probed_device() -> tuple[ADXL355, MockTransport]:
    transport = MockTransport()
    transport.set_identity_ok()
    device = ADXL355(transport)
    device.probe()
    return device, transport


def write_calls(transport: MockTransport) -> list[dict[str, object]]:
    return [call for call in transport.calls if call["is_write"]]


@pytest.mark.parametrize(
    ("delta", "expected"),
    [(7, 0), (8, 1), (23, 1), (24, 2), (-7, 0), (-8, -1), (-23, -1), (-24, -2)],
)
def test_calculate_offset_rounds_half_away_from_zero(delta: int, expected: int) -> None:
    assert calculate_offset(1000, 1000 + delta) == -expected


def test_calculate_offset_returns_new_absolute_register_value() -> None:
    assert calculate_offset(1000, 1008, current_offset=100) == 99


def test_calculate_offset_rejects_or_saturates_overflow() -> None:
    with pytest.raises(InvalidConfigurationError):
        calculate_offset(-(1 << 19), (1 << 19) - 1)
    assert calculate_offset(-(1 << 19), (1 << 19) - 1, saturate=True) == -(1 << 15)
    assert calculate_offset((1 << 19) - 1, -(1 << 19), saturate=True) == (1 << 15) - 1


@pytest.mark.parametrize("value", [1.5, True, 1 << 19, -(1 << 19) - 1])
def test_calculate_offset_rejects_invalid_raw_inputs(value: object) -> None:
    with pytest.raises(InvalidConfigurationError):
        calculate_offset(value, 0)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [1.5, True, 1 << 15, -(1 << 15) - 1])
def test_calculate_offset_rejects_invalid_current_offset(value: object) -> None:
    with pytest.raises(InvalidConfigurationError):
        calculate_offset(0, 0, current_offset=value)  # type: ignore[arg-type]


def test_offset_read_write_uses_signed_big_endian_burst_and_restores_mode() -> None:
    device, transport = probed_device()
    transport.set_register(Register.OFFSET_Y_H, 0xFE)
    transport.set_register(Register.OFFSET_Y_L, 0xDC)
    assert device.read_offset(Axis.Y) == -292

    transport.set_register(Register.POWER_CTL, PowerMode.MEASUREMENT)
    transport.clear_call_log()
    device.write_offset(Axis.X, -1234)

    assert transport.register(Register.OFFSET_X_H) == 0xFB
    assert transport.register(Register.OFFSET_X_L) == 0x2E
    assert transport.register(Register.POWER_CTL) == PowerMode.MEASUREMENT
    calls = write_calls(transport)
    assert [call["reg"] for call in calls] == [
        Register.POWER_CTL,
        Register.OFFSET_X_H,
        Register.POWER_CTL,
    ]
    assert calls[1]["length"] == 2


@pytest.mark.parametrize(
    ("fail_reg", "occurrence", "expected_power", "expected_low"),
    [
        (Register.OFFSET_Z_H, 0, PowerMode.MEASUREMENT, 0),
        (Register.POWER_CTL, 2, PowerMode.STANDBY, 100),
    ],
)
def test_offset_write_failures_preserve_safe_state(
    fail_reg: Register,
    occurrence: int,
    expected_power: PowerMode,
    expected_low: int,
) -> None:
    device, transport = probed_device()
    transport.set_register(Register.POWER_CTL, PowerMode.MEASUREMENT)
    transport.inject_write_error(fail_reg, occurrence=occurrence)

    with pytest.raises(BusError):
        device.write_offset(Axis.Z, 100)

    assert transport.register(Register.POWER_CTL) == expected_power
    assert transport.register(Register.OFFSET_Z_H) == 0
    assert transport.register(Register.OFFSET_Z_L) == expected_low


def test_offset_validation_and_pre_probe_contract() -> None:
    transport = MockTransport()
    device = ADXL355(transport)
    with pytest.raises(DeviceStateError):
        device.read_offset(Axis.X)
    with pytest.raises(DeviceStateError):
        device.write_offset(Axis.X, 0)
    assert transport.calls == []

    transport.set_identity_ok()
    device.probe()
    with pytest.raises(InvalidConfigurationError):
        device.read_offset(99)  # type: ignore[arg-type]
    for value in (True, 1.5, 1 << 15, -(1 << 15) - 1):
        with pytest.raises(InvalidConfigurationError):
            device.write_offset(Axis.X, value)  # type: ignore[arg-type]
