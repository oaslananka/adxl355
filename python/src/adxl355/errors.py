"""ADXL355 exception hierarchy."""


class ADXL355Error(Exception):
    """Base exception for all ADXL355 errors."""


class BusError(ADXL355Error):
    """Bus communication error (SPI/I2C transfer failed)."""


class DeviceNotFoundError(ADXL355Error):
    """Probe failed: identity registers didn't match expected values."""


class DeviceStateError(ADXL355Error):
    """Operation requires a successful probe or a different device state."""


class InvalidConfigurationError(ADXL355Error):
    """Invalid configuration argument."""


class DataNotReadyError(ADXL355Error):
    """Data not yet available."""
