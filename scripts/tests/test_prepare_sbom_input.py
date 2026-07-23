from __future__ import annotations

import io
import json
import shutil
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.prepare_sbom_input import SbomInputError, prepare_sbom_input, select_archives


class PrepareSbomInputTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="adxl355-sbom-input-test-"))
        self.addCleanup(shutil.rmtree, root)
        return root

    @staticmethod
    def add_tar_text(handle: tarfile.TarFile, name: str, text: str) -> None:
        payload = text.encode()
        info = tarfile.TarInfo(name)
        info.size = len(payload)
        handle.addfile(info, io.BytesIO(payload))

    def create_artifacts(self, root: Path) -> Path:
        artifacts = root / "artifacts"
        for package in ("python", "rust", "node", "go", "native"):
            (artifacts / package).mkdir(parents=True)

        with zipfile.ZipFile(artifacts / "python/adxl355-0.1.0a2-py3-none-any.whl", "w") as handle:
            handle.writestr("adxl355/__init__.py", "")
            handle.writestr(
                "adxl355-0.1.0a2.dist-info/METADATA",
                "Name: adxl355\nVersion: 0.1.0a2\n",
            )

        archives = (
            (
                artifacts / "rust/adxl355-driver-0.1.0-alpha.2.crate",
                "adxl355-driver-0.1.0-alpha.2/Cargo.toml",
                '[package]\nname="adxl355-driver"\nversion="0.1.0-alpha.2"\n',
            ),
            (
                artifacts / "node/oaslananka-adxl355-0.1.0-alpha.2.tgz",
                "package/package.json",
                json.dumps({"name": "@oaslananka/adxl355", "version": "0.1.0-alpha.2"}),
            ),
            (
                artifacts / "go/adxl355-go-0.1.0-alpha.2.tar.gz",
                "adxl355-go-0.1.0-alpha.2/go.mod",
                "module github.com/oaslananka/adxl355/go\n",
            ),
            (
                artifacts / "native/adxl355-c-cpp-0.1.0-alpha.2.tar.gz",
                "BUILD_INFO.txt",
                "version=0.1.0-alpha.2\n",
            ),
        )
        for archive, member, text in archives:
            with tarfile.open(archive, "w:gz") as handle:
                if "native" in archive.parts:
                    root_entry = tarfile.TarInfo(".")
                    root_entry.type = tarfile.DIRTYPE
                    handle.addfile(root_entry)
                self.add_tar_text(handle, member, text)
        return artifacts

    def test_selects_one_runtime_archive_for_each_package_family(self) -> None:
        root = self.make_root()
        artifacts = self.create_artifacts(root)
        selected = select_archives(artifacts)
        self.assertEqual(
            {entry.kind for entry in selected},
            {"python-wheel", "rust-crate", "node-tarball", "go-module", "native"},
        )

    def test_prepares_deterministic_scan_tree_and_manifest(self) -> None:
        root = self.make_root()
        artifacts = self.create_artifacts(root)
        output = root / "sbom-input"
        report = prepare_sbom_input(artifacts, output)

        self.assertEqual(len(report["archives"]), 5)
        self.assertTrue((output / "python-wheel/adxl355-0.1.0a2.dist-info/METADATA").is_file())
        self.assertTrue((output / "rust-crate/adxl355-driver-0.1.0-alpha.2/Cargo.toml").is_file())
        self.assertTrue((output / "node-tarball/package/package.json").is_file())
        self.assertTrue(
            (output / "go-module/adxl355-go-0.1.0-alpha.2/go.mod").is_file()
        )
        manifest = json.loads((output / "SBOM_INPUT.json").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(
            {entry["kind"] for entry in manifest["archives"]},
            {"python-wheel", "rust-crate", "node-tarball", "go-module", "native"},
        )
        for entry in manifest["archives"]:
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(str(entry["purl"]).startswith("pkg:"))
            self.assertTrue(entry["name"])
            self.assertTrue(entry["version"])
            self.assertGreater(entry["files"], 0)

    def test_rejects_duplicate_package_archives(self) -> None:
        root = self.make_root()
        artifacts = self.create_artifacts(root)
        shutil.copy2(
            artifacts / "python/adxl355-0.1.0a2-py3-none-any.whl",
            artifacts / "python/adxl355-copy.whl",
        )
        with self.assertRaisesRegex(SbomInputError, "duplicate archive kinds"):
            select_archives(artifacts)

    def test_rejects_archive_path_traversal(self) -> None:
        root = self.make_root()
        artifacts = self.create_artifacts(root)
        archive = artifacts / "node/oaslananka-adxl355-0.1.0-alpha.2.tgz"
        with tarfile.open(archive, "w:gz") as handle:
            self.add_tar_text(handle, "../escape.json", "{}")
        with self.assertRaisesRegex(SbomInputError, "unsafe path"):
            prepare_sbom_input(artifacts, root / "output")


if __name__ == "__main__":
    unittest.main()
