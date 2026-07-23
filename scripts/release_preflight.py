#!/usr/bin/env python3
"""Validate release tags, source state, package identities, and version consistency."""

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

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.versioning import VersionSet, load_version  # noqa: E402


@dataclass(frozen=True)
class ReleaseVersion:
    tag: str
    full: str
    python: str
    core: str
    go_tag: str
    major: int
    minor: int
    patch: int


@dataclass(frozen=True)
class VersionSource:
    label: str
    value: str
    kind: Literal["semver", "python", "core"] = "semver"


def parse_release_tag(tag: str) -> ReleaseVersion:
    if not tag.startswith("v"):
        raise ValueError(f"release tag must be strict SemVer prefixed with 'v': {tag!r}")
    try:
        version = VersionSet.parse(tag[1:])
    except ValueError as error:
        raise ValueError(f"invalid release tag {tag!r}: {error}") from error
    return ReleaseVersion(
        tag=tag,
        full=version.semver,
        python=version.python,
        core=version.core,
        go_tag=version.go_tag,
        major=version.major,
        minor=version.minor,
        patch=version.patch,
    )


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _require_match(path: Path, pattern: str, description: str) -> re.Match[str]:
    match = re.search(pattern, path.read_text(encoding="utf-8"), flags=re.MULTILINE)
    if match is None:
        raise ValueError(f"cannot read {description} from {path}")
    return match


def _validate_package_identities(
    rust_manifest: dict[str, Any], node_package: dict[str, Any], node_lock: dict[str, Any]
) -> None:
    package = rust_manifest["package"]
    if package.get("name") != "adxl355-driver":
        raise ValueError("rust/Cargo.toml package name must be 'adxl355-driver'")
    if rust_manifest.get("lib", {}).get("name") != "adxl355":
        raise ValueError("rust/Cargo.toml [lib] name must preserve the 'adxl355' import")

    expected_node = "@oaslananka/adxl355"
    node_names = {
        "node/package.json": node_package.get("name"),
        "node/package-lock.json": node_lock.get("name"),
        'node/package-lock.json packages[""]': node_lock.get("packages", {})
        .get("", {})
        .get("name"),
    }
    mismatches = [f"{label}={value!r}" for label, value in node_names.items() if value != expected_node]
    if mismatches:
        raise ValueError(
            "Node package identity must be '@oaslananka/adxl355': " + ", ".join(mismatches)
        )


def collect_version_sources(root: Path) -> list[VersionSource]:
    root = root.resolve()

    canonical = load_version(root)
    python_project = _read_toml(root / "python/pyproject.toml")
    rust_manifest = _read_toml(root / "rust/Cargo.toml")
    rust_lock = _read_toml(root / "rust/Cargo.lock")
    node_package = json.loads((root / "node/package.json").read_text(encoding="utf-8"))
    node_lock = json.loads((root / "node/package-lock.json").read_text(encoding="utf-8"))
    vectors = json.loads((root / "spec/test_vectors.json").read_text(encoding="utf-8"))
    _validate_package_identities(rust_manifest, node_package, node_lock)

    rust_lock_version = next(
        (
            package["version"]
            for package in rust_lock.get("package", [])
            if package.get("name") == "adxl355-driver"
        ),
        None,
    )
    if rust_lock_version is None:
        raise ValueError("rust/Cargo.lock does not contain the adxl355-driver package")

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
    header_core = ".".join(
        _require_match(
            version_header,
            rf"#define\s+ADXL355_VERSION_{name}\s+(\d+)",
            f"C {name.lower()} version",
        ).group(1)
        for name in ("MAJOR", "MINOR", "PATCH")
    )

    changelog_version = _require_match(
        root / "CHANGELOG.md",
        r"^## \[([^\]]+)\] - Unreleased$",
        "CHANGELOG Unreleased version",
    ).group(1)

    python_runtime = _require_match(
        root / "python/src/adxl355/_version.py",
        r'__version__\s*=\s*"([^"]+)"',
        "Python runtime version",
    ).group(1)

    go_module = (root / "go/go.mod").read_text(encoding="utf-8").splitlines()[0].strip()
    expected_go_module = "module github.com/oaslananka/adxl355/go"
    if go_module != expected_go_module:
        raise ValueError(
            f"go/go.mod module mismatch: expected {expected_go_module!r}, found {go_module!r}"
        )

    return [
        VersionSource("VERSION", canonical.semver),
        VersionSource(
            "python/pyproject.toml", str(python_project["project"]["version"]), "python"
        ),
        VersionSource("python/src/adxl355/_version.py", python_runtime, "python"),
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
        VersionSource(
            "c/include/adxl355/adxl355_version.h components", header_core, "core"
        ),
        VersionSource("spec/test_vectors.json", str(vectors["version"])),
        VersionSource("CHANGELOG.md Unreleased", changelog_version),
    ]


def validate_versions(
    release: ReleaseVersion, sources: Iterable[VersionSource]
) -> list[str]:
    expected_by_kind = {
        "semver": release.full,
        "python": release.python,
        "core": release.core,
    }
    errors: list[str] = []
    for source in sources:
        expected = expected_by_kind[source.kind]
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
        "python_version": release.python,
        "core_version": release.core,
        "go_tag": release.go_tag,
        "rust_crate_name": "adxl355-driver",
        "node_package_name": "@oaslananka/adxl355",
        "release_sha": release_sha,
        "short_sha": release_sha[:12],
    }
    print(json.dumps({"status": "ok", **outputs, "sources": len(sources)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
