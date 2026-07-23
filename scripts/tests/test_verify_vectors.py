from __future__ import annotations

import copy
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from enum import IntEnum
from pathlib import Path
from unittest.mock import patch

from scripts.verify_vectors import (
    CommandSpec,
    LanguageCheck,
    build_language_checks,
    build_range_map,
    load_vectors,
    run_language_check,
    verify_python_vectors,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeRange(IntEnum):
    G2 = 0x11
    G4 = 0x22
    G8 = 0x33


class VerifyVectorsTests(unittest.TestCase):
    def test_range_mapping_uses_real_enum_members(self) -> None:
        mapping = build_range_map(FakeRange)
        self.assertEqual(mapping, {"G2": FakeRange.G2, "G4": FakeRange.G4, "G8": FakeRange.G8})

    def test_command_plan_uses_active_python_and_isolated_builds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adxl355-vector-plan-") as temp:
            build_root = Path(temp)
            checks = build_language_checks(
                repo_root=REPO_ROOT,
                build_root=build_root,
                python_executable="/active/python",
            )

        self.assertEqual(
            [check.label for check in checks],
            ["C", "C++", "Python", "Rust", "Node.js", "Go"],
        )

        by_label = {check.label: check for check in checks}
        c_commands = [command.argv for command in by_label["C"].commands]
        self.assertIn(str(build_root / "c"), c_commands[0])
        self.assertEqual(c_commands[-1][0], "ctest")

        cpp_commands = [command.argv for command in by_label["C++"].commands]
        self.assertIn(
            f"-DADXL355_C_LIB={build_root / 'c' / 'libadxl355.a'}",
            cpp_commands[0],
        )
        self.assertIn(str(build_root / "cpp"), cpp_commands[0])

        python_command = by_label["Python"].commands[0]
        self.assertEqual(python_command.argv[:4], ("/active/python", "-B", "-m", "pytest"))
        self.assertIn(f"cache_dir={build_root / 'pytest-cache'}", python_command.argv)
        self.assertEqual(python_command.cwd, REPO_ROOT / "python")

        rust_command = by_label["Rust"].commands[0]
        self.assertIn(str(build_root / "rust-target"), rust_command.argv)

        node_commands = [command.argv for command in by_label["Node.js"].commands]
        self.assertEqual(by_label["Node.js"].commands[0].cwd, build_root / "node-workspace")
        self.assertEqual(node_commands[0], ("npm", "ci", "--ignore-scripts"))
        self.assertIn(("npm", "run", "build"), node_commands)
        self.assertIn(("npm", "test", "--", "--run"), node_commands)

    def test_ci_mode_turns_a_missing_tool_into_failure(self) -> None:
        check = LanguageCheck(
            "Missing",
            (CommandSpec(("missing-tool", "--version"), REPO_ROOT),),
        )
        with (
            patch("scripts.verify_vectors._executable_available", return_value=False),
            redirect_stdout(io.StringIO()),
        ):
            result = run_language_check(check, ci_mode=True, timeout=1)
        self.assertEqual(result.status, "FAIL")
        self.assertIn("missing required executable", result.detail)

    def test_conversion_divergence_is_reported(self) -> None:
        vectors = copy.deepcopy(load_vectors())
        vectors["acceleration_conversion"]["vectors"][0]["expected_g"] = 1.0
        result = verify_python_vectors(vectors, REPO_ROOT)
        self.assertGreater(result.failed, 0)
        self.assertTrue(any("g/zero_raw_2g" in message for message in result.messages))


if __name__ == "__main__":
    unittest.main()
