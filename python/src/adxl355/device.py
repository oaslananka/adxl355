"""Main ADXL355 device driver."""

from __future__ import annotations

import math

from adxl355.constants import (
    DEVID_AD,
    DEVID_MST,
    PARTID,
    RESET_CODE,
    SCALE_2G_G_PER_LSB,
    SCALE_4G_G_PER_LSB,
    SCALE_8G_G_PER_LSB,
    STANDARD_GRAVITY_M_S2,
    TEMP2_DATA_MASK,
    TEMP_INTERCEPT_C,
    TEMP_INTERCEPT_LSB,
    TEMP_READ_ATTEMPTS,
    TEMP_SLOPE_LSB_PER_C,
)
from adxl355.errors import (
    BusError,
    DataNotReadyError,
    DataReadyTimeoutError,
    DeviceNotFoundError,
    DeviceStateError,
    FifoBusError,
    FifoEmptyError,
    FifoFormatError,
    FifoOverrunError,
    FifoReadError,
    InvalidConfigurationError,
    RestoreError,
    SelfTestThresholdError,
    UnsupportedConfigurationError,
)
from adxl355.registers import (
    FILTER_HPF_MASK,
    FILTER_ODR_MASK,
    FILTER_ODR_SHIFT,
    INT_MAP_DATA_READY_MASK,
    INT_MAP_RDY_EN1,
    INT_MAP_RDY_EN2,
    ODR,
    POWER_DRDY_OFF,
    RANGE_INT_POL,
    RANGE_SEL_MASK,
    SELF_TEST_MASK,
    STATUS_DATA_RDY,
    STATUS_FIFO_OVR,
    SYNC_TIMING_MASK,
    Axis,
    InterruptPolarity,
    PowerMode,
    Range,
    Register,
)
from adxl355.transport import Transport
from adxl355.types import (
    AccelXYZ,
    DataReadyConfig,
    FifoLocation,
    FifoReadResult,
    RawXYZ,
    SelfTestConfig,
    SelfTestResult,
    SelfTestThresholds,
)


