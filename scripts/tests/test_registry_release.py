from __future__ import annotations

import base64
import hashlib
import contextlib
import io
import json
import tarfile
import tempfile
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.registry_release import RegistryError, inspect_registry, main


class RegistryReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_python_artifacts(self) -> tuple[Path, Path]:
        wheel = self.root / "adxl355-0.1.0a3-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(
                "adxl355-0.1.0a3.dist-info/METADATA",
                "Metadata-Version: 2.4\nName: adxl355\nVersion: 0.1.0a3\n",
            )
        sdist = self.root / "adxl355-0.1.0a3.tar.gz"
        with tarfile.open(sdist, "w:gz") as archive:
            data = b"Metadata-Version: 2.4\nName: adxl355\nVersion: 0.1.0a3\n"
            info = tarfile.TarInfo("adxl355-0.1.0a3/PKG-INFO")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        return wheel, sdist

    def make_node_artifact(self) -> Path:
        tarball = self.root / "oaslananka-adxl355-0.1.0-alpha.3.tgz"
        package = json.dumps(
            {"name": "@oaslananka/adxl355", "version": "0.1.0-alpha.3"}
        ).encode()
        with tarfile.open(tarball, "w:gz") as archive:
            info = tarfile.TarInfo("package/package.json")
            info.size = len(package)
            archive.addfile(info, io.BytesIO(package))
        return tarball

    def make_rust_artifact(self) -> Path:
        crate = self.root / "adxl355-driver-0.1.0-alpha.3.crate"
        manifest = b'[package]\nname = "adxl355-driver"\nversion = "0.1.0-alpha.3"\n'
        with tarfile.open(crate, "w:gz") as archive:
            info = tarfile.TarInfo("adxl355-driver-0.1.0-alpha.3/Cargo.toml")
            info.size = len(manifest)
            archive.addfile(info, io.BytesIO(manifest))
        return crate

    def test_absent_python_release_requires_publication(self) -> None:
        self.make_python_artifacts()
        with patch("scripts.registry_release._request_json", return_value=None):
            result = inspect_registry("python", self.root, "0.1.0a3")
        self.assertEqual(result["state"], "absent")
        self.assertTrue(result["publish_required"])
        self.assertEqual(result["package"], "adxl355")

    def test_python_sdist_uses_root_pkg_info_when_egg_info_is_present(self) -> None:
        wheel, sdist = self.make_python_artifacts()
        root_metadata = b"Metadata-Version: 2.4\nName: adxl355\nVersion: 0.1.0a3\n"
        nested_metadata = b"Metadata-Version: 2.4\nName: ignored-copy\nVersion: 9.9.9\n"
        with tarfile.open(sdist, "w:gz") as archive:
            for name, data in (
                ("adxl355-0.1.0a3/PKG-INFO", root_metadata),
                ("adxl355-0.1.0a3/src/adxl355.egg-info/PKG-INFO", nested_metadata),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        payload = {
            "urls": [
                {
                    "filename": artifact.name,
                    "digests": {
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()
                    },
                }
                for artifact in (wheel, sdist)
            ]
        }
        with patch("scripts.registry_release._request_json", return_value=payload):
            result = inspect_registry("python", self.root, "0.1.0a3")
        self.assertEqual(result["state"], "exact")

    def test_mismatched_python_sdist_identity_is_blocked_before_network(self) -> None:
        _wheel, sdist = self.make_python_artifacts()
        with tarfile.open(sdist, "w:gz") as archive:
            data = b"Metadata-Version: 2.4\nName: other\nVersion: 0.1.0a3\n"
            info = tarfile.TarInfo("adxl355-0.1.0a3/PKG-INFO")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        with patch("scripts.registry_release._request_json") as request:
            with self.assertRaisesRegex(RegistryError, "sdist package name mismatch"):
                inspect_registry("python", self.root, "0.1.0a3")
        request.assert_not_called()

    def test_exact_python_release_is_idempotent(self) -> None:
        wheel, sdist = self.make_python_artifacts()
        payload = {
            "urls": [
                {
                    "filename": artifact.name,
                    "digests": {
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()
                    },
                }
                for artifact in (wheel, sdist)
            ]
        }
        with patch("scripts.registry_release._request_json", return_value=payload):
            result = inspect_registry("python", self.root, "0.1.0a3")
        self.assertEqual(result["state"], "exact")
        self.assertFalse(result["publish_required"])

    def test_partial_or_changed_python_release_is_blocked(self) -> None:
        wheel, _sdist = self.make_python_artifacts()
        payload = {
            "urls": [
                {
                    "filename": wheel.name,
                    "digests": {"sha256": "0" * 64},
                }
            ]
        }
        with patch("scripts.registry_release._request_json", return_value=payload):
            with self.assertRaisesRegex(RegistryError, "does not match"):
                inspect_registry("python", self.root, "0.1.0a3")

    def test_exact_npm_release_matches_sha512_integrity(self) -> None:
        tarball = self.make_node_artifact()
        digest = base64.b64encode(
            hashlib.sha512(tarball.read_bytes()).digest()
        ).decode()
        payload = {
            "name": "@oaslananka/adxl355",
            "version": "0.1.0-alpha.3",
            "dist": {"integrity": f"sha512-{digest}"},
        }
        with patch("scripts.registry_release._request_json", return_value=payload):
            result = inspect_registry("node", self.root, "0.1.0-alpha.3")
        self.assertEqual(result["state"], "exact")
        self.assertFalse(result["publish_required"])

    def test_changed_npm_release_is_blocked(self) -> None:
        self.make_node_artifact()
        payload = {
            "name": "@oaslananka/adxl355",
            "version": "0.1.0-alpha.3",
            "dist": {"integrity": "sha512-invalid"},
        }
        with patch("scripts.registry_release._request_json", return_value=payload):
            with self.assertRaisesRegex(RegistryError, "does not match"):
                inspect_registry("node", self.root, "0.1.0-alpha.3")

    def test_exact_crates_release_matches_checksum(self) -> None:
        crate = self.make_rust_artifact()
        payload = {
            "version": {
                "num": "0.1.0-alpha.3",
                "checksum": hashlib.sha256(crate.read_bytes()).hexdigest(),
            }
        }
        with patch("scripts.registry_release._request_json", return_value=payload):
            result = inspect_registry("rust", self.root, "0.1.0-alpha.3")
        self.assertEqual(result["state"], "exact")
        self.assertFalse(result["publish_required"])

    def test_github_output_mode_writes_only_fixed_records_to_stdout(self) -> None:
        self.make_node_artifact()
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = [
            "registry_release.py",
            "node",
            "--directory",
            str(self.root),
            "--version",
            "0.1.0-alpha.3",
            "--github-output",
        ]
        with (
            patch.object(sys, "argv", argv),
            patch("scripts.registry_release._request_json", return_value=None),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(main(), 0)
        self.assertEqual(
            stdout.getvalue(),
            "state=absent\npublish_required=true\n"
            "package=@oaslananka/adxl355\nversion=0.1.0-alpha.3\n",
        )
        self.assertIn('"state": "absent"', stderr.getvalue())

    def test_local_identity_mismatch_is_blocked_before_network(self) -> None:
        self.make_node_artifact()
        with patch("scripts.registry_release._request_json") as request:
            with self.assertRaisesRegex(RegistryError, "version mismatch"):
                inspect_registry("node", self.root, "9.9.9")
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
