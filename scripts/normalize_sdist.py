#!/usr/bin/env python3
"""Normalize a Python sdist's archive metadata for reproducible release builds.

Run after the pinned setuptools builder and before generating checksums or signing.
The complete source payload is preserved; only tar/gzip container metadata changes.
"""

from __future__ import annotations

import argparse
import gzip
import os
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


class SdistError(ValueError):
    """Archive contains entries unsuitable for normalized source packaging."""


def _read_archive_members(archive: Path) -> list[tuple[tarfile.TarInfo, bytes | None]]:
    contents: list[tuple[tarfile.TarInfo, bytes | None]] = []
    names: set[str] = set()
    with tarfile.open(archive, "r:gz") as source:
        for member in source.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or not name.parts:
                raise SdistError(f"unsafe archive path: {member.name!r}")
            if member.name in names:
                raise SdistError(f"duplicate archive member: {member.name!r}")
            names.add(member.name)
            if member.isdir():
                contents.append((member, None))
                continue
            if not member.isfile():
                raise SdistError(f"unsupported archive member type: {member.name!r}")
            fileobj = source.extractfile(member)
            if fileobj is None:
                raise SdistError(f"missing archive payload: {member.name!r}")
            with fileobj:
                contents.append((member, fileobj.read()))
    return contents


def _add_member(
    target: tarfile.TarFile,
    original: tarfile.TarInfo,
    payload: bytes | None,
    epoch: int,
) -> None:
    member = tarfile.TarInfo(original.name)
    member.type = tarfile.DIRTYPE if payload is None else tarfile.REGTYPE
    member.size = 0 if payload is None else len(payload)
    member.mode = 0o755 if payload is None or original.mode & 0o111 else 0o644
    member.uid = member.gid = 0
    member.uname = member.gname = ""
    member.mtime = epoch
    if payload is None:
        target.addfile(member)
    else:
        from io import BytesIO

        target.addfile(member, BytesIO(payload))


def _write_archive(
    fileobj: object, contents: list[tuple[tarfile.TarInfo, bytes | None]], epoch: int
) -> None:
    with (
        gzip.GzipFile(fileobj=fileobj, mode="wb", filename="", mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as target,
    ):
        for original, payload in sorted(contents, key=lambda item: item[0].name):
            _add_member(target, original, payload, epoch)


def normalize_sdist(archive: Path, *, epoch: int) -> None:
    if epoch < 0:
        raise SdistError("SOURCE_DATE_EPOCH must be nonnegative")
    archive = archive.resolve(strict=True)
    if not archive.name.endswith(".tar.gz"):
        raise SdistError("expected a .tar.gz source distribution")
    contents = _read_archive_members(archive)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=archive.parent, prefix=f".{archive.stem}.", suffix=".tmp", delete=False
        ) as temp:
            temp_name = temp.name
            _write_archive(temp, contents, epoch)
        os.replace(temp_name, archive)
        temp_name = None
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--epoch", type=int, required=True, help="source commit UNIX timestamp"
    )
    args = parser.parse_args()
    normalize_sdist(args.archive, epoch=args.epoch)


if __name__ == "__main__":
    main()
