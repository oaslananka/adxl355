"""ADXL355 accelerometer driver - cross-platform Python package."""

from adxl355._version import __version__
from adxl355.constants import (
    SCALE_2G_G_PER_LSB,
    SCALE_4G_G_PER_LSB,
    SCALE_8G_G_PER_LSB,
    STANDARD_GRAVITY_M_S2,
)
from adxl355.device import ADXL355
from adxl355.errors import (
    ADXL355Error,
    BusError,
    DataNotReadyError,
    DeviceNotFoundError,
    DeviceStateError,
    InvalidConfigurationError,
)
from adxl355.registers import ODR, PowerMode, Range, Register
from adxl355.transport import Transport
from adxl355.types import AccelXYZ, RawXYZ

__all__ = [
    "__version__",
    "ADXL355",
    "Register",
    "Range",
    "PowerMode",
    "ODR",
    "RawXYZ",
    "AccelXYZ",
    "Transport",
    "ADXL355Error",
    "BusError",
    "DeviceNotFoundError",
    "DeviceStateError",
    "InvalidConfigurationError",
    "DataNotReadyError",
    "STANDARD_GRAVITY_M_S2",
    "SCALE_2G_G_PER_LSB",
    "SCALE_4G_G_PER_LSB",
    "SCALE_8G_G_PER_LSB",
]
