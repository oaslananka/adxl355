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
        self.assertEqual(
            policy.resolve_commit_from_tag(baseline["source_release_tag"]),
            baseline["validated_commit"],
        )

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

    def test_missing_or_nonancestor_release_baseline_is_rejected(self) -> None:
        with patch.object(policy.subprocess, "run") as run:
            run.return_value.returncode = 1
            run.return_value.stdout = ""
            with self.assertRaises(policy.PolicyError):
                policy.changed_paths("a" * 40, "b" * 40)

    def test_no_external_runner_is_needed_to_classify_changes(self) -> None:
        baseline = policy.load_baseline()
        head = policy.resolve_commit("HEAD")
        paths = policy.changed_paths(baseline["validated_commit"], head)
        self.assertTrue(
            policy.assess(baseline["validated_commit"], head, paths)[
                "requires_fresh_hil"
            ]
        )
