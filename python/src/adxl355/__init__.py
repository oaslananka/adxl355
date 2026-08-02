"""ADXL355 accelerometer driver - cross-platform Python package."""

from adxl355._version import __version__
from adxl355.calibration import calculate_offset
from adxl355.constants import (
    SCALE_2G_G_PER_LSB,
    SCALE_4G_G_PER_LSB,
    SCALE_8G_G_PER_LSB,
    STANDARD_GRAVITY_M_S2,
)
from adxl355.device import ADXL355, decode_fifo_location, decode_fifo_sample
from adxl355.errors import (
    ADXL355Error,
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
    ODR,
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

__all__ = [
    "__version__",
    "ADXL355",
    "decode_fifo_location",
    "decode_fifo_sample",
    "Axis",
    "calculate_offset",
    "Register",
    "Range",
    "PowerMode",
    "ODR",
    "InterruptPolarity",
    "DataReadyConfig",
    "RawXYZ",
    "FifoLocation",
    "FifoReadResult",
    "SelfTestConfig",
    "SelfTestResult",
    "SelfTestThresholds",
    "AccelXYZ",
    "Transport",
    "ADXL355Error",
    "BusError",
    "FifoReadError",
    "FifoBusError",
    "FifoEmptyError",
    "FifoOverrunError",
    "FifoFormatError",
    "DataReadyTimeoutError",
    "DeviceNotFoundError",
    "DeviceStateError",
    "InvalidConfigurationError",
    "UnsupportedConfigurationError",
    "RestoreError",
    "SelfTestThresholdError",
    "DataNotReadyError",
    "STANDARD_GRAVITY_M_S2",
    "SCALE_2G_G_PER_LSB",
    "SCALE_4G_G_PER_LSB",
    "SCALE_8G_G_PER_LSB",
]
