#!/usr/bin/env python3
"""Safely expand release package archives into a deterministic SBOM scan tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class SbomInputError(ValueError):
    """Raised when release artifacts cannot be prepared safely for SBOM scanning."""


@dataclass(frozen=True)
class SelectedArchive:
    kind: str
    path: Path


ARCHIVE_RULES = (
    ("python-wheel", re.compile(r"\.whl$")),
    ("rust-crate", re.compile(r"\.crate$")),
    ("node-tarball", re.compile(r"\.tgz$")),
    ("go-module", re.compile(r"/adxl355-go-[^/]+\.tar\.gz$")),
    ("native", re.compile(r"/adxl355-c-cpp-[^/]+\.tar\.gz$")),
)


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise SbomInputError(f"archive contains unsafe path: {name!r}")
    return path


def _archive_kind(relative: str) -> str | None:
    normalized = f"/{relative.replace(chr(92), '/')}"
    for kind, pattern in ARCHIVE_RULES:
        if pattern.search(normalized):
            return kind
    return None


def select_archives(artifacts_root: Path) -> list[SelectedArchive]:
    root = artifacts_root.resolve()
    selected: list[SelectedArchive] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        kind = _archive_kind(relative)
        if kind is not None:
            selected.append(SelectedArchive(kind, path))

    counts: dict[str, int] = {}
    for archive in selected:
        counts[archive.kind] = counts.get(archive.kind, 0) + 1
    expected = {kind for kind, _pattern in ARCHIVE_RULES}
    missing = expected - counts.keys()
    duplicates = {kind: count for kind, count in counts.items() if count != 1}
    if missing or duplicates:
        details: list[str] = []
        if missing:
            details.append(f"missing archive kinds: {', '.join(sorted(missing))}")
        if duplicates:
            details.append(
                "duplicate archive kinds: "
                + ", ".join(f"{kind}={count}" for kind, count in sorted(duplicates.items()))
            )
        raise SbomInputError("; ".join(details))
    return selected


def _extract_zip(archive: Path, destination: Path) -> int:
    count = 0
    with zipfile.ZipFile(archive) as handle:
        for info in handle.infolist():
            member = _safe_member(info.filename)
            target = destination.joinpath(*member.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            count += 1
    return count


def _extract_tar(archive: Path, destination: Path) -> int:
    count = 0
    with tarfile.open(archive, "r:*") as handle:
        for info in handle.getmembers():
            if info.name in {".", "./"} and info.isdir():
                continue
            member = _safe_member(info.name)
            if info.issym() or info.islnk() or info.isdev():
                raise SbomInputError(
                    f"archive contains unsupported link or device entry: {info.name!r}"
                )
            target = destination.joinpath(*member.parts)
            if info.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not info.isfile():
                continue
            source = handle.extractfile(info)
            if source is None:
                raise SbomInputError(f"cannot read archive member: {info.name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            count += 1
    return count



def _require_single(root: Path, pattern: str) -> Path:
    matches = sorted(root.rglob(pattern))
    if len(matches) != 1:
        raise SbomInputError(
            f"expected exactly one {pattern!r} below {root}, found {len(matches)}"
        )
    return matches[0]


def _metadata_value(text: str, field: str) -> str:
    prefix = f"{field}:"
    for line in text.splitlines():
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
            if value:
                return value
    raise SbomInputError(f"package metadata is missing {field!r}")


def _package_identity(kind: str, destination: Path, archive_name: str) -> tuple[str, str, str]:
    if kind == "python-wheel":
        metadata = _require_single(destination, "METADATA").read_text(encoding="utf-8")
        name = _metadata_value(metadata, "Name")
        version = _metadata_value(metadata, "Version")
        return name, version, f"pkg:pypi/{name.lower()}@{version}"

    if kind == "rust-crate":
        with _require_single(destination, "Cargo.toml").open("rb") as handle:
            package = tomllib.load(handle)["package"]
        name = str(package["name"])
        version = str(package["version"])
        return name, version, f"pkg:cargo/{name}@{version}"

    if kind == "node-tarball":
        package_path = _require_single(destination, "package.json")
        package = json.loads(package_path.read_text(encoding="utf-8"))
        name = str(package["name"])
        version = str(package["version"])
        encoded_name = name.replace("@", "%40", 1)
        return name, version, f"pkg:npm/{encoded_name}@{version}"

    if kind == "go-module":
        module_line = _require_single(destination, "go.mod").read_text(encoding="utf-8").splitlines()[0]
        if not module_line.startswith("module "):
            raise SbomInputError("Go artifact contains an invalid module declaration")
        name = module_line.removeprefix("module ").strip()
        match = re.fullmatch(r"adxl355-go-(.+)\.tar\.gz", archive_name)
        if match is None:
            raise SbomInputError(f"cannot derive Go artifact version from {archive_name!r}")
        version = match.group(1)
        return name, version, f"pkg:golang/{name}@{version}"

    if kind == "native":
        build_info = _require_single(destination, "BUILD_INFO.txt").read_text(encoding="utf-8")
        version_line = next(
            (line for line in build_info.splitlines() if line.startswith("version=")), None
        )
        if version_line is None or not version_line.removeprefix("version="):
            raise SbomInputError("native artifact is missing version metadata")
        version = version_line.removeprefix("version=")
        name = "adxl355-c-cpp"
        return name, version, f"pkg:generic/{name}@{version}"

    raise SbomInputError(f"unsupported archive kind: {kind}")

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_sbom_input(artifacts_root: Path, output_root: Path) -> dict[str, object]:
    artifacts = artifacts_root.resolve()
    output = output_root.resolve()
    if not artifacts.is_dir():
        raise SbomInputError(f"artifact root does not exist: {artifacts}")
    if output == artifacts or artifacts in output.parents:
        raise SbomInputError("SBOM output must not be inside the artifact root")

    archives = select_archives(artifacts)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    entries: list[dict[str, object]] = []
    for archive in archives:
        destination = output / archive.kind
        destination.mkdir()
        if archive.path.suffix == ".whl":
            files = _extract_zip(archive.path, destination)
        else:
            files = _extract_tar(archive.path, destination)
        if files == 0:
            raise SbomInputError(f"archive extracted no files: {archive.path.name}")
        name, version, purl = _package_identity(
            archive.kind, destination, archive.path.name
        )
        entries.append(
            {
                "kind": archive.kind,
                "archive": archive.path.relative_to(artifacts).as_posix(),
                "name": name,
                "version": version,
                "purl": purl,
                "sha256": _sha256(archive.path),
                "files": files,
            }
        )

    manifest = {
        "schema_version": 1,
        "source": "verified-release-artifacts",
        "archives": entries,
    }
    (output / "SBOM_INPUT.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = prepare_sbom_input(args.artifacts_root, args.output)
    except (OSError, SbomInputError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"SBOM input preparation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "ok", **report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
