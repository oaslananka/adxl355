"""Abstract transport interface for ADXL355 communication."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Transport(Protocol):
    """
    Abstract bus transport for ADXL355 communication.

    Implementations wrap SPI, I2C, or mock backends.
    """

    def read_register(self, reg: int, length: int = 1) -> bytes:
        """Return exactly `length` bytes or raise an exception.

        Zero-length, truncated, and overlong payloads violate the transport
        contract and are converted to :class:`adxl355.errors.BusError` by the
        driver.
        """
        ...

    def write_register(self, reg: int, data: bytes) -> None:
        """Write all bytes or raise an exception; partial success is invalid."""
        ...

    def delay_ms(self, ms: int) -> None:
        """Blocking delay in milliseconds (optional)."""
        ...
