"""Electrostatic self-test sequence, policy, and restoration tests."""

from __future__ import annotations

import math

import pytest

from adxl355 import (
    ADXL355,
    AccelXYZ,
    BusError,
    DataReadyTimeoutError,
    DeviceStateError,
    InvalidConfigurationError,
    RestoreError,
    SelfTestConfig,
    SelfTestThresholdError,
    SelfTestThresholds,
)
from adxl355.registers import SELF_TEST_MASK, Range, Register
from adxl355.testing import MockTransport
from adxl355.types import RawXYZ, SelfTestResult


def small_config(thresholds: SelfTestThresholds | None = None) -> SelfTestConfig:
    return SelfTestConfig(
        sample_count=4,
        settle_samples=1,
        max_ready_polls=4,
        poll_delay_ms=1,
        thresholds=thresholds,
    )


def self_test_fixture() -> tuple[ADXL355, MockTransport]:
    transport = MockTransport()
    transport.set_identity_ok()
    transport.set_register(Register.RANGE, 0x80 | int(Range.G4))
    transport.set_register(Register.FILTER, 0xA5)
    transport.set_self_test_xyz(
        RawXYZ(100, -200, 300),
        RawXYZ(25741, -25841, 128505),
    )
    device = ADXL355(transport)
    device.probe()
    transport.set_register(Register.POWER_CTL, 0x04)
    return device, transport


def assert_restored(transport: MockTransport) -> None:
    assert transport.register(Register.RANGE) == 0x80 | int(Range.G4)
    assert transport.register(Register.FILTER) == 0xA5
    assert transport.register(Register.POWER_CTL) == 0x04
    assert transport.register(Register.SELF_TEST) == 0


def test_self_test_defaults_do_not_claim_normative_thresholds() -> None:
    config = SelfTestConfig()
    assert config.sample_count == 32
    assert config.settle_samples == 4
    assert config.max_ready_polls == 500
    assert config.poll_delay_ms == 1
    assert config.thresholds is None


def test_self_test_requires_probe_and_valid_bounded_config() -> None:
    transport = MockTransport()
    device = ADXL355(transport)
    with pytest.raises(DeviceStateError):
        device.run_self_test()
    assert transport.calls == []

    device, _ = self_test_fixture()
    invalid = (
        SelfTestConfig(sample_count=0),
        SelfTestConfig(settle_samples=1025),
        SelfTestConfig(max_ready_polls=0),
        SelfTestConfig(poll_delay_ms=0),
        SelfTestConfig(sample_count=True),  # type: ignore[arg-type]
        SelfTestConfig(
            thresholds=SelfTestThresholds(
                min_abs_delta_g=AccelXYZ(math.nan, 0.0, 0.0),
                max_abs_delta_g=AccelXYZ(1.0, 1.0, 1.0),
            )
        ),
        SelfTestConfig(
            thresholds=SelfTestThresholds(
                min_abs_delta_g=AccelXYZ(0.2, 0.0, 0.0),
                max_abs_delta_g=AccelXYZ(0.1, 1.0, 1.0),
            )
        ),
    )
    for config in invalid:
        with pytest.raises(InvalidConfigurationError):
            device.run_self_test(config)


def test_self_test_rejects_preexisting_st_bits_without_modification() -> None:
    device, transport = self_test_fixture()
    transport.set_register(Register.SELF_TEST, 0x80 | SELF_TEST_MASK)
    transport.clear_call_log()
    with pytest.raises(DeviceStateError):
        device.run_self_test(small_config())
    assert not any(call["is_write"] for call in transport.calls)
    assert transport.register(Register.SELF_TEST) == 0x80 | SELF_TEST_MASK


def test_self_test_measures_typical_response_and_restores_exact_state() -> None:
    device, transport = self_test_fixture()
    transport.clear_call_log()
    result = device.run_self_test(small_config())

    assert result.samples == 4
    assert result.delta_g.x == pytest.approx(0.1000, abs=2e-5)
    assert result.delta_g.y == pytest.approx(-0.1000, abs=2e-5)
    assert result.delta_g.z == pytest.approx(0.5, abs=2e-5)
    assert result.abs_delta_g.y == pytest.approx(0.1000, abs=2e-5)
    assert result.thresholds_evaluated is False
    assert result.thresholds_passed is True
    assert_restored(transport)
    assert device.get_range() is Range.G4

    self_test_writes = [
        call for call in transport.calls if call["is_write"] and call["reg"] == Register.SELF_TEST
    ]
    assert any(call["data"] & SELF_TEST_MASK == SELF_TEST_MASK for call in self_test_writes)


def test_caller_threshold_policy_passes_or_returns_measured_failure() -> None:
    device, transport = self_test_fixture()
    thresholds = SelfTestThresholds(
        min_abs_delta_g=AccelXYZ(0.08, 0.08, 0.40),
        max_abs_delta_g=AccelXYZ(0.12, 0.12, 0.60),
    )
    result = device.run_self_test(small_config(thresholds))
    assert result.thresholds_evaluated is True
    assert result.thresholds_passed is True

    failing = SelfTestThresholds(
        min_abs_delta_g=AccelXYZ(0.11, 0.08, 0.40),
        max_abs_delta_g=AccelXYZ(0.12, 0.12, 0.60),
    )
    with pytest.raises(SelfTestThresholdError) as captured:
        device.run_self_test(small_config(failing))
    failed_result = captured.value.result
    assert isinstance(failed_result, SelfTestResult)
    assert failed_result.thresholds_evaluated is True
    assert failed_result.thresholds_passed is False
    assert failed_result.abs_delta_g.x > 0.09
    assert_restored(transport)


def test_data_ready_timeout_is_bounded_and_restores_state() -> None:
    device, transport = self_test_fixture()
    transport.set_register(Register.STATUS, 0)
    config = SelfTestConfig(
        sample_count=1,
        settle_samples=0,
        max_ready_polls=2,
        poll_delay_ms=1,
    )
    with pytest.raises(DataReadyTimeoutError):
        device.run_self_test(config)
    assert_restored(transport)


def test_short_xyz_response_is_bus_error_and_restores_state() -> None:
    device, transport = self_test_fixture()
    transport.inject_short_read(Register.XDATA3, 8)
    config = SelfTestConfig(sample_count=1, settle_samples=0, max_ready_polls=2)
    with pytest.raises(BusError):
        device.run_self_test(config)
    assert_restored(transport)


def test_target_write_failure_restores_original_state() -> None:
    device, transport = self_test_fixture()
    transport.inject_write_error(Register.SELF_TEST, occurrence=2)
    config = SelfTestConfig(sample_count=1, settle_samples=0, max_ready_polls=2)
    with pytest.raises(BusError):
        device.run_self_test(config)
    assert_restored(transport)


def test_restore_failure_is_distinct_and_leaves_st_bits_disabled() -> None:
    device, transport = self_test_fixture()
    transport.inject_write_error(Register.POWER_CTL, occurrence=4)
    config = SelfTestConfig(sample_count=1, settle_samples=0, max_ready_polls=2)
    with pytest.raises(RestoreError) as captured:
        device.run_self_test(config)
    assert len(captured.value.failures) == 1
    assert transport.register(Register.SELF_TEST) == 0
    assert transport.register(Register.RANGE) == 0x80 | int(Range.G4)
    assert transport.register(Register.FILTER) == 0xA5
    assert transport.register(Register.POWER_CTL) & 0x01
    assert device.get_range() is Range.G4
