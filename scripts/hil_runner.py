#!/usr/bin/env python3
"""Opt-in hardware-in-the-loop validation for a physical ADXL355.

The runner intentionally lives outside the default unit-test discovery path. It
supports Linux spidev and smbus2 adapters, produces a sanitized JSON report, and
returns a nonzero status when any hardware step fails.
"""

from __future__ import annotations

import argparse
import json
import math
import operator
import os
import platform
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from functools import reduce
from typing import Any, Callable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = REPO_ROOT / "python" / "src"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from adxl355 import ADXL355, PowerMode, Range  # noqa: E402
from adxl355.constants import (  # noqa: E402
    DEVID_AD,
    DEVID_MST,
    PARTID,
    TEMP_INTERCEPT_C,
    TEMP_INTERCEPT_LSB,
    TEMP_SLOPE_LSB_PER_C,
)
from adxl355.device import raw_to_g  # noqa: E402
from adxl355.registers import ODR, STATUS_DATA_RDY, Register  # noqa: E402
from adxl355.transport import Transport  # noqa: E402

SPI_MIN_HZ = 100_000
SPI_MAX_HZ = 10_000_000
I2C_ADDRESSES = (0x1D, 0x53)
I2C_BUS_SPEEDS = (100_000, 400_000, 1_000_000, 3_400_000)
MIN_SAMPLES = 4
MAX_SAMPLES = 1_000
MIN_TIMEOUT_MS = 50
MAX_TIMEOUT_MS = 10_000
REPORT_SCHEMA_VERSION = 1
I2C_ADDRESS_ERROR = "I2C address must be 0x1D or 0x53"
REPORT_ROOT = REPO_ROOT / "artifacts"
SECRET_PATTERN = re.compile(
    r"(?i)\b(token|secret|password|passwd|api[_-]?key)\s*[:=]\s*[^\s,;]+"
)


@dataclass(frozen=True)
class HilConfig:
    """Validated HIL execution settings."""

    transport: str
    samples: int = 16
    sample_timeout_ms: int = 500
    spi_bus: int = 0
    spi_device: int = 0
    spi_speed_hz: int = 1_000_000
    i2c_bus: int = 1
    i2c_address: int = 0x1D
    i2c_bus_hz: int = 400_000
    runner_id: str = "local"
    git_sha: str = "unknown"

    def validate(self) -> None:
        self._validate_common()
        if self.transport == "spi":
            self._validate_spi()
        else:
            self._validate_i2c()

    def _validate_common(self) -> None:
        if self.transport not in {"spi", "i2c"}:
            raise ValueError("transport must be 'spi' or 'i2c'")
        if not MIN_SAMPLES <= self.samples <= MAX_SAMPLES:
            raise ValueError(f"samples must be between {MIN_SAMPLES} and {MAX_SAMPLES}")
        if not MIN_TIMEOUT_MS <= self.sample_timeout_ms <= MAX_TIMEOUT_MS:
            raise ValueError(
                f"sample timeout must be between {MIN_TIMEOUT_MS} and {MAX_TIMEOUT_MS} ms"
            )

    def _validate_spi(self) -> None:
        if self.spi_bus < 0 or self.spi_device < 0:
            raise ValueError("SPI bus and chip-select values must be nonnegative")
        if not SPI_MIN_HZ <= self.spi_speed_hz <= SPI_MAX_HZ:
            raise ValueError(
                f"SPI speed must be between {SPI_MIN_HZ} and {SPI_MAX_HZ} Hz"
            )

    def _validate_i2c(self) -> None:
        if self.i2c_bus < 0:
            raise ValueError("I2C bus must be nonnegative")
        if self.i2c_address not in I2C_ADDRESSES:
            raise ValueError(I2C_ADDRESS_ERROR)
        if self.i2c_bus_hz not in I2C_BUS_SPEEDS:
            allowed = ", ".join(str(value) for value in I2C_BUS_SPEEDS)
            raise ValueError(f"declared I2C bus speed must be one of: {allowed}")

    @property
    def bus(self) -> dict[str, Any]:
        if self.transport == "spi":
            return {
                "transport": "spi",
                "device_path": f"/dev/spidev{self.spi_bus}.{self.spi_device}",
                "bus": self.spi_bus,
                "chip_select": self.spi_device,
                "mode": 0,
                "speed_hz": self.spi_speed_hz,
                "supported_speed_hz": [SPI_MIN_HZ, SPI_MAX_HZ],
            }
        return {
            "transport": "i2c",
            "device_path": f"/dev/i2c-{self.i2c_bus}",
            "bus": self.i2c_bus,
            "address": f"0x{self.i2c_address:02X}",
            "declared_bus_hz": self.i2c_bus_hz,
            "supported_addresses": [f"0x{value:02X}" for value in I2C_ADDRESSES],
        }


