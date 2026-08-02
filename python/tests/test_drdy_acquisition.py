"""Bounded event-driven acquisition and Linux lifecycle tests."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast

import pytest

from adxl355 import ODR, DataReadyConfig, PowerMode, Range, RestoreError
from adxl355.errors import BusError, InvalidConfigurationError
from adxl355.registers import STATUS_FIFO_OVR
from adxl355.types import RawXYZ
from examples.drdy_acquisition import (
    AcquisitionBusError,
    AcquisitionOverrunError,
    ContinuousAcquisitionConfig,
    MissedReadyEventError,
    ReadyEvent,
    ReadyEventOrderError,
    ReadySourceError,
    ReadyTimeoutError,
    acquire_continuous,
)
from examples.linux_drdy import (
    GpiodReadyEventSource,
    parse_args,
    run_session,
    summarize_result,
)


class IncrementingClock:
    def __init__(self, start: int = 1_000_000, step: int = 100) -> None:
        self.value = start - step
        self.step = step

    def __call__(self) -> int:
        self.value += self.step
        return self.value


class FakeEventSource:
    def __init__(self, events: list[ReadyEvent | None | BaseException]) -> None:
        self.events = events
        self.timeouts: list[float] = []
        self.closed = False

    def wait_event(self, timeout_s: float) -> ReadyEvent | None:
        self.timeouts.append(timeout_s)
        item = self.events.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self) -> None:
        self.closed = True


class FakeSampleDevice:
    def __init__(
        self,
        *,
        statuses: list[int] | None = None,
        raws: list[RawXYZ] | None = None,
        raw_error_at: int | None = None,
    ) -> None:
        self.statuses = statuses or [0]
        self.raws = raws or [RawXYZ(1, 2, 3)]
        self.raw_error_at = raw_error_at
        self.raw_reads = 0

    def read_status(self) -> int:
        return self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]

    def read_raw(self) -> RawXYZ:
        self.raw_reads += 1
        if self.raw_error_at == self.raw_reads:
            raise BusError("injected sensor failure")
        return self.raws.pop(0) if len(self.raws) > 1 else self.raws[0]


def test_success_preserves_kernel_timestamps_and_sequence() -> None:
    source = FakeEventSource([ReadyEvent(10_000, 1), ReadyEvent(20_000, 2)])
    device = FakeSampleDevice(raws=[RawXYZ(1, 2, 3), RawXYZ(4, 5, 6)])
    result = acquire_continuous(
        device,
        source,
        ContinuousAcquisitionConfig(sample_count=2, timeout_s=1.0),
        clock_ns=IncrementingClock(),
    )

    assert tuple(sample.event_timestamp_ns for sample in result.samples) == (10_000, 20_000)
    assert tuple(sample.line_sequence for sample in result.samples) == (1, 2)
    assert tuple(sample.raw for sample in result.samples) == (
        RawXYZ(1, 2, 3),
        RawXYZ(4, 5, 6),
    )
    assert result.missed_events == 0
    assert result.fifo_overruns == 0
    assert all(timeout > 0 for timeout in source.timeouts)


def test_evidence_summary_reports_uniqueness_sequence_and_timing() -> None:
    result = acquire_continuous(
        FakeSampleDevice(raws=[RawXYZ(1, 2, 3), RawXYZ(4, 5, 6)]),
        FakeEventSource([ReadyEvent(10_000, 7), ReadyEvent(20_000, 8)]),
        ContinuousAcquisitionConfig(sample_count=2, timeout_s=1.0),
        clock_ns=IncrementingClock(start=10_100, step=100),
    )
    summary = summarize_result(result, "i2c")
    assert summary["transport"] == "i2c"
    assert summary["sampleCount"] == 2
    assert summary["uniqueRawSamples"] == 2
    assert summary["firstSequence"] == 7
    assert summary["lastSequence"] == 8
    assert summary["minEventIntervalNs"] == 10_000
    assert summary["maxEventIntervalNs"] == 10_000
    assert isinstance(summary["maxCaptureLatencyNs"], int)


def test_sequence_gap_is_counted_within_budget() -> None:
    result = acquire_continuous(
        FakeSampleDevice(raws=[RawXYZ(1, 1, 1), RawXYZ(2, 2, 2)]),
        FakeEventSource([ReadyEvent(10, 4), ReadyEvent(20, 6)]),
        ContinuousAcquisitionConfig(sample_count=2, timeout_s=1.0, max_missed_events=1),
        clock_ns=IncrementingClock(),
    )
    assert result.missed_events == 1


def test_sequence_gap_beyond_budget_reports_partial_result() -> None:
    with pytest.raises(MissedReadyEventError) as captured:
        acquire_continuous(
            FakeSampleDevice(),
            FakeEventSource([ReadyEvent(10, 1), ReadyEvent(20, 3)]),
            ContinuousAcquisitionConfig(sample_count=2, timeout_s=1.0),
            clock_ns=IncrementingClock(),
        )
    assert len(captured.value.result.samples) == 1
    assert captured.value.result.missed_events == 1


@pytest.mark.parametrize(
    "events",
    [
        [ReadyEvent(10, 2), ReadyEvent(20, 2)],
        [ReadyEvent(20, 1), ReadyEvent(10, 2)],
        [ReadyEvent(-1, 1)],
        [ReadyEvent(1, 0)],
    ],
)
def test_invalid_or_out_of_order_events_are_rejected(events: list[ReadyEvent]) -> None:
    with pytest.raises(ReadyEventOrderError):
        acquire_continuous(
            FakeSampleDevice(),
            FakeEventSource(events),
            ContinuousAcquisitionConfig(sample_count=len(events), timeout_s=1.0),
            clock_ns=IncrementingClock(),
        )


def test_event_returned_after_deadline_is_rejected() -> None:
    clock_values = iter((0, 1, 1_000_000_001, 1_000_000_002))
    with pytest.raises(ReadyTimeoutError):
        acquire_continuous(
            FakeSampleDevice(),
            FakeEventSource([ReadyEvent(10, 1)]),
            ContinuousAcquisitionConfig(sample_count=1, timeout_s=1.0),
            clock_ns=lambda: next(clock_values),
        )


def test_timeout_and_gpio_failure_are_explicit() -> None:
    with pytest.raises(ReadyTimeoutError) as timeout:
        acquire_continuous(
            FakeSampleDevice(),
            FakeEventSource([None]),
            ContinuousAcquisitionConfig(sample_count=1, timeout_s=1.0),
            clock_ns=IncrementingClock(),
        )
    assert timeout.value.result.samples == ()

    with pytest.raises(ReadySourceError) as source_error:
        acquire_continuous(
            FakeSampleDevice(),
            FakeEventSource([OSError("gpio failed")]),
            ContinuousAcquisitionConfig(sample_count=1, timeout_s=1.0),
            clock_ns=IncrementingClock(),
        )
    assert source_error.value.result.samples == ()


def test_overrun_and_sensor_bus_failure_preserve_partial_result() -> None:
    with pytest.raises(AcquisitionOverrunError) as overrun:
        acquire_continuous(
            FakeSampleDevice(statuses=[STATUS_FIFO_OVR]),
            FakeEventSource([ReadyEvent(10, 1)]),
            ContinuousAcquisitionConfig(sample_count=1, timeout_s=1.0),
            clock_ns=IncrementingClock(),
        )
    assert overrun.value.result.fifo_overruns == 1
    assert overrun.value.result.samples == ()

    with pytest.raises(AcquisitionBusError) as bus_error:
        acquire_continuous(
            FakeSampleDevice(
                raws=[RawXYZ(1, 2, 3), RawXYZ(4, 5, 6)],
                raw_error_at=2,
            ),
            FakeEventSource([ReadyEvent(10, 1), ReadyEvent(20, 2)]),
            ContinuousAcquisitionConfig(sample_count=2, timeout_s=1.0),
            clock_ns=IncrementingClock(),
        )
    assert tuple(sample.raw for sample in bus_error.value.result.samples) == (RawXYZ(1, 2, 3),)


@pytest.mark.parametrize(
    "config",
    [
        ContinuousAcquisitionConfig(sample_count=0),
        ContinuousAcquisitionConfig(sample_count=4097),
        ContinuousAcquisitionConfig(timeout_s=0),
        ContinuousAcquisitionConfig(max_missed_events=-1),
    ],
)
def test_acquisition_bounds_are_validated(config: ContinuousAcquisitionConfig) -> None:
    with pytest.raises(InvalidConfigurationError):
        acquire_continuous(
            FakeSampleDevice(),
            FakeEventSource([ReadyEvent(1, 1)]),
            config,
        )


@dataclass
class FakeEdge:
    timestamp_ns: int
    line_seqno: int


class FakeLineRequest:
    def __init__(self, batches: list[list[FakeEdge]]) -> None:
        self.batches = batches
        self.wait_calls = 0
        self.release_calls = 0

    def wait_edge_events(self, timeout: float | None = None) -> bool:
        assert timeout is not None and timeout > 0
        self.wait_calls += 1
        return bool(self.batches)

    def read_edge_events(self, max_events: int | None = None) -> list[FakeEdge]:
        assert max_events == 64
        return self.batches.pop(0)

    def release(self) -> None:
        self.release_calls += 1


class FakeGpiodModule:
    line = SimpleNamespace(
        Direction=SimpleNamespace(INPUT="input"),
        Edge=SimpleNamespace(RISING="rising"),
        Bias=SimpleNamespace(DISABLED="disabled"),
        Clock=SimpleNamespace(MONOTONIC="monotonic"),
    )

    def __init__(self, request: FakeLineRequest) -> None:
        self.request = request
        self.settings_kwargs: dict[str, object] | None = None
        self.request_kwargs: dict[str, object] | None = None

    def LineSettings(self, **kwargs: object) -> object:  # noqa: N802
        self.settings_kwargs = kwargs
        return object()

    def request_lines(self, path: str, **kwargs: object) -> FakeLineRequest:
        self.request_kwargs = {"path": path, **kwargs}
        return self.request


def test_gpiod_source_requests_rising_monotonic_edges_and_buffers_events() -> None:
    request = FakeLineRequest([[FakeEdge(100, 7), FakeEdge(200, 8)]])
    module = FakeGpiodModule(request)
    source = GpiodReadyEventSource("/dev/gpiochip0", 17, module=module)

    assert module.settings_kwargs == {
        "direction": "input",
        "edge_detection": "rising",
        "bias": "disabled",
        "event_clock": "monotonic",
    }
    assert module.request_kwargs is not None
    assert module.request_kwargs["path"] == "/dev/gpiochip0"
    assert module.request_kwargs["consumer"] == "adxl355-drdy"
    assert set(cast(dict[int, object], module.request_kwargs["config"])) == {17}

    assert source.wait_event(1.0) == ReadyEvent(100, 7)
    assert source.wait_event(1.0) == ReadyEvent(200, 8)
    assert request.wait_calls == 1
    source.close()
    source.close()
    assert request.release_calls == 1


@pytest.mark.parametrize(
    ("chip", "line"),
    [("gpiochip0", 17), ("/dev/gpiochip0", -1), ("/dev/gpiochip0", 4096)],
)
def test_gpiod_source_validates_device_node_and_line(chip: str, line: int) -> None:
    with pytest.raises(ValueError):
        GpiodReadyEventSource(chip, line, module=FakeGpiodModule(FakeLineRequest([])))


def test_cli_uses_transport_specific_bus_defaults_and_validates_bounds() -> None:
    assert parse_args(["--transport", "spi"]).bus == 0
    assert parse_args(["--transport", "i2c"]).bus == 1
    assert parse_args(["--transport", "i2c", "--address", "0x53"]).address == 0x53
    for argv in (
        ["--transport", "spi", "--speed-hz", "99999"],
        ["--transport", "i2c", "--address", "0x20"],
        ["--transport", "i2c", "--samples", "0"],
        ["--transport", "i2c", "--timeout-s", "0"],
    ):
        with pytest.raises(SystemExit):
            parse_args(argv)


class FakeSessionDevice(FakeSampleDevice):
    def __init__(self) -> None:
        super().__init__()
        self.operations: list[tuple[str, object]] = []
        self.fail_cleanup = False

    def probe(self) -> bool:
        self.operations.append(("probe", True))
        return True

    def reset(self) -> None:
        self.operations.append(("reset", True))

    def set_range(self, range_val: Range) -> None:
        self.operations.append(("range", range_val))

    def set_odr(self, odr: ODR) -> None:
        self.operations.append(("odr", odr))

    def configure_data_ready(self, config: DataReadyConfig) -> None:
        self.operations.append(("drdy", config))

    def set_power_mode(self, mode: PowerMode) -> None:
        self.operations.append(("power", mode))
        if self.fail_cleanup and mode is PowerMode.STANDBY:
            raise BusError("standby cleanup failed")


class FakeClosableTransport:
    def __init__(self) -> None:
        self.closed = False

    def read_register(self, reg: int, length: int = 1) -> bytes:
        return bytes(length)

    def write_register(self, reg: int, data: bytes) -> None:
        return None

    def delay_ms(self, ms: int) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_run_session_configures_measurement_then_restores_safe_defaults() -> None:
    device = FakeSessionDevice()
    source = FakeEventSource([ReadyEvent(100, 1)])
    transport = FakeClosableTransport()
    result = run_session(
        device,
        transport,
        source,
        ContinuousAcquisitionConfig(sample_count=1, timeout_s=1.0),
    )

    assert len(result.samples) == 1
    assert device.operations[:6] == [
        ("probe", True),
        ("reset", True),
        ("range", Range.G2),
        ("odr", ODR.HZ_125),
        ("drdy", DataReadyConfig()),
        ("power", PowerMode.MEASUREMENT),
    ]
    assert device.operations[-4:] == [
        ("power", PowerMode.STANDBY),
        ("range", Range.G2),
        ("odr", ODR.HZ_4000),
        ("drdy", DataReadyConfig()),
    ]
    assert source.closed and transport.closed


def test_run_session_restores_and_closes_after_timeout() -> None:
    device = FakeSessionDevice()
    source = FakeEventSource([None])
    transport = FakeClosableTransport()
    with pytest.raises(ReadyTimeoutError):
        run_session(
            device,
            transport,
            source,
            ContinuousAcquisitionConfig(sample_count=1, timeout_s=1.0),
        )
    assert ("power", PowerMode.STANDBY) in device.operations
    assert source.closed and transport.closed


def test_run_session_reports_cleanup_failure_distinctly() -> None:
    device = FakeSessionDevice()
    device.fail_cleanup = True
    source = FakeEventSource([ReadyEvent(100, 1)])
    transport = FakeClosableTransport()
    with pytest.raises(RestoreError) as captured:
        run_session(
            device,
            transport,
            source,
            ContinuousAcquisitionConfig(sample_count=1, timeout_s=1.0),
        )
    assert captured.value.failures
    assert source.closed and transport.closed
