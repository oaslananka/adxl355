from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_ASSIGN = REPO_ROOT / ".github/workflows/auto-assign.yml"
GENERATOR = REPO_ROOT / "spec/generate_c_header.py"


def load_generator() -> Any:
    spec = importlib.util.spec_from_file_location("generate_c_header", GENERATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load generate_c_header")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SecurityRegressionTests(unittest.TestCase):
    def test_auto_assign_does_not_use_forgeable_context_as_a_trust_decision(
        self,
    ) -> None:
        workflow = yaml.safe_load(AUTO_ASSIGN.read_text(encoding="utf-8"))
        job = workflow["jobs"]["assign"]
        self.assertNotIn("if", job)
        rendered = AUTO_ASSIGN.read_text(encoding="utf-8")
        self.assertNotIn("github.actor", rendered)
        self.assertNotIn("github.triggering_actor", rendered)

    def test_generator_renders_the_authoritative_register_spec(self) -> None:
        generator = load_generator()
        rendered = generator.generate(REPO_ROOT / "spec/adxl355.registers.yaml")
        self.assertIn("#define ADXL355_REG_DEVID_AD 0x00", rendered)
        self.assertIn("#define ADXL355_STATUS_DATA_RDY", rendered)
        self.assertIn("#define ADXL355_RANGE_2G 0x01", rendered)
        self.assertIn("ADXL355_SPI_READ_CMD", rendered)

    def test_generator_main_supports_stdout_diff_and_repository_output(self) -> None:
        generator = load_generator()

        stdout = io.StringIO()
        with (
            mock.patch.object(generator, "generate", return_value="generated-header"),
            redirect_stdout(stdout),
        ):
            generator.main([])
        self.assertEqual(stdout.getvalue(), "generated-header\n")

        with (
            mock.patch.object(generator, "generate", return_value="generated-header"),
            mock.patch.object(generator, "diff_headers") as diff_headers,
        ):
            generator.main(["--diff"])
        diff_headers.assert_called_once()

        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmp:
            output = Path(tmp) / "registers.h"
            relative_output = output.relative_to(REPO_ROOT)
            stdout = io.StringIO()
            with (
                mock.patch.object(
                    generator, "generate", return_value="generated-header"
                ),
                redirect_stdout(stdout),
            ):
                generator.main(["--output", str(relative_output)])
            self.assertEqual(output.read_text(encoding="utf-8"), "generated-header")
            self.assertIn("Written:", stdout.getvalue())

        with (
            mock.patch.object(generator, "generate", return_value="generated-header"),
            self.assertRaisesRegex(SystemExit, "repository"),
        ):
            generator.main(["--output", "../outside.h"])

    def test_generator_output_must_resolve_inside_repository_and_be_a_header(
        self,
    ) -> None:
        generator = load_generator()
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp).resolve()
            valid = generator.validate_output_path(
                Path("generated/registers.h"), repo_root
            )
            self.assertEqual(valid, repo_root / "generated/registers.h")

            with self.assertRaisesRegex(ValueError, "repository"):
                generator.validate_output_path(Path("../outside.h"), repo_root)
            with self.assertRaisesRegex(ValueError, "header"):
                generator.validate_output_path(
                    Path("generated/registers.txt"), repo_root
                )

    def test_generator_parser_rejects_conflicting_or_missing_output_arguments(
        self,
    ) -> None:
        generator = load_generator()
        with self.assertRaises(SystemExit):
            generator.parse_args(["--diff", "--output", "generated.h"])
        with self.assertRaises(SystemExit):
            generator.parse_args(["--output"])


if __name__ == "__main__":
    unittest.main()
