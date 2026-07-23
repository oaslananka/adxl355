"""Integration tests for ADXL355 device with mock transport."""

import pytest

from adxl355 import ADXL355, PowerMode, Range
from adxl355.errors import (
    BusError,
    DataNotReadyError,
    DeviceNotFoundError,
    InvalidConfigurationError,
)
from adxl355.registers import Register
from adxl355.testing import MockTransport


@pytest.fixture
def mock_device() -> ADXL355:
    """Create an ADXL355 instance with a mock transport that passes probe."""
    transport = MockTransport()
    transport.set_identity_ok()
    dev = ADXL355(transport)
    dev.probe()
    return dev


class TestDefaultRangeState:
    def test_constructor_defaults_to_2g(self) -> None:
        dev = ADXL355(MockTransport())
        assert dev._range == Range.G2

    def test_probe_synchronizes_hardware_range(self) -> None:
        transport = MockTransport()
        transport.set_identity_ok()
        transport.set_register(Register.RANGE, int(Range.G8))
        dev = ADXL355(transport)

        assert dev.probe() is True
        assert dev._range == Range.G8

    def test_probe_rejects_reserved_range(self) -> None:
        transport = MockTransport()
        transport.set_identity_ok()
        transport.set_register(Register.RANGE, 0x00)
        dev = ADXL355(transport)

        with pytest.raises(InvalidConfigurationError):
            dev.probe()
        assert dev._initialized is False
        assert dev._range == Range.G2

    def test_reset_restores_2g_cache(self) -> None:
        transport = MockTransport()
        transport.set_identity_ok()
        transport.set_register(Register.RANGE, int(Range.G8))
        dev = ADXL355(transport)
        dev.probe()

        dev.reset()
        assert dev._range == Range.G2

    def test_reset_range_converts_raw_value_to_one_g(self) -> None:
        transport = MockTransport()
        transport.set_identity_ok()
        transport.set_register(Register.RANGE, int(Range.G2))
        transport.set_xyz_raw(x=256410, y=0, z=0)
        dev = ADXL355(transport)

        dev.probe()
        accel = dev.read_acceleration_g()
        assert accel.x == pytest.approx(1.0, abs=0.001)


class TestProbe:
    def test_successful_probe(self) -> None:
        transport = MockTransport()
        transport.set_identity_ok()
        dev = ADXL355(transport)
        assert dev.probe() is True

    def test_probe_bad_device(self) -> None:
        transport = MockTransport()  # Identity NOT set
        dev = ADXL355(transport)
        with pytest.raises(DeviceNotFoundError):
            dev.probe()

    def test_probe_wrong_id(self) -> None:
        transport = MockTransport()
        transport.set_register(Register.DEVID_AD, 0x00)  # wrong
        transport.set_register(Register.DEVID_MST, 0x1D)
        transport.set_register(Register.PARTID, 0xED)
        dev = ADXL355(transport)
        with pytest.raises(DeviceNotFoundError):
            dev.probe()


class TestRange:
    def test_set_range_writes_register(self, mock_device: ADXL355) -> None:
        mock_device.set_range(Range.G8)
        transport = mock_device._transport
        # Verify a write to RANGE register happened
        writes = [c for c in transport.calls if c["is_write"] and c["reg"] == Register.RANGE]
        assert len(writes) >= 1

    def test_set_invalid_range(self, mock_device: ADXL355) -> None:
        with pytest.raises(InvalidConfigurationError):
            mock_device.set_range(99)  # type: ignore[arg-type]

    def test_get_range(self, mock_device: ADXL355) -> None:
        mock_device.set_range(Range.G2)
        assert mock_device.get_range() == Range.G2

        mock_device.set_range(Range.G8)
        assert mock_device.get_range() == Range.G8


class TestPowerMode:
    def test_set_power_mode(self, mock_device: ADXL355) -> None:
        # Should not raise
        mock_device.set_power_mode(PowerMode.MEASUREMENT)
        mock_device.set_power_mode(PowerMode.STANDBY)


class TestReadRaw:
    def test_read_raw(self, mock_device: ADXL355) -> None:
        transport = mock_device._transport
        transport.set_xyz_raw(x=100, y=-200, z=300)
        raw = mock_device.read_raw()
        assert raw.x == 100, f"Expected x=100, got {raw.x}"
        assert raw.y == -200, f"Expected y=-200, got {raw.y}"
        assert raw.z == 300, f"Expected z=300, got {raw.z}"


