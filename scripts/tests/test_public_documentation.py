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
            "FIFO support",
            "Self-test response",
            "DRDY / event flow",
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
        self.assertIn(
            "PYTHONPATH=python/src python python/examples/basic_read.py", text
        )
        self.assertIn("npm ci --ignore-scripts", text)
        self.assertNotIn("npm install\n", text)
        self.assertIn("cmake -S c -B build/c", text)
        self.assertIn("cmake -S cpp -B build/cpp", text)
        self.assertIn("cargo run --manifest-path rust/Cargo.toml --example basic", text)
        self.assertIn("go test ./...", text)

    def test_data_ready_docs_separate_signals_and_bound_acquisition(self) -> None:
        readme = README.read_text()
        architecture = (REPO_ROOT / "docs" / "architecture.md").read_text()
        testing = (REPO_ROOT / "docs" / "testing.md").read_text()
        hardware = (REPO_ROOT / "docs" / "hardware-testing.md").read_text()
        python_readme = (REPO_ROOT / "python" / "README.md").read_text()
        todo = (REPO_ROOT / "TODO.md").read_text()
        combined = " ".join(
            (readme + architecture + testing + hardware + python_readme).split()
        )
        for phrase in (
            "dedicated DRDY",
            "always active high",
            "INT1/INT2",
            "internal synchronization",
            "blocking rising-edge",
            "kernel monotonic",
            "line sequence",
            "FIFO overrun",
            "not a background service",
            "Recorded dedicated DRDY result",
        ):
            self.assertIn(phrase, combined)
        self.assertIn("Internal-clock DRDY/INT1/INT2 configuration", readme)
        self.assertIn("bounded libgpiod reference", readme)
        for phrase in (
            "002173d0c8dae8b15261b6d00cf011011cf8db7c",
            "32 samples, 32 unique raw XYZ tuples",
            "zero missed events",
            "zero FIFO overruns",
            "POWER_CTL=0x01",
            "GPIO17 was released",
            "does **not** prove SPI DRDY",
        ):
            self.assertIn(phrase, hardware)
        self.assertIn(
            "[x] Internal-clock DRDY and DATA_RDY-to-INT1/INT2 configuration API",
            todo,
        )
        self.assertIn("[x] Physical GPIO17/DRDY event and restoration evidence", todo)

    def test_fifo_contract_is_scoped_bounded_and_nonblocking(self) -> None:
        readme = README.read_text()
        architecture = (REPO_ROOT / "docs" / "architecture.md").read_text()
        testing = (REPO_ROOT / "docs" / "testing.md").read_text()
        hardware = (REPO_ROOT / "docs" / "hardware-testing.md").read_text()
        python_readme = (REPO_ROOT / "python" / "README.md").read_text()
        todo = (REPO_ROOT / "TODO.md").read_text()
        combined = " ".join(
            (readme + architecture + testing + hardware + python_readme).split()
        ).lower()
        for phrase in (
            "96 axis locations",
            "three locations",
            "x/y/z",
            "caller-bounded",
            "cannot be restored",
            "partial_samples",
            "consumed_locations",
            "physical fifo validation",
        ):
            self.assertIn(phrase, combined)
        self.assertIn("Bounded count/decode/read, caller storage", readme)
        self.assertIn("typed partial results", readme)
        self.assertIn("C++, Rust, Node.js, and Go do not expose", readme)
        self.assertIn("[x] FIFO sample-data decode/read API", todo)

    def test_register_presence_and_language_specific_apis_are_explicit(self) -> None:
        combined = "\n".join(path.read_text() for path in (README, *DOCS))
        normalized = combined.lower()
        self.assertIn("register presence does not imply a public api", normalized)
        self.assertIn("SELF_TEST", combined)
        self.assertIn("c and python expose", normalized)
        self.assertIn("do not currently expose", normalized)
        self.assertIn("do not apply undocumented factory acceptance limits", normalized)

    def test_trusted_publishing_docs_define_exact_bindings_and_recovery(self) -> None:
        publishing = (REPO_ROOT / "docs" / "publishing.md").read_text()
        supply_chain = (REPO_ROOT / "docs" / "security" / "supply-chain.md").read_text()
        combined = publishing + "\n" + supply_chain
        for phrase in (
            "REGISTRY_PUBLISHING_ENABLED",
            "release.yml",
            "environment `release`",
            "@oaslananka/adxl355",
            "adxl355-driver",
            "scripts/registry_release.py",
            "partial or changed",
            "idempotent",
            "short-lived",
        ):
            self.assertIn(phrase, combined)
        self.assertIn("v[0-9]*", publishing)
        self.assertIn("pending Trusted Publisher", publishing)
        self.assertIn("first package reservation/publication", publishing)
        self.assertIn("initial crate release", publishing)

    def test_package_and_release_wording_matches_repository_state(self) -> None:
        readme = README.read_text()
        publishing = (REPO_ROOT / "docs" / "publishing.md").read_text()
        changelog = (REPO_ROOT / "CHANGELOG.md").read_text()
        self.assertIn("available as `adxl355` on PyPI", readme)
        self.assertIn("Current `main` may contain additional unreleased work", readme)
        self.assertIn("v0.1.0-alpha.3", publishing)
        self.assertIn("GitHub prerelease", publishing)
        self.assertIn("PyPI `adxl355==0.1.0a3`", publishing)
        self.assertIn("Release Gate run", publishing)
        self.assertIn("TestPyPI is", publishing)
        self.assertIn("not published and is not part", publishing)
        self.assertNotIn(
            "does not publish to PyPI, npm, crates.io, GitHub Releases", publishing
        )
        self.assertIn("[0.1.0-alpha.3] - Unreleased", changelog)
        self.assertIn("[0.1.0-alpha.1]", changelog)

    def test_docs_do_not_contradict_hil_or_calibration_status(self) -> None:
        combined = "\n".join(path.read_text() for path in DOCS)
        self.assertNotIn("Not yet implemented", combined)
        self.assertIn("manual-only", combined)
        self.assertIn("calibration procedure", combined.lower())
        self.assertIn("c and python expose", combined.lower())
        self.assertIn(
            "1 offset-register count = 16 raw acceleration lsb", combined.lower()
        )
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
            "must not be presented as an analog devices production limit",
        ):
            self.assertIn(phrase, hardware)
        self.assertIn(
            "default configuration reports the measured response", python_readme
        )

    def test_self_test_docs_record_rev_d_limits_and_physical_evidence(self) -> None:
        readme = " ".join(README.read_text().split())
        hardware = " ".join(
            (REPO_ROOT / "docs" / "hardware-testing.md").read_text().split()
        )
        todo = (REPO_ROOT / "TODO.md").read_text()
        self.assertIn("12d6206393223439e14b8e36b97e567751e8f8bb", readme)
        self.assertIn("0.34236", hardware)
        self.assertIn("0.33908", hardware)
        self.assertIn("1.41865", hardware)
        self.assertIn("X/Y `0.10–0.60 g`", hardware)
        self.assertIn("Z `0.50–3.00 g`", hardware)
        self.assertIn("raw temporary JSON report is not stored", hardware)
        self.assertIn("[x] Self-test API hardware testing on Raspberry Pi 5 SPI", todo)

    def test_support_policy_matches_package_metadata_and_ci(self) -> None:
        contributing = CONTRIBUTING.read_text()
        self.assertIn("Python >= 3.10", contributing)
        self.assertNotIn("Python >= 3.9", contributing)
        self.assertIn("Node.js 22 or >= 24", contributing)
        self.assertIn("CI covers 22, 24, and 26", contributing)

    def test_hil_status_records_published_alpha3_release_evidence(self) -> None:
        readme = README.read_text()
        todo = (REPO_ROOT / "TODO.md").read_text()
        hardware = (REPO_ROOT / "docs" / "hardware-testing.md").read_text()
        publishing = (REPO_ROOT / "docs" / "publishing.md").read_text()
        for content in (readme, hardware, publishing):
            self.assertIn("71de69b8727a9f8eef254de586d9bce7bc8fa8ac", content)
            self.assertIn("30736413982", content)
            self.assertIn("30736668298", content)
            self.assertIn("v0.1.0-alpha.3", content)
        self.assertIn("hil-spi-30736413982.json", readme)
        self.assertIn("hil-i2c-30736668298.json", readme)
        self.assertIn("[x] Publish the verified GitHub prerelease", todo)
        self.assertNotIn("Both SPI and I2C must still be rerun", readme)
        self.assertNotIn("final-candidate reruns remain required", publishing)

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

    def test_go_linux_transports_are_documented_and_bounded(self) -> None:
        readme = README.read_text()
        testing = (REPO_ROOT / "docs" / "testing.md").read_text()
        architecture = (REPO_ROOT / "docs" / "architecture.md").read_text()
        todo = (REPO_ROOT / "TODO.md").read_text()
        for phrase in (
            "adxl355/linuxio",
            "Linux amd64 and arm64",
            "--samples 8 --timeout 10s",
            "restore standby",
            "Raspberry Pi 5 SPI and I2C bounded example passes",
            "08273bff4611a33f1b88dae6a08c92d5199eab28",
        ):
            self.assertIn(phrase, readme)
        for phrase in (
            "SPI_IOC_MESSAGE(1)",
            "I2C_RDWR",
            "idempotent",
            "errors.Is",
            "does not claim to reconfigure",
        ):
            self.assertIn(phrase, architecture)
        self.assertIn("GOOS=linux GOARCH=arm64 go build ./...", testing)
        self.assertIn("linuxio.ErrUnsupported", testing)
        self.assertIn("[x] spidev/Linux implementation", todo)
        self.assertIn(
            "[x] Bounded SPI example with real hardware on Raspberry Pi 5", todo
        )
        self.assertIn(
            "[x] Bounded I2C example with real hardware on Raspberry Pi 5 (`0x1D`)",
            todo,
        )
        hardware = (REPO_ROOT / "docs" / "hardware-testing.md").read_text()
        for phrase in (
            "Go Linux SPI bounded example",
            "a74fd41821d3decc8a4e67d31411659487af83106b697b124975255f5749f2de",
            "28.0939 °C",
            "29 unique tuples",
            "POWER_CTL=0x01",
            "233.2873 °C",
            "That rejected run is not accepted as evidence",
            "Go Linux I2C bounded example",
            "1c97921239baea9994942a4a77fbbd2b2048ba9f84e81f452d929bb7715c367c",
            "28.4254 °C",
            "32 unique tuples",
        ):
            self.assertIn(phrase, hardware)

    def test_node_i2c_physical_evidence_is_scoped_and_spi_remains_pending(self) -> None:
        readme = " ".join(README.read_text().split())
        hardware = " ".join(
            (REPO_ROOT / "docs" / "hardware-testing.md").read_text().split()
        )
        node_readme = " ".join((REPO_ROOT / "node" / "README.md").read_text().split())
        self.assertIn("Raspberry Pi 5 I2C bounded example pass; SPI pending", readme)
        for phrase in (
            "commit `6a30a322cdbc482a455df25dfdf03b076a66e299`",
            "Node.js `v24.18.0`",
            "8 samples captured, all 8 unique",
            "standby, ±2 g, and default ODR",
            "Node SPI physical result remains pending",
        ):
            self.assertIn(phrase, hardware)
        self.assertIn("Physical Node SPI validation remains pending", node_readme)

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
