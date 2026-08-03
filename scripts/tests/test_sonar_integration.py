from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/sonar.yml"
PROPERTIES = REPO_ROOT / "sonar-project.properties"
SUMMARY_SCRIPT = REPO_ROOT / "scripts/sonar_summary.py"


def load_summary_module() -> Any:
    spec = importlib.util.spec_from_file_location("sonar_summary", SUMMARY_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load sonar_summary")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SonarIntegrationTests(unittest.TestCase):
    def test_workflow_uses_official_immutable_action_and_least_privilege(self) -> None:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["analysis"]
        self.assertEqual(job["permissions"], {"contents": "read"})
        self.assertEqual(job["runs-on"], "ubuntu-24.04")
        checkout = next(
            step
            for step in job["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        self.assertEqual(checkout["with"]["fetch-depth"], 0)
        self.assertFalse(checkout["with"]["persist-credentials"])
        scan = next(
            step
            for step in job["steps"]
            if str(step.get("uses", "")).startswith(
                "SonarSource/sonarqube-scan-action@"
            )
        )
        self.assertRegex(
            scan["uses"],
            r"^SonarSource/sonarqube-scan-action@[0-9a-f]{40}$",
        )
        self.assertEqual(scan["env"]["SONAR_TOKEN"], "${{ secrets.SONAR_TOKEN }}")

    def test_workflow_builds_cfamily_database_and_imports_go_coverage(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("CMAKE_EXPORT_COMPILE_COMMANDS=ON", text)
        self.assertIn("sonar-build/compile_commands.json", text)
        self.assertIn("go test -covermode=atomic -coverprofile=coverage.out", text)
        self.assertIn("scripts/sonar_summary.py", text)
        self.assertNotIn("sonar.qualitygate.wait=true", text)

    def test_project_properties_define_real_multilanguage_scope(self) -> None:
        text = PROPERTIES.read_text(encoding="utf-8")
        properties = dict(
            line.split("=", 1)
            for line in text.splitlines()
            if line and not line.startswith("#") and "=" in line
        )
        self.assertEqual(properties["sonar.projectKey"], "oaslananka_adxl355")
        self.assertEqual(properties["sonar.organization"], "oaslananka")
        self.assertEqual(
            properties["sonar.cfamily.compile-commands"],
            "sonar-build/compile_commands.json",
        )
        self.assertEqual(properties["sonar.go.coverage.reportPaths"], "go/coverage.out")
        sources = set(properties["sonar.sources"].split(","))
        self.assertTrue(
            {"c", "cpp", "python/src", "node/src", "rust/src", "go"}.issubset(sources)
        )
        self.assertIn("**/build/**", properties["sonar.exclusions"])
        self.assertIn("python/src/adxl355.egg-info/**", properties["sonar.exclusions"])

    def test_summary_redacts_security_issue_details(self) -> None:
        module = load_summary_module()
        markdown = module.render_markdown(
            gate={
                "status": "ERROR",
                "conditions": [
                    {
                        "status": "ERROR",
                        "metricKey": "new_security_rating",
                        "actualValue": "3",
                        "errorThreshold": "1",
                    }
                ],
            },
            measures={"bugs": "1", "vulnerabilities": "3", "code_smells": "5"},
            issues=[
                {
                    "rule": "python:S1234",
                    "message": "Use the safer branch.",
                    "component": "oaslananka_adxl355:python/src/adxl355/device.py",
                    "line": 12,
                    "impacts": [{"softwareQuality": "RELIABILITY", "severity": "HIGH"}],
                },
                {
                    "rule": "secrets:S9999",
                    "message": "Sensitive exploit detail must not appear.",
                    "component": "oaslananka_adxl355:.github/workflows/release.yml",
                    "line": 50,
                    "impacts": [{"softwareQuality": "SECURITY", "severity": "HIGH"}],
                },
            ],
            dashboard_url="https://sonarcloud.io/dashboard?id=oaslananka_adxl355",
            scope="main",
            total_issues=2,
        )
        self.assertIn("python:S1234", markdown)
        self.assertIn("device.py:12", markdown)
        self.assertIn("Security issue details are intentionally omitted", markdown)
        self.assertNotIn("Sensitive exploit detail", markdown)
        self.assertNotIn("secrets:S9999", markdown)

    def test_report_task_rejects_untrusted_hosts(self) -> None:
        module = load_summary_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report-task.txt"
            path.write_text(
                "ceTaskUrl=https://example.invalid/api/ce/task?id=1\n"
                "dashboardUrl=https://sonarcloud.io/dashboard?id=oaslananka_adxl355\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                module.parse_report_task(path)


if __name__ == "__main__":
    unittest.main()
