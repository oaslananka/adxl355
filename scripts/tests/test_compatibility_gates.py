from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from typing import Any, cast

import yaml
from pathlib import Path

from scripts.check_package_sizes import (
    ArtifactBudget,
    SizeBudgetError,
    evaluate,
    load_budgets,
    resolve_artifact_directory,
    resolve_report_path,
)
from scripts.check_public_api import (
    CompatibilityError,
    c_type_entries,
    canonical_cpp_entries,
    compare,
    snapshot,
    validate_baseline_update,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
API_BASELINE = REPO_ROOT / "spec" / "compatibility" / "public-api.json"
SIZE_BUDGETS = REPO_ROOT / "spec" / "compatibility" / "package-size-budgets.json"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


class PublicApiCompatibilityTests(unittest.TestCase):
    def test_current_public_api_contains_every_baseline_declaration(self) -> None:
        baseline = json.loads(API_BASELINE.read_text())
        self.assertEqual(compare(baseline, snapshot(REPO_ROOT)), [])
        for surface in ("c", "cpp", "python", "rust", "node", "go"):
            self.assertGreater(len(baseline["surfaces"][surface]), 0, surface)
        self.assertTrue(
            any("adxl355_read_offset" in entry for entry in baseline["surfaces"]["c"])
        )
        self.assertTrue(
            any(
                "signature:calculate_offset" in entry
                for entry in baseline["surfaces"]["python"]
            )
        )
        self.assertIn(
            "member:ADXL355:async readRaw(): Promise<RawXYZ>",
            baseline["surfaces"]["node"],
        )
        self.assertTrue(
            any(
                "linuxio/types.go:type SPIConfig struct" in entry
                for entry in baseline["surfaces"]["go"]
            )
        )
        self.assertTrue(
            any(
                "linuxio/transport_linux.go:func OpenSPI" in entry
                for entry in baseline["surfaces"]["go"]
            )
        )
        self.assertTrue(
            any(
                "device.go:func New(transport Transport) *Device" in entry
                for entry in baseline["surfaces"]["go"]
            )
        )
        self.assertTrue(
            any(
                "linuxio/types.go:func DefaultI2CConfig() I2CConfig" in entry
                for entry in baseline["surfaces"]["go"]
            )
        )

    def test_additive_public_api_change_is_allowed(self) -> None:
        baseline = {"surfaces": {"python": ["signature:read()"]}}
        current = {
            "surfaces": {"python": ["signature:read()", "signature:write(value)"]}
        }
        self.assertEqual(compare(baseline, current), [])

    def test_trailing_c_enum_member_is_additive(self) -> None:
        old = "typedef enum { OK = 0, ERR = -1 } status_t;"
        new = "typedef enum { OK = 0, ERR = -1, TIMEOUT = -2 } status_t;"
        self.assertIn(f"type:{old}", c_type_entries(new))
        self.assertEqual(
            compare(
                {"surfaces": {"c": [f"type:{old}"]}},
                {"surfaces": {"c": sorted(c_type_entries(new))}},
            ),
            [],
        )

    def test_legacy_cpp_inline_body_entries_migrate_to_signatures(self) -> None:
        legacy = {
            "member:Device:void probe() { check(probe()); } void reset() { check(reset()); } private: int hidden{};"
        }
        migrated = canonical_cpp_entries(legacy)
        self.assertEqual(
            migrated,
            {"member:Device:void probe()", "member:Device:void reset()"},
        )
        current = {
            "surfaces": {
                "cpp": [
                    "member:Device:void probe()",
                    "member:Device:void reset()",
                    "member:Device:void setOdr(Odr odr)",
                ]
            }
        }
        self.assertEqual(compare({"surfaces": {"cpp": sorted(legacy)}}, current), [])

    def test_changed_existing_cpp_method_signature_is_blocked(self) -> None:
        baseline = {"surfaces": {"cpp": ["member:Device:void probe()"]}}
        current = {"surfaces": {"cpp": ["member:Device:Status probe()"]}}
        self.assertEqual(len(compare(baseline, current)), 1)

    def test_changed_existing_c_enum_member_is_blocked(self) -> None:
        old = "typedef enum { OK = 0, ERR = -1 } status_t;"
        changed = "typedef enum { OK = 0, ERR = -9, TIMEOUT = -2 } status_t;"
        self.assertNotIn(f"type:{old}", c_type_entries(changed))

    def test_removed_public_api_declaration_is_blocked(self) -> None:
        baseline = {"surfaces": {"python": ["signature:read()"]}}
        current = {"surfaces": {"python": []}}
        self.assertEqual(
            compare(baseline, current),
            ["python: removed or changed public declaration: signature:read()"],
        )

    def test_signature_change_is_blocked_as_remove_plus_add(self) -> None:
        baseline = {"surfaces": {"go": ["func::Read(reg byte):error"]}}
        current = {"surfaces": {"go": ["func::Read(reg byte, length int):error"]}}
        self.assertEqual(len(compare(baseline, current)), 1)

    def test_additive_baseline_update_does_not_require_breaking_note(self) -> None:
        old = {"surfaces": {"c": ["function:read"]}}
        new = {"surfaces": {"c": ["function:read", "function:write"]}}
        validate_baseline_update(old, new, "")

    def test_breaking_baseline_update_requires_changelog_evidence(self) -> None:
        old = {"surfaces": {"rust": ["fn:read:()"]}}
        new = {"surfaces": {"rust": ["fn:read:(mode: Mode)"]}}
        with self.assertRaisesRegex(CompatibilityError, "CHANGELOG Breaking entry"):
            validate_baseline_update(old, new, "")
        validate_baseline_update(
            old,
            new,
            "+- **Breaking (Rust):** require an explicit mode argument.\n",
        )


class PackageSizeBudgetTests(unittest.TestCase):
    def test_current_go_module_archive_fits_reviewed_budget(self) -> None:
        version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / f"adxl355-go-{version}.tar.gz"
            subprocess.run(
                [
                    "git",
                    "archive",
                    "--format=tar.gz",
                    f"--prefix=adxl355-go-{version}/",
                    f"--output={archive}",
                    "HEAD:go",
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            report = evaluate(root, load_budgets("go"))
        self.assertEqual(report["status"], "ok", report)

    def test_artifact_directory_resolves_inside_temporary_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(
                resolve_artifact_directory(Path(temp)), Path(temp).resolve()
            )

    def test_symlink_cannot_escape_trusted_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            link = Path(temp) / "escape"
            link.symlink_to("/etc", target_is_directory=True)
            with self.assertRaisesRegex(SizeBudgetError, "outside trusted"):
                resolve_artifact_directory(link)

    def test_report_path_cannot_escape_artifact_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self.assertEqual(
                resolve_report_path(root / "SIZE_REPORT.json", root),
                root / "SIZE_REPORT.json",
            )
            with self.assertRaisesRegex(SizeBudgetError, "must remain inside"):
                resolve_report_path(root.parent / "escaped.json", root)

    def test_size_report_records_headroom(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "package.whl").write_bytes(b"x" * 80)
            report = evaluate(root, [ArtifactBudget("wheel", "*.whl", 100)])
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["artifacts"][0]["remaining_bytes"], 20)
        self.assertIsNone(report["artifacts"][0]["growth_from_baseline_bytes"])

    def test_size_report_records_change_from_measured_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "package.whl").write_bytes(b"x" * 90)
            report = evaluate(
                root,
                [ArtifactBudget("wheel", "*.whl", 100, measured_bytes=80)],
            )
        self.assertEqual(report["artifacts"][0]["growth_from_baseline_bytes"], 10)

    def test_oversized_package_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "package.tgz").write_bytes(b"x" * 101)
            report = evaluate(root, [ArtifactBudget("npm", "*.tgz", 100)])
        self.assertEqual(report["status"], "failure")
        self.assertIn("exceeding the reviewed 100-byte budget", report["failures"][0])

    def test_missing_or_duplicate_artifact_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = evaluate(root, [ArtifactBudget("crate", "*.crate", 100)])
        self.assertEqual(report["status"], "failure")
        self.assertIn("expected 1 artifact", report["failures"][0])


