from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, cast

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = REPO_ROOT / ".github/workflows/release.yml"
CI_WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"
PACKAGE_JOBS = {
    "python-package",
    "rust-package",
    "node-package",
    "go-package",
    "c-cpp-package",
}


class ReleaseWorkflowTests(unittest.TestCase):
    def load_release(self) -> dict[str, Any]:
        return cast(dict[str, Any], yaml.safe_load(RELEASE_WORKFLOW.read_text()))

    def test_placeholder_gate_is_removed(self) -> None:
        text = RELEASE_WORKFLOW.read_text()
        self.assertNotIn("assumes CI was green", text)
        self.assertNotIn("In a real workflow", text)

    def test_release_reuses_ci_workflow(self) -> None:
        release = self.load_release()
        self.assertEqual(release["jobs"]["ci"]["uses"], "./.github/workflows/ci.yml")
        ci = yaml.safe_load(CI_WORKFLOW.read_text())
        triggers = ci.get("on", ci.get(True, {}))
        self.assertIn("workflow_call", triggers)

    def test_every_package_job_requires_ci_and_preflight(self) -> None:
        jobs = self.load_release()["jobs"]
        for job_name in PACKAGE_JOBS:
            self.assertEqual(set(jobs[job_name]["needs"]), {"ci", "preflight"})

    def test_release_has_job_scoped_least_privilege_and_bundle_artifact(self) -> None:
        release = self.load_release()
        jobs = release["jobs"]
        self.assertNotIn("permissions", release)
        for job_name in {"ci", "preflight", *PACKAGE_JOBS}:
            self.assertEqual(jobs[job_name]["permissions"], {"contents": "read"})
        self.assertEqual(jobs["release-bundle"]["permissions"], {})
        self.assertIn("release-bundle", jobs)
        self.assertIn("actions/upload-artifact", RELEASE_WORKFLOW.read_text())

    def test_dependency_installation_is_pinned_and_script_safe(self) -> None:
        text = RELEASE_WORKFLOW.read_text()
        self.assertIn("build==1.5.0", text)
        self.assertIn("npm ci --ignore-scripts", text)
        self.assertNotIn("--github-output", text)

    def test_package_jobs_checkout_preflight_sha_and_upload_checksums(self) -> None:
        jobs = self.load_release()["jobs"]
        workflow_text = RELEASE_WORKFLOW.read_text()
        self.assertGreaterEqual(workflow_text.count("sha256sum"), len(PACKAGE_JOBS) + 1)
        for job_name in PACKAGE_JOBS:
            checkout_steps = [
                step
                for step in jobs[job_name]["steps"]
                if step.get("uses", "").startswith("actions/checkout")
            ]
            self.assertEqual(len(checkout_steps), 1)
            self.assertEqual(
                checkout_steps[0]["with"]["ref"],
                "${{ needs.preflight.outputs.release_sha }}",
            )
            self.assertTrue(
                any(
                    step.get("uses", "").startswith("actions/upload-artifact")
                    for step in jobs[job_name]["steps"]
                )
            )


if __name__ == "__main__":
    unittest.main()
