#!/usr/bin/env python3
"""Run deterministic mutation smoke tests for Python and release-tool boundaries."""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python" / "src"))
sys.path.insert(0, str(REPO_ROOT))

from adxl355 import ADXL355, BusError, DeviceNotFoundError, InvalidConfigurationError  # noqa: E402
from adxl355.constants import DEVID_AD, DEVID_MST, PARTID  # noqa: E402
from adxl355.registers import Range, Register  # noqa: E402
from adxl355.device import _decode_raw20  # noqa: E402
from scripts.prepare_sbom_input import SbomInputError, _archive_kind, _safe_member  # noqa: E402

MAX_INPUT: Final = 1024


@dataclass
class MutationTransport:
    """Use an exact probe prefix, then return one arbitrary mutated payload."""

    payload: bytes
    requested_delta: int
    valid_probe: bool
    reads: int = 0

    def read_register(self, reg: int, length: int = 1) -> bytes:
        self.reads += 1
        if self.valid_probe and self.reads <= 5:
            probe_values = {
                int(Register.DEVID_AD): DEVID_AD,
                int(Register.DEVID_MST): DEVID_MST,
                int(Register.PARTID): PARTID,
                int(Register.RANGE): int(Range.G2),
                int(Register.POWER_CTL): 1,
            }
            value = probe_values.get(reg, 0)
            return bytes([value]) if length == 1 else bytes([value]) + bytes(length - 1)
        returned = max(0, min(MAX_INPUT, length + self.requested_delta))
        if not self.payload:
            return bytes(returned)
        repeats = (returned + len(self.payload) - 1) // len(self.payload)
        return (self.payload * repeats)[:returned]

    def write_register(self, reg: int, data: bytes) -> None:
        del reg, data

    def delay_ms(self, ms: int) -> None:
        del ms


def mutated_path(rng: random.Random) -> str:
    atoms = [
        "..",
        ".",
        "pkg",
        "METADATA",
        "C:\\temp",
        "",
        "α",
        "//server",
        "package.json",
    ]
    count = rng.randint(0, 8)
    separator = rng.choice(("/", "//", "\\"))
    value = separator.join(rng.choice(atoms) for _ in range(count))
    if rng.randrange(4) == 0:
        value = "/" + value
    if rng.randrange(3) == 0:
        value += rng.choice((".whl", ".crate", ".tgz", ".tar.gz", ".zip", ""))
    return value[:MAX_INPUT]


def mutate_bytes(rng: random.Random) -> bytes:
    length = rng.randint(0, 64)
    return bytes(rng.randrange(256) for _ in range(length))


def exercise_decode(payload: bytes) -> None:
    padded = (payload + b"\x00\x00\x00")[:3]
    decoded = _decode_raw20(padded[0], padded[1], padded[2])
    if not -(1 << 19) <= decoded <= (1 << 19) - 1:
        raise AssertionError(f"decoded value escaped signed 20-bit range: {decoded}")


def exercise_transport(payload: bytes, delta: int, valid_probe: bool) -> str:
    device = ADXL355(MutationTransport(payload, delta, valid_probe))
    try:
        device.probe()
    except (BusError, DeviceNotFoundError, InvalidConfigurationError):
        return "probe-rejected"
    try:
        device.read_raw()
    except BusError:
        return "raw-rejected"
    return "raw-accepted"


def exercise_archive_path(value: str) -> str:
    try:
        member = _safe_member(value)
    except SbomInputError:
        return "unsafe-rejected"
    if member.is_absolute() or ".." in member.parts or not member.parts:
        raise AssertionError(f"unsafe archive member accepted: {value!r}")
    _archive_kind(value)
    return "safe-accepted"


def write_reproducer(artifact_dir: Path, details: dict[str, object]) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "python-reproducer.json").write_text(
        json.dumps(details, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run(iterations: int, seed: int, artifact_dir: Path) -> dict[str, object]:
    if not 1 <= iterations <= 100_000:
        raise ValueError("iterations must be between 1 and 100000")
    rng = random.Random(seed)
    counters = {
        "decode": 0,
        "probe-rejected": 0,
        "raw-rejected": 0,
        "raw-accepted": 0,
        "unsafe-rejected": 0,
        "safe-accepted": 0,
    }
    for index in range(iterations):
        payload = mutate_bytes(rng)
        path = mutated_path(rng)
        delta = rng.randint(-2, 2)
        valid_probe = index % 3 == 0
        try:
            exercise_decode(payload)
            counters["decode"] += 1
            counters[exercise_transport(payload, delta, valid_probe)] += 1
            counters[exercise_archive_path(path)] += 1
        except Exception as error:
            write_reproducer(
                artifact_dir,
                {
                    "seed": seed,
                    "iteration": index,
                    "payload_hex": payload.hex(),
                    "path": path,
                    "length_delta": delta,
                    "valid_probe": valid_probe,
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            )
            raise
    if counters["unsafe-rejected"] == 0 or counters["safe-accepted"] == 0:
        raise AssertionError(
            "archive mutation did not exercise both safe and unsafe paths"
        )
    if any(
        counters[name] == 0
        for name in ("probe-rejected", "raw-rejected", "raw-accepted")
    ):
        raise AssertionError(
            "transport mutation did not exercise accept and reject paths"
        )
    return {
        "status": "ok",
        "seed": seed,
        "iterations": iterations,
        "counters": counters,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=355)
    parser.add_argument("--artifact-dir", type=Path, default=Path("artifacts/fuzz"))
    args = parser.parse_args(argv)
    try:
        report = run(args.iterations, args.seed, args.artifact_dir)
    except (AssertionError, ValueError) as error:
        print(f"Python fuzz smoke failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
