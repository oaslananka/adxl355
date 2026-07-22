"""
ADXL355 register addresses, enums, and bit masks.

Preliminary values - verify against official ADXL355 datasheet.
"""

from enum import IntEnum


class Register(IntEnum):
    """ADXL355 register addresses."""

    DEVID_AD = 0x00
    DEVID_MST = 0x01
    PARTID = 0x02
    REVID = 0x03
    STATUS = 0x04
    FIFO_ENTRIES = 0x05
    TEMP2 = 0x06
    TEMP1 = 0x07
    XDATA3 = 0x08
    XDATA2 = 0x09
    XDATA1 = 0x0A
    YDATA3 = 0x0B
    YDATA2 = 0x0C
    YDATA1 = 0x0D
    ZDATA3 = 0x0E
    ZDATA2 = 0x0F
    ZDATA1 = 0x10
    FIFO_DATA = 0x11
    OFFSET_X_H = 0x1E
    OFFSET_X_L = 0x1F
    OFFSET_Y_H = 0x20
    OFFSET_Y_L = 0x21
    OFFSET_Z_H = 0x22
    OFFSET_Z_L = 0x23
    ACT_EN = 0x24
    ACT_THRESH_H = 0x25
    ACT_THRESH_L = 0x26
    ACT_COUNT = 0x27
    FILTER = 0x28
    FIFO_SAMPLES = 0x29
    INT_MAP = 0x2A
    SYNC = 0x2B
    RANGE = 0x2C
    POWER_CTL = 0x2D
    SELF_TEST = 0x2E
    RESET = 0x2F


class Range(IntEnum):
    """Acceleration range selection.

    Datasheet Rev.D, Table 42: 0x01=2g, 0x02=4g, 0x03=8g
    """

    G2 = 0x01
    G4 = 0x02
    G8 = 0x03


class PowerMode(IntEnum):
    """Power mode control.

    Datasheet Rev.D, Table 43: bit 0 = 1 => standby, bit 0 = 0 => measurement.
    """

    STANDBY = 1
    MEASUREMENT = 0


class ODR(IntEnum):
    """Output data rate selection."""

    HZ_4000 = 0
    HZ_2000 = 1
    HZ_1000 = 2
    HZ_500 = 3
    HZ_250 = 4
    HZ_125 = 5
    HZ_62_5 = 6
    HZ_31_25 = 7
    HZ_15_625 = 8
    HZ_7_813 = 9
    HZ_3_906 = 10


# Status register bits (datasheet Rev.D, Table 27)
STATUS_NVM_BUSY = 1 << 4
STATUS_ACTIVITY = 1 << 3
STATUS_FIFO_OVR = 1 << 2
STATUS_FIFO_FULL = 1 << 1
STATUS_DATA_RDY = 1 << 0

# Filter register masks (datasheet Rev.D, Table 38)
# bits 3:0 = ODR_LPF, bits 6:4 = HPF_CORNER
FILTER_ODR_MASK = 0x0F
FILTER_ODR_SHIFT = 0
FILTER_HPF_MASK = 0x70
FILTER_HPF_SHIFT = 4

# Range register mask (datasheet Rev.D, Table 42)
RANGE_SEL_MASK = 0x03


# SPI command byte helpers (datasheet Rev.D, SPI protocol)
def spi_read_cmd(reg: int) -> int:
    """Encode an ADXL355 SPI read command byte."""
    return (reg << 1) | 0x01


def spi_write_cmd(reg: int) -> int:
    """Encode an ADXL355 SPI write command byte."""
    return reg << 1
