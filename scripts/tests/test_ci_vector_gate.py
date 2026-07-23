from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"


class VectorGateWorkflowTests(unittest.TestCase):
    def load_ci(self) -> dict[str, Any]:
        return cast(dict[str, Any], yaml.safe_load(CI_WORKFLOW.read_text()))

    def test_required_consistency_job_runs_strict_vector_verifier(self) -> None:
        ci = self.load_ci()
        job = ci["jobs"]["consistency"]
        self.assertEqual(set(job["needs"]), {"c", "cpp", "python", "rust", "node", "go"})
        commands = "\n".join(
            step.get("run", "") for step in job["steps"] if isinstance(step, dict)
        )
        self.assertIn("python scripts/verify_vectors.py --ci", commands)

    def test_vector_gate_installs_all_required_toolchains(self) -> None:
        job = self.load_ci()["jobs"]["consistency"]
        uses = [step.get("uses", "") for step in job["steps"] if isinstance(step, dict)]
        for action in (
            "actions/setup-python",
            "actions/setup-node",
            "actions/setup-go",
            "dtolnay/rust-toolchain",
        ):
            self.assertTrue(any(value.startswith(action) for value in uses), action)
        commands = "\n".join(
            step.get("run", "") for step in job["steps"] if isinstance(step, dict)
        )
        self.assertIn("cmake", commands)
        self.assertIn("g++", commands)


if __name__ == "__main__":
    unittest.main()
