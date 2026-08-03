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
        self.assertIn("requirements/python/**", config["ignorePaths"])
        self.assertTrue(config["vulnerabilityAlerts"]["enabled"])
        self.assertEqual(config["vulnerabilityAlerts"]["prCreation"], "immediate")
        major = next(
            rule for rule in config["packageRules"]
            if rule.get("matchUpdateTypes") == ["major"]
        )
        self.assertTrue(major["dependencyDashboardApproval"])
        self.assertFalse(major["automerge"])

    def test_mergify_only_auto_merges_opted_in_renovate_prs(self) -> None:
        config = cast(
            dict[str, Any], yaml.safe_load(MERGIFY.read_text(encoding="utf-8"))
        )
        self.assertEqual(
            config["merge_protections_settings"]["auto_merge_conditions"],
            ["author = renovate[bot]", "label = automerge"],
        )
        protections = config["merge_protections"]
        self.assertEqual(len(protections), 1)
        conditions = protections[0]["success_conditions"]
        self.assertIn("label = automerge", conditions)
        self.assertIn("label != manual-review", conditions)
        self.assertIn("-draft", conditions)
        queue = config["queue_rules"][0]
        self.assertEqual(queue["merge_method"], "squash")
        self.assertIn("author = renovate[bot]", queue["queue_conditions"])
        self.assertIn("label = automerge", queue["queue_conditions"])


if __name__ == "__main__":
    unittest.main()
