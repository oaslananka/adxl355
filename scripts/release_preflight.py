#!/usr/bin/env python3
"""Validate release tags, source state, and cross-package version consistency."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal


SEMVER_TAG = re.compile(
    r"^v(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?P<prerelease>-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?P<build>\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


@dataclass(frozen=True)
class ReleaseVersion:
    tag: str
    full: str
    core: str
    major: int
    minor: int
    patch: int


@dataclass(frozen=True)
class VersionSource:
    label: str
    value: str
    kind: Literal["full", "core"] = "full"


def parse_release_tag(tag: str) -> ReleaseVersion:
    match = SEMVER_TAG.fullmatch(tag)
    if match is None:
        raise ValueError(f"release tag must be strict SemVer prefixed with 'v': {tag!r}")

    prerelease = match.group("prerelease")
    if prerelease is not None:
        for identifier in prerelease[1:].split("."):
            if identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0"):
                raise ValueError(
                    f"numeric prerelease identifiers must not contain leading zeros: {tag!r}"
                )

    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    full = tag[1:]
    return ReleaseVersion(
        tag=tag,
        full=full,
        core=f"{major}.{minor}.{patch}",
        major=major,
        minor=minor,
        patch=patch,
    )


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _require_match(path: Path, pattern: str, description: str) -> re.Match[str]:
    match = re.search(pattern, path.read_text(), flags=re.MULTILINE)
    if match is None:
        raise ValueError(f"cannot read {description} from {path}")
    return match


def collect_version_sources(root: Path) -> list[VersionSource]:
    root = root.resolve()

    python_project = _read_toml(root / "python/pyproject.toml")
    rust_manifest = _read_toml(root / "rust/Cargo.toml")
    rust_lock = _read_toml(root / "rust/Cargo.lock")
    node_package = json.loads((root / "node/package.json").read_text())
    node_lock = json.loads((root / "node/package-lock.json").read_text())
    vectors = json.loads((root / "spec/test_vectors.json").read_text())

    rust_lock_version = next(
        (
            package["version"]
            for package in rust_lock.get("package", [])
            if package.get("name") == "adxl355"
        ),
        None,
    )
    if rust_lock_version is None:
        raise ValueError("rust/Cargo.lock does not contain the adxl355 package")

    c_cmake = _require_match(
        root / "c/CMakeLists.txt",
        r"project\(adxl355\s+VERSION\s+([^\s\)]+)",
        "C project version",
    ).group(1)
    cpp_cmake = _require_match(
        root / "cpp/CMakeLists.txt",
        r"project\(adxl355-cpp\s+VERSION\s+([^\s\)]+)",
        "C++ project version",
    ).group(1)

    version_header = root / "c/include/adxl355/adxl355_version.h"
    header_string = _require_match(
        version_header,
        r'#define\s+ADXL355_VERSION_STRING\s+"([^"]+)"',
        "C version string",
    ).group(1)
    header_major = _require_match(
        version_header, r"#define\s+ADXL355_VERSION_MAJOR\s+(\d+)", "C major version"
    ).group(1)
    header_minor = _require_match(
        version_header, r"#define\s+ADXL355_VERSION_MINOR\s+(\d+)", "C minor version"
    ).group(1)
    header_patch = _require_match(
        version_header, r"#define\s+ADXL355_VERSION_PATCH\s+(\d+)", "C patch version"
    ).group(1)
    header_core = f"{header_major}.{header_minor}.{header_patch}"

    python_runtime = _require_match(
        root / "python/src/adxl355/_version.py",
        r'__version__\s*=\s*"([^"]+)"',
        "Python runtime version",
    ).group(1)

    go_module = (root / "go/go.mod").read_text().splitlines()[0].strip()
    expected_go_module = "module github.com/oaslananka/adxl355/go"
    if go_module != expected_go_module:
        raise ValueError(
            f"go/go.mod module mismatch: expected {expected_go_module!r}, found {go_module!r}"
        )

    return [
        VersionSource("python/pyproject.toml", str(python_project["project"]["version"])),
        VersionSource("python/src/adxl355/_version.py", python_runtime),
        VersionSource("rust/Cargo.toml", str(rust_manifest["package"]["version"])),
        VersionSource("rust/Cargo.lock", str(rust_lock_version)),
        VersionSource("node/package.json", str(node_package["version"])),
        VersionSource("node/package-lock.json", str(node_lock["version"])),
        VersionSource(
            'node/package-lock.json packages[""]',
            str(node_lock["packages"][""]["version"]),
        ),
        VersionSource("c/CMakeLists.txt", c_cmake, "core"),
        VersionSource("cpp/CMakeLists.txt", cpp_cmake, "core"),
        VersionSource("c/include/adxl355/adxl355_version.h string", header_string),
        VersionSource("c/include/adxl355/adxl355_version.h components", header_core, "core"),
        VersionSource("spec/test_vectors.json", str(vectors["version"])),
    ]


def validate_versions(
    release: ReleaseVersion, sources: Iterable[VersionSource]
) -> list[str]:
    errors: list[str] = []
    for source in sources:
        expected = release.full if source.kind == "full" else release.core
        if source.value != expected:
            errors.append(
                f"{source.label}: expected {expected!r} from tag {release.tag!r}, "
                f"found {source.value!r}"
            )
    return errors


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def validate_git_state(root: Path, tag: str, expected_sha: str) -> str:
    head_sha = _git(root, "rev-parse", "HEAD")
    tag_sha = _git(root, "rev-parse", f"refs/tags/{tag}^{{commit}}")
    expected_sha = expected_sha.lower()

    errors: list[str] = []
    if head_sha.lower() != expected_sha:
        errors.append(f"checked-out HEAD {head_sha} does not match release SHA {expected_sha}")
    if tag_sha.lower() != expected_sha:
        errors.append(f"tag {tag!r} points to {tag_sha}, not release SHA {expected_sha}")

    dirty = _git(root, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        errors.append(f"release source tree is dirty:\n{dirty}")

    if errors:
        raise ValueError("\n".join(errors))
    return head_sha



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args(argv)

    try:
        release = parse_release_tag(args.tag)
        sources = collect_version_sources(args.root)
        errors = validate_versions(release, sources)
        if errors:
            raise ValueError("version consistency check failed:\n- " + "\n- ".join(errors))
        release_sha = validate_git_state(args.root, release.tag, args.sha)
    except (KeyError, OSError, ValueError) as error:
        print(f"release preflight failed: {error}", file=sys.stderr)
        return 1

    outputs = {
        "tag": release.tag,
        "version": release.full,
        "core_version": release.core,
        "release_sha": release_sha,
        "short_sha": release_sha[:12],
    }
    print(json.dumps({"status": "ok", **outputs, "sources": len(sources)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
