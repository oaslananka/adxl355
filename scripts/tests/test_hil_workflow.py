from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/hil.yml"
PUBLISHING_PATH = REPO_ROOT / "docs/publishing.md"
HARDWARE_GUIDE = REPO_ROOT / "docs/hardware-testing.md"


class HilWorkflowTests(unittest.TestCase):
    def load_workflow(self) -> dict[str, Any]:
        return cast(dict[str, Any], yaml.safe_load(WORKFLOW_PATH.read_text()))

    def load_triggers(self) -> dict[str, Any]:
        workflow = cast(dict[Any, Any], self.load_workflow())
        return cast(dict[str, Any], workflow.get("on", workflow.get(True, {})))

    def test_hil_is_manual_only_and_uses_dedicated_self_hosted_labels(self) -> None:
        workflow = self.load_workflow()
        triggers = self.load_triggers()
        self.assertEqual(set(triggers), {"workflow_dispatch"})
        job = workflow["jobs"]["hil"]
        self.assertEqual(job["runs-on"], ["self-hosted", "linux", "adxl355-hil"])
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertNotIn("pull_request", WORKFLOW_PATH.read_text())
        self.assertNotIn("pull_request_target", WORKFLOW_PATH.read_text())

    def test_hil_job_is_restricted_to_protected_main(self) -> None:
        job = self.load_workflow()["jobs"]["hil"]
        self.assertEqual(job["if"], "${{ github.ref == 'refs/heads/main' }}")

    def test_workflow_supports_spi_and_i2c_with_pinned_inputs(self) -> None:
        triggers = self.load_triggers()
        inputs = triggers["workflow_dispatch"]["inputs"]
        self.assertEqual(inputs["transport"]["options"], ["spi", "i2c"])
        self.assertEqual(inputs["i2c_address"]["options"], ["0x1D", "0x53"])
        text = WORKFLOW_PATH.read_text()
        self.assertIn("--transport spi", text)
        self.assertIn("--transport i2c", text)
        self.assertIn("--spi-speed-hz", text)
        self.assertIn("spidev==3.8", text)
        self.assertIn("smbus2==0.6.1", text)

    def test_actions_are_pinned_and_credentials_are_not_persisted(self) -> None:
        workflow = self.load_workflow()
        steps = workflow["jobs"]["hil"]["steps"]
        action_steps = [step for step in steps if isinstance(step, dict) and "uses" in step]
        for step in action_steps:
            self.assertRegex(str(step["uses"]), r"@[0-9a-f]{40}$")
        checkout = next(step for step in action_steps if str(step["uses"]).startswith("actions/checkout@"))
        self.assertFalse(checkout["with"]["persist-credentials"])
        self.assertNotIn("${{ secrets.", WORKFLOW_PATH.read_text())

    def test_report_is_always_uploaded_with_bounded_retention(self) -> None:
        workflow = self.load_workflow()
        steps = workflow["jobs"]["hil"]["steps"]
        upload = next(step for step in steps if str(step.get("uses", "")).startswith("actions/upload-artifact@"))
        self.assertEqual(upload["if"], "${{ always() }}")
        self.assertEqual(upload["with"]["path"], "artifacts/")
        self.assertEqual(upload["with"]["retention-days"], 30)
        self.assertEqual(upload["with"]["if-no-files-found"], "error")

    def test_public_docs_cover_wiring_diagnostics_and_release_evidence(self) -> None:
        guide = HARDWARE_GUIDE.read_text()
        for text in (
            "2.25 V to 3.6 V",
            "VDDIO",
            "SPI Mode 0",
            "100 kHz to 10 MHz",
            "0x1D",
            "0x53",
            "SCLK/VSSIO",
            "Troubleshooting",
            "device revision",
        ):
            self.assertIn(text, guide)

        publishing = PUBLISHING_PATH.read_text()
        self.assertRegex(publishing, r"(?i)HIL.*30 days")
        self.assertIn("SPI", publishing)
        self.assertIn("I2C", publishing)
        self.assertIn("revision", publishing.lower())

    def test_workflow_has_no_unbounded_shell_interpolation(self) -> None:
        text = WORKFLOW_PATH.read_text()
        unsafe = re.findall(r"run:.*\$\{\{\s*inputs\.", text)
        self.assertEqual(unsafe, [])


if __name__ == "__main__":
    unittest.main()
