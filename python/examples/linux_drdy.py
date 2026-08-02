"""Bounded Linux GPIO/DRDY acquisition example using libgpiod v2.

Example I2C run on the maintained Raspberry Pi fixture::

    PYTHONPATH=src python -m examples.linux_drdy --transport i2c --bus 1 --address 0x1D \
        --gpio-chip /dev/gpiochip0 --gpio-line 17 --samples 32 --timeout-s 5

The portable ADXL355 core configures the sensor. GPIO ownership, blocking edge
waiting, timestamps, and shutdown remain in this Linux-only reference example.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
from collections import deque
from dataclasses import asdict
from types import ModuleType
from typing import Callable, Protocol, Sequence, cast

from adxl355 import (
    ADXL355,
    ODR,
    DataReadyConfig,
    PowerMode,
    Range,
    RestoreError,
)
from adxl355.adapters.smbus2 import Smbus2Transport
from adxl355.adapters.spidev import SpiDevTransport
from adxl355.transport import Transport
from adxl355.types import RawXYZ
from examples.drdy_acquisition import (
    ContinuousAcquisitionConfig,
    ContinuousAcquisitionResult,
    ReadyEvent,
    ReadyEventSource,
    acquire_continuous,
)


class _EdgeEvent(Protocol):
    timestamp_ns: int
    line_seqno: int


class _LineRequest(Protocol):
    def wait_edge_events(self, timeout: float | None = None) -> bool: ...

    def read_edge_events(self, max_events: int | None = None) -> list[_EdgeEvent]: ...

    def release(self) -> None: ...


class _HardwareTransport(Transport, Protocol):
    def close(self) -> None: ...


class _SessionDevice(Protocol):
    def probe(self) -> bool: ...

    def reset(self) -> None: ...

    def set_range(self, range_val: Range) -> None: ...

    def set_odr(self, odr: ODR) -> None: ...

    def configure_data_ready(self, config: DataReadyConfig) -> None: ...

    def set_power_mode(self, mode: PowerMode) -> None: ...

    def read_status(self) -> int: ...

    def read_raw(self) -> RawXYZ: ...


class GpiodReadyEventSource(ReadyEventSource):
    """Blocking rising-edge source backed by the official libgpiod v2 binding."""

    def __init__(
        self,
        chip_path: str,
        line_offset: int,
        *,
        module: object | None = None,
    ) -> None:
        if re.fullmatch(r"/dev/gpiochip\d+", chip_path) is None:
            raise ValueError("gpio chip must be an exact /dev/gpiochipN path")
        if not 0 <= line_offset <= 4095:
            raise ValueError("gpio line offset must be in the range 0..4095")
        if module is None:
            try:
                module = importlib.import_module("gpiod")
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "libgpiod v2 Python binding is required; install adxl355[gpio]"
                ) from exc
        resolved = cast(ModuleType, module)
        line = getattr(resolved, "line")
        settings_factory = cast(Callable[..., object], getattr(resolved, "LineSettings"))
        request_lines = cast(Callable[..., _LineRequest], getattr(resolved, "request_lines"))
        settings = settings_factory(
            direction=getattr(line.Direction, "INPUT"),
            edge_detection=getattr(line.Edge, "RISING"),
            bias=getattr(line.Bias, "DISABLED"),
            event_clock=getattr(line.Clock, "MONOTONIC"),
        )
        self._request: _LineRequest | None = request_lines(
            chip_path,
            consumer="adxl355-drdy",
            config={line_offset: settings},
        )
        self._pending: deque[ReadyEvent] = deque()

    def wait_event(self, timeout_s: float) -> ReadyEvent | None:
        if self._request is None:
            raise RuntimeError("GPIO event source is closed")
        if self._pending:
            return self._pending.popleft()
        if not self._request.wait_edge_events(timeout_s):
            return None
        for event in self._request.read_edge_events(max_events=64):
            self._pending.append(
                ReadyEvent(
                    timestamp_ns=int(event.timestamp_ns),
                    line_sequence=int(event.line_seqno),
                )
            )
        return self._pending.popleft() if self._pending else None

    def close(self) -> None:
        if self._request is not None:
            self._request.release()
            self._request = None
            self._pending.clear()


def run_session(
    device: _SessionDevice,
    transport: _HardwareTransport,
    source: ReadyEventSource,
    config: ContinuousAcquisitionConfig,
) -> ContinuousAcquisitionResult:
    """Own one reset-to-safe-state acquisition lifecycle."""

    primary: BaseException | None = None
    result: ContinuousAcquisitionResult | None = None
    initialized = False
    try:
        if not device.probe():
            raise RuntimeError("ADXL355 probe did not confirm the device")
        initialized = True
        device.reset()
        device.set_range(Range.G2)
        device.set_odr(ODR.HZ_125)
        device.configure_data_ready(DataReadyConfig())
        device.set_power_mode(PowerMode.MEASUREMENT)
        result = acquire_continuous(device, source, config)
    except BaseException as exc:
        primary = exc

    failures: list[BaseException] = []
    if initialized:
        device_cleanups: tuple[Callable[[], None], ...] = (
            lambda: device.set_power_mode(PowerMode.STANDBY),
            lambda: device.set_range(Range.G2),
            lambda: device.set_odr(ODR.HZ_4000),
            lambda: device.configure_data_ready(DataReadyConfig()),
        )
        for cleanup in device_cleanups:
            try:
                cleanup()
            except BaseException as exc:
                failures.append(exc)
    for cleanup in (source.close, transport.close):
        try:
            cleanup()
        except BaseException as exc:
            failures.append(exc)

    if failures:
        raise RestoreError(tuple(failures)) from primary
    if primary is not None:
        raise primary
    if result is None:
        raise RuntimeError("acquisition completed without a result")
    return result


def _int_auto(value: str) -> int:
    return int(value, 0)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("spi", "i2c"), required=True)
    parser.add_argument("--bus", type=int)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--address", type=_int_auto, default=0x1D)
    parser.add_argument("--speed-hz", type=int, default=1_000_000)
    parser.add_argument("--gpio-chip", default="/dev/gpiochip0")
    parser.add_argument("--gpio-line", type=int, default=17)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--timeout-s", type=float, default=5.0)
    parser.add_argument("--max-missed-events", type=int, default=0)
    args = parser.parse_args(argv)
    if args.bus is None:
        args.bus = 0 if args.transport == "spi" else 1
    if args.bus < 0 or args.device < 0:
        parser.error("bus and device must be non-negative")
    if args.address not in (0x1D, 0x53):
        parser.error("address must be 0x1D or 0x53")
    if not 100_000 <= args.speed_hz <= 10_000_000:
        parser.error("speed-hz must be in the range 100000..10000000")
    if not 1 <= args.samples <= 4096:
        parser.error("samples must be in the range 1..4096")
    if not 0.001 <= args.timeout_s <= 3600.0:
        parser.error("timeout-s must be in the range 0.001..3600")
    if not 0 <= args.max_missed_events <= 1_000_000:
        parser.error("max-missed-events must be in the range 0..1000000")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.transport == "spi":
        transport: _HardwareTransport = SpiDevTransport(
            bus=args.bus,
            device=args.device,
            max_speed_hz=args.speed_hz,
        )
    else:
        transport = Smbus2Transport(bus=args.bus, address=args.address)
    device = ADXL355(transport)
    source = GpiodReadyEventSource(args.gpio_chip, args.gpio_line)
    result = run_session(
        device,
        transport,
        source,
        ContinuousAcquisitionConfig(
            sample_count=args.samples,
            timeout_s=args.timeout_s,
            max_missed_events=args.max_missed_events,
        ),
    )
    payload = {
        "transport": args.transport,
        "sampleCount": len(result.samples),
        "missedEvents": result.missed_events,
        "fifoOverruns": result.fifo_overruns,
        "durationNs": result.completed_ns - result.started_ns,
        "first": asdict(result.samples[0]) if result.samples else None,
        "last": asdict(result.samples[-1]) if result.samples else None,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
