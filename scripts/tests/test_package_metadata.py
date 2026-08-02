from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class PackageMetadataTests(unittest.TestCase):
    def test_python_distribution_metadata_is_complete(self) -> None:
        with (REPO_ROOT / "python/pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]

        self.assertEqual(project["name"], "adxl355")
        self.assertEqual(project["version"], "0.1.0a3")
        self.assertEqual(project["readme"], "README.md")
        self.assertEqual(project["license"], "MIT")
        self.assertEqual(
            project["urls"]["Repository"], "https://github.com/oaslananka/adxl355"
        )
        self.assertEqual(
            project["urls"]["Documentation"],
            "https://github.com/oaslananka/adxl355/tree/main/docs",
        )
        self.assertEqual(
            project["urls"]["Changelog"],
            "https://github.com/oaslananka/adxl355/blob/main/CHANGELOG.md",
        )
        self.assertEqual(
            project["urls"]["Security"],
            "https://github.com/oaslananka/adxl355/security/policy",
        )

    def test_rust_distribution_uses_available_name_and_preserves_import_name(
        self,
    ) -> None:
        with (REPO_ROOT / "rust/Cargo.toml").open("rb") as handle:
            manifest = tomllib.load(handle)

        package = manifest["package"]
        self.assertEqual(package["name"], "adxl355-driver")
        self.assertEqual(package["version"], "0.1.0-alpha.3")
        self.assertEqual(manifest["lib"]["name"], "adxl355")
        self.assertEqual(package["repository"], "https://github.com/oaslananka/adxl355")
        self.assertEqual(package["homepage"], "https://github.com/oaslananka/adxl355")
        self.assertEqual(package["documentation"], "https://docs.rs/adxl355-driver")
        self.assertEqual(
            package["include"],
            ["src/**", "Cargo.toml", "Cargo.lock", "README.md", "LICENSE"],
        )

    def test_node_distribution_uses_owned_scope_and_optional_linux_exports(
        self,
    ) -> None:
        package = json.loads((REPO_ROOT / "node/package.json").read_text())
        lock = json.loads((REPO_ROOT / "node/package-lock.json").read_text())

        self.assertEqual(package["name"], "@oaslananka/adxl355")
        self.assertEqual(lock["name"], "@oaslananka/adxl355")
        self.assertEqual(lock["packages"][""]["name"], "@oaslananka/adxl355")
        self.assertEqual(package["version"], "0.1.0-alpha.3")
        self.assertEqual(package["publishConfig"], {"access": "public"})
        self.assertEqual(set(package["exports"]), {".", "./linux/spi", "./linux/i2c"})
        self.assertEqual(
            package["optionalDependencies"], {"i2c-bus": "5.2.3", "spi-device": "3.1.2"}
        )
        self.assertEqual(
            lock["packages"][""]["optionalDependencies"],
            package["optionalDependencies"],
        )
        self.assertEqual(package["files"], ["dist", "README.md", "LICENSE"])

    def test_registry_package_readmes_link_policy_and_history(self) -> None:
        for relative in ("node/README.md", "rust/README.md"):
            text = (REPO_ROOT / relative).read_text()
            self.assertIn("CHANGELOG.md", text, relative)
            self.assertIn("security/policy", text, relative)
            self.assertIn("LICENSE", text, relative)

    def test_go_submodule_tag_convention_is_documented(self) -> None:
        versioning = (REPO_ROOT / "docs/versioning.md").read_text()
        publishing = (REPO_ROOT / "docs/publishing.md").read_text()
        self.assertIn("go/v0.1.0-alpha.3", versioning)
        self.assertIn("go/v0.1.0-alpha.3", publishing)
        self.assertIn("module github.com/oaslananka/adxl355/go", versioning)

    def test_registry_name_decisions_are_dated_and_rechecked_before_publish(
        self,
    ) -> None:
        text = (REPO_ROOT / "docs/versioning.md").read_text()
        self.assertIn("2026-08-02", text)
        self.assertIn("PyPI", text)
        self.assertIn("@oaslananka/adxl355", text)
        self.assertIn("adxl355-driver", text)
        self.assertIn("re-check", text)


if __name__ == "__main__":
    unittest.main()