def parse_i2c_address(value: str) -> int:
    """Parse and validate one of the two datasheet-defined I2C addresses."""

    try:
        parsed = int(value, 0)
    except ValueError as exc:
        raise ValueError(I2C_ADDRESS_ERROR) from exc
    if parsed not in I2C_ADDRESSES:
        raise ValueError(I2C_ADDRESS_ERROR)
    return parsed


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_label(value: str, fallback: str) -> str:
    redacted = SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}_[REDACTED]", value.strip()
    )
    cleaned = re.sub(r"[^A-Za-z0-9_.:@/-]", "_", redacted)[:80]
    return cleaned or fallback


def _base_report(config: HilConfig) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "started_at": _utc_now(),
        "finished_at": None,
        "duration_ms": None,
        "success": False,
        "runner": {
            "id": _safe_label(config.runner_id, "unspecified"),
            "git_sha": _safe_label(config.git_sha, "unknown")[:40],
            "os": platform.system(),
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
        },
        "bus": config.bus,
        "device": {},
        "configuration": {},
        "temperature": {},
        "samples": {},
        "steps": [],
        "diagnostic_hints": [],
    }


def _redact_message(message: str) -> str:
    flattened = " ".join(message.splitlines())[:512]
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", flattened)


def _error_payload(exc: BaseException) -> dict[str, str]:
    return {
        "type": type(exc).__name__,
        "message": _redact_message(str(exc)) or type(exc).__name__,
    }


def _diagnostic_hints(config: HilConfig, exc: BaseException) -> list[str]:
    message = str(exc).lower()
    hints = [
        f"Confirm that {config.bus['device_path']} exists and the runner account has read/write access.",
        "Confirm a common ground and voltage levels before retrying.",
    ]
    if config.transport == "spi":
        hints.extend(
            [
                "Verify 4-wire SPI wiring, chip select, and Mode 0 (CPOL=0, CPHA=0).",
                f"Verify the configured SPI clock is within {SPI_MIN_HZ}..{SPI_MAX_HZ} Hz.",
            ]
        )
    else:
        hints.extend(
            [
                f"Verify the MISO/ASEL strap matches 0x{config.i2c_address:02X}.",
                "Use a dedicated I2C bus with pull-ups to VDDIO and tie SCLK/VSSIO to ground.",
            ]
        )
    if "permission" in message:
        hints.append("Fix runner group or udev permissions; do not run the workflow as root by default.")
    if "identity" in message or "device id" in message:
        hints.append("Inspect command framing and logic-analyzer traces for the identity-register reads.")
    if "data_ready" in message or "data ready" in message or "timeout" in message:
        hints.append("Confirm measurement mode, ODR configuration, and that the sensor clock is running.")
    return hints


def _read_exact(transport: Transport, reg: int, length: int) -> bytes:
    data = transport.read_register(reg, length)
    if len(data) != length:
        raise RuntimeError(
            f"transport returned {len(data)} bytes for register 0x{reg:02X}; expected {length}"
        )
    return data


def _step(
    report: dict[str, Any],
    name: str,
    action: Callable[[], Any],
    monotonic: Callable[[], float],
) -> Any:
    started = monotonic()
    try:
        details = action()
    except Exception as exc:
        report["steps"].append(
            {
                "name": name,
                "status": "failed",
                "duration_ms": round((monotonic() - started) * 1000, 3),
                "error": _error_payload(exc),
            }
        )
        raise
    step: dict[str, Any] = {
        "name": name,
        "status": "passed",
        "duration_ms": round((monotonic() - started) * 1000, 3),
    }
    if details is not None:
        step["details"] = details
    report["steps"].append(step)
    return details


