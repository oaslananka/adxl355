#!/usr/bin/env python3
"""Map the canonical repository version into ecosystem-specific declarations."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PYTHON_PROJECT_PATH = "python/pyproject.toml"
PYTHON_RUNTIME_PATH = "python/src/adxl355/_version.py"
RUST_MANIFEST_PATH = "rust/Cargo.toml"
RUST_LOCK_PATH = "rust/Cargo.lock"
NODE_PACKAGE_PATH = "node/package.json"
NODE_LOCK_PATH = "node/package-lock.json"
C_CMAKE_PATH = "c/CMakeLists.txt"
CPP_CMAKE_PATH = "cpp/CMakeLists.txt"
VECTOR_SPEC_PATH = "spec/test_vectors.json"
VERSION_HEADER_PATH = "c/include/adxl355/adxl355_version.h"
CHANGELOG_PATH = "CHANGELOG.md"


SEMVER = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<label>alpha|beta|rc)\.(?P<number>0|[1-9]\d*))?$"
)


@dataclass(frozen=True)
class VersionSet:
    """Canonical SemVer and its required ecosystem representations."""

    semver: str
    python: str
    core: str
    root_tag: str
    go_tag: str
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "VersionSet":
        normalized = value.strip()
        match = SEMVER.fullmatch(normalized)
        if match is None:
            raise ValueError(
                "version must be strict SemVer with a supported prerelease "
                "shape: alpha.N, beta.N, or rc.N"
            )

        major = int(match.group("major"))
        minor = int(match.group("minor"))
        patch = int(match.group("patch"))
        core = f"{major}.{minor}.{patch}"
        label = match.group("label")
        number = match.group("number")
        if label is None:
            python_version = core
        else:
            pep_label = {"alpha": "a", "beta": "b", "rc": "rc"}[label]
            python_version = f"{core}{pep_label}{number}"

        return cls(
            semver=normalized,
            python=python_version,
            core=core,
            root_tag=f"v{normalized}",
            go_tag=f"go/v{normalized}",
            major=major,
            minor=minor,
            patch=patch,
        )


def load_version(root: Path) -> VersionSet:
    """Read the canonical version from ``VERSION``."""

    path = root.resolve() / "VERSION"
    return VersionSet.parse(path.read_text(encoding="utf-8"))


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"cannot update {label}")
    return updated


def _current_values(root: Path) -> dict[str, str]:
    python_project = _read_toml(root / PYTHON_PROJECT_PATH)
    rust_manifest = _read_toml(root / RUST_MANIFEST_PATH)
    rust_lock = _read_toml(root / RUST_LOCK_PATH)
    node_package = json.loads((root / NODE_PACKAGE_PATH).read_text())
    node_lock = json.loads((root / NODE_LOCK_PATH).read_text())
    vectors = json.loads((root / VECTOR_SPEC_PATH).read_text())

    rust_package = next(
        (
            package
            for package in rust_lock.get("package", [])
            if package.get("name") in {"adxl355", "adxl355-driver"}
        ),
        None,
    )
    if rust_package is None:
        raise ValueError("rust/Cargo.lock does not contain this repository's crate")

    c_text = (root / C_CMAKE_PATH).read_text()
    cpp_text = (root / CPP_CMAKE_PATH).read_text()
    header = (root / VERSION_HEADER_PATH).read_text()
    runtime = (root / PYTHON_RUNTIME_PATH).read_text()
    changelog = (root / CHANGELOG_PATH).read_text()

    def require(text: str, pattern: str, label: str) -> str:
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match is None:
            raise ValueError(f"cannot read {label}")
        return match.group(1)

    return {
        PYTHON_PROJECT_PATH: str(python_project["project"]["version"]),
        PYTHON_RUNTIME_PATH: require(
            runtime, r'__version__\s*=\s*"([^"]+)"', "Python runtime version"
        ),
        RUST_MANIFEST_PATH: str(rust_manifest["package"]["version"]),
        RUST_LOCK_PATH: str(rust_package["version"]),
        NODE_PACKAGE_PATH: str(node_package["version"]),
        NODE_LOCK_PATH: str(node_lock["version"]),
        'node/package-lock.json packages[""]': str(node_lock["packages"][""]["version"]),
        C_CMAKE_PATH: require(
            c_text,
            r"project\(adxl355\s+VERSION\s+([^\s\)]+)",
            "C project version",
        ),
        CPP_CMAKE_PATH: require(
            cpp_text,
            r"project\(adxl355-cpp\s+VERSION\s+([^\s\)]+)",
            "C++ project version",
        ),
        "c/include/adxl355/adxl355_version.h string": require(
            header,
            r'#define\s+ADXL355_VERSION_STRING\s+"([^"]+)"',
            "C version string",
        ),
        "c/include/adxl355/adxl355_version.h components": ".".join(
            require(
                header,
                rf"#define\s+ADXL355_VERSION_{name}\s+(\d+)",
                f"C {name.lower()} version",
            )
            for name in ("MAJOR", "MINOR", "PATCH")
        ),
        VECTOR_SPEC_PATH: str(vectors["version"]),
        "CHANGELOG.md Unreleased": require(
            changelog,
            r"^## \[([^\]]+)\] - Unreleased$",
            "CHANGELOG Unreleased version",
        ),
    }


def _expected_values(version: VersionSet) -> dict[str, str]:
    return {
        PYTHON_PROJECT_PATH: version.python,
        PYTHON_RUNTIME_PATH: version.python,
        RUST_MANIFEST_PATH: version.semver,
        RUST_LOCK_PATH: version.semver,
        NODE_PACKAGE_PATH: version.semver,
        NODE_LOCK_PATH: version.semver,
        'node/package-lock.json packages[""]': version.semver,
        C_CMAKE_PATH: version.core,
        CPP_CMAKE_PATH: version.core,
        "c/include/adxl355/adxl355_version.h string": version.semver,
        "c/include/adxl355/adxl355_version.h components": version.core,
        VECTOR_SPEC_PATH: version.semver,
        "CHANGELOG.md Unreleased": version.semver,
    }


def _write_versions(root: Path, version: VersionSet) -> None:
    pyproject = root / PYTHON_PROJECT_PATH
    pyproject.write_text(
        _replace_once(
            pyproject.read_text(),
            r'^(version\s*=\s*)"[^"]+"',
            rf'\g<1>"{version.python}"',
            str(pyproject),
        )
    )

    runtime = root / PYTHON_RUNTIME_PATH
    runtime.write_text(f'__version__ = "{version.python}"\n')

    cargo = root / RUST_MANIFEST_PATH
    cargo.write_text(
        _replace_once(
            cargo.read_text(),
            r'^(version\s*=\s*)"[^"]+"',
            rf'\g<1>"{version.semver}"',
            str(cargo),
        )
    )

    cargo_lock = root / RUST_LOCK_PATH
    lock_text = cargo_lock.read_text()
    lock_pattern = (
        r'(\[\[package\]\]\nname = "(?:adxl355|adxl355-driver)"\nversion = )"[^"]+"'
    )
    cargo_lock.write_text(
        _replace_once(
            lock_text,
            lock_pattern,
            rf'\g<1>"{version.semver}"',
            str(cargo_lock),
        )
    )

    package = root / NODE_PACKAGE_PATH
    package_data = json.loads(package.read_text())
    package_data["version"] = version.semver
    package.write_text(json.dumps(package_data, indent=2) + "\n")

    package_lock = root / NODE_LOCK_PATH
    package_lock_data = json.loads(package_lock.read_text())
    package_lock_data["version"] = version.semver
    package_lock_data["packages"][""]["version"] = version.semver
    package_lock.write_text(json.dumps(package_lock_data, indent=2) + "\n")

    for relative, project in (
        (C_CMAKE_PATH, "adxl355"),
        (CPP_CMAKE_PATH, "adxl355-cpp"),
    ):
        path = root / relative
        path.write_text(
            _replace_once(
                path.read_text(),
                rf"(project\({re.escape(project)}\s+VERSION\s+)[^\s\)]+",
                rf"\g<1>{version.core}",
                str(path),
            )
        )

    header = root / VERSION_HEADER_PATH
    header_text = header.read_text()
    for name, value in (
        ("MAJOR", version.major),
        ("MINOR", version.minor),
        ("PATCH", version.patch),
    ):
        header_text = _replace_once(
            header_text,
            rf"(#define\s+ADXL355_VERSION_{name}\s+)\d+",
            rf"\g<1>{value}",
            str(header),
        )
    header_text = _replace_once(
        header_text,
        r'(#define\s+ADXL355_VERSION_STRING\s+)"[^"]+"',
        rf'\g<1>"{version.semver}"',
        str(header),
    )
    header.write_text(header_text)

    vectors = root / VECTOR_SPEC_PATH
    vectors.write_text(
        _replace_once(
            vectors.read_text(),
            r'^(  "version": )"[^"]+"',
            rf'\g<1>"{version.semver}"',
            str(vectors),
        )
    )

    changelog = root / CHANGELOG_PATH
    changelog.write_text(
        _replace_once(
            changelog.read_text(),
            r"^(## \[[^\]]+\] - Unreleased)$",
            f"## [{version.semver}] - Unreleased",
            str(changelog),
        )
    )


def sync_versions(root: Path, *, write: bool) -> list[str]:
    """Check or update every maintained version declaration."""

    root = root.resolve()
    version = load_version(root)
    if write:
        _write_versions(root, version)

    actual = _current_values(root)
    expected = _expected_values(version)
    errors = []
    for label, expected_value in expected.items():
        actual_value = actual[label]
        if actual_value != expected_value:
            errors.append(
                f"{label}: expected {expected_value!r} from VERSION, found {actual_value!r}"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write", action="store_true", help="Update declarations in place")
    args = parser.parse_args(argv)

    try:
        errors = sync_versions(args.root, write=args.write)
    except (KeyError, OSError, ValueError) as error:
        print(f"version synchronization failed: {error}", file=sys.stderr)
        return 1
    if errors:
        print("version synchronization failed:", file=sys.stderr)
        for message in errors:
            print(f"- {message}", file=sys.stderr)
        return 1

    version = load_version(args.root)
    print(
        json.dumps(
            {
                "status": "ok",
                "canonical": version.semver,
                "python": version.python,
                "core": version.core,
                "root_tag": version.root_tag,
                "go_tag": version.go_tag,
                "updated": args.write,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
