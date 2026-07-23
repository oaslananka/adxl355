from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
DOCS = (
    REPO_ROOT / "docs" / "architecture.md",
    REPO_ROOT / "docs" / "testing.md",
    REPO_ROOT / "docs" / "calibration.md",
    REPO_ROOT / "docs" / "publishing.md",
    REPO_ROOT / "TODO.md",
    REPO_ROOT / "CHANGELOG.md",
)


class PublicDocumentationTests(unittest.TestCase):
    def test_readme_does_not_overstate_maturity_or_unsupported_apis(self) -> None:
        text = README.read_text().lower()
        self.assertNotIn("production-ready", text)
        self.assertNotIn("production ready", text)
        self.assertNotIn("self-test and offset calibration api", text)
        self.assertNotIn("fifo basic support", text)
        self.assertIn("alpha", text)
        self.assertIn("physical hil", text)

    def test_readme_has_explicit_language_feature_matrix(self) -> None:
        text = README.read_text()
        for heading in (
            "Core device API",
            "ODR configuration",
            "FIFO entry count",
            "Linux SPI adapter",
            "Linux I2C adapter",
            "embedded-hal SPI/I2C",
            "Packaging dry run",
            "Physical HIL evidence",
        ):
            self.assertIn(heading, text)
        for language in ("C", "C++", "Python", "Rust", "Node.js", "Go"):
            self.assertRegex(text, rf"\|\s*{re.escape(language)}\s*\|")

    def test_quick_start_uses_reproducible_commands(self) -> None:
        text = README.read_text()
        self.assertIn("python -m pip install --no-deps -e ./python", text)
        self.assertIn("PYTHONPATH=python/src python python/examples/basic_read.py", text)
        self.assertIn("npm ci --ignore-scripts", text)
        self.assertNotIn("npm install\n", text)
        self.assertIn("cmake -S c -B build/c", text)
        self.assertIn("cmake -S cpp -B build/cpp", text)
        self.assertIn("cargo run --manifest-path rust/Cargo.toml --example basic", text)
        self.assertIn("go test ./...", text)

    def test_register_presence_is_not_described_as_public_api(self) -> None:
        combined = "\n".join(path.read_text() for path in (README, *DOCS))
        self.assertIn("register presence does not imply a public api", combined.lower())
        self.assertIn("SELF_TEST", combined)
        self.assertIn("not implemented as a public driver method", combined)

    def test_package_and_release_wording_matches_repository_state(self) -> None:
        readme = README.read_text()
        publishing = (REPO_ROOT / "docs" / "publishing.md").read_text()
        changelog = (REPO_ROOT / "CHANGELOG.md").read_text()
        self.assertIn("buildable package metadata", readme)
        self.assertIn("not published by this repository", readme)
        self.assertIn("verification and packaging dry run", publishing)
        self.assertIn("[0.1.0-alpha.2] - Unreleased", changelog)
        self.assertIn("[0.1.0-alpha.1]", changelog)

    def test_docs_do_not_contradict_hil_or_calibration_status(self) -> None:
        combined = "\n".join(path.read_text() for path in DOCS)
        self.assertNotIn("Not yet implemented", combined)
        self.assertIn("manual-only", combined)
        self.assertIn("calibration procedure", combined.lower())
        self.assertIn("no public calibration helper", combined.lower())


if __name__ == "__main__":
    unittest.main()
