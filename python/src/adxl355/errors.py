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


class DataReadyTimeoutError(ADXL355Error):
    """Raised when bounded DATA_RDY polling expires."""


class SelfTestThresholdError(ADXL355Error):
    """Raised when measured self-test response violates caller-owned thresholds."""

    def __init__(self, result: object) -> None:
        super().__init__("Self-test response violated caller-owned thresholds")
        self.result = result


class RestoreError(ADXL355Error):
    """Raised when one or more saved hardware registers cannot be restored."""

    def __init__(self, failures: tuple[BaseException, ...]) -> None:
        super().__init__(f"Failed to restore {len(failures)} self-test state write(s)")
        self.failures = failures
