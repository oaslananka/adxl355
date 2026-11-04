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
