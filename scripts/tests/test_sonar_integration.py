from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

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


SONAR = load_summary_module()


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class SequenceClient:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = iter(payloads)
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def get(
        self, endpoint: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        self.calls.append((endpoint, params))
        return next(self.payloads)


class SonarIntegrationTests(unittest.TestCase):
    def test_workflow_uses_official_immutable_actions_and_least_privilege(self) -> None:
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
        setup_python = next(
            step
            for step in job["steps"]
            if str(step.get("uses", "")).startswith("actions/setup-python@")
        )
        self.assertRegex(setup_python["uses"], r"^actions/setup-python@[0-9a-f]{40}$")
        rust_toolchain = next(
            step
            for step in job["steps"]
            if str(step.get("uses", "")).startswith("dtolnay/rust-toolchain@")
        )
        self.assertRegex(
            rust_toolchain["uses"], r"^dtolnay/rust-toolchain@[0-9a-f]{40}$"
        )
        self.assertEqual(rust_toolchain["with"]["components"], "clippy")

    def test_workflow_builds_databases_and_imports_bounded_coverage(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("CMAKE_EXPORT_COMPILE_COMMANDS=ON", text)
        self.assertIn("sonar-build/compile_commands.json", text)
        self.assertIn("go test -covermode=atomic -coverprofile=coverage.out", text)
        self.assertIn("requirements/python/ci-test.txt", text)
        self.assertIn("coverage xml -o sonar-build/python-coverage.xml", text)
        self.assertIn("*/spec/generate_c_header.py", text)
        self.assertIn("scripts.tests.test_security_regressions", text)
        self.assertIn("coverage report --fail-under=80", text)
        self.assertIn(
            'python scripts/sonar_summary.py "${args[@]}" > "$GITHUB_STEP_SUMMARY"',
            text,
        )
        self.assertNotIn("--output", text)
        self.assertNotIn("--report-task", text)
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
        self.assertEqual(
            properties["sonar.python.coverage.reportPaths"],
            "sonar-build/python-coverage.xml",
        )
        self.assertEqual(properties["sonar.python.version"], "3.10,3.11,3.12")
        self.assertEqual(
            properties["sonar.rust.cargo.manifestPaths"], "rust/Cargo.toml"
        )
        self.assertEqual(properties["sonar.yaml.activate"], "true")
        sources = set(properties["sonar.sources"].split(","))
        self.assertTrue(
            {"c", "cpp", "python/src", "node/src", "rust/src", "go"}.issubset(sources)
        )
        self.assertIn("**/build/**", properties["sonar.exclusions"])
        self.assertIn("python/src/adxl355.egg-info/**", properties["sonar.exclusions"])

    def test_report_task_accepts_only_fixed_task_ids_and_sonarcloud_dashboard(
        self,
    ) -> None:
        parsed = SONAR.parse_report_task(
            "ceTaskId=AX12345678\n"
            "dashboardUrl=https://sonarcloud.io/dashboard?id=oaslananka_adxl355\n"
        )
        self.assertEqual(parsed["ceTaskId"], "AX12345678")

        with self.assertRaisesRegex(ValueError, "task id"):
            SONAR.parse_report_task(
                "ceTaskId=bad/id\n"
                "dashboardUrl=https://sonarcloud.io/dashboard?id=oaslananka_adxl355\n"
            )
        with self.assertRaisesRegex(ValueError, "approved"):
            SONAR.parse_report_task(
                "ceTaskId=AX12345678\ndashboardUrl=https://example.invalid/dashboard\n"
            )
        with self.assertRaisesRegex(ValueError, "dashboardUrl"):
            SONAR.parse_report_task("ceTaskId=AX12345678\n")

    def test_report_task_loader_uses_only_the_fixed_scanner_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report-task.txt"
            with mock.patch.object(SONAR, "REPORT_TASK_PATH", path):
                with self.assertRaises(FileNotFoundError):
                    SONAR.load_report_task()
                path.write_text(
                    "ceTaskId=AX12345678\n"
                    "dashboardUrl=https://sonarcloud.io/dashboard?id=oaslananka_adxl355\n",
                    encoding="utf-8",
                )
                self.assertEqual(SONAR.load_report_task()["ceTaskId"], "AX12345678")

    def test_client_uses_fixed_host_allowlisted_endpoint_and_bearer_auth(self) -> None:
        with self.assertRaisesRegex(ValueError, "SONAR_TOKEN"):
            SONAR.SonarClient("")
        client = SONAR.SonarClient("test-token")
        with self.assertRaisesRegex(ValueError, "allow-listed"):
            client.get("https://example.invalid/api/test")
        with mock.patch.object(
            SONAR.urllib.request,
            "urlopen",
            return_value=FakeResponse({"ok": True}),
        ) as urlopen:
            self.assertEqual(client.get("api/test", {"a": "b"}), {"ok": True})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://sonarcloud.io/api/test?a=b")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")

    def test_client_converts_network_failures_and_rejects_non_object_json(self) -> None:
        client = SONAR.SonarClient("test-token")
        http_error = urllib.error.HTTPError(
            "https://sonarcloud.io/api/test", 403, "denied", None, None
        )
        with mock.patch.object(SONAR.urllib.request, "urlopen", side_effect=http_error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                client.get("api/test")
        with mock.patch.object(
            SONAR.urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            with self.assertRaisesRegex(RuntimeError, "request failed"):
                client.get("api/test")
        with mock.patch.object(
            SONAR.urllib.request, "urlopen", return_value=FakeResponse([])
        ):
            with self.assertRaisesRegex(ValueError, "unexpected payload"):
                client.get("api/test")

    def test_wait_for_analysis_polls_fixed_endpoint_until_success(self) -> None:
        client = SequenceClient(
            [
                {"task": {"status": "PENDING"}},
                {"task": {"status": "SUCCESS", "analysisId": "analysis-1"}},
            ]
        )
        with mock.patch.object(SONAR.time, "sleep") as sleep:
            result = SONAR.wait_for_analysis(
                client, "AX12345678", attempts=3, interval_seconds=0.01
            )
        self.assertEqual(result, "analysis-1")
        self.assertEqual(
            client.calls,
            [
                ("api/ce/task", {"id": "AX12345678"}),
                ("api/ce/task", {"id": "AX12345678"}),
            ],
        )
        sleep.assert_called_once_with(0.01)

    def test_wait_for_analysis_rejects_failed_invalid_and_timeout_tasks(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "FAILED"):
            SONAR.wait_for_analysis(
                SequenceClient([{"task": {"status": "FAILED"}}]),
                "AX12345678",
                attempts=1,
                interval_seconds=0,
            )
        with self.assertRaisesRegex(ValueError, "response is invalid"):
            SONAR.wait_for_analysis(
                SequenceClient([{"task": "bad"}]),
                "AX12345678",
                attempts=1,
                interval_seconds=0,
            )
        with self.assertRaisesRegex(ValueError, "analysis id"):
            SONAR.wait_for_analysis(
                SequenceClient([{"task": {"status": "SUCCESS"}}]),
                "AX12345678",
                attempts=1,
                interval_seconds=0,
            )
        with mock.patch.object(SONAR.time, "sleep"):
            with self.assertRaises(TimeoutError):
                SONAR.wait_for_analysis(
                    SequenceClient([{"task": {"status": "IN_PROGRESS"}}]),
                    "AX12345678",
                    attempts=1,
                    interval_seconds=0,
                )

    def test_fetch_analysis_data_parses_gate_measures_issues_and_scope(self) -> None:
        client = SequenceClient(
            [
                {"projectStatus": {"status": "OK", "conditions": []}},
                {
                    "component": {
                        "measures": [
                            {"metric": "coverage", "value": "88.5"},
                            "ignored",
                        ]
                    }
                },
                {
                    "issues": [{"rule": "python:S1"}, "ignored"],
                    "paging": {"total": "7"},
                },
            ]
        )
        gate, measures, issues, total = SONAR.fetch_analysis_data(
            client,
            project_key="oaslananka_adxl355",
            analysis_id="analysis-1",
            branch="main",
            pull_request=None,
        )
        self.assertEqual(gate["status"], "OK")
        self.assertEqual(measures, {"coverage": "88.5"})
        self.assertEqual(issues, [{"rule": "python:S1"}])
        self.assertEqual(total, 7)
        self.assertEqual(client.calls[0][1], {"analysisId": "analysis-1"})
        self.assertEqual(client.calls[1][1]["branch"], "main")
        self.assertEqual(SONAR._scope_params(None, "107"), {"pullRequest": "107"})
        self.assertEqual(SONAR._scope_params(None, None), {})

    def test_fetch_analysis_data_rejects_invalid_gate_payload(self) -> None:
        client = SequenceClient([{"projectStatus": "invalid"}])
        with self.assertRaisesRegex(ValueError, "quality gate"):
            SONAR.fetch_analysis_data(
                client,
                project_key="oaslananka_adxl355",
                analysis_id="analysis-1",
                branch="main",
                pull_request=None,
            )

    def test_summary_redacts_security_issue_details(self) -> None:
        markdown = SONAR.render_markdown(
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
            scope="main|branch\n",
            total_issues=2,
        )
        self.assertIn("python:S1234", markdown)
        self.assertIn("device.py:12", markdown)
        self.assertIn("main\\|branch", markdown)
        self.assertIn("Security issue details are intentionally omitted", markdown)
        self.assertNotIn("Sensitive exploit detail", markdown)
        self.assertNotIn("secrets:S9999", markdown)

    def test_summary_handles_empty_results_legacy_security_and_paging(self) -> None:
        markdown = SONAR.render_markdown(
            gate={"status": "OK", "conditions": []},
            measures={},
            issues=[
                {
                    "type": "VULNERABILITY",
                    "message": "must stay hidden",
                    "component": "oaslananka_adxl355:file.py",
                }
            ],
            dashboard_url="https://sonarcloud.io/dashboard?id=oaslananka_adxl355",
            scope="branch main",
            total_issues=101,
        )
        self.assertIn("No conditions returned", markdown)
        self.assertIn("No measures returned", markdown)
        self.assertIn("No non-security issue details", markdown)
        self.assertIn("Only the first 1 of 101", markdown)
        self.assertNotIn("must stay hidden", markdown)
        self.assertIn(
            "Summary generation warning: line one line two",
            SONAR.render_warning("line one\nline two"),
        )

    def test_main_writes_success_summary_to_stdout_only(self) -> None:
        argv = [
            "sonar_summary.py",
            "--project-key",
            "oaslananka_adxl355",
            "--branch",
            "main",
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.dict(os.environ, {"SONAR_TOKEN": "test-token"}, clear=False),
            mock.patch.object(
                SONAR,
                "load_report_task",
                return_value={
                    "ceTaskId": "AX12345678",
                    "dashboardUrl": "https://sonarcloud.io/dashboard?id=oaslananka_adxl355",
                },
            ),
            mock.patch.object(SONAR, "SonarClient", return_value=object()),
            mock.patch.object(SONAR, "wait_for_analysis", return_value="analysis-1"),
            mock.patch.object(
                SONAR,
                "fetch_analysis_data",
                return_value=({"status": "OK", "conditions": []}, {}, [], 0),
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(SONAR.main(), 0)
        self.assertIn("Quality Gate: **OK**", stdout.getvalue())
        self.assertIn("Sonar summary written", stderr.getvalue())

    def test_main_soft_fail_writes_bounded_warning_and_non_soft_fail_raises(
        self,
    ) -> None:
        soft_argv = [
            "sonar_summary.py",
            "--project-key",
            "oaslananka_adxl355",
            "--branch",
            "main",
            "--soft-fail",
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "argv", soft_argv),
            mock.patch.object(
                SONAR, "load_report_task", side_effect=ValueError("bounded failure")
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(SONAR.main(), 0)
        self.assertIn("bounded failure", stdout.getvalue())
        self.assertIn("could not be generated", stderr.getvalue())

        hard_argv = [
            "sonar_summary.py",
            "--project-key",
            "oaslananka_adxl355",
            "--pull-request",
            "107",
        ]
        with (
            mock.patch.object(sys, "argv", hard_argv),
            mock.patch.object(
                SONAR, "load_report_task", side_effect=ValueError("hard failure")
            ),
        ):
            with self.assertRaisesRegex(ValueError, "hard failure"):
                SONAR.main()


if __name__ == "__main__":
    unittest.main()
