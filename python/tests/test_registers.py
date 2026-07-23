"""Tests for register definitions and enums."""

from adxl355.constants import (
    ADXL355_I2C_ADDRESS_ALTERNATE,
    ADXL355_I2C_ADDRESS_DEFAULT,
    DEVID_AD,
    DEVID_MST,
    PARTID,
    RESET_CODE,
)
from adxl355.registers import PowerMode, Range, Register


class TestRegisterValues:
    def test_devid_ad(self) -> None:
        assert Register.DEVID_AD == 0x00

    def test_reset(self) -> None:
        assert Register.RESET == 0x2F

    def test_xdata3(self) -> None:
        assert Register.XDATA3 == 0x08

    def test_range_register(self) -> None:
        assert Register.RANGE == 0x2C


class TestRegisterMasks:
    def test_filter_odr_mask(self) -> None:
        from adxl355.registers import FILTER_ODR_MASK
        assert FILTER_ODR_MASK == 0x0F

    def test_filter_hpf_mask(self) -> None:
        from adxl355.registers import FILTER_HPF_MASK
        assert FILTER_HPF_MASK == 0x70

    def test_filter_odr_shift(self) -> None:
        from adxl355.registers import FILTER_ODR_SHIFT
        assert FILTER_ODR_SHIFT == 0

    def test_filter_hpf_shift(self) -> None:
        from adxl355.registers import FILTER_HPF_SHIFT
        assert FILTER_HPF_SHIFT == 4

    def test_range_sel_mask(self) -> None:
        from adxl355.registers import RANGE_SEL_MASK
        assert RANGE_SEL_MASK == 0x03


class TestStatusBits:
    def test_data_rdy_bit(self) -> None:
        from adxl355.registers import STATUS_DATA_RDY
        assert STATUS_DATA_RDY == 1 << 0

    def test_fifo_full_bit(self) -> None:
        from adxl355.registers import STATUS_FIFO_FULL
        assert STATUS_FIFO_FULL == 1 << 1

    def test_fifo_ovr_bit(self) -> None:
        from adxl355.registers import STATUS_FIFO_OVR
        assert STATUS_FIFO_OVR == 1 << 2

    def test_activity_bit(self) -> None:
        from adxl355.registers import STATUS_ACTIVITY
        assert STATUS_ACTIVITY == 1 << 3

    def test_nvm_busy_bit(self) -> None:
        from adxl355.registers import STATUS_NVM_BUSY
        assert STATUS_NVM_BUSY == 1 << 4


class TestRangeEnum:
    def test_values(self) -> None:
        assert Range.G2 == 0x01
        assert Range.G4 == 0x02
        assert Range.G8 == 0x03

    def test_members(self) -> None:
        assert len(Range) == 3


class TestPowerMode:
    def test_values(self) -> None:
        assert PowerMode.STANDBY == 1
        assert PowerMode.MEASUREMENT == 0


class TestI2CAddress:
    def test_default_address(self) -> None:
        assert ADXL355_I2C_ADDRESS_DEFAULT == 0x1D

    def test_alternate_address(self) -> None:
        assert ADXL355_I2C_ADDRESS_ALTERNATE == 0x53


class TestIdentityConstants:
    def test_devid_ad(self) -> None:
        assert DEVID_AD == 0xAD

    def test_devid_mst(self) -> None:
        assert DEVID_MST == 0x1D

    def test_partid(self) -> None:
        assert PARTID == 0xED

    def test_reset_code(self) -> None:
        assert RESET_CODE == 0x52