class WorkflowCompatibilityGateTests(unittest.TestCase):
    def load_workflow(self, path: Path) -> dict[str, Any]:
        return cast(dict[str, Any], yaml.safe_load(path.read_text()))

    def test_required_consistency_job_checks_public_api_with_full_history(self) -> None:
        job = self.load_workflow(CI_WORKFLOW)["jobs"]["consistency"]
        checkout = next(
            step
            for step in job["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        self.assertEqual(checkout["with"]["fetch-depth"], 0)
        self.assertFalse(checkout["with"]["persist-credentials"])
        commands = "\n".join(str(step.get("run", "")) for step in job["steps"])
        self.assertIn("scripts/check_public_api.py", commands)
        self.assertIn("github.event.pull_request.base.sha", CI_WORKFLOW.read_text())

    def test_release_records_size_reports_for_every_artifact_family(self) -> None:
        workflow = self.load_workflow(RELEASE_WORKFLOW)
        jobs = workflow["jobs"]
        expected = {
            "python-package": "python",
            "rust-package": "rust",
            "node-package": "node",
            "go-package": "go",
            "c-cpp-package": "native",
        }
        for job_name, family in expected.items():
            commands = "\n".join(
                str(step.get("run", "")) for step in jobs[job_name]["steps"]
            )
            self.assertIn("check_package_sizes.py", commands, job_name)
            self.assertIn(f"--family {family}", commands, job_name)
            self.assertIn("SIZE_REPORT.json", commands, job_name)
        bundle_commands = "\n".join(
            str(step.get("run", "")) for step in jobs["release-bundle"]["steps"]
        )
        self.assertIn("--family release", bundle_commands)
        self.assertIn("RELEASE_SIZE_REPORT.json", RELEASE_WORKFLOW.read_text())

    def test_all_size_budgets_are_positive_and_bounded(self) -> None:
        data = json.loads(SIZE_BUDGETS.read_text())
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(
            set(data["families"]), {"python", "rust", "node", "go", "native", "release"}
        )
        for budgets in data["families"].values():
            for budget in budgets:
                self.assertGreater(budget["max_bytes"], 0)
                self.assertGreaterEqual(budget["count"], 1)
                self.assertNotIn("**", budget["pattern"])
                if budget["name"] != "aggregate-release-bundle":
                    self.assertGreater(budget["measured_bytes"], 0)
                    self.assertLess(budget["measured_bytes"], budget["max_bytes"])


if __name__ == "__main__":
    unittest.main()
