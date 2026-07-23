from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.versioning import VersionSet, load_version, sync_versions


REPO_ROOT = Path(__file__).resolve().parents[2]


class VersioningTests(unittest.TestCase):
    def test_alpha_version_maps_to_each_ecosystem(self) -> None:
        version = VersionSet.parse("0.1.0-alpha.2")

        self.assertEqual(version.semver, "0.1.0-alpha.2")
        self.assertEqual(version.python, "0.1.0a2")
        self.assertEqual(version.core, "0.1.0")
        self.assertEqual(version.root_tag, "v0.1.0-alpha.2")
        self.assertEqual(version.go_tag, "go/v0.1.0-alpha.2")

    def test_stable_and_rc_versions_map_to_pep440(self) -> None:
        self.assertEqual(VersionSet.parse("1.2.3").python, "1.2.3")
        self.assertEqual(VersionSet.parse("1.2.3-rc.4").python, "1.2.3rc4")
        self.assertEqual(VersionSet.parse("1.2.3-beta.5").python, "1.2.3b5")

    def test_unsupported_prerelease_shape_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "supported prerelease"):
            VersionSet.parse("1.2.3-preview.1")

    def test_repository_version_file_is_canonical_alpha(self) -> None:
        version = load_version(REPO_ROOT)
        self.assertEqual(version.semver, "0.1.0-alpha.2")

    def test_sync_check_reports_manifest_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in (
                "VERSION",
    "CHANGELOG.md",
                "python/pyproject.toml",
                "python/src/adxl355/_version.py",
                "rust/Cargo.toml",
                "rust/Cargo.lock",
                "node/package.json",
                "node/package-lock.json",
                "c/CMakeLists.txt",
                "cpp/CMakeLists.txt",
                "c/include/adxl355/adxl355_version.h",
                "spec/test_vectors.json",
            ):
                source = REPO_ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())

            package_path = root / "node/package.json"
            package = json.loads(package_path.read_text())
            package["version"] = "9.9.9"
            package_path.write_text(json.dumps(package, indent=2) + "\n")

            errors = sync_versions(root, write=False)
            self.assertTrue(
                any("node/package.json" in error and "9.9.9" in error for error in errors)
            )

    def test_sync_write_updates_all_ecosystem_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in (
                "VERSION",
    "CHANGELOG.md",
                "python/pyproject.toml",
                "python/src/adxl355/_version.py",
                "rust/Cargo.toml",
                "rust/Cargo.lock",
                "node/package.json",
                "node/package-lock.json",
                "c/CMakeLists.txt",
                "cpp/CMakeLists.txt",
                "c/include/adxl355/adxl355_version.h",
                "spec/test_vectors.json",
            ):
                source = REPO_ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())

            errors = sync_versions(root, write=True)
            self.assertEqual(errors, [])
            self.assertEqual(sync_versions(root, write=False), [])


if __name__ == "__main__":
    unittest.main()
