"""Main ADXL355 device driver."""

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
    DeviceNotFoundError,
    InvalidConfigurationError,
)
from adxl355.registers import (
    FILTER_HPF_MASK,
    FILTER_ODR_MASK,
    FILTER_ODR_SHIFT,
    ODR,
    RANGE_SEL_MASK,
    PowerMode,
    Range,
    Register,
)
from adxl355.transport import Transport
from adxl355.types import AccelXYZ, RawXYZ


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

    def _read_reg(self, reg: int) -> int:
        data = self._transport.read_register(reg, 1)
        return data[0]

    def _write_reg(self, reg: int, value: int) -> None:
        self._transport.write_register(reg, bytes([value]))

    def _check_init(self) -> None:
        if not self._initialized:
            raise DeviceNotFoundError("Device not initialized. Call probe() first.")

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

        # Enter standby mode after probe. Commit state only after all bus operations succeed.
        self._write_reg(Register.POWER_CTL, PowerMode.STANDBY)
        self._range = detected_range
        self._initialized = True
        return True

    def reset(self) -> None:
        """Perform a software reset."""
        self._write_reg(Register.RESET, RESET_CODE)
        self._transport.delay_ms(10)
        self._range = Range.G2

    def set_range(self, range_val: Range) -> None:
        """Set the acceleration range.

        Datasheet Rev.D, Table 42: range in bits 1:0 (0x01=2g, 0x02=4g, 0x03=8g).
        Unrelated bits (INT_POL, I2C_HS) are preserved.
        """
        if range_val not in (Range.G2, Range.G4, Range.G8):
            raise InvalidConfigurationError(f"Invalid range: {range_val}")
        reg = self._read_reg(Register.RANGE)
        reg = (reg & ~RANGE_SEL_MASK) | (int(range_val) & RANGE_SEL_MASK)
        self._write_reg(Register.RANGE, reg)
        self._range = range_val

    def get_range(self) -> Range:
        """Read the currently configured range from hardware."""
        reg = self._read_reg(Register.RANGE)
        range_bits = reg & RANGE_SEL_MASK
        try:
            return Range(range_bits)
        except ValueError as exc:
            raise InvalidConfigurationError(
                f"Invalid RANGE register encoding: 0x{range_bits:02X}"
            ) from exc

    def set_power_mode(self, mode: PowerMode) -> None:
        """Set power mode (standby or measurement).

        Datasheet Rev.D, Table 43: bit 0 = 1 => standby, bit 0 = 0 => measurement.
        """
        reg = self._read_reg(Register.POWER_CTL)
        if mode == PowerMode.STANDBY:
            reg |= 1
        else:
            reg &= ~1
        self._write_reg(Register.POWER_CTL, reg)

    def set_odr(self, odr: ODR) -> None:
        """Set output data rate.

        Datasheet Rev.D, Table 38: ODR_LPF in bits 3:0, HPF_CORNER in bits 6:4.
        """
        if odr not in ODR.__members__.values():
            raise InvalidConfigurationError(f"Invalid ODR: {odr}")
        reg = self._read_reg(Register.FILTER)
        reg = (reg & FILTER_HPF_MASK) | ((int(odr) << FILTER_ODR_SHIFT) & FILTER_ODR_MASK)
        self._write_reg(Register.FILTER, reg)

    # ------------------------------------------------------------------
    # Data readout
    # ------------------------------------------------------------------

    def read_raw(self) -> RawXYZ:
        """Read raw 20-bit acceleration data for all three axes."""
        data = self._transport.read_register(Register.XDATA3, 9)
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
        for _ in range(TEMP_READ_ATTEMPTS):
            data = self._transport.read_register(Register.TEMP2, 2)
            if len(data) != 2:
                raise BusError(f"Short temperature read: expected 2 bytes, got {len(data)}")
            confirm = self._transport.read_register(Register.TEMP2, 1)
            if len(confirm) != 1:
                raise BusError(
                    f"Short TEMP2 confirmation read: expected 1 byte, got {len(confirm)}"
                )

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
        return self._read_reg(Register.STATUS)

    def read_fifo_entries(self) -> int:
        """Read the number of valid samples in the FIFO."""
        return self._read_reg(Register.FIFO_ENTRIES)


# ------------------------------------------------------------------
# Stateless conversion functions
# ------------------------------------------------------------------


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
