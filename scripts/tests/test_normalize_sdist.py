"""Regression tests for deterministic, safe source archive metadata."""

from __future__ import annotations

import gzip
import tarfile
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import os
import stat

from scripts.normalize_sdist import SdistError, normalize_sdist


class NormalizeSdistTests(unittest.TestCase):
    @staticmethod
    def sample(path: Path, *, mtime: int, uid: int = 1000) -> None:
        with path.open("wb") as output:
            with gzip.GzipFile(
                filename="sdist", fileobj=output, mode="wb", mtime=mtime
            ) as gz:
                with tarfile.open(fileobj=gz, mode="w") as tar:
                    for name, contents in (
                        ("package-1.0/setup.cfg", b"[metadata]\nname = package\n"),
                        ("package-1.0/package.py", b"print('ok')\n"),
                    ):
                        member = tarfile.TarInfo(name)
                        member.size = len(contents)
                        member.mtime = mtime
                        member.uid = uid
                        tar.addfile(member, BytesIO(contents))

    def test_different_initial_archives_normalize_identically_and_idempotently(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            a, b = folder / "a.tar.gz", folder / "b.tar.gz"
            self.sample(a, mtime=1000)
            self.sample(b, mtime=2000, uid=2000)
            self.assertNotEqual(a.read_bytes(), b.read_bytes())
            for archive in (a, b):
                normalize_sdist(archive, epoch=1793810237)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            normalize_sdist(a, epoch=1793810237)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with tarfile.open(a, "r:gz") as tar:
                names = tar.getnames()
                self.assertEqual(names, sorted(names))
                self.assertTrue(all(m.mtime == 1793810237 and m.uid == 0 for m in tar))
                self.assertEqual(
                    tar.extractfile("package-1.0/package.py").read(), b"print('ok')\n"
                )

    def test_traversal_and_symlinks_are_rejected_without_modification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for path, symlink in (("../escape", False), ("package-1.0/bad", True)):
                archive = Path(temporary) / "bad.tar.gz"
                with tarfile.open(archive, "w:gz") as tar:
                    member = tarfile.TarInfo(path)
                    if symlink:
                        member.type = tarfile.SYMTYPE
                        member.linkname = "/etc/shadow"
                    else:
                        member.size = 1
                    tar.addfile(member, None if symlink else BytesIO(b"x"))
                before = archive.read_bytes()
                with self.assertRaises(SdistError):
                    normalize_sdist(archive, epoch=1)
                self.assertEqual(archive.read_bytes(), before)

    def test_directory_entry_preserved_and_original_permissions_retained(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "package.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                directory = tarfile.TarInfo("package-1.0/")
                directory.type = tarfile.DIRTYPE
                tar.addfile(directory)
                file = tarfile.TarInfo("package-1.0/module.py")
                file.size = 2
                tar.addfile(file, BytesIO(b"x\n"))
            archive.chmod(0o640)
            before = stat.S_IMODE(archive.stat().st_mode)
            normalize_sdist(archive, epoch=42)
            self.assertEqual(stat.S_IMODE(archive.stat().st_mode), before)
            with tarfile.open(archive, "r:gz") as tar:
                self.assertTrue(tar.getmember("package-1.0").isdir())
                self.assertEqual(
                    tar.extractfile("package-1.0/module.py").read(), b"x\n"
                )

    def test_cli_normalizes_and_rejects_wrong_extension(self) -> None:
        from scripts import normalize_sdist as module

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.tar.gz"
            self.sample(path, mtime=100)
            with patch("sys.argv", ["normalize_sdist.py", str(path), "--epoch", "456"]):
                module.main()
            with tarfile.open(path, "r:gz") as archive:
                self.assertTrue(all(member.mtime == 456 for member in archive))
            path.rename(Path(temporary) / "test.zip")
            with self.assertRaisesRegex(SdistError, "expected a .tar.gz"):
                normalize_sdist(Path(temporary) / "test.zip", epoch=1)

    def test_duplicate_archive_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "duplicate.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for _ in range(2):
                    member = tarfile.TarInfo("package/file.py")
                    member.size = 1
                    tar.addfile(member, BytesIO(b"x"))
            before = archive.read_bytes()
            with self.assertRaisesRegex(SdistError, "duplicate archive member"):
                normalize_sdist(archive, epoch=1)
            self.assertEqual(before, archive.read_bytes())

    def test_failed_atomic_replace_cleans_temporary_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            archive = folder / "test.tar.gz"
            self.sample(archive, mtime=2)
            with patch.object(
                os, "replace", side_effect=OSError("mock file-system error")
            ):
                with self.assertRaisesRegex(OSError, "mock file-system error"):
                    normalize_sdist(archive, epoch=2)
            self.assertEqual(
                sorted(path.name for path in folder.iterdir()), ["test.tar.gz"]
            )

    def test_negative_epoch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "a.tar.gz"
            self.sample(archive, mtime=1000)
            with self.assertRaises(SdistError):
                normalize_sdist(archive, epoch=-1)
