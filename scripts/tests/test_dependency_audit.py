from __future__ import annotations

import datetime as dt
import json
import re
import unittest
from pathlib import Path
from typing import Any, cast

import tomllib
import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
AUDIT = WORKFLOWS / "dependency-audit.yml"
REVIEW = WORKFLOWS / "dependency-review.yml"
GO_OSV_CONFIG = REPO_ROOT / "go" / "osv-scanner.toml"
GOVULNCHECK_MOD = REPO_ROOT / "tools" / "govulncheck" / "go.mod"
GOVULNCHECK_SUM = REPO_ROOT / "tools" / "govulncheck" / "go.sum"
CI_TEST_INPUT = REPO_ROOT / "requirements" / "python" / "ci-test.in"
CI_TEST_LOCK = CI_TEST_INPUT.with_suffix(".txt")
RENOVATE = REPO_ROOT / "renovate.json"
SHA_PIN = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def load_yaml(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")))


class DependencyAuditTests(unittest.TestCase):
    def test_pytest_security_floor_is_reviewed_and_hash_locked(self) -> None:
        self.assertIn("pytest==9.1.1", CI_TEST_INPUT.read_text(encoding="utf-8"))
        self.assertIn("pytest==9.1.1", CI_TEST_LOCK.read_text(encoding="utf-8"))
        self.assertNotIn("pytest==8.4.2", CI_TEST_INPUT.read_text(encoding="utf-8"))

    def test_dependency_review_blocks_moderate_runtime_and_development_risk(
        self,
    ) -> None:
        workflow = load_yaml(REVIEW)
        step = workflow["jobs"]["dependency-review"]["steps"][-1]
        self.assertEqual(step["with"]["fail-on-severity"], "moderate")
        self.assertEqual(step["with"]["fail-on-scopes"], "runtime, development")
        self.assertFalse(step["with"]["warn-only"])

    def test_dependency_audit_runs_on_pr_main_schedule_and_manual_dispatch(
        self,
    ) -> None:
        workflow = load_yaml(AUDIT)
        triggers = workflow.get("on", workflow.get(True, {}))
        self.assertIn("pull_request", triggers)
        self.assertIn("push", triggers)
        self.assertIn("schedule", triggers)
        self.assertIn("workflow_dispatch", triggers)
        self.assertEqual(workflow["permissions"], {})
        self.assertEqual(
            workflow["jobs"]["python-audit"]["permissions"],
            {"contents": "read"},
        )
        self.assertEqual(
            workflow["jobs"]["go-reachability"]["permissions"],
            {"contents": "read"},
        )
        self.assertEqual(workflow["jobs"]["dependency-audit"]["permissions"], {})

    def test_dependency_audit_uses_pinned_python_go_and_osv_controls(self) -> None:
        workflow = load_yaml(AUDIT)
        jobs = workflow["jobs"]
        self.assertEqual(
            set(jobs),
            {"python-audit", "go-reachability", "osv-scan", "dependency-audit"},
        )

        python_steps = jobs["python-audit"]["steps"]
        pip_audit = next(
            step
            for step in python_steps
            if "pypa/gh-action-pip-audit@" in str(step.get("uses", ""))
        )
        self.assertRegex(str(pip_audit["uses"]), SHA_PIN)
        self.assertEqual(pip_audit["with"]["no-deps"], True)
        self.assertEqual(pip_audit["with"]["require-hashes"], True)
        self.assertEqual(
            pip_audit["with"]["internal-be-careful-extra-flags"],
            "--disable-pip",
        )
        locks = jobs["python-audit"]["strategy"]["matrix"]["lock"]
        self.assertEqual(
            set(locks),
            {
                "ci-quality",
                "ci-test",
                "consistency",
                "hil-build",
                "hil-i2c",
                "hil-spi",
                "platformio",
                "release",
            },
        )
        self.assertEqual(
            pip_audit["with"]["inputs"],
            "requirements/python/${{ matrix.lock }}.txt",
        )

        go_job = jobs["go-reachability"]
        commands = "\n".join(str(step.get("run", "")) for step in go_job["steps"])
        self.assertNotIn("go install", commands)
        self.assertIn("go mod verify", commands)
        self.assertIn("go build -mod=readonly", commands)
        self.assertIn('runner.temp }}/govulncheck" ./...', commands)
        self.assertIn("golang.org/x/vuln v1.6.0", GOVULNCHECK_MOD.read_text())
        self.assertTrue(GOVULNCHECK_SUM.is_file())
        self.assertIn("golang.org/x/vuln v1.6.0", GOVULNCHECK_SUM.read_text())
        setup_go = next(
            step
            for step in go_job["steps"]
            if "actions/setup-go@" in str(step.get("uses", ""))
        )
        self.assertEqual(setup_go["with"]["go-version"], "1.25")

        osv_job = jobs["osv-scan"]
        self.assertRegex(str(osv_job["uses"]), SHA_PIN)
        self.assertEqual(osv_job["with"]["fail-on-vuln"], True)
        self.assertIn("--recursive", str(osv_job["with"]["scan-args"]))
        self.assertEqual(
            osv_job["permissions"],
            {"actions": "read", "contents": "read", "security-events": "write"},
        )

        aggregate = jobs["dependency-audit"]
        self.assertEqual(
            set(aggregate["needs"]), {"python-audit", "go-reachability", "osv-scan"}
        )
        self.assertEqual(aggregate["name"], "Dependency Audit")
        env = aggregate["steps"][0]["env"]
        self.assertEqual(env["PYTHON_AUDIT"], "${{ needs.python-audit.result }}")
        self.assertEqual(env["GO_REACHABILITY"], "${{ needs.go-reachability.result }}")
        self.assertEqual(env["OSV_SCAN"], "${{ needs.osv-scan.result }}")

    def test_go_osv_exception_is_reachability_based_bounded_and_reviewable(
        self,
    ) -> None:
        config = tomllib.loads(GO_OSV_CONFIG.read_text(encoding="utf-8"))
        ignored = config["IgnoredVulns"]
        self.assertEqual(config["GoVersionOverride"], "1.21.0")
        by_id = {item["id"]: item for item in ignored}
        self.assertEqual(set(by_id), {"GO-2025-3750", "GO-2026-5024"})
        for entry in by_id.values():
            expiry = dt.date.fromisoformat(str(entry["ignoreUntil"]))
            self.assertGreater(expiry, dt.date(2026, 8, 3))
            self.assertLessEqual(expiry, dt.date(2026, 11, 3))
        xsys_reason = str(by_id["GO-2026-5024"]["reason"]).lower()
        self.assertIn("govulncheck", xsys_reason)
        self.assertIn("x/sys/unix", xsys_reason)
        self.assertIn("go 1.21", xsys_reason)
        stdlib_reason = str(by_id["GO-2025-3750"]["reason"]).lower()
        self.assertIn("windows-only", stdlib_reason)
        self.assertIn("linux build-tagged", stdlib_reason)
        self.assertIn("go 1.21", stdlib_reason)

    def test_renovate_security_updates_remain_immediate(self) -> None:
        config = json.loads(RENOVATE.read_text(encoding="utf-8"))
        self.assertTrue(config["vulnerabilityAlerts"]["enabled"])
        self.assertEqual(config["vulnerabilityAlerts"]["prCreation"], "immediate")
        self.assertIsNone(config["vulnerabilityAlerts"]["minimumReleaseAge"])
        self.assertTrue(config["osvVulnerabilityAlerts"])


if __name__ == "__main__":
    unittest.main()
