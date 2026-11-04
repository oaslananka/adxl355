#!/usr/bin/env python3
"""Compare independent C, Python, Rust and npm build outputs, without publishing.

This is an opt-in local acceptance check. Run it in a fixed Linux toolchain
with npm development dependencies already installed (`cd node && npm ci`).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.normalize_sdist import normalize_sdist


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("c", "python", "rust", "npm")


def run(args: list[str], *, cwd: Path = ROOT, env: dict[str, str]) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True, stdout=subprocess.DEVNULL)


def sha256(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def compare(first: Path, second: Path) -> list[tuple[str, str]]:
    left = {file.name: file for file in first.iterdir() if file.is_file()}
    right = {file.name: file for file in second.iterdir() if file.is_file()}
    if not left or left.keys() != right.keys():
        raise ValueError(f"artifact set mismatch: {sorted(left)} != {sorted(right)}")
    matches = []
    for name in sorted(left):
        first_hash, second_hash = sha256(left[name]), sha256(right[name])
        if first_hash != second_hash:
            raise ValueError(f"NOT REPRODUCIBLE {name}: {first_hash} != {second_hash}")
        matches.append((name, first_hash))
    return matches


def build_one(component: str, destination: Path, env: dict[str, str]) -> None:
    destination.mkdir(parents=True)
    if component == "c":
        build = destination.parent / "c-build"
        run(
            [
                "cmake",
                "-S",
                "c",
                "-B",
                str(build),
                "-DCMAKE_BUILD_TYPE=Release",
                "-DADXL355_BUILD_TESTS=OFF",
                "-DADXL355_BUILD_EXAMPLES=OFF",
            ],
            env=env,
        )
        run(["cmake", "--build", str(build), "--parallel", "2"], env=env)
        shutil.copy2(build / "libadxl355.a", destination / "libadxl355.a")
    elif component == "python":
        run(
            [
                "uvx",
                "--from",
                "build==1.5.0",
                "--with",
                "setuptools==84.1.0",
                "pyproject-build",
                "--no-isolation",
                "python",
                "--outdir",
                str(destination),
            ],
            env=env,
        )
        for sdist in destination.glob("*.tar.gz"):
            normalize_sdist(sdist, epoch=int(env["SOURCE_DATE_EPOCH"]))
    elif component == "rust":
        build = destination.parent / "rust-target"
        local = dict(env, CARGO_TARGET_DIR=str(build))
        run(
            [
                "cargo",
                "package",
                "--locked",
                "--manifest-path",
                "rust/Cargo.toml",
                "--no-verify",
            ],
            env=local,
        )
        crates = list((build / "package").glob("*.crate"))
        if len(crates) != 1:
            raise ValueError(f"expected one Rust crate, got {len(crates)}")
        shutil.copy2(crates[0], destination / crates[0].name)
    elif component == "npm":
        if not (ROOT / "node/node_modules/.bin/tsc").exists():
            raise ValueError("run 'cd node && npm ci --ignore-scripts' first")
        copy = destination.parent / "npm-source"
        shutil.copytree(
            ROOT / "node",
            copy,
            ignore=shutil.ignore_patterns(
                "node_modules", "dist", ".npm-*", ".vitest-*"
            ),
        )
        (copy / "node_modules").symlink_to(
            ROOT / "node/node_modules", target_is_directory=True
        )
        run(["npm", "run", "build"], cwd=copy, env=env)
        run(
            [
                "npm",
                "pack",
                "--ignore-scripts",
                "--silent",
                "--pack-destination",
                str(destination),
            ],
            cwd=copy,
            env=env,
        )
    else:
        raise ValueError(f"unrecognized component: {component}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--components", nargs="+", choices=COMPONENTS, default=list(COMPONENTS)
    )
    args = parser.parse_args()
    epoch = subprocess.check_output(
        ["git", "show", "-s", "--format=%ct", "HEAD"], cwd=ROOT, text=True
    ).strip()
    env = dict(os.environ, SOURCE_DATE_EPOCH=epoch, TZ="UTC", LC_ALL="C")
    with tempfile.TemporaryDirectory(prefix="adxl355-repro-") as temporary:
        scratch = Path(temporary)
        for component in dict.fromkeys(args.components):
            a, b = (scratch / attempt / component for attempt in ("a", "b"))
            for out in (a, b):
                build_one(component, out, env)
            results = compare(a, b)
            for name, digest in results:
                print(f"PASS {component}: {name} sha256={digest}")
    print(
        "All selected artifacts reproduced byte-for-byte in the controlled local environment."
    )


if __name__ == "__main__":
    main()
