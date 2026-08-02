#!/usr/bin/env python3
"""Verify immutable registry releases against already-reviewed package artifacts."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import tarfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath
from typing import Any, Final


USER_AGENT: Final = "oaslananka-adxl355-registry-verifier/1"
PYPI_PACKAGE: Final = "adxl355"
NPM_PACKAGE: Final = "@oaslananka/adxl355"
CRATES_PACKAGE: Final = "adxl355-driver"


class RegistryError(ValueError):
    """Raised when local or remote registry state violates release immutability."""


def _single(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise RegistryError(
            f"expected exactly one {pattern!r} artifact in {directory}, found {len(matches)}"
        )
    return matches[0]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _request_json(url: str) -> dict[str, Any] | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RegistryError(
            f"registry request failed with HTTP {exc.code}: {url}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RegistryError(f"registry request failed: {url}") from exc
    if not isinstance(payload, dict):
        raise RegistryError(f"registry returned a non-object response: {url}")
    return payload


def _python_local(directory: Path, expected_version: str) -> dict[str, Any]:
    wheel = _single(directory, "*.whl")
    sdist = _single(directory, "*.tar.gz")
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            raise RegistryError("Python wheel must contain exactly one METADATA file")
        metadata = BytesParser(policy=default).parsebytes(
            archive.read(metadata_names[0])
        )
    if metadata.get("Name") != PYPI_PACKAGE:
        raise RegistryError("Python wheel package name mismatch")
    if metadata.get("Version") != expected_version:
        raise RegistryError("Python wheel version mismatch")
    with tarfile.open(sdist, "r:gz") as archive:
        pkg_info_names = [
            member.name
            for member in archive.getmembers()
            if PurePosixPath(member.name).name == "PKG-INFO"
            and len(PurePosixPath(member.name).parts) == 2
        ]
        if len(pkg_info_names) != 1:
            raise RegistryError("Python sdist must contain exactly one PKG-INFO file")
        pkg_info_file = archive.extractfile(pkg_info_names[0])
        if pkg_info_file is None:
            raise RegistryError("Python sdist PKG-INFO is unreadable")
        pkg_info = BytesParser(policy=default).parsebytes(pkg_info_file.read())
    if pkg_info.get("Name") != PYPI_PACKAGE:
        raise RegistryError("Python sdist package name mismatch")
    if pkg_info.get("Version") != expected_version:
        raise RegistryError("Python sdist version mismatch")
    artifacts = {path.name: _sha256(path) for path in (wheel, sdist)}
    return {
        "package": PYPI_PACKAGE,
        "version": expected_version,
        "artifacts": artifacts,
        "url": f"https://pypi.org/pypi/{PYPI_PACKAGE}/{expected_version}/json",
    }


def _node_local(directory: Path, expected_version: str) -> dict[str, Any]:
    tarball = _single(directory, "*.tgz")
    with tarfile.open(tarball, "r:gz") as archive:
        member = archive.extractfile("package/package.json")
        if member is None:
            raise RegistryError("npm artifact is missing package/package.json")
        package = json.load(member)
    if package.get("name") != NPM_PACKAGE:
        raise RegistryError("npm artifact package name mismatch")
    if package.get("version") != expected_version:
        raise RegistryError("npm artifact version mismatch")
    content = tarball.read_bytes()
    sha512 = base64.b64encode(hashlib.sha512(content).digest()).decode("ascii")
    return {
        "package": NPM_PACKAGE,
        "version": expected_version,
        "artifacts": {tarball.name: _sha256(tarball)},
        "integrity": f"sha512-{sha512}",
        "url": (
            "https://registry.npmjs.org/"
            f"{urllib.parse.quote(NPM_PACKAGE, safe='')}/{expected_version}"
        ),
    }


def _rust_local(directory: Path, expected_version: str) -> dict[str, Any]:
    crate = _single(directory, f"{CRATES_PACKAGE}-*.crate")
    with tarfile.open(crate, "r:gz") as archive:
        manifest_names = [
            member.name
            for member in archive.getmembers()
            if member.name.endswith("/Cargo.toml")
        ]
        if len(manifest_names) != 1:
            raise RegistryError("Rust crate must contain exactly one Cargo.toml")
        manifest_file = archive.extractfile(manifest_names[0])
        if manifest_file is None:
            raise RegistryError("Rust crate Cargo.toml is unreadable")
        manifest = tomllib.loads(manifest_file.read().decode("utf-8"))
    package = manifest.get("package", {})
    if package.get("name") != CRATES_PACKAGE:
        raise RegistryError("Rust artifact package name mismatch")
    if package.get("version") != expected_version:
        raise RegistryError("Rust artifact version mismatch")
    return {
        "package": CRATES_PACKAGE,
        "version": expected_version,
        "artifacts": {crate.name: _sha256(crate)},
        "checksum": _sha256(crate),
        "url": f"https://crates.io/api/v1/crates/{CRATES_PACKAGE}/{expected_version}",
    }


def _compare_python(local: dict[str, Any], remote: dict[str, Any]) -> None:
    urls = remote.get("urls")
    if not isinstance(urls, list):
        raise RegistryError("PyPI response is missing release files")
    remote_artifacts: dict[str, str] = {}
    for entry in urls:
        if not isinstance(entry, dict):
            raise RegistryError("PyPI returned malformed release file metadata")
        filename = entry.get("filename")
        digests = entry.get("digests")
        sha256 = digests.get("sha256") if isinstance(digests, dict) else None
        if not isinstance(filename, str) or not isinstance(sha256, str):
            raise RegistryError("PyPI returned incomplete release file metadata")
        remote_artifacts[filename] = sha256
    if remote_artifacts != local["artifacts"]:
        raise RegistryError("published PyPI release does not match verified artifacts")


def _compare_node(local: dict[str, Any], remote: dict[str, Any]) -> None:
    if (
        remote.get("name") != local["package"]
        or remote.get("version") != local["version"]
    ):
        raise RegistryError("published npm identity does not match verified artifact")
    dist = remote.get("dist")
    if not isinstance(dist, dict):
        raise RegistryError("npm response is missing distribution metadata")
    if dist.get("integrity") != local["integrity"]:
        raise RegistryError("published npm release does not match verified artifact")


def _compare_rust(local: dict[str, Any], remote: dict[str, Any]) -> None:
    version = remote.get("version")
    if not isinstance(version, dict):
        raise RegistryError("crates.io response is missing version metadata")
    if version.get("num") != local["version"]:
        raise RegistryError(
            "published crates.io version does not match verified artifact"
        )
    if version.get("checksum") != local["checksum"]:
        raise RegistryError(
            "published crates.io release does not match verified artifact"
        )


def inspect_registry(family: str, directory: Path, version: str) -> dict[str, Any]:
    """Return absent/exact registry state, blocking any partial or changed release."""
    if family == "python":
        local = _python_local(directory, version)
        compare = _compare_python
    elif family == "node":
        local = _node_local(directory, version)
        compare = _compare_node
    elif family == "rust":
        local = _rust_local(directory, version)
        compare = _compare_rust
    else:
        raise RegistryError(f"unsupported registry family: {family!r}")

    remote = _request_json(str(local["url"]))
    if remote is None:
        return {
            "family": family,
            "package": local["package"],
            "version": version,
            "state": "absent",
            "publish_required": True,
            "artifacts": local["artifacts"],
        }
    compare(local, remote)
    return {
        "family": family,
        "package": local["package"],
        "version": version,
        "state": "exact",
        "publish_required": False,
        "artifacts": local["artifacts"],
    }


def _github_output(result: dict[str, Any]) -> str:
    """Return fixed-key GitHub output records without accepting a filesystem path."""
    return "".join(
        (
            f"state={result['state']}\n",
            f"publish_required={str(result['publish_required']).lower()}\n",
            f"package={result['package']}\n",
            f"version={result['version']}\n",
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("family", choices=("python", "node", "rust"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--require-published", action="store_true")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    parser.add_argument("--github-output", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.attempts < 1 or args.attempts > 60:
        raise RegistryError("attempts must be in the range 1..60")
    if args.interval_seconds < 0 or args.interval_seconds > 60:
        raise RegistryError("interval-seconds must be in the range 0..60")

    result: dict[str, Any] | None = None
    for attempt in range(1, args.attempts + 1):
        result = inspect_registry(args.family, args.directory, args.version)
        if result["state"] == "exact" or not args.require_published:
            break
        if attempt < args.attempts:
            time.sleep(args.interval_seconds)
    assert result is not None
    if args.require_published and result["state"] != "exact":
        raise RegistryError(
            f"{result['package']} {result['version']} was not observable after publication"
        )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.github_output:
        print(_github_output(result), end="")
        print(rendered, file=sys.stderr)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RegistryError as exc:
        print(f"registry release verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
