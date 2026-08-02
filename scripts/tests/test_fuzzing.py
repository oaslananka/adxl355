from __future__ import annotations

import importlib
import unittest
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


class FuzzingTests(unittest.TestCase):
    def load_jobs(self) -> dict[str, Any]:
        workflow = cast(dict[str, Any], yaml.safe_load(CI_WORKFLOW.read_text()))
        return cast(dict[str, Any], workflow["jobs"])

    def load_fuzz_module(self) -> Any:
        return importlib.import_module("scripts.fuzz_python_boundaries")

    def test_python_mutation_smoke_exercises_accept_and_reject_paths(self) -> None:
        module = self.load_fuzz_module()
        report = module.run(300, 355)
        counters = report["counters"]
        for name in (
            "decode",
            "probe-rejected",
            "raw-rejected",
            "raw-accepted",
            "unsafe-rejected",
            "safe-accepted",
        ):
            self.assertGreater(counters[name], 0, name)

    def test_python_mutation_budget_is_bounded(self) -> None:
        module = self.load_fuzz_module()
        for value in (0, 100_001):
            with self.assertRaisesRegex(ValueError, "iterations"):
                module.run(value, 355)

    def test_c_target_uses_libfuzzer_and_transport_boundaries(self) -> None:
        cmake = (REPO_ROOT / "c" / "fuzz" / "CMakeLists.txt").read_text()
        source = (REPO_ROOT / "c" / "fuzz" / "fuzz_adxl355.c").read_text()
        root_cmake = (REPO_ROOT / "c" / "CMakeLists.txt").read_text()
        self.assertIn("ADXL355_BUILD_FUZZERS", root_cmake)
        self.assertIn("-fsanitize=fuzzer,address,undefined", cmake)
        self.assertIn("LLVMFuzzerTestOneInput", source)
        self.assertIn("return len == 0U ? 0 : (int)(len - 1U)", source)
        self.assertIn("(int)(len + 1U)", source)
        self.assertIn("adxl355_read_raw", source)
        self.assertIn("adxl355_read_temperature_raw", source)

    def test_fuzz_job_is_bounded_hosted_and_required(self) -> None:
        jobs = self.load_jobs()
        fuzz = jobs["fuzz"]
        self.assertEqual(fuzz["name"], "Fuzz smoke")
        self.assertEqual(fuzz["runs-on"], "ubuntu-24.04")
        self.assertEqual(fuzz["timeout-minutes"], 10)
        commands = "\n".join(str(step.get("run", "")) for step in fuzz["steps"])
        for value in (
            "-runs=10000",
            "-max_total_time=30",
            "-timeout=2",
            "-rss_limit_mb=1024",
            "--iterations 10000",
            "--seed 355",
        ):
            self.assertIn(value, commands)
        self.assertNotIn("self-hosted", str(fuzz))
        self.assertNotIn("secrets.", str(fuzz))
        self.assertIn("fuzz", jobs["consistency"]["needs"])

    def test_failure_artifacts_are_short_lived_and_optional(self) -> None:
        fuzz = self.load_jobs()["fuzz"]
        upload = next(
            step
            for step in fuzz["steps"]
            if str(step.get("uses", "")).startswith("actions/upload-artifact@")
        )
        self.assertEqual(upload["if"], "failure()")
        self.assertEqual(upload["with"]["retention-days"], 5)
        self.assertEqual(upload["with"]["if-no-files-found"], "ignore")


if __name__ == "__main__":
    unittest.main()
