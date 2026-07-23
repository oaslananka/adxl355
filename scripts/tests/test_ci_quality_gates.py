from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"
NODE_RISK_ACCEPTANCE = REPO_ROOT / "docs/security/node-dev-dependency-risk.md"


class CiQualityGateTests(unittest.TestCase):
    def load_jobs(self) -> dict[str, Any]:
        workflow = cast(dict[str, Any], yaml.safe_load(CI_WORKFLOW.read_text()))
        return cast(dict[str, Any], workflow["jobs"])

    @staticmethod
    def commands(job: dict[str, Any]) -> str:
        return "\n".join(
            str(step.get("run", ""))
            for step in job["steps"]
            if isinstance(step, dict)
        )

    @staticmethod
    def environment(job: dict[str, Any]) -> str:
        values: list[str] = []
        for step in job["steps"]:
            if not isinstance(step, dict):
                continue
            env = step.get("env", {})
            if isinstance(env, dict):
                values.extend(f"{key}={value}" for key, value in env.items())
        return "\n".join(values)

    def test_c_and_cpp_enforce_warnings_sanitizers_and_install_smoke(self) -> None:
        jobs = self.load_jobs()
        c_commands = self.commands(jobs["c"])
        cpp_commands = self.commands(jobs["cpp"])

        for job_name, commands in (("c", c_commands), ("cpp", cpp_commands)):
            self.assertIn("ADXL355_WARNINGS_AS_ERRORS=ON", commands)
            self.assertIn("ADXL355_ENABLE_SANITIZERS=ON", commands)
            environment = self.environment(jobs[job_name])
            self.assertIn("ASAN_OPTIONS=", environment)
            self.assertIn("UBSAN_OPTIONS=", environment)
        self.assertIn("scripts/smoke_cmake_packages.sh", cpp_commands)

    def test_python_runs_lint_type_package_wheel_and_examples(self) -> None:
        python_job = self.load_jobs()["python"]
        commands = self.commands(python_job)
        self.assertEqual(
            python_job["strategy"]["matrix"]["python-version"],
            ["3.10", "3.11", "3.12"],
        )
        self.assertIn("setuptools==83.0.0", commands)
        self.assertIn("ruff check", commands)
        self.assertIn("mypy src examples", commands)
        self.assertIn("python -m build --no-isolation", commands)
        self.assertIn("dist/*.whl", commands)
        self.assertIn("scripts.versioning import load_version", commands)
        self.assertIn("EXPECTED_VERSION", commands)
        self.assertNotIn("__version__ == '0.1.0'", commands)
        self.assertIn("examples/basic_read.py", commands)
        self.assertIn("examples/calibrate.py", commands)

    def test_rust_runs_format_hal_lint_docs_and_package_verification(self) -> None:
        commands = self.commands(self.load_jobs()["rust"])
        self.assertIn("cargo fmt --all -- --check", commands)
        self.assertIn("cargo clippy --no-default-features --features hal -- -D warnings", commands)
        self.assertIn("cargo test --doc --all-features", commands)
        self.assertIn("cargo package", commands)

    def test_node_optional_dependency_risk_is_scoped_and_expires(self) -> None:
        text = NODE_RISK_ACCEPTANCE.read_text()
        self.assertIn("@emnapi/runtime@1.11.1", text)
        self.assertIn("2026-10-23", text)
        self.assertIn("not part of the published", text)
        self.assertIn("not a blanket ignore", text)

    def test_node_uses_supported_matrix_and_enforces_pack_and_audit(self) -> None:
        node = self.load_jobs()["node"]
        versions = node["strategy"]["matrix"]["node-version"]
        self.assertEqual(versions, ["22", "24", "26"])
        commands = self.commands(node)
        self.assertIn("npm ci --ignore-scripts", commands)
        self.assertIn("npm run typecheck", commands)
        self.assertIn("npm run pack:check", commands)
        self.assertIn("npm run audit:ci", commands)

    def test_all_ci_actions_are_pinned_to_full_commit_shas(self) -> None:
        jobs = self.load_jobs()
        for job in jobs.values():
            for step in job["steps"]:
                if not isinstance(step, dict) or "uses" not in step:
                    continue
                action = str(step["uses"])
                self.assertRegex(action, r"@[0-9a-f]{40}$", action)

    def test_go_runs_format_vet_race_and_coverage_without_threshold(self) -> None:
        commands = self.commands(self.load_jobs()["go"])
        self.assertIn("gofmt -l", commands)
        self.assertIn("go vet ./...", commands)
        self.assertIn("go test -race ./...", commands)
        self.assertIn("-coverprofile=coverage.out", commands)
        self.assertIn("go tool cover -func=coverage.out", commands)
        self.assertNotIn("cover-threshold", commands)


if __name__ == "__main__":
    unittest.main()
