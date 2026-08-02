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


class FifoReadError(ADXL355Error):
    """Base for FIFO marker, empty, overrun, and framing failures."""

    def __init__(
        self,
        message: str,
        partial_samples: tuple[object, ...] = (),
        consumed_locations: int = 0,
        consumption_indeterminate: bool = False,
    ) -> None:
        super().__init__(message)
        self.partial_samples = partial_samples
        self.consumed_locations = consumed_locations
        self.consumption_indeterminate = consumption_indeterminate


class FifoEmptyError(FifoReadError):
    """FIFO had no complete sample or returned the empty/invalid marker."""


class FifoOverrunError(FifoReadError):
    """FIFO overrun status indicated that the oldest data was lost."""


class FifoFormatError(FifoReadError):
    """FIFO count, marker order, virtual bits, or payload length was malformed."""


class FifoBusError(BusError):
    """FIFO transfer failed after zero or more complete samples were consumed."""

    def __init__(
        self,
        message: str,
        partial_samples: tuple[object, ...] = (),
        consumed_locations: int = 0,
        consumption_indeterminate: bool = True,
    ) -> None:
        super().__init__(message)
        self.partial_samples = partial_samples
        self.consumed_locations = consumed_locations
        self.consumption_indeterminate = consumption_indeterminate
