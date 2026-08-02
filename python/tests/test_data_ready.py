"""Rev.D DRDY and DATA_RDY interrupt-routing contract tests."""

from __future__ import annotations

from typing import cast

import pytest

from adxl355 import (
    ADXL355,
    DataReadyConfig,
    InterruptPolarity,
    PowerMode,
    Range,
)
from adxl355.errors import (
    BusError,
    DeviceStateError,
    InvalidConfigurationError,
    RestoreError,
    UnsupportedConfigurationError,
)
from adxl355.registers import Register
from adxl355.testing import MockTransport


def fixture() -> tuple[ADXL355, MockTransport]:
    transport = MockTransport()
    transport.set_identity_ok()
    transport.set_register(Register.RANGE, 0xA0 | int(Range.G4))
    transport.set_register(Register.POWER_CTL, 0x82)
    transport.set_register(Register.INT_MAP, 0x88)
    device = ADXL355(transport)
    device.probe()
    transport.set_register(Register.POWER_CTL, 0x82)
    transport.clear_call_log()
    return device, transport


def writes(transport: MockTransport) -> list[int]:
    return [int(call["reg"]) for call in transport.calls if call["is_write"]]


def test_defaults_use_dedicated_active_high_drdy_only() -> None:
    config = DataReadyConfig()
    assert config.dedicated_drdy_enabled is True
    assert config.route_to_int1 is False
    assert config.route_to_int2 is False
    assert config.interrupt_polarity is InterruptPolarity.ACTIVE_LOW


def test_configuration_preserves_unrelated_bits_and_measurement_mode() -> None:
    device, transport = fixture()
    device.configure_data_ready(
        DataReadyConfig(
            dedicated_drdy_enabled=False,
            route_to_int1=True,
            route_to_int2=True,
            interrupt_polarity=InterruptPolarity.ACTIVE_HIGH,
        )
    )

    assert transport.register(Register.POWER_CTL) == 0x86
    assert transport.register(Register.RANGE) == 0xE2
    assert transport.register(Register.INT_MAP) == 0x99
    assert writes(transport) == [
        Register.POWER_CTL,
        Register.RANGE,
        Register.INT_MAP,
        Register.POWER_CTL,
    ]
    assert all(call["reg"] != Register.STATUS for call in transport.calls)

    assert device.get_data_ready_config() == DataReadyConfig(
        dedicated_drdy_enabled=False,
        route_to_int1=True,
        route_to_int2=True,
        interrupt_polarity=InterruptPolarity.ACTIVE_HIGH,
    )


def test_external_timing_modes_are_rejected_without_writes() -> None:
    device, transport = fixture()
    transport.set_register(Register.SYNC, 0x01)

    with pytest.raises(UnsupportedConfigurationError):
        device.configure_data_ready(DataReadyConfig(route_to_int1=True))
    with pytest.raises(UnsupportedConfigurationError):
        device.get_data_ready_config()
    assert writes(transport) == []


def test_invalid_config_and_pre_probe_are_rejected() -> None:
    invalid = DataReadyConfig(
        interrupt_polarity=cast(InterruptPolarity, 7),
    )
    device, _ = fixture()
    with pytest.raises(InvalidConfigurationError):
        device.configure_data_ready(invalid)

    transport = MockTransport()
    unprobed = ADXL355(transport)
    with pytest.raises(DeviceStateError):
        unprobed.configure_data_ready(DataReadyConfig())
    assert transport.calls == []


def test_target_failure_restores_exact_state() -> None:
    device, transport = fixture()
    original = (
        transport.register(Register.POWER_CTL),
        transport.register(Register.RANGE),
        transport.register(Register.INT_MAP),
    )
    transport.inject_write_error(Register.INT_MAP, occurrence=1)

    with pytest.raises(BusError):
        device.configure_data_ready(
            DataReadyConfig(
                dedicated_drdy_enabled=False,
                route_to_int1=True,
                route_to_int2=True,
                interrupt_polarity=InterruptPolarity.ACTIVE_HIGH,
            )
        )

    assert (
        transport.register(Register.POWER_CTL),
        transport.register(Register.RANGE),
        transport.register(Register.INT_MAP),
    ) == original


def test_restore_failure_is_distinct_and_best_effort_restores_mode() -> None:
    device, transport = fixture()
    transport.inject_write_error(Register.INT_MAP)

    with pytest.raises(RestoreError) as captured:
        device.configure_data_ready(DataReadyConfig(route_to_int1=True))

    assert captured.value.failures
    assert transport.register(Register.POWER_CTL) & 0x01 == PowerMode.MEASUREMENT