def _build_transport(config: HilConfig) -> Transport:
    device_path = Path(str(config.bus["device_path"]))
    if not device_path.exists():
        raise FileNotFoundError(f"hardware device node does not exist: {device_path}")
    if config.transport == "spi":
        from adxl355.adapters.spidev import SpiDevTransport

        return SpiDevTransport(
            bus=config.spi_bus,
            device=config.spi_device,
            max_speed_hz=config.spi_speed_hz,
        )

    from adxl355.adapters.smbus2 import Smbus2Transport

    return Smbus2Transport(bus=config.i2c_bus, address=config.i2c_address)


def _identity(transport: Transport) -> dict[str, Any]:
    values = _read_exact(transport, Register.DEVID_AD, 4)
    actual = tuple(values[:3])
    expected = (DEVID_AD, DEVID_MST, PARTID)
    if actual != expected:
        raise RuntimeError(
            "identity mismatch: "
            f"DEVID_AD=0x{actual[0]:02X}, DEVID_MST=0x{actual[1]:02X}, "
            f"PARTID=0x{actual[2]:02X}"
        )
    return {
        "identity": {
            "devid_ad": f"0x{values[0]:02X}",
            "devid_mst": f"0x{values[1]:02X}",
            "partid": f"0x{values[2]:02X}",
        },
        "revision": f"0x{values[3]:02X}",
    }


def _verify_bus_configuration(config: HilConfig, transport: Transport) -> dict[str, Any]:
    if config.transport == "spi":
        mode = int(getattr(transport, "mode", 0))
        speed_hz = int(getattr(transport, "speed_hz", config.spi_speed_hz))
        if mode != 0:
            raise RuntimeError(f"SPI mode verification failed: expected 0, got {mode}")
        if not SPI_MIN_HZ <= speed_hz <= SPI_MAX_HZ:
            raise RuntimeError(
                f"SPI speed verification failed: {speed_hz} is outside "
                f"{SPI_MIN_HZ}..{SPI_MAX_HZ} Hz"
            )
        return {"verified_mode": mode, "verified_speed_hz": speed_hz}
    return {
        "verified_address": f"0x{config.i2c_address:02X}",
        "declared_bus_hz": config.i2c_bus_hz,
    }


