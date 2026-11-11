from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[2]
RENOVATE = REPO_ROOT / "renovate.json"
MERGIFY = REPO_ROOT / ".mergify.yml"
DEPENDABOT = REPO_ROOT / ".github/dependabot.yml"
RELEASE_WORKFLOW = REPO_ROOT / ".github/workflows/release.yml"


class DependencyAutomationTests(unittest.TestCase):
    def test_renovate_is_the_only_version_update_bot(self) -> None:
        self.assertTrue(RENOVATE.is_file())
        self.assertFalse(DEPENDABOT.exists())

    def test_renovate_covers_supported_ecosystems_and_preserves_custom_locks(self) -> None:
        config = cast(dict[str, Any], json.loads(RENOVATE.read_text(encoding="utf-8")))
        self.assertEqual(
            set(config["enabledManagers"]),
            {"github-actions", "pep621", "cargo", "npm", "gomod"},
        )
        self.assertEqual(config["timezone"], "Europe/Istanbul")
        self.assertEqual(config["minimumReleaseAge"], "7 days")
        # Branch CI runs on pull_request, not bare Renovate branches. With
        # minimumReleaseAge set, not-pending can hold PRs indefinitely.
        self.assertEqual(config["prCreation"], "immediate")
        self.assertEqual(config["internalChecksFilter"], "strict")
        self.assertIn("requirements/python/**", config["ignorePaths"])
        self.assertTrue(config["vulnerabilityAlerts"]["enabled"])
        self.assertEqual(config["vulnerabilityAlerts"]["prCreation"], "immediate")
        major = next(
            rule for rule in config["packageRules"]
            if rule.get("matchUpdateTypes") == ["major"]
        )
        self.assertTrue(major["dependencyDashboardApproval"])
        self.assertFalse(major["automerge"])

    def test_crates_io_auth_action_uses_a_resolvable_semver_comment(self) -> None:
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(
            workflow,
            r"rust-lang/crates-io-auth-action@[0-9a-f]{40} # v\d+\.\d+\.\d+",
        )

    def test_mergify_only_auto_merges_opted_in_renovate_prs(self) -> None:
        config = cast(
            dict[str, Any], yaml.safe_load(MERGIFY.read_text(encoding="utf-8"))
        )
        self.assertEqual(
            config["merge_protections_settings"]["auto_merge_conditions"],
            [
                "author = renovate[bot]",
                "base = main",
                "label = automerge",
                "label != manual-review",
            ],
        )
        protections = config["merge_protections"]
        self.assertEqual(len(protections), 1)
        self.assertEqual(
            protections[0]["if"],
            ["base = main", "author = renovate[bot]", "label = automerge", "label != manual-review"],
        )
        conditions = protections[0]["success_conditions"]
        self.assertIn("label = automerge", conditions)
        self.assertIn("label != manual-review", conditions)
        self.assertIn("-draft", conditions)
        self.assertIn("check-success = Tests", conditions)
        self.assertIn("check-success = Dependency Audit", conditions)
        self.assertNotIn("check-success = renovate/stability-days", conditions)
        self.assertEqual(config["merge_queue"]["max_parallel_checks"], 1)
        queue = config["queue_rules"][0]
        self.assertEqual(queue["merge_method"], "squash")
        self.assertIn("author = renovate[bot]", queue["queue_conditions"])
        self.assertIn("label = automerge", queue["queue_conditions"])
        self.assertIn("label != manual-review", queue["queue_conditions"])
        self.assertIn("-draft", queue["queue_conditions"])
        self.assertNotIn("check-success = renovate/stability-days", queue["queue_conditions"])
        self.assertNotIn("merge_conditions", queue)

    def test_only_low_risk_updates_receive_automerge_label(self) -> None:
        config = cast(dict[str, Any], json.loads(RENOVATE.read_text(encoding="utf-8")))
        self.assertEqual(config["schedule"], ["before 8am every weekday"])
        rules = config["packageRules"]
        stable = next(
            rule for rule in rules
            if set(rule.get("matchManagers", [])) == {"npm", "cargo", "gomod", "pep621"}
            and rule.get("matchCurrentVersion") == "!/^0/"
        )
        self.assertEqual(set(stable["matchManagers"]), {"npm", "cargo", "gomod", "pep621"})
        self.assertEqual(set(stable["matchUpdateTypes"]), {"minor", "patch"})
        self.assertIn("automerge", stable["addLabels"])
        self.assertFalse(stable["automerge"])
        self.assertEqual(set(stable["matchPackageNames"]), {"!typescript", "!setuptools"})
        actions = [rule for rule in rules if rule.get("matchManagers") == ["github-actions"]]
        self.assertEqual(len(actions), 4)
        base, other_actions, artifact_nonpatch, artifact_patch = actions
        names = {
            "actions/upload-artifact",
            "actions/download-artifact",
            "github/codeql-action",
            "SonarSource/sonarqube-scan-action",
        }
        self.assertEqual(base["addLabels"], ["area/ci"])
        self.assertFalse(base["automerge"])
        self.assertEqual(set(other_actions["matchPackageNames"]), {f"!{name}" for name in names})
        self.assertIn("manual-review", other_actions["addLabels"])
        self.assertEqual(set(artifact_nonpatch["matchPackageNames"]), names)
        self.assertNotIn("patch", artifact_nonpatch["matchUpdateTypes"])
        self.assertIn("major", artifact_nonpatch["matchUpdateTypes"])
        self.assertIn("minor", artifact_nonpatch["matchUpdateTypes"])
        self.assertIn("manual-review", artifact_nonpatch["addLabels"])
        self.assertEqual(set(artifact_patch["matchPackageNames"]), names)
        self.assertEqual(artifact_patch["matchUpdateTypes"], ["patch"])
        self.assertEqual(artifact_patch["addLabels"], ["automerge"])
        self.assertFalse(artifact_patch["automerge"])
        node_dev = next(rule for rule in rules if rule.get("matchDepTypes") == ["devDependencies"])
        self.assertEqual(set(node_dev["matchUpdateTypes"]), {"minor", "patch"})
        self.assertEqual(node_dev["matchCurrentVersion"], "!/^0/")
        self.assertEqual(set(node_dev["matchPackageNames"]), {"!typescript"})
        self.assertIn("manual-review", config["lockFileMaintenance"]["addLabels"])
        self.assertNotIn("automerge", config["lockFileMaintenance"]["addLabels"])
        self.assertIn("manual-review", config["vulnerabilityAlerts"]["labels"])
        self.assertNotIn("automerge", config["vulnerabilityAlerts"]["labels"])


if __name__ == "__main__":
    unittest.main()