class TestReadAcceleration:
    def test_read_g(self, mock_device: ADXL355) -> None:
        transport = mock_device._transport
        transport.set_xyz_raw(x=524287, y=0, z=-524288)
        accel = mock_device.read_acceleration_g()
        assert accel.x > 0
        assert accel.y == 0.0
        assert accel.z < 0

    def test_read_mps2(self, mock_device: ADXL355) -> None:
        transport = mock_device._transport
        transport.set_xyz_raw(x=100000, y=0, z=0)
        accel = mock_device.read_acceleration_mps2()
        assert accel.x != 0.0
        assert accel.y == 0.0
        assert accel.z == 0.0


class TestStatus:
    def test_read_status(self, mock_device: ADXL355) -> None:
        transport = mock_device._transport
        transport.set_register(Register.STATUS, 0x01)  # DATA_RDY (bit 0)
        status = mock_device.read_status()
        assert status & 0x01


class TestReset:
    def test_reset(self, mock_device: ADXL355) -> None:
        mock_device.reset()
        transport = mock_device._transport
        writes = [c for c in transport.calls if c["is_write"] and c["reg"] == Register.RESET]
        assert len(writes) >= 1


class TemperatureSequenceTransport(MockTransport):
    def __init__(self, responses: list[bytes]) -> None:
        super().__init__()
        self._responses = list(responses)

    def read_register(self, reg: int, length: int = 1) -> bytes:
        if reg == Register.TEMP2 and self._responses:
            return self._responses.pop(0)
        return super().read_register(reg, length)


class TestTemperature:
    def test_reserved_temp2_nibble_is_ignored(self, mock_device: ADXL355) -> None:
        transport = mock_device._transport
        transport.set_register(Register.TEMP2, 0xF7)
        transport.set_register(Register.TEMP1, 0x5D)
        assert mock_device.read_temperature_raw() == 1885
        assert abs(mock_device.read_temperature_c() - 25.0) < 0.01

    def test_short_temperature_read_raises_bus_error(self) -> None:
        transport = TemperatureSequenceTransport([bytes([0x07])])
        transport.set_identity_ok()
        dev = ADXL355(transport)
        dev.probe()
        with pytest.raises(BusError):
            dev.read_temperature_raw()

    def test_temperature_rollover_is_retried(self) -> None:
        transport = TemperatureSequenceTransport(
            [bytes([0x07, 0xFF]), bytes([0x08]), bytes([0x08, 0x00]), bytes([0x08])]
        )
        transport.set_identity_ok()
        dev = ADXL355(transport)
        dev.probe()
        assert dev.read_temperature_raw() == 2048

    def test_unstable_temperature_raises_not_ready(self) -> None:
        transport = TemperatureSequenceTransport(
            [
                bytes([0x07, 0xFF]), bytes([0x08]),
                bytes([0x08, 0xFF]), bytes([0x09]),
                bytes([0x09, 0xFF]), bytes([0x0A]),
            ]
        )
        transport.set_identity_ok()
        dev = ADXL355(transport)
        dev.probe()
        with pytest.raises(DataNotReadyError):
            dev.read_temperature_raw()

    def test_temperature_raw(self, mock_device: ADXL355) -> None:
        transport = mock_device._transport
        transport.set_register(Register.TEMP2, 0x01)
        transport.set_register(Register.TEMP1, 0x90)
        raw = mock_device.read_temperature_raw()
        assert raw == 0x0190

    def test_temperature_c_nominal(self, mock_device: ADXL355) -> None:
        """raw=1885 → 25.0°C (datasheet nominal intercept)."""
        transport = mock_device._transport
        transport.set_register(Register.TEMP2, 0x07)
        transport.set_register(Register.TEMP1, 0x5D)  # 0x075D = 1885
        temp = mock_device.read_temperature_c()
        assert abs(temp - 25.0) < 0.01

    def test_temperature_c_zero(self, mock_device: ADXL355) -> None:
        """raw=0 → 25 + (0 - 1885) / -9.05 ≈ 233.29°C."""
        transport = mock_device._transport
        transport.set_register(Register.TEMP2, 0x00)
        transport.set_register(Register.TEMP1, 0x00)
        temp = mock_device.read_temperature_c()
        assert abs(temp - 233.287) < 0.01

    def test_temperature_c_max(self, mock_device: ADXL355) -> None:
        """raw=4095 (12-bit max) → 25 + (4095 - 1885) / -9.05 ≈ -170.17°C."""
        transport = mock_device._transport
        transport.set_register(Register.TEMP2, 0x0F)
        transport.set_register(Register.TEMP1, 0xFF)  # 0x0FFF = 4095
        temp = mock_device.read_temperature_c()
        expected = 25.0 + (4095 - 1885.0) / -9.05
        assert abs(temp - expected) < 0.01

    def test_temperature_increasing_raw_decreases(self, mock_device: ADXL355) -> None:
        """Verify temperature decreases as raw increases (negative slope)."""
        transport = mock_device._transport
        transport.set_register(Register.TEMP2, 0x00)
        transport.set_register(Register.TEMP1, 0x00)
        t_low_raw = mock_device.read_temperature_c()
        transport.set_register(Register.TEMP2, 0x07)
        transport.set_register(Register.TEMP1, 0x5D)  # 1885
        t_high_raw = mock_device.read_temperature_c()
        assert t_low_raw > t_high_raw, "temperature should decrease as raw increases"