class ADXL355:
    """
    ADXL355 accelerometer driver.

    Transport-agnostic: accepts any object conforming to the Transport protocol.
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        self._range = Range.G2
        self._initialized = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_exact(self, reg: int, length: int) -> bytes:
        try:
            data = self._transport.read_register(reg, length)
        except Exception as exc:
            if isinstance(exc, BusError):
                raise
            raise BusError(f"Transport read failed at register 0x{reg:02X}") from exc
        if len(data) != length:
            raise BusError(
                f"Invalid read length at register 0x{reg:02X}: expected {length}, got {len(data)}"
            )
        return data

    def _read_reg(self, reg: int) -> int:
        return self._read_exact(reg, 1)[0]

    def _write_exact(self, reg: int, data: bytes) -> None:
        try:
            self._transport.write_register(reg, data)
        except Exception as exc:
            if isinstance(exc, BusError):
                raise
            raise BusError(f"Transport write failed at register 0x{reg:02X}") from exc

    def _write_reg(self, reg: int, value: int) -> None:
        self._write_exact(reg, bytes([value]))

    def _delay_ms(self, ms: int) -> None:
        try:
            self._transport.delay_ms(ms)
        except Exception as exc:
            if isinstance(exc, BusError):
                raise
            raise BusError(f"Transport delay failed for {ms} ms") from exc

    def _check_init(self) -> None:
        if not self._initialized:
            raise DeviceStateError("Device has not been probed. Call probe() first.")

    def _enter_configuration_standby(self) -> int | None:
        """Enter standby for a configuration write and return state to restore."""
        original_power_ctl = self._read_reg(Register.POWER_CTL)
        if original_power_ctl & 0x01:
            return None
        self._write_reg(Register.POWER_CTL, original_power_ctl | 0x01)
        return original_power_ctl

    def _restore_configuration_mode(self, original_power_ctl: int | None) -> None:
        if original_power_ctl is not None:
            self._write_reg(Register.POWER_CTL, original_power_ctl)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def probe(self) -> bool:
        """
        Verify device identity by reading ID registers.

        Returns True if all three ID registers match expected values.
        After successful probe, the cached range matches the hardware RANGE register
        and the device is left in standby mode.
        """
        self._initialized = False
        id_ad = self._read_reg(Register.DEVID_AD)
        id_mst = self._read_reg(Register.DEVID_MST)
        part_id = self._read_reg(Register.PARTID)

        if id_ad != DEVID_AD or id_mst != DEVID_MST or part_id != PARTID:
            raise DeviceNotFoundError(
                f"Device ID mismatch: DEVID_AD=0x{id_ad:02X}, "
                f"DEVID_MST=0x{id_mst:02X}, PARTID=0x{part_id:02X}"
            )

        range_bits = self._read_reg(Register.RANGE) & RANGE_SEL_MASK
        try:
            detected_range = Range(range_bits)
        except ValueError as exc:
            raise InvalidConfigurationError(
                f"Invalid RANGE register encoding: 0x{range_bits:02X}"
            ) from exc

        power_ctl = self._read_reg(Register.POWER_CTL)
        if not power_ctl & 0x01:
            self._write_reg(Register.POWER_CTL, power_ctl | 0x01)
        self._range = detected_range
        self._initialized = True
        return True

    def reset(self) -> None:
        """Perform a software reset after a successful probe."""
        self._check_init()
        self._write_reg(Register.RESET, RESET_CODE)
        self._delay_ms(10)
        self._range = Range.G2

    def set_range(self, range_val: Range) -> None:
        """Set range in standby, restoring measurement mode when necessary."""
        self._check_init()
        if range_val not in (Range.G2, Range.G4, Range.G8):
            raise InvalidConfigurationError(f"Invalid range: {range_val}")

        original_power_ctl = self._enter_configuration_standby()
        try:
            reg = self._read_reg(Register.RANGE)
            reg = (reg & ~RANGE_SEL_MASK) | (int(range_val) & RANGE_SEL_MASK)
            self._write_reg(Register.RANGE, reg)
            self._range = range_val
        finally:
            self._restore_configuration_mode(original_power_ctl)

    def get_range(self) -> Range:
        """Read the currently configured range from hardware."""
        self._check_init()
        reg = self._read_reg(Register.RANGE)
        range_bits = reg & RANGE_SEL_MASK
        try:
            return Range(range_bits)
        except ValueError as exc:
            raise InvalidConfigurationError(
                f"Invalid RANGE register encoding: 0x{range_bits:02X}"
            ) from exc

    def set_power_mode(self, mode: PowerMode) -> None:
        """Set power mode after a successful probe."""
        self._check_init()
        if mode not in (PowerMode.STANDBY, PowerMode.MEASUREMENT):
            raise InvalidConfigurationError(f"Invalid power mode: {mode}")
        reg = self._read_reg(Register.POWER_CTL)
        if mode == PowerMode.STANDBY:
            reg |= 1
        else:
            reg &= ~1
        self._write_reg(Register.POWER_CTL, reg)

    def set_odr(self, odr: ODR) -> None:
        """Set output data rate in standby and restore the prior mode."""
        self._check_init()
        if odr not in ODR.__members__.values():
            raise InvalidConfigurationError(f"Invalid ODR: {odr}")

        original_power_ctl = self._enter_configuration_standby()
        try:
            reg = self._read_reg(Register.FILTER)
            reg = (reg & FILTER_HPF_MASK) | ((int(odr) << FILTER_ODR_SHIFT) & FILTER_ODR_MASK)
            self._write_reg(Register.FILTER, reg)
        finally:
            self._restore_configuration_mode(original_power_ctl)

    @staticmethod
    def _validate_data_ready_config(config: DataReadyConfig) -> None:
        if not isinstance(config, DataReadyConfig):
            raise InvalidConfigurationError("config must be a DataReadyConfig")
        if not isinstance(config.dedicated_drdy_enabled, bool):
            raise InvalidConfigurationError("dedicated_drdy_enabled must be bool")
        if not isinstance(config.route_to_int1, bool) or not isinstance(config.route_to_int2, bool):
            raise InvalidConfigurationError("interrupt routing fields must be bool")
        if config.interrupt_polarity not in (
            InterruptPolarity.ACTIVE_LOW,
            InterruptPolarity.ACTIVE_HIGH,
        ):
            raise InvalidConfigurationError("invalid INT1/INT2 polarity")

    def _read_internal_timing_registers(self) -> tuple[int, int, int]:
        sync = self._read_reg(Register.SYNC)
        if sync & SYNC_TIMING_MASK:
            raise UnsupportedConfigurationError(
                "external clock/synchronization pin multiplexing is outside "
                "the maintained data-ready contract"
            )
        return (
            self._read_reg(Register.INT_MAP),
            self._read_reg(Register.RANGE),
            self._read_reg(Register.POWER_CTL),
        )

    def get_data_ready_config(self) -> DataReadyConfig:
        """Read dedicated DRDY and DATA_RDY-to-INT routing without clearing STATUS."""
        self._check_init()
        int_map, range_reg, power_ctl = self._read_internal_timing_registers()
        return DataReadyConfig(
            dedicated_drdy_enabled=not bool(power_ctl & POWER_DRDY_OFF),
            route_to_int1=bool(int_map & INT_MAP_RDY_EN1),
            route_to_int2=bool(int_map & INT_MAP_RDY_EN2),
            interrupt_polarity=(
                InterruptPolarity.ACTIVE_HIGH
                if range_reg & RANGE_INT_POL
                else InterruptPolarity.ACTIVE_LOW
            ),
        )

    def _restore_data_ready_state(self, *, power_ctl: int, range_reg: int, int_map: int) -> None:
        failures: list[BaseException] = []
        for reg, value in (
            (Register.POWER_CTL, power_ctl | 0x01),
            (Register.RANGE, range_reg),
            (Register.INT_MAP, int_map),
            (Register.POWER_CTL, power_ctl),
        ):
            try:
                self._write_reg(reg, value)
            except BusError as exc:
                failures.append(exc)
        if failures:
            raise RestoreError(tuple(failures))

    def configure_data_ready(self, config: DataReadyConfig) -> None:
        """Configure internal-clock DRDY/INT routing with exact rollback.

        Dedicated DRDY is always active high. ``interrupt_polarity`` affects only
        INT1/INT2. External synchronization modes are rejected because DRDY and
        INT2 are multiplexed differently in those modes.
        """
        self._check_init()
        self._validate_data_ready_config(config)
        int_map, range_reg, power_ctl = self._read_internal_timing_registers()

        target_int_map = int_map & ~INT_MAP_DATA_READY_MASK
        if config.route_to_int1:
            target_int_map |= INT_MAP_RDY_EN1
        if config.route_to_int2:
            target_int_map |= INT_MAP_RDY_EN2

        target_range = range_reg & ~RANGE_INT_POL
        if config.interrupt_polarity == InterruptPolarity.ACTIVE_HIGH:
            target_range |= RANGE_INT_POL

        target_power = power_ctl & ~POWER_DRDY_OFF
        if not config.dedicated_drdy_enabled:
            target_power |= POWER_DRDY_OFF

        try:
            self._write_reg(Register.POWER_CTL, power_ctl | 0x01)
            self._write_reg(Register.RANGE, target_range)
            self._write_reg(Register.INT_MAP, target_int_map)
            self._write_reg(Register.POWER_CTL, target_power)
        except BusError:
            self._restore_data_ready_state(
                power_ctl=power_ctl, range_reg=range_reg, int_map=int_map
            )
            raise

    @staticmethod
    def _offset_register(axis: Axis) -> Register:
        try:
            return {
                Axis.X: Register.OFFSET_X_H,
                Axis.Y: Register.OFFSET_Y_H,
                Axis.Z: Register.OFFSET_Z_H,
            }[Axis(axis)]
        except (ValueError, KeyError) as exc:
            raise InvalidConfigurationError(f"Invalid axis: {axis}") from exc

    def read_offset(self, axis: Axis) -> int:
        """Read a signed 16-bit hardware offset; one count equals 16 raw LSB."""
        self._check_init()
        reg = self._offset_register(axis)
        return int.from_bytes(self._read_exact(reg, 2), byteorder="big", signed=True)

    def write_offset(self, axis: Axis, offset: int) -> None:
        """Write a volatile signed 16-bit offset in standby and restore mode."""
        self._check_init()
        reg = self._offset_register(axis)
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise InvalidConfigurationError("offset must be an integer")
        if not -(1 << 15) <= offset <= (1 << 15) - 1:
            raise InvalidConfigurationError("offset is outside the signed 16-bit range")

        original_power_ctl = self._enter_configuration_standby()
        try:
            self._write_exact(reg, offset.to_bytes(2, byteorder="big", signed=True))
        finally:
            self._restore_configuration_mode(original_power_ctl)

    # ------------------------------------------------------------------
    # Electrostatic self-test
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_self_test_config(config: SelfTestConfig) -> None:
        bounded = (
            ("sample_count", config.sample_count, 1, 1024),
            ("settle_samples", config.settle_samples, 0, 1024),
            ("max_ready_polls", config.max_ready_polls, 1, 60000),
            ("poll_delay_ms", config.poll_delay_ms, 1, 1000),
        )
        for name, value, minimum, maximum in bounded:
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidConfigurationError(f"{name} must be an integer")
            if not minimum <= value <= maximum:
                raise InvalidConfigurationError(f"{name} must be between {minimum} and {maximum}")
        if config.thresholds is None:
            return
        for axis_name in ("x", "y", "z"):
            minimum = getattr(config.thresholds.min_abs_delta_g, axis_name)
            maximum = getattr(config.thresholds.max_abs_delta_g, axis_name)
            if (
                not math.isfinite(minimum)
                or not math.isfinite(maximum)
                or minimum < 0.0
                or maximum < minimum
            ):
                raise InvalidConfigurationError(
                    f"Invalid self-test threshold range for axis {axis_name}"
                )

    def _wait_for_data_ready(self, config: SelfTestConfig) -> None:
        for _ in range(config.max_ready_polls):
            if self._read_reg(Register.STATUS) & STATUS_DATA_RDY:
                return
            self._delay_ms(config.poll_delay_ms)
        raise DataReadyTimeoutError("DATA_RDY did not assert within the bounded poll budget")

    def _collect_self_test_mean(self, config: SelfTestConfig) -> AccelXYZ:
        for _ in range(config.settle_samples):
            self._wait_for_data_ready(config)
            self.read_raw()
        sum_x = 0
        sum_y = 0
        sum_z = 0
        for _ in range(config.sample_count):
            self._wait_for_data_ready(config)
            sample = self.read_raw()
            sum_x += sample.x
            sum_y += sample.y
            sum_z += sample.z
        scale = SCALE_2G_G_PER_LSB / config.sample_count
        return AccelXYZ(sum_x * scale, sum_y * scale, sum_z * scale)

    @staticmethod
    def _thresholds_pass(thresholds: SelfTestThresholds, value: AccelXYZ) -> bool:
        return all(
            getattr(thresholds.min_abs_delta_g, axis)
            <= getattr(value, axis)
            <= getattr(thresholds.max_abs_delta_g, axis)
            for axis in ("x", "y", "z")
        )

    def _restore_self_test_state(
        self,
        *,
        range_reg: int,
        filter_reg: int,
        power_ctl_reg: int,
        self_test_reg: int,
        cached_range: Range,
    ) -> None:
        standby = power_ctl_reg | 0x01
        failures: list[BaseException] = []
        for reg, value in (
            (Register.SELF_TEST, self_test_reg),
            (Register.POWER_CTL, standby),
            (Register.RANGE, range_reg),
            (Register.FILTER, filter_reg),
            (Register.POWER_CTL, power_ctl_reg),
        ):
            try:
                self._write_reg(reg, value)
            except BusError as exc:
                failures.append(exc)
        self._range = cached_range
        if failures:
            raise RestoreError(tuple(failures))

    def run_self_test(self, config: SelfTestConfig | None = None) -> SelfTestResult:
        """Measure Rev.D ST1+ST2 response and restore all prior state exactly.

        Datasheet typical values are reported by documentation but are not used
        as default normative thresholds. Supply ``SelfTestThresholds`` only for
        a caller-owned, fixture-specific policy.
        """
        self._check_init()
        selected = config or SelfTestConfig()
        self._validate_self_test_config(selected)
        range_reg = self._read_reg(Register.RANGE)
        filter_reg = self._read_reg(Register.FILTER)
        power_ctl_reg = self._read_reg(Register.POWER_CTL)
        self_test_reg = self._read_reg(Register.SELF_TEST)
        cached_range = self._range
        if self_test_reg & SELF_TEST_MASK:
            raise DeviceStateError("ST1/ST2 are already active")

        standby = power_ctl_reg | 0x01
        range_2g = (range_reg & ~RANGE_SEL_MASK) | int(Range.G2)
        filter_125hz = (filter_reg & ~FILTER_ODR_MASK) | int(ODR.HZ_125)
        self_test_off = self_test_reg & ~SELF_TEST_MASK
        measurement = power_ctl_reg & ~0x01
        try:
            self._write_reg(Register.POWER_CTL, standby)
            self._write_reg(Register.RANGE, range_2g)
            self._write_reg(Register.FILTER, filter_125hz)
            self._write_reg(Register.SELF_TEST, self_test_off)
            self._write_reg(Register.POWER_CTL, measurement)
            self._range = Range.G2

            self._write_reg(Register.SELF_TEST, self_test_off | 0x01)
            baseline = self._collect_self_test_mean(selected)
            self._write_reg(Register.SELF_TEST, self_test_off | SELF_TEST_MASK)
            stimulated = self._collect_self_test_mean(selected)
            delta = AccelXYZ(
                stimulated.x - baseline.x,
                stimulated.y - baseline.y,
                stimulated.z - baseline.z,
            )
            absolute = AccelXYZ(abs(delta.x), abs(delta.y), abs(delta.z))
            evaluated = selected.thresholds is not None
            passed = (
                True
                if selected.thresholds is None
                else self._thresholds_pass(selected.thresholds, absolute)
            )
            result = SelfTestResult(
                baseline_g=baseline,
                stimulated_g=stimulated,
                delta_g=delta,
                abs_delta_g=absolute,
                samples=selected.sample_count,
                thresholds_evaluated=evaluated,
                thresholds_passed=passed,
            )
            if not passed:
                raise SelfTestThresholdError(result)
            return result
        finally:
            self._restore_self_test_state(
                range_reg=range_reg,
                filter_reg=filter_reg,
                power_ctl_reg=power_ctl_reg,
                self_test_reg=self_test_reg,
                cached_range=cached_range,
            )

    # ------------------------------------------------------------------
    # Data readout
    # ------------------------------------------------------------------

    def read_raw(self) -> RawXYZ:
        """Read raw 20-bit acceleration data for all three axes."""
        self._check_init()
        data = self._read_exact(Register.XDATA3, 9)
        x = _decode_raw20(data[0], data[1], data[2])
        y = _decode_raw20(data[3], data[4], data[5])
        z = _decode_raw20(data[6], data[7], data[8])
        return RawXYZ(x, y, z)

    def read_acceleration_g(self) -> AccelXYZ:
        """Read acceleration in g (gravity multiples)."""
        raw = self.read_raw()
        scale = _range_to_scale(self._range)
        return AccelXYZ(
            x=raw.x * scale,
            y=raw.y * scale,
            z=raw.z * scale,
        )

    def read_acceleration_mps2(self) -> AccelXYZ:
        """Read acceleration in m/s²."""
        accel = self.read_acceleration_g()
        return AccelXYZ(
            x=accel.x * STANDARD_GRAVITY_M_S2,
            y=accel.y * STANDARD_GRAVITY_M_S2,
            z=accel.z * STANDARD_GRAVITY_M_S2,
        )

    def read_temperature_raw(self) -> int:
        """Read a coherent 12-bit unsigned temperature sample.

        TEMP2/TEMP1 are not double-buffered. Read both bytes in one burst,
        then re-read TEMP2 and retry if its data nibble changed. Reserved
        TEMP2 bits 7:4 are ignored.
        """
        self._check_init()
        for _ in range(TEMP_READ_ATTEMPTS):
            data = self._read_exact(Register.TEMP2, 2)
            confirm = self._read_exact(Register.TEMP2, 1)

            temp2 = data[0] & TEMP2_DATA_MASK
            if temp2 == (confirm[0] & TEMP2_DATA_MASK):
                return (temp2 << 8) | data[1]

        raise DataNotReadyError("Temperature sample changed during all read attempts")

    def read_temperature_c(self) -> float:
        """
        Read temperature in degrees Celsius.

        Datasheet Rev.D: 12-bit unsigned, nominal intercept 1885 LSB at 25°C,
        slope -9.05 LSB/°C. Formula: T(°C) = 25.0 + (raw - 1885.0) / -9.05
        """
        raw = self.read_temperature_raw()
        return TEMP_INTERCEPT_C + (raw - TEMP_INTERCEPT_LSB) / TEMP_SLOPE_LSB_PER_C

    def read_status(self) -> int:
        """Read the status register."""
        self._check_init()
        return self._read_reg(Register.STATUS)

    def read_fifo_entries(self) -> int:
        """Read valid FIFO axis locations, not complete XYZ sample count.

        Rev.D defines a range of 0..96 locations. A remainder of one or two
        locations is valid but does not form a complete XYZ sample. Reserved bit
        7 and values above 96 are rejected as :class:`FifoFormatError`.
        """
        self._check_init()
        raw = self._read_reg(Register.FIFO_ENTRIES)
        locations = raw & 0x7F
        if raw & 0x80 or locations > FIFO_MAX_LOCATIONS:
            raise FifoFormatError(f"Invalid FIFO_ENTRIES value: 0x{raw:02X}")
        return locations

    def read_fifo_samples(self, max_samples: int) -> FifoReadResult:
        """Read up to ``max_samples`` complete XYZ samples without blocking.

        ``max_samples`` must be 1..32. STATUS is read first and therefore uses
        the device's documented clear-on-read behavior. FIFO overrun aborts
        without consuming data. Each sample is one sustained nine-byte read.
        Format/empty failures expose the valid prefix and exact consumed-location
        count. A FIFO_DATA bus failure marks consumption as indeterminate because
        the hardware may have popped data before the backend reported failure.
        """
        self._check_init()
        if isinstance(max_samples, bool) or not 1 <= max_samples <= FIFO_MAX_SAMPLES:
            raise InvalidConfigurationError("max_samples must be in the range 1..32")

        samples: list[RawXYZ] = []
        consumed_locations = 0
        try:
            status = self._read_reg(Register.STATUS)
            if status & STATUS_FIFO_OVR:
                raise FifoOverrunError("FIFO overrun indicates lost oldest data")
            available_locations = self.read_fifo_entries()
            target = min(available_locations // 3, max_samples)
            if target == 0:
                raise FifoEmptyError("FIFO contains no complete XYZ sample")
            for _ in range(target):
                try:
                    payload = self._read_exact(Register.FIFO_DATA, FIFO_BYTES_PER_SAMPLE)
                except BusError as exc:
                    raise FifoBusError(
                        "FIFO_DATA transfer failed; hardware consumption is indeterminate",
                        tuple(samples),
                        consumed_locations,
                        True,
                    ) from exc
                consumed_locations += 3
                try:
                    samples.append(decode_fifo_sample(payload))
                except FifoEmptyError as exc:
                    raise FifoEmptyError(str(exc), tuple(samples), consumed_locations) from exc
                except FifoFormatError as exc:
                    raise FifoFormatError(str(exc), tuple(samples), consumed_locations) from exc
        except FifoBusError:
            raise
        except FifoReadError:
            raise
        except BusError as exc:
            raise FifoBusError(
                "FIFO status/count transfer failed",
                tuple(samples),
                consumed_locations,
                False,
            ) from exc

        return FifoReadResult(
            samples=tuple(samples),
            available_locations=available_locations,
            consumed_locations=consumed_locations,
            remaining_locations=available_locations - consumed_locations,
        )


# ------------------------------------------------------------------
# Stateless conversion functions
# ------------------------------------------------------------------

FIFO_MAX_LOCATIONS = 96
FIFO_BYTES_PER_LOCATION = 3
FIFO_BYTES_PER_SAMPLE = 9
FIFO_MAX_SAMPLES = FIFO_MAX_LOCATIONS // 3


def decode_fifo_location(payload: bytes) -> FifoLocation:
    """Decode one exact three-byte FIFO axis location."""
    if len(payload) != FIFO_BYTES_PER_LOCATION:
        raise FifoFormatError(f"FIFO location must be exactly 3 bytes, got {len(payload)}")
    if payload[2] & 0x0C:
        raise FifoFormatError("FIFO virtual bits 3:2 must be zero")
    if payload[2] & 0x02:
        raise FifoEmptyError("FIFO location carries the empty/invalid marker")
    return FifoLocation(
        raw=_decode_raw20(payload[0], payload[1], payload[2]),
        is_x_axis=bool(payload[2] & 0x01),
    )


def decode_fifo_sample(payload: bytes) -> RawXYZ:
    """Decode one exact X/Y/Z FIFO sample with marker-order validation."""
    if len(payload) != FIFO_BYTES_PER_SAMPLE:
        raise FifoFormatError(f"FIFO sample must be exactly 9 bytes, got {len(payload)}")
    axes = tuple(
        decode_fifo_location(payload[offset : offset + FIFO_BYTES_PER_LOCATION])
        for offset in range(0, FIFO_BYTES_PER_SAMPLE, FIFO_BYTES_PER_LOCATION)
    )
    if not axes[0].is_x_axis or axes[1].is_x_axis or axes[2].is_x_axis:
        raise FifoFormatError("FIFO marker order must be X, Y, Z")
    return RawXYZ(x=axes[0].raw, y=axes[1].raw, z=axes[2].raw)


def _decode_raw20(b0: int, b1: int, b2: int) -> int:
    """
    Decode three bytes into a 20-bit two's complement integer.

    Args:
        b0: MSB (first byte from XDATA3/YDATA3/ZDATA3)
        b1: Middle byte
        b2: LSB (last byte)

    Returns:
        Sign-extended integer in range [-524288, 524287]
    """
    raw = (b0 << 12) | (b1 << 4) | (b2 >> 4)
    if raw & 0x80000:
        raw -= 0x100000
    return raw


def raw_to_g(raw: int, range_val: Range) -> float:
    """Convert a decoded raw value to g."""
    return raw * _range_to_scale(range_val)


def raw_to_mps2(raw: int, range_val: Range) -> float:
    """Convert a decoded raw value to m/s²."""
    return raw * _range_to_scale(range_val) * STANDARD_GRAVITY_M_S2


def _range_to_scale(range_val: Range) -> float:
    if range_val == Range.G2:
        return SCALE_2G_G_PER_LSB
    elif range_val == Range.G4:
        return SCALE_4G_G_PER_LSB
    elif range_val == Range.G8:
        return SCALE_8G_G_PER_LSB
    return SCALE_4G_G_PER_LSB
