from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github/workflows"
DEPENDABOT = REPO_ROOT / ".github/dependabot.yml"
CODEQL = WORKFLOWS / "codeql.yml"
RELEASE = WORKFLOWS / "release.yml"
SECURITY_POLICY = REPO_ROOT / "SECURITY.md"
SUPPLY_CHAIN_DOC = REPO_ROOT / "docs/security/supply-chain.md"
SHA_PIN = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def load_yaml(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")))


def workflow_commands(job: dict[str, Any]) -> str:
    return "\n".join(
        str(step.get("run", ""))
        for step in job.get("steps", [])
        if isinstance(step, dict)
    )


class SupplyChainTests(unittest.TestCase):
    def test_dependabot_groups_and_rate_limits_all_ecosystems(self) -> None:
        config = load_yaml(DEPENDABOT)
        updates = config["updates"]
        ecosystems = {entry["package-ecosystem"]: entry for entry in updates}
        self.assertEqual(
            set(ecosystems), {"github-actions", "pip", "cargo", "npm", "gomod"}
        )
        expected_directories = {
            "github-actions": "/",
            "pip": "/python",
            "cargo": "/rust",
            "npm": "/node",
            "gomod": "/go",
        }
        for ecosystem, entry in ecosystems.items():
            self.assertEqual(entry["directory"], expected_directories[ecosystem])
            self.assertEqual(entry["schedule"]["interval"], "weekly")
            self.assertEqual(entry["schedule"]["timezone"], "Europe/Istanbul")
            self.assertLessEqual(entry["open-pull-requests-limit"], 3)
            self.assertIn("dependencies", entry["labels"])
            groups = entry["groups"]
            self.assertEqual(len(groups), 1)
            group = next(iter(groups.values()))
            self.assertEqual(group["patterns"], ["*"])

    def test_codeql_is_primary_sast_for_supported_languages(self) -> None:
        workflow = load_yaml(CODEQL)
        permissions = workflow["permissions"]
        self.assertEqual(permissions["contents"], "read")
        self.assertEqual(permissions["security-events"], "write")
        self.assertEqual(permissions["packages"], "read")
        triggers = workflow["on"]
        self.assertIn("pull_request", triggers)
        self.assertIn("push", triggers)
        self.assertIn("schedule", triggers)

        job = workflow["jobs"]["analyze"]
        matrix = job["strategy"]["matrix"]["include"]
        self.assertEqual(
            {entry["language"] for entry in matrix},
            {"c-cpp", "python", "javascript-typescript", "go"},
        )
        self.assertEqual(
            {entry["build_mode"] for entry in matrix}, {"manual", "none"}
        )
        actions = [
            str(step["uses"])
            for step in job["steps"]
            if isinstance(step, dict) and "uses" in step
        ]
        self.assertTrue(any(action.startswith("github/codeql-action/init@") for action in actions))
        self.assertTrue(
            any(action.startswith("github/codeql-action/analyze@") for action in actions)
        )
        commands = workflow_commands(job)
        self.assertIn("cmake -S c", commands)
        self.assertIn("go build ./...", commands)

    def test_all_external_workflow_actions_are_immutable(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            workflow = load_yaml(path)
            for job_name, job in workflow.get("jobs", {}).items():
                if "uses" in job:
                    reusable = str(job["uses"])
                    if reusable.startswith("./"):
                        continue
                    self.assertRegex(reusable, SHA_PIN, f"{path.name}:{job_name}")
                for step in job.get("steps", []):
                    if not isinstance(step, dict) or "uses" not in step:
                        continue
                    action = str(step["uses"])
                    if action.startswith("./"):
                        continue
                    self.assertRegex(action, SHA_PIN, f"{path.name}:{action}")

    def test_workflows_declare_least_privilege_permissions(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            workflow = load_yaml(path)
            self.assertIn("permissions", workflow, path.name)
            self.assertNotEqual(workflow["permissions"], "write-all", path.name)
            self.assertNotIn("actions", workflow.get("permissions", {}), path.name)

        release = load_yaml(RELEASE)
        bundle = release["jobs"]["release-bundle"]
        self.assertEqual(
            bundle["permissions"],
            {
                "contents": "read",
                "id-token": "write",
                "attestations": "write",
                "artifact-metadata": "write",
            },
        )

    def test_release_bundle_has_sbom_high_severity_gate_and_oidc_attestations(self) -> None:
        release = load_yaml(RELEASE)
        job = release["jobs"]["release-bundle"]
        steps = job["steps"]
        actions = [str(step.get("uses", "")) for step in steps]
        commands = workflow_commands(job)
        rendered = RELEASE.read_text(encoding="utf-8")

        self.assertTrue(any(action.startswith("anchore/sbom-action@") for action in actions))
        scan = next(
            step for step in steps if str(step.get("uses", "")).startswith("anchore/scan-action@")
        )
        self.assertEqual(scan["with"]["severity-cutoff"], "high")
        self.assertTrue(scan["with"]["fail-build"])
        self.assertFalse(scan["with"]["only-fixed"])
        self.assertIn("prepare_sbom_input.py", commands)
        self.assertIn("finalize_release_sbom.py", commands)
        self.assertIn("release.syft.spdx.json", rendered)
        self.assertIn("SBOM_FINALIZE.json", rendered)
        self.assertIn("sbom-input", rendered)
        self.assertIn("SBOM_INPUT.json", rendered)
        self.assertIn("release.spdx.json", rendered)
        self.assertIn("release-vulnerabilities.json", rendered)
        sbom = next(
            step for step in steps if str(step.get("uses", "")).startswith("anchore/sbom-action@")
        )
        self.assertEqual(sbom["with"]["syft-version"], "v1.49.0")
        self.assertEqual(scan["with"]["grype-version"], "v0.116.0")
        self.assertIn("RELEASE_SHA256SUMS", rendered)
        self.assertIn("RELEASE_BUNDLE_SHA256SUMS", rendered)
        self.assertIn("tar -czf", commands)

        attestations = [
            step for step in steps if str(step.get("uses", "")).startswith("actions/attest@")
        ]
        self.assertEqual(len(attestations), 2)
        self.assertTrue(any("sbom-path" in step.get("with", {}) for step in attestations))
        self.assertTrue(any("sbom-path" not in step.get("with", {}) for step in attestations))
        self.assertNotRegex(rendered, r"secrets\.(PYPI|NPM|CARGO|TWINE|REGISTRY).*TOKEN")

    def test_security_policy_has_private_reporting_and_response_targets(self) -> None:
        text = SECURITY_POLICY.read_text(encoding="utf-8")
        self.assertIn(
            "https://github.com/oaslananka/adxl355/security/advisories/new", text
        )
        self.assertIn("48 hours", text)
        self.assertIn("7 calendar days", text)
        self.assertIn("90 days", text)
        self.assertIn("Do not open a public issue", text)

    def test_supply_chain_policy_assigns_one_primary_control_per_category(self) -> None:
        text = SUPPLY_CHAIN_DOC.read_text(encoding="utf-8")
        for phrase in (
            "Dependabot",
            "Dependency Review",
            "CodeQL",
            "Grype",
            "high severity",
            "full commit SHA",
            "GitHub OIDC",
            "trusted publishing",
            "no long-lived registry token",
            "gh attestation verify",
        ):
            self.assertIn(phrase, text)
        self.assertIn("PyPI", text)
        self.assertIn("npm", text)
        self.assertIn("crates.io", text)
        self.assertIn("Go", text)

    def test_publishing_guide_does_not_require_long_lived_tokens(self) -> None:
        text = (REPO_ROOT / "docs/publishing.md").read_text(encoding="utf-8")
        self.assertIn("Trusted Publisher", text)
        self.assertIn("trusted-publishing-only", text)
        self.assertIn("No long-lived registry token", text)
        self.assertNotIn("~/.pypirc", text)
        self.assertNotIn("npm login", text)
        self.assertNotIn("cargo login", text)



if __name__ == "__main__":
    unittest.main()