def _wait_for_data_ready(
    device: ADXL355,
    timeout_ms: int,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> int:
    deadline = monotonic() + timeout_ms / 1000.0
    while True:
        status = device.read_status()
        if status & STATUS_DATA_RDY:
            return status
        if monotonic() >= deadline:
            raise TimeoutError(f"DATA_READY did not assert within {timeout_ms} ms")
        sleep(0.002)


def _sample_summary(
    device: ADXL355,
    config: HilConfig,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    raw_samples: list[tuple[int, int, int]] = []
    status_values: list[int] = []
    for _ in range(config.samples):
        status_values.append(
            _wait_for_data_ready(device, config.sample_timeout_ms, monotonic, sleep)
        )
        raw = device.read_raw()
        values = (raw.x, raw.y, raw.z)
        if any(value < -524_288 or value > 524_287 for value in values):
            raise RuntimeError(f"raw sample is outside the signed 20-bit range: {values}")
        raw_samples.append(values)

    unique_count = len(set(raw_samples))
    if unique_count < 2:
        raise RuntimeError(
            "continuous-read check returned one repeated sample; verify DATA_READY and bus timing"
        )

    axis_names = ("x", "y", "z")
    raw_min = {name: min(sample[index] for sample in raw_samples) for index, name in enumerate(axis_names)}
    raw_max = {name: max(sample[index] for sample in raw_samples) for index, name in enumerate(axis_names)}
    accel_samples = [
        tuple(raw_to_g(value, Range.G4) for value in sample) for sample in raw_samples
    ]
    accel_min = {
        name: min(sample[index] for sample in accel_samples)
        for index, name in enumerate(axis_names)
    }
    accel_max = {
        name: max(sample[index] for sample in accel_samples)
        for index, name in enumerate(axis_names)
    }
    if any(abs(value) > 4.2 for sample in accel_samples for value in sample):
        raise RuntimeError("converted acceleration exceeded the configured ±4 g range")

    return {
        "count": len(raw_samples),
        "unique": unique_count,
        "status_or": f"0x{reduce(operator.or_, status_values, 0):02X}",
        "first_raw": dict(zip(axis_names, raw_samples[0])),
        "last_raw": dict(zip(axis_names, raw_samples[-1])),
        "raw_min": raw_min,
        "raw_max": raw_max,
        "acceleration_g_min": accel_min,
        "acceleration_g_max": accel_max,
    }


def _restore_after_failure(
    device: ADXL355,
    restore_range: Range,
    restore_odr: ODR,
) -> list[dict[str, str]]:
    """Best-effort restoration after a failed physical test step."""

    errors: list[dict[str, str]] = []
    operations: tuple[tuple[str, Callable[[], None]], ...] = (
        ("standby", lambda: device.set_power_mode(PowerMode.STANDBY)),
        ("range", lambda: device.set_range(restore_range)),
        ("odr", lambda: device.set_odr(restore_odr)),
    )
    for operation, action in operations:
        try:
            action()
        except Exception as exc:
            payload = _error_payload(exc)
            payload["operation"] = operation
            errors.append(payload)
    return errors


def _reset_check(device: ADXL355, transport: Transport) -> dict[str, Any]:
    device.reset()
    after = _identity(transport)
    range_after = int(_read_exact(transport, Register.RANGE, 1)[0]) & 0x03
    if range_after != int(Range.G2):
        raise RuntimeError(
            f"reset did not restore RANGE to G2: register encoding 0x{range_after:02X}"
        )
    return {
        "revision_after_reset": after["revision"],
        "range_after_reset": "G2",
    }


def _configure_device(device: ADXL355, transport: Transport) -> dict[str, Any]:
    device.set_range(Range.G4)
    device.set_odr(ODR.HZ_125)
    verified_range = device.get_range()
    filter_value = _read_exact(transport, Register.FILTER, 1)[0]
    if verified_range != Range.G4:
        raise RuntimeError(f"range verification failed: {verified_range.name}")
    if filter_value & 0x0F != int(ODR.HZ_125):
        raise RuntimeError(f"ODR verification failed: FILTER=0x{filter_value:02X}")
    device.set_power_mode(PowerMode.MEASUREMENT)
    transport.delay_ms(20)
    power_ctl = _read_exact(transport, Register.POWER_CTL, 1)[0]
    if power_ctl & 0x01:
        raise RuntimeError("device remained in standby after measurement-mode request")
    return {
        "verified_range": verified_range.name,
        "odr": ODR.HZ_125.name,
        "power_mode": PowerMode.MEASUREMENT.name,
    }


def _read_temperature(device: ADXL355) -> dict[str, Any]:
    raw = device.read_temperature_raw()
    celsius = TEMP_INTERCEPT_C + (
        raw - TEMP_INTERCEPT_LSB
    ) / TEMP_SLOPE_LSB_PER_C
    if not math.isfinite(celsius) or not -40.0 <= celsius <= 125.0:
        raise RuntimeError(
            f"temperature {celsius:.2f} °C is outside the ADXL355 operating range"
        )
    return {"raw": raw, "celsius": round(celsius, 4)}


def _restore_device(
    device: ADXL355,
    transport: Transport,
    restore_range: Range,
    restore_odr: ODR,
) -> dict[str, Any]:
    device.set_power_mode(PowerMode.STANDBY)
    device.set_range(restore_range)
    device.set_odr(restore_odr)
    power_ctl = _read_exact(transport, Register.POWER_CTL, 1)[0]
    if not power_ctl & 0x01:
        raise RuntimeError("device did not return to standby")
    return {
        "power_mode": "STANDBY",
        "range": restore_range.name,
        "odr": restore_odr.name,
    }


def _run_post_probe_sequence(
    report: dict[str, Any],
    config: HilConfig,
    device: ADXL355,
    transport: Transport,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    restore_range: Range,
    restore_odr: ODR,
) -> None:
    report["device"]["reset"] = _step(
        report,
        "reset",
        lambda: _reset_check(device, transport),
        monotonic,
    )
    report["configuration"] = _step(
        report,
        "configuration",
        lambda: _configure_device(device, transport),
        monotonic,
    )
    report["temperature"] = _step(
        report,
        "temperature",
        lambda: _read_temperature(device),
        monotonic,
    )
    report["samples"] = _step(
        report,
        "continuous-read",
        lambda: _sample_summary(device, config, monotonic, sleep),
        monotonic,
    )
    _step(
        report,
        "restore-standby",
        lambda: _restore_device(device, transport, restore_range, restore_odr),
        monotonic,
    )


def _close_transport(report: dict[str, Any], transport: Optional[Transport]) -> None:
    if transport is None:
        return
    close = getattr(transport, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception as exc:
        report.setdefault("cleanup_errors", []).append(_error_payload(exc))
        report["success"] = False


def run_hil(
    config: HilConfig,
    *,
    transport: Optional[Transport] = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run the HIL sequence and return a sanitized report without raising."""

    report = _base_report(config)
    overall_started = monotonic()
    active_transport = transport
    device: Optional[ADXL355] = None
    probed = False
    restore_range = Range.G2
    restore_odr = ODR.HZ_4000

    try:
        config.validate()
        if active_transport is None:
            active_transport = _build_transport(config)

        bus_details = _step(
            report,
            "bus-configuration",
            lambda: _verify_bus_configuration(config, active_transport),
            monotonic,
        )
        report["bus"].update(bus_details)

        device_details = _step(
            report,
            "identity",
            lambda: _identity(active_transport),
            monotonic,
        )
        report["device"].update(device_details)

        device = ADXL355(active_transport)
        _step(report, "probe", device.probe, monotonic)
        probed = True
        _run_post_probe_sequence(
            report,
            config,
            device,
            active_transport,
            monotonic,
            sleep,
            restore_range,
            restore_odr,
        )
        report["success"] = True
    except Exception as exc:
        report["error"] = _error_payload(exc)
        report["diagnostic_hints"] = _diagnostic_hints(config, exc)
        if device is not None and probed:
            cleanup_errors = _restore_after_failure(device, restore_range, restore_odr)
            if cleanup_errors:
                report["cleanup_errors"] = cleanup_errors
    finally:
        _close_transport(report, active_transport)
        report["finished_at"] = _utc_now()
        report["duration_ms"] = round((monotonic() - overall_started) * 1000, 3)

    return report


def _validated_report_path(path: Path, allowed_root: Path) -> Path:
    root = allowed_root.resolve(strict=False)
    candidate = path if path.is_absolute() else REPO_ROOT / path
    candidate = candidate.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"report path must remain under {root}") from exc
    if candidate == root or candidate.suffix.lower() != ".json":
        raise ValueError("report path must name a JSON file under the artifacts directory")
    return candidate


def parse_report_path(value: str) -> Path:
    """Resolve a CLI report path beneath the repository artifacts directory."""

    return _validated_report_path(Path(value), REPORT_ROOT)


def write_report(
    path: Path,
    report: dict[str, Any],
    *,
    allowed_root: Path = REPORT_ROOT,
) -> None:
    """Atomically write the public HIL result document inside an allowed root."""

    target = _validated_report_path(path, allowed_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, target)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("spi", "i2c"), required=True)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--sample-timeout-ms", type=int, default=500)
    parser.add_argument("--spi-bus", type=int, default=0)
    parser.add_argument("--spi-device", type=int, default=0)
    parser.add_argument("--spi-speed-hz", type=int, default=1_000_000)
    parser.add_argument("--i2c-bus", type=int, default=1)
    parser.add_argument("--i2c-address", type=parse_i2c_address, default=0x1D)
    parser.add_argument("--i2c-bus-hz", type=int, default=400_000)
    parser.add_argument("--runner-id", default="local")
    parser.add_argument("--git-sha", default="unknown")
    parser.add_argument(
        "--report",
        type=parse_report_path,
        default=REPORT_ROOT / "hil-report.json",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    config = HilConfig(
        transport=args.transport,
        samples=args.samples,
        sample_timeout_ms=args.sample_timeout_ms,
        spi_bus=args.spi_bus,
        spi_device=args.spi_device,
        spi_speed_hz=args.spi_speed_hz,
        i2c_bus=args.i2c_bus,
        i2c_address=args.i2c_address,
        i2c_bus_hz=args.i2c_bus_hz,
        runner_id=args.runner_id,
        git_sha=args.git_sha,
    )
    report = run_hil(config)
    write_report(args.report, report)
    if report["success"]:
        revision = report["device"].get("revision", "unknown")
        print(f"HIL PASS: {args.transport} device revision {revision}")
        print(f"Report: {args.report}")
        return 0

    error = report.get("error", {"type": "UnknownError", "message": "unknown failure"})
    print(f"HIL FAIL: {error['type']}: {error['message']}", file=sys.stderr)
    for hint in report.get("diagnostic_hints", []):
        print(f"  - {hint}", file=sys.stderr)
    print(f"Report: {args.report}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
