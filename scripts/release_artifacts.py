#!/usr/bin/env python3
"""Inspect and smoke-test release artifacts without publishing them."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import venv
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable


DEVELOPMENT_PATH_MARKERS = ("/tests/", "/examples/")
RUST_FORBIDDEN_PATH_MARKERS = (*DEVELOPMENT_PATH_MARKERS, "/target/", "/.github/")


class ArtifactError(ValueError):
    """Raised when a release artifact violates its package contract."""


def _single(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise ArtifactError(
            f"expected exactly one {pattern!r} artifact in {directory}, found {len(matches)}"
        )
    return matches[0]


def _safe_members(names: Iterable[str]) -> list[str]:
    checked: list[str] = []
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ArtifactError(f"archive contains unsafe path: {name!r}")
        checked.append(name)
    return checked


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, check=False, text=True)
    if result.returncode != 0:
        raise ArtifactError(f"command failed ({result.returncode}): {' '.join(command)}")


def _extract_tar(archive: Path, destination: Path) -> list[str]:
    with tarfile.open(archive, "r:*") as handle:
        names = _safe_members(member.name for member in handle.getmembers())
        handle.extractall(destination, filter="data")
    return names


def inspect_python(directory: Path, version: str, *, smoke: bool) -> dict[str, object]:
    wheel = _single(directory, "*.whl")
    sdist = _single(directory, "*.tar.gz")

    with zipfile.ZipFile(wheel) as handle:
        wheel_names = _safe_members(handle.namelist())
        metadata_name = next(
            (name for name in wheel_names if name.endswith(".dist-info/METADATA")), None
        )
        if metadata_name is None:
            raise ArtifactError("Python wheel is missing dist-info/METADATA")
        metadata = handle.read(metadata_name).decode("utf-8")

    if f"Version: {version}\n" not in metadata:
        raise ArtifactError(f"Python wheel metadata does not contain version {version!r}")
    for required_url in (
        "Project-URL: Repository, https://github.com/oaslananka/adxl355",
        "Project-URL: Documentation, https://github.com/oaslananka/adxl355/tree/main/docs",
    ):
        if required_url not in metadata:
            raise ArtifactError(f"Python wheel metadata is missing {required_url!r}")
    if any(any(marker in f"/{name}" for marker in DEVELOPMENT_PATH_MARKERS) for name in wheel_names):
        raise ArtifactError("Python wheel contains tests or examples")

    with tarfile.open(sdist, "r:gz") as handle:
        sdist_names = _safe_members(member.name for member in handle.getmembers())
    if any(any(marker in f"/{name}" for marker in DEVELOPMENT_PATH_MARKERS) for name in sdist_names):
        raise ArtifactError("Python sdist contains tests or examples")
    if not any(name.endswith("/README.md") for name in sdist_names):
        raise ArtifactError("Python sdist is missing README.md")
    if not any(name.endswith("/LICENSE") for name in sdist_names):
        raise ArtifactError("Python sdist is missing LICENSE")

    if smoke:
        with tempfile.TemporaryDirectory(prefix="adxl355-python-artifact-") as temp:
            environment = Path(temp) / "venv"
            venv.EnvBuilder(with_pip=True, clear=True).create(environment)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            _run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)])
            _run(
                [
                    str(python),
                    "-c",
                    (
                        "import adxl355; "
                        f"assert adxl355.__version__ == {version!r}; "
                        "assert adxl355.Range.G2.value == 1; "
                        "assert adxl355.ADXL355 is not None"
                    ),
                ]
            )

    return {
        "package": "python",
        "version": version,
        "artifacts": [wheel.name, sdist.name],
        "wheel_files": len(wheel_names),
        "sdist_files": len(sdist_names),
        "smoke": smoke,
    }


def inspect_rust(directory: Path, version: str, *, smoke: bool) -> dict[str, object]:
    crate = _single(directory, "adxl355-driver-*.crate")
    with tempfile.TemporaryDirectory(prefix="adxl355-rust-artifact-") as temp:
        extracted = Path(temp) / "crate"
        extracted.mkdir()
        names = _extract_tar(crate, extracted)
        prefix = f"adxl355-driver-{version}/"
        if not all(name == prefix.rstrip("/") or name.startswith(prefix) for name in names):
            raise ArtifactError("Rust crate contains an unexpected archive prefix")
        if any(
            any(marker in f"/{name}" for marker in RUST_FORBIDDEN_PATH_MARKERS)
            for name in names
        ):
            raise ArtifactError("Rust crate contains development-only files")

        package_root = extracted / prefix.rstrip("/")
        with (package_root / "Cargo.toml").open("rb") as handle:
            manifest = tomllib.load(handle)
        if manifest["package"]["name"] != "adxl355-driver":
            raise ArtifactError("Rust crate package name mismatch")
        if manifest["package"]["version"] != version:
            raise ArtifactError("Rust crate version mismatch")
        if manifest["lib"]["name"] != "adxl355":
            raise ArtifactError("Rust crate import name mismatch")
        for required in ("README.md", "LICENSE", "src/lib.rs"):
            if not (package_root / required).is_file():
                raise ArtifactError(f"Rust crate is missing {required}")

        if smoke:
            consumer = Path(temp) / "consumer"
            (consumer / "src").mkdir(parents=True)
            path_value = package_root.as_posix().replace('"', '\\"')
            (consumer / "Cargo.toml").write_text(
                "[package]\n"
                'name = "adxl355-artifact-smoke"\n'
                'version = "0.0.0"\n'
                'edition = "2021"\n\n'
                "[dependencies]\n"
                f'adxl355 = {{ package = "adxl355-driver", path = "{path_value}" }}\n',
                encoding="utf-8",
            )
            (consumer / "src/main.rs").write_text(
                "fn main() { let _ = adxl355::Range::G2; }\n", encoding="utf-8"
            )
            _run(["cargo", "check", "--offline"], cwd=consumer)

    return {
        "package": "rust",
        "version": version,
        "artifacts": [crate.name],
        "files": len(names),
        "smoke": smoke,
    }


def inspect_node(directory: Path, version: str, *, smoke: bool) -> dict[str, object]:
    tarball = _single(directory, "*.tgz")
    with tarfile.open(tarball, "r:gz") as handle:
        names = _safe_members(member.name for member in handle.getmembers())
        package_member = handle.extractfile("package/package.json")
        if package_member is None:
            raise ArtifactError("npm tarball is missing package.json")
        package = json.load(package_member)

    if package.get("name") != "@oaslananka/adxl355":
        raise ArtifactError("npm package name mismatch")
    if package.get("version") != version:
        raise ArtifactError("npm package version mismatch")
    if set(package.get("exports", {})) != {"."}:
        raise ArtifactError("npm package exposes unsupported entry points")
    allowed_roots = {"package/LICENSE", "package/README.md", "package/package.json"}
    for name in names:
        if name in allowed_roots or name.startswith("package/dist/"):
            continue
        raise ArtifactError(f"npm tarball contains unexpected file: {name}")

    if smoke:
        with tempfile.TemporaryDirectory(prefix="adxl355-node-artifact-") as temp:
            consumer = Path(temp)
            (consumer / "package.json").write_text(
                json.dumps({"name": "artifact-smoke", "private": True, "type": "module"})
                + "\n",
                encoding="utf-8",
            )
            _run(
                [
                    "npm",
                    "install",
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                    str(tarball),
                ],
                cwd=consumer,
            )
            _run(
                [
                    "node",
                    "--input-type=module",
                    "-e",
                    (
                        "const m = await import('@oaslananka/adxl355'); "
                        "if (m.decodeRaw20(0,0,0) !== 0) process.exit(1);"
                    ),
                ],
                cwd=consumer,
            )

    return {
        "package": "node",
        "version": version,
        "artifacts": [tarball.name],
        "files": len(names),
        "smoke": smoke,
    }


def inspect_go(directory: Path, version: str, *, smoke: bool) -> dict[str, object]:
    archive = _single(directory, f"adxl355-go-{version}.tar.gz")
    with tempfile.TemporaryDirectory(prefix="adxl355-go-artifact-") as temp:
        extracted = Path(temp)
        names = _extract_tar(archive, extracted)
        prefix = f"adxl355-go-{version}/"
        if not all(name == prefix.rstrip("/") or name.startswith(prefix) for name in names):
            raise ArtifactError("Go archive contains an unexpected prefix")
        module_root = extracted / prefix.rstrip("/")
        first_line = (module_root / "go.mod").read_text(encoding="utf-8").splitlines()[0]
        if first_line != "module github.com/oaslananka/adxl355/go":
            raise ArtifactError("Go module path mismatch")
        if smoke:
            _run(["go", "test", "./..."], cwd=module_root)
            _run(["go", "build", "./..."], cwd=module_root)

    return {
        "package": "go",
        "version": version,
        "artifacts": [archive.name],
        "files": len(names),
        "smoke": smoke,
    }


def inspect_native(directory: Path, version: str, *, smoke: bool) -> dict[str, object]:
    archive = _single(directory, f"adxl355-c-cpp-{version}.tar.gz")
    with tempfile.TemporaryDirectory(prefix="adxl355-native-artifact-") as temp:
        extracted = Path(temp)
        names = _extract_tar(archive, extracted)
        required = (
            "include/adxl355/adxl355.h",
            "include/adxl355/adxl355_version.h",
            "include/adxl355-cpp/adxl355.hpp",
            "lib/libadxl355.a",
            "bin/adxl355-c-basic-read",
            "bin/adxl355-cpp-basic-read",
            "BUILD_INFO.txt",
        )
        for path in required:
            if not (extracted / path).is_file():
                raise ArtifactError(f"native archive is missing {path}")
        build_info = (extracted / "BUILD_INFO.txt").read_text(encoding="utf-8")
        if f"version={version}\n" not in build_info:
            raise ArtifactError("native archive version metadata mismatch")
        if smoke:
            _run([str(extracted / "bin/adxl355-c-basic-read")], cwd=extracted)
            _run([str(extracted / "bin/adxl355-cpp-basic-read")], cwd=extracted)

    return {
        "package": "c-cpp",
        "version": version,
        "artifacts": [archive.name],
        "files": len(names),
        "smoke": smoke,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", choices=("python", "rust", "node", "go", "native"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--no-smoke", action="store_true")
    args = parser.parse_args(argv)

    inspectors = {
        "python": inspect_python,
        "rust": inspect_rust,
        "node": inspect_node,
        "go": inspect_go,
        "native": inspect_native,
    }
    try:
        report = inspectors[args.package](
            args.directory.resolve(), args.version, smoke=not args.no_smoke
        )
    except (ArtifactError, OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f"release artifact verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "ok", **report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
