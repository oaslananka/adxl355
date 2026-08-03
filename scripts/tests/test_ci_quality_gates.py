from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"
PYTHON_LOCK_ROOT = REPO_ROOT / "requirements/python"
NODE_RISK_ACCEPTANCE = REPO_ROOT / "docs/security/node-dev-dependency-risk.md"


class CiQualityGateTests(unittest.TestCase):
    def load_jobs(self) -> dict[str, Any]:
        workflow = cast(dict[str, Any], yaml.safe_load(CI_WORKFLOW.read_text()))
        return cast(dict[str, Any], workflow["jobs"])

    @staticmethod
    def commands(job: dict[str, Any]) -> str:
        return "\n".join(
            str(step.get("run", "")) for step in job["steps"] if isinstance(step, dict)
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
        self.assertIn("requirements/python/ci-test.txt", commands)
        self.assertIn("requirements/python/ci-quality.txt", commands)
        quality_lock = (PYTHON_LOCK_ROOT / "ci-quality.txt").read_text()
        self.assertIn("setuptools==83.0.0", quality_lock)
        self.assertIn("ruff==0.15.22", quality_lock)
        self.assertIn("mypy==1.20.2", quality_lock)
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
        self.assertIn(
            "cargo clippy --no-default-features --features hal -- -D warnings", commands
        )
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
        self.assertIn("npm rebuild spi-device i2c-bus --foreground-scripts", commands)
        self.assertIn("npm run native:check", commands)
        self.assertIn("npm run typecheck", commands)
        self.assertIn("npm run pack:check", commands)
        self.assertIn("npm run pack:core-only", commands)
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
        self.assertIn("go mod verify", commands)
        self.assertIn("go build ./...", commands)
        self.assertIn("GOOS=linux GOARCH=arm64 go build ./...", commands)
        self.assertIn("GOOS=linux GOARCH=arm go build ./...", commands)
        self.assertIn("GOOS=windows GOARCH=amd64 go build ./...", commands)
        self.assertIn("GOOS=darwin GOARCH=arm64 go build ./...", commands)
        self.assertIn("go vet ./...", commands)
        self.assertIn("go test -race ./...", commands)
        self.assertIn("-coverprofile=coverage.out", commands)
        self.assertIn("go tool cover -func=coverage.out", commands)
        self.assertNotIn("cover-threshold", commands)

    def test_native_platform_matrix_is_required_by_consistency(self) -> None:
        jobs = self.load_jobs()
        expected = {
            "native-clang": ("Native (Clang/Linux)", "ubuntu-24.04"),
            "native-macos": ("Native (macOS/arm64)", "macos-15"),
            "native-windows": ("Native (Windows/MSVC)", "windows-2025"),
            "native-arm": ("Native (Linux/arm64)", "ubuntu-24.04-arm"),
        }
        for job_id, (name, runner) in expected.items():
            job = jobs[job_id]
            self.assertEqual(job["name"], name)
            self.assertEqual(job["runs-on"], runner)
            commands = self.commands(job)
            self.assertIn("ADXL355_WARNINGS_AS_ERRORS=ON", commands)
            self.assertIn("ctest --test-dir", commands)
            self.assertIn("smoke_cmake_packages", commands)

        windows_commands = self.commands(jobs["native-windows"])
        self.assertIn('$ErrorActionPreference = "Stop"', windows_commands)
        self.assertIn(
            "$PSNativeCommandUseErrorActionPreference = $true", windows_commands
        )

        for job_id in expected:
            checkout = next(
                step
                for step in jobs[job_id]["steps"]
                if str(step.get("uses", "")).startswith("actions/checkout@")
            )
            self.assertFalse(checkout["with"]["persist-credentials"])

        consistency_needs = set(jobs["consistency"]["needs"])
        self.assertTrue(set(expected).issubset(consistency_needs))

    def test_aggregate_tests_gate_enforces_every_ci_job(self) -> None:
        jobs = self.load_jobs()
        gate = jobs["tests"]
        expected = {
            "c",
            "cpp",
            "native-clang",
            "native-macos",
            "native-windows",
            "native-arm",
            "python",
            "rust",
            "node",
            "go",
            "embedded",
            "fuzz",
            "consistency",
        }
        self.assertEqual(gate["name"], "Tests")
        self.assertEqual(set(gate["needs"]), expected)
        self.assertEqual(gate["if"], "always()")
        self.assertEqual(gate["permissions"], {})
        self.assertEqual(gate["runs-on"], "ubuntu-24.04")
        self.assertNotIn("uses", str(gate["steps"]))
        env = gate["steps"][0]["env"]
        self.assertEqual(
            set(env), {name.upper().replace("-", "_") for name in expected}
        )
        command = str(gate["steps"][0]["run"])
        self.assertIn('test "$result" = success', command)

    def test_windows_smoke_script_is_bounded_and_uses_installed_consumers(self) -> None:
        script = (REPO_ROOT / "scripts" / "smoke_cmake_packages.ps1").read_text()
        self.assertIn('$ErrorActionPreference = "Stop"', script)
        self.assertIn("$PSNativeCommandUseErrorActionPreference = $true", script)
        self.assertIn("cmake --install", script)
        self.assertIn("adxl355_c_consumer.exe", script)
        self.assertIn("adxl355_cpp_consumer.exe", script)
        self.assertIn("CMAKE_PREFIX_PATH", script)


if __name__ == "__main__":
    unittest.main()
