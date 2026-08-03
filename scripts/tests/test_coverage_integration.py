from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/coverage.yml"
CONFIG = REPO_ROOT / "codecov.yml"


class CoverageIntegrationTests(unittest.TestCase):
    def test_codecov_uses_oidc_and_an_immutable_action(self) -> None:
        workflow = cast(dict[str, Any], yaml.safe_load(WORKFLOW.read_text()))
        job = workflow["jobs"]["go-coverage"]
        self.assertEqual(job["permissions"], {"contents": "read", "id-token": "write"})
        upload = next(
            step for step in job["steps"]
            if str(step.get("uses", "")).startswith("codecov/codecov-action@")
        )
        self.assertRegex(upload["uses"], r"^codecov/codecov-action@[0-9a-f]{40}$")
        self.assertTrue(upload["with"]["use_oidc"])
        self.assertTrue(upload["with"]["fail_ci_if_error"])
        self.assertEqual(upload["with"]["files"], "go/coverage.out")
        self.assertEqual(upload["with"]["flags"], "go")
        self.assertNotIn("CODECOV_TOKEN", WORKFLOW.read_text())
        self.assertNotIn("verbose", upload["with"])

    def test_initial_codecov_statuses_are_informational(self) -> None:
        config = cast(dict[str, Any], yaml.safe_load(CONFIG.read_text()))
        statuses = config["coverage"]["status"]
        self.assertTrue(statuses["project"]["default"]["informational"])
        self.assertTrue(statuses["patch"]["default"]["informational"])
        self.assertEqual(statuses["patch"]["default"]["target"], "80%")
        self.assertEqual(config["flags"]["go"]["paths"], ["go/"])


if __name__ == "__main__":
    unittest.main()