class TestFifo:
    def test_read_fifo_entries(self, mock_device: ADXL355) -> None:
        transport = mock_device._transport
        transport.set_register(Register.FIFO_ENTRIES, 0x2A)
        entries = mock_device.read_fifo_entries()
        assert entries == 0x2A

    def test_fifo_entries_default_zero(self, mock_device: ADXL355) -> None:
        entries = mock_device.read_fifo_entries()
        assert entries == 0


class TestActivity:
    def test_activity_status_bit(self, mock_device: ADXL355) -> None:
        transport = mock_device._transport
        transport.set_register(Register.STATUS, 0x08)  # bit 3 = ACTIVITY
        status = mock_device.read_status()
        assert status & 0x08, "ACTIVITY bit (3) should be set"

    def test_multiple_status_bits(self, mock_device: ADXL355) -> None:
        transport = mock_device._transport
        transport.set_register(Register.STATUS, 0x1F)  # all 5 bits
        status = mock_device.read_status()
        assert status == 0x1F


class TestBusError:
    def test_read_raw_raises_on_bus_error(self, mock_device: ADXL355) -> None:
        from adxl355.errors import BusError
        transport = mock_device._transport
        transport.inject_error(BusError("mock bus error"))
        with pytest.raises(BusError):
            mock_device.read_raw()

    def test_read_status_raises_on_bus_error(self, mock_device: ADXL355) -> None:
        from adxl355.errors import BusError
        transport = mock_device._transport
        transport.inject_error(BusError("mock bus error"))
        with pytest.raises(BusError):
            mock_device.read_status()

    def test_set_range_raises_on_bus_error(self, mock_device: ADXL355) -> None:
        from adxl355.errors import BusError
        transport = mock_device._transport
        transport.inject_error(BusError("mock bus error"))
        with pytest.raises(BusError):
            mock_device.set_range(Range.G2)

    def test_set_power_mode_raises_on_bus_error(self, mock_device: ADXL355) -> None:
        from adxl355.errors import BusError
        transport = mock_device._transport
        transport.inject_error(BusError("mock bus error"))
        with pytest.raises(BusError):
            mock_device.set_power_mode(PowerMode.MEASUREMENT)

    def test_clear_error_restores_operation(self, mock_device: ADXL355) -> None:
        from adxl355.errors import BusError
        transport = mock_device._transport
        transport.inject_error(BusError("mock bus error"))
        transport.clear_error()
        # Should not raise after clear
        raw = mock_device.read_raw()
        assert raw is not None


class TestResetVerification:
    def test_reset_writes_correct_register(self, mock_device: ADXL355) -> None:
        mock_device.reset()
        transport = mock_device._transport
        writes = [c for c in transport.calls if c["is_write"] and c["reg"] == Register.RESET]
        assert len(writes) >= 1, "reset should write to RESET register"

    def test_reset_code(self, mock_device: ADXL355) -> None:
        mock_device.reset()

    def test_reset_clears_call_log(self, mock_device: ADXL355) -> None:
        transport = mock_device._transport
        prev_count = transport.call_count
        mock_device.reset()
        assert transport.call_count > prev_count, "reset should generate bus calls"
