from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
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
            "Self-test response",
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

    def test_register_presence_and_language_specific_apis_are_explicit(self) -> None:
        combined = "\n".join(path.read_text() for path in (README, *DOCS))
        normalized = combined.lower()
        self.assertIn("register presence does not imply a public api", normalized)
        self.assertIn("SELF_TEST", combined)
        self.assertIn("c and python expose", normalized)
        self.assertIn("do not currently expose", normalized)
        self.assertIn("do not apply undocumented factory acceptance limits", normalized)

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
        self.assertIn("c and python expose", combined.lower())
        self.assertIn("1 offset-register count = 16 raw acceleration lsb", combined.lower())
        self.assertIn("not factory", combined.lower())

    def test_self_test_docs_define_sequence_restore_and_policy_boundary(self) -> None:
        hardware = " ".join(
            (REPO_ROOT / "docs" / "hardware-testing.md").read_text().lower().split()
        )
        python_readme = " ".join(
            (REPO_ROOT / "python" / "README.md").read_text().lower().split()
        )
        for phrase in (
            "st1 only",
            "st1+st2",
            "restore every saved register",
            "fixture-specific",
            "must not be presented as analog devices production limits",
        ):
            self.assertIn(phrase, hardware)
        self.assertIn("default configuration reports the measured response", python_readme)

    def test_support_policy_matches_package_metadata_and_ci(self) -> None:
        contributing = CONTRIBUTING.read_text()
        self.assertIn("Python >= 3.10", contributing)
        self.assertNotIn("Python >= 3.9", contributing)
        self.assertIn("Node.js 22 or >= 24", contributing)
        self.assertIn("CI covers 22, 24, and 26", contributing)

    def test_hil_status_distinguishes_spi_evidence_from_i2c_requirement(self) -> None:
        readme = README.read_text()
        todo = (REPO_ROOT / "TODO.md").read_text()
        hardware = (REPO_ROOT / "docs" / "hardware-testing.md").read_text()
        releasing = (REPO_ROOT / "docs" / "releasing.md").read_text()
        for text in (readme, todo, hardware, releasing):
            self.assertIn("30725059679", text)
        self.assertIn("SPI pass on Raspberry Pi 5; I2C pending", readme)
        self.assertIn("final release-candidate", todo)
        self.assertIn("I2C run is still pending", hardware)

    def test_contributor_templates_exist_and_route_security_privately(self) -> None:
        issue_root = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
        for name in ("bug_report.yml", "feature_request.yml", "config.yml"):
            self.assertTrue((issue_root / name).is_file(), name)
        pull_request = REPO_ROOT / ".github" / "pull_request_template.md"
        self.assertTrue(pull_request.is_file())
        combined = "\n".join(
            (issue_root / name).read_text()
            for name in ("bug_report.yml", "feature_request.yml", "config.yml")
        )
        self.assertIn("security/advisories/new", combined)
        self.assertNotIn("paste your secret", combined.lower())

    def test_testing_guide_documents_required_check_lifecycle(self) -> None:
        text = (REPO_ROOT / "docs" / "testing.md").read_text()
        self.assertIn("Required status-check lifecycle", text)
        self.assertIn("must never be renamed or removed in one step", text)
        self.assertIn("export the current ruleset JSON", text)
        self.assertIn("without bypassing CI", text)

    def test_calibration_docs_define_units_rollback_and_limitations(self) -> None:
        text = (REPO_ROOT / "docs" / "calibration.md").read_text().lower()
        for phrase in (
            "signed 16-bit two's-complement",
            "measured_raw - expected_raw",
            "half-away-from-zero",
            "restore the saved offsets",
            "temperature",
            "residual error",
            "do not record secrets",
        ):
            self.assertIn(phrase, text)


    def test_calibration_docs_record_repeatable_physical_evidence(self) -> None:
        text = (REPO_ROOT / "docs" / "calibration.md").read_text()
        normalized = " ".join(text.split())
        self.assertIn("commit `c4e774f`", normalized)
        self.assertIn("two independent runs", normalized)
        self.assertIn("2051.23 raw LSB", normalized)
        self.assertIn("42.37 raw LSB", normalized)
        self.assertIn("restored X/Y/Z offsets to zero", normalized)
        self.assertIn("it does not establish factory accuracy", normalized.lower())



if __name__ == "__main__":
    unittest.main()
