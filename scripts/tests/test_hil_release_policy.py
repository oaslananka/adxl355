"""Risk-based HIL gate: do not require hardware for routine software work."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import hil_release_policy as policy


class HILReleasePolicyTests(unittest.TestCase):
    def test_allowlisted_software_changes_do_not_trigger_hil(self) -> None:
        paths = [
            "README.md",
            "docs/testing.md",
            "docs/quality-evidence.md",
            "scripts/tests/test_release_preflight.py",
            "python/tests/test_device.py",
            ".github/workflows/ci.yml",
            ".github/workflows/codeql.yml",
        ]
        self.assertFalse(policy.assess("a" * 40, "b" * 40, paths)["requires_fresh_hil"])

    def test_sensor_code_release_and_hil_validation_changes_require_new_evidence(
        self,
    ) -> None:
        for path in (
            "python/src/adxl355/device.py",
            "python/src/adxl355/adapters/spidev.py",
            "c/src/adxl355.c",
            "rust/src/lib.rs",
            "go/adxl355/device.go",
            "node/src/linux/i2c.ts",
            "spec/registers.json",
            ".github/workflows/hil.yml",
            ".github/workflows/release.yml",
            "scripts/hil_runner.py",
            "scripts/hil_release_policy.py",
            "scripts/unrecognized.py",
            "future-driver/native.cpp",
            "../unsafe",
            r"c\src\adxl355.c",
        ):
            with self.subTest(path=path):
                self.assertTrue(policy.requires_hil(path))

    def test_classification_reports_exact_hardware_paths(self) -> None:
        report = policy.assess(
            "1" * 40,
            "2" * 40,
            ["README.md", "python/src/adxl355/device.py", "c/src/adxl355.c"],
        )
        self.assertEqual(report["classification"], "hardware-change")
        self.assertEqual(
            report["hardware_sensitive_paths"],
            ["c/src/adxl355.c", "python/src/adxl355/device.py"],
        )
        self.assertEqual(report["changed_paths"], 3)

    def test_baseline_matches_archived_release_evidence_shape(self) -> None:
        baseline = policy.load_baseline()
        self.assertEqual(
            baseline["validated_commit"], "71de69b8727a9f8eef254de586d9bce7bc8fa8ac"
        )
        self.assertEqual(set(baseline["recorded_evidence"]), {"spi", "i2c"})
        self.assertEqual(baseline["source_release_tag"], "v0.1.0-alpha.3")

    def test_invalid_baselines_fail_closed(self) -> None:
        valid = policy.load_baseline()
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "baseline.json"
            for edit in (
                {"source_release_url": "https://example.invalid/fake"},
                {"validated_commit": "not-a-sha"},
                {"recorded_evidence": {}},
                {"source_release_tag": "../../main"},
            ):
                broken = dict(valid)
                broken.update(edit)
                file.write_text(json.dumps(broken), encoding="utf-8")
                with self.subTest(edit=edit), self.assertRaises(policy.PolicyError):
                    policy.load_baseline(file)

    def test_future_unreleased_candidate_evidence_may_anchor_new_baseline(self) -> None:
        baseline = policy.load_baseline()
        fresh = dict(baseline)
        fresh.pop("source_release_tag")
        fresh.pop("source_release_url")
        fresh["evidence_run_urls"] = {
            "spi": "https://github.com/oaslananka/adxl355/actions/runs/123456",
            "i2c": "https://github.com/oaslananka/adxl355/actions/runs/123457",
        }
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "baseline.json"
            file.write_text(json.dumps(fresh), encoding="utf-8")
            self.assertEqual(
                policy.load_baseline(file)["evidence_run_urls"]["spi"],
                fresh["evidence_run_urls"]["spi"],
            )
            fresh["evidence_run_urls"]["i2c"] = "https://example.org/fake"
            file.write_text(json.dumps(fresh), encoding="utf-8")
            with self.assertRaisesRegex(policy.PolicyError, "evidence run URL"):
                policy.load_baseline(file)

    def test_release_disclosure_retains_strict_manual_hil_gate(self) -> None:
        script = (policy.ROOT / "scripts/check_hil_release.sh").read_text()
        self.assertIn('"--report-only"', script)
        self.assertIn('if [[ "$report_only" == true ]]', script)
        self.assertIn('--head "$head" --require-software-only', script)
        self.assertIn('--head "$head"', script)
    def test_git_diff_parsing_requires_complete_nul_framing(self) -> None:
        self.assertEqual(
            policy.paths_from_git_diff(b"README.md\x00c/src/adxl355.c\x00"),
            ["README.md", "c/src/adxl355.c"],
        )
        self.assertEqual(policy.paths_from_git_diff(b""), [])
        for broken in (b"README.md", b"a\x00a\x00", b"\xff\x00"):
            with self.subTest(broken=broken), self.assertRaises(policy.PolicyError):
                policy.paths_from_git_diff(broken)

    def test_cli_metadata_and_fail_closed_sensor_change(self) -> None:
        from contextlib import redirect_stdout
        from io import BytesIO, StringIO, TextIOWrapper

        with patch("sys.argv", ["hil_release_policy.py", "--metadata"]):
            metadata = StringIO()
            with redirect_stdout(metadata):
                self.assertEqual(policy.main(), 0)
            self.assertIn(
                "71de69b8727a9f8eef254de586d9bce7bc8fa8ac", metadata.getvalue()
            )

        sha = "b" * 40
        for path, status in ((b"README.md\0", 0), (b"c/src/adxl355.c\0", 2)):
            with (
                patch(
                    "sys.argv",
                    ["hil_release_policy.py", "--head", sha, "--require-software-only"],
                ),
                patch("sys.stdin", TextIOWrapper(BytesIO(path), encoding="utf-8")),
            ):
                report = StringIO()
                with redirect_stdout(report):
                    self.assertEqual(policy.main(), status)
                self.assertIn("release_sha", report.getvalue())
                self.assertIn(
                    "HIL REQUIRED" if status == 2 else "software-only",
                    report.getvalue(),
                )
