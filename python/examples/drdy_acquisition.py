"""Bounded event-driven ADXL355 acquisition primitives.

This module contains no board-specific GPIO code. A caller supplies a
``ReadyEventSource`` whose timestamps and sequence numbers come from the host
GPIO event API. The Linux example in ``linux_drdy.py`` uses libgpiod v2.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic_ns
from typing import Callable, Protocol

from adxl355.errors import BusError, InvalidConfigurationError
from adxl355.registers import STATUS_FIFO_OVR
from adxl355.types import RawXYZ


@dataclass(frozen=True)
class ReadyEvent:
    """One rising-edge event using a monotonic timestamp and line sequence."""

    timestamp_ns: int
    line_sequence: int


class ReadyEventSource(Protocol):
    """Host-owned event source; implementations must block rather than busy-wait."""

    def wait_event(self, timeout_s: float) -> ReadyEvent | None: ...

    def close(self) -> None: ...


class SampleDevice(Protocol):
    """Minimum sensor surface required by the acquisition loop."""

    def read_status(self) -> int: ...

    def read_raw(self) -> RawXYZ: ...


@dataclass(frozen=True)
class ContinuousAcquisitionConfig:
    """Finite acquisition bounds and tolerated GPIO sequence gaps."""

    sample_count: int = 32
    timeout_s: float = 5.0
    max_missed_events: int = 0


@dataclass(frozen=True)
class TimedRawSample:
    """Raw sample associated with the kernel edge and host capture timestamps."""

    event_timestamp_ns: int
    captured_timestamp_ns: int
    line_sequence: int
    raw: RawXYZ


@dataclass(frozen=True)
class ContinuousAcquisitionResult:
    """Finite acquisition output and explicit event-loss/overrun counters."""

    samples: tuple[TimedRawSample, ...]
    missed_events: int
    fifo_overruns: int
    started_ns: int
    completed_ns: int


class ContinuousAcquisitionError(Exception):
    """Base acquisition error carrying every sample completed before failure."""

    def __init__(self, message: str, result: ContinuousAcquisitionResult) -> None:
        super().__init__(message)
        self.result = result


class ReadyTimeoutError(ContinuousAcquisitionError):
    """The bounded overall deadline expired before the next DRDY edge."""


class ReadySourceError(ContinuousAcquisitionError):
    """The host GPIO event source failed."""


class MissedReadyEventError(ContinuousAcquisitionError):
    """GPIO line sequence numbers exceeded the configured loss budget."""


class ReadyEventOrderError(ContinuousAcquisitionError):
    """GPIO event sequence or timestamps moved backwards."""


class AcquisitionOverrunError(ContinuousAcquisitionError):
    """STATUS.FIFO_OVR indicated that acquisition data was lost."""


class AcquisitionBusError(ContinuousAcquisitionError):
    """The sensor transport failed after zero or more completed samples."""


def _validate_config(config: ContinuousAcquisitionConfig) -> None:
    if isinstance(config.sample_count, bool) or not 1 <= config.sample_count <= 4096:
        raise InvalidConfigurationError("sample_count must be in the range 1..4096")
    if isinstance(config.timeout_s, bool) or not 0.001 <= config.timeout_s <= 3600.0:
        raise InvalidConfigurationError("timeout_s must be in the range 0.001..3600")
    if isinstance(config.max_missed_events, bool) or not 0 <= config.max_missed_events <= 1_000_000:
        raise InvalidConfigurationError("max_missed_events must be in the range 0..1000000")


def acquire_continuous(
    device: SampleDevice,
    source: ReadyEventSource,
    config: ContinuousAcquisitionConfig,
    *,
    clock_ns: Callable[[], int] = monotonic_ns,
) -> ContinuousAcquisitionResult:
    """Collect a finite number of samples from blocking DRDY edge events.

    The function never polls GPIO. ``wait_event`` receives only the remaining
    overall deadline. STATUS is read after each edge so FIFO overrun is surfaced
    before the corresponding data read. Sequence gaps are counted and may be
    tolerated up to ``max_missed_events``.
    """

    _validate_config(config)
    started_ns = clock_ns()
    deadline_ns = started_ns + int(config.timeout_s * 1_000_000_000)
    samples: list[TimedRawSample] = []
    missed_events = 0
    fifo_overruns = 0
    last_sequence: int | None = None
    last_event_timestamp: int | None = None

    def result() -> ContinuousAcquisitionResult:
        return ContinuousAcquisitionResult(
            samples=tuple(samples),
            missed_events=missed_events,
            fifo_overruns=fifo_overruns,
            started_ns=started_ns,
            completed_ns=clock_ns(),
        )

    while len(samples) < config.sample_count:
        remaining_ns = deadline_ns - clock_ns()
        if remaining_ns <= 0:
            raise ReadyTimeoutError("DRDY acquisition deadline expired", result())
        try:
            event = source.wait_event(remaining_ns / 1_000_000_000)
        except Exception as exc:
            raise ReadySourceError("GPIO DRDY event source failed", result()) from exc
        if event is None:
            raise ReadyTimeoutError("DRDY did not assert before the bounded deadline", result())
        if clock_ns() > deadline_ns:
            raise ReadyTimeoutError("DRDY edge arrived after the bounded deadline", result())
        if event.line_sequence <= 0 or event.timestamp_ns < 0:
            raise ReadyEventOrderError("DRDY event metadata is invalid", result())
        if last_sequence is not None:
            if event.line_sequence <= last_sequence:
                raise ReadyEventOrderError("DRDY line sequence did not increase", result())
            if last_event_timestamp is not None and event.timestamp_ns < last_event_timestamp:
                raise ReadyEventOrderError("DRDY monotonic timestamp moved backwards", result())
            missed_events += event.line_sequence - last_sequence - 1
            if missed_events > config.max_missed_events:
                raise MissedReadyEventError(
                    "DRDY line sequence exceeded the configured missed-event budget",
                    result(),
                )
        last_sequence = event.line_sequence
        last_event_timestamp = event.timestamp_ns

        try:
            status = device.read_status()
            if status & STATUS_FIFO_OVR:
                fifo_overruns += 1
                raise AcquisitionOverrunError(
                    "STATUS.FIFO_OVR indicates that acquisition data was lost",
                    result(),
                )
            raw = device.read_raw()
        except AcquisitionOverrunError:
            raise
        except BusError as exc:
            raise AcquisitionBusError(
                "sensor transport failed during acquisition", result()
            ) from exc

        samples.append(
            TimedRawSample(
                event_timestamp_ns=event.timestamp_ns,
                captured_timestamp_ns=clock_ns(),
                line_sequence=event.line_sequence,
                raw=raw,
            )
        )

    return result()
