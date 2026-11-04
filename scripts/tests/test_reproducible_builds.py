"""Test that reproducibility checks fail closed on changed package bytes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_reproducible_builds import compare


class ReproducibleBuildsTests(unittest.TestCase):
    def test_identical_files_return_digest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a", Path(d) / "b"
            a.mkdir()
            b.mkdir()
            (a / "bundle.tgz").write_bytes(b"test")
            (b / "bundle.tgz").write_bytes(b"test")
            result = compare(a, b)
            self.assertEqual(result[0][0], "bundle.tgz")
            self.assertEqual(len(result[0][1]), 64)

    def test_rejects_missing_artifact_and_different_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a", Path(d) / "b"
            a.mkdir()
            b.mkdir()
            (a / "bundle.tgz").write_bytes(b"test")
            with self.assertRaises(ValueError):
                compare(a, b)
            (b / "bundle.tgz").write_bytes(b"different")
            with self.assertRaisesRegex(ValueError, "NOT REPRODUCIBLE"):
                compare(a, b)

    def test_all_build_modes_dispatch_expected_tools(self) -> None:
        from unittest.mock import patch

        from scripts import check_reproducible_builds as module

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "a" / "out"
            env = {"SOURCE_DATE_EPOCH": "123"}

            def fake_run(command: list[str], **kwargs: object) -> None:
                env = kwargs["env"]
                assert isinstance(env, dict)
                if command[:2] == ["cmake", "--build"]:
                    output = destination.parent / "c-build"
                    output.mkdir(exist_ok=True)
                    (output / "libadxl355.a").write_bytes(b"library")
                if command and command[0] == "uvx":
                    (destination / "package.whl").write_bytes(b"wheel")
                    (destination / "package.tar.gz").write_bytes(b"sdist")
                if command[:2] == ["cargo", "package"]:
                    output = Path(env["CARGO_TARGET_DIR"]) / "package"
                    output.mkdir(parents=True)
                    (output / "test.crate").write_bytes(b"crate")
                if command[:2] == ["npm", "pack"]:
                    (destination / "test.tgz").write_bytes(b"npm")

            with patch.object(module.subprocess, "run", side_effect=fake_run):
                module.build_one("c", destination, env)
                self.assertEqual(
                    (destination / "libadxl355.a").read_bytes(), b"library"
                )
                destination = root / "a" / "python"
                with patch.object(module, "normalize_sdist") as normalizer:
                    module.build_one("python", destination, env)
                    self.assertEqual(
                        (destination / "package.whl").read_bytes(), b"wheel"
                    )
                    normalizer.assert_called_once_with(
                        destination / "package.tar.gz", epoch=123
                    )
                destination = root / "a" / "rust"
                module.build_one("rust", destination, env)
                self.assertEqual((destination / "test.crate").read_bytes(), b"crate")
                with self.assertRaisesRegex(ValueError, "unrecognized component"):
                    module.build_one("unsupported", root / "a" / "unsupported", env)

            # npm's copied source and toolchain symlink are isolated from the checkout.
            node = root / "source" / "node"
            (node / "node_modules" / ".bin").mkdir(parents=True)
            (node / "node_modules" / ".bin" / "tsc").touch()
            (node / "package.json").write_text('{"name":"test"}')
            destination = root / "a" / "npm"
            with patch.object(module, "ROOT", root / "source"):
                with patch.object(module.subprocess, "run", side_effect=fake_run):
                    module.build_one("npm", destination, env)
                    self.assertEqual((destination / "test.tgz").read_bytes(), b"npm")
                    self.assertTrue(
                        (destination.parent / "npm-source/node_modules").is_symlink()
                    )
            with patch.object(module, "ROOT", root / "absent"):
                with self.assertRaisesRegex(ValueError, "npm ci"):
                    module.build_one("npm", root / "a" / "npm-missing", env)

    def test_rejects_ambiguous_crates_and_uses_fail_closed_commands(self) -> None:
        from unittest.mock import patch
        from scripts import check_reproducible_builds as module

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "output"
            with patch.object(module.subprocess, "run") as runner:
                with self.assertRaisesRegex(ValueError, "expected one Rust crate"):
                    module.build_one("rust", destination, {"SOURCE_DATE_EPOCH": "123"})
                runner.assert_called_once()
                self.assertIn("--locked", runner.call_args.args[0])

                self.assertTrue(runner.call_args.kwargs["check"])
                self.assertEqual(
                    runner.call_args.kwargs["stdout"], module.subprocess.DEVNULL
                )

    def test_cli_uses_separate_workdirs_and_checks_both_builds(self) -> None:
        from unittest.mock import patch
        from scripts import check_reproducible_builds as module

        def generate(_component: str, dest: Path, _env: dict[str, str]) -> None:
            dest.mkdir(parents=True)
            (dest / "same.bin").write_bytes(b"deterministic")

        with (
            patch.object(module, "build_one", side_effect=generate) as builder,
            patch.object(module.subprocess, "check_output", return_value="12345\n"),
            patch.object(
                module.sys, "argv", ["check_reproducible_builds", "--components", "c"]
            ),
        ):
            module.main()
            self.assertEqual(builder.call_count, 2)
            self.assertNotEqual(
                builder.call_args_list[0].args[1], builder.call_args_list[1].args[1]
            )
