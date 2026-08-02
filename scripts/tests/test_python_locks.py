from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from scripts.generate_python_locks import (
    LOCK_ROOT,
    LockError,
    parse_input,
    parse_lock,
    verify,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
DEPENDABOT = REPO_ROOT / ".github" / "dependabot.yml"
LOCK_NAMES = {
    "ci-quality",
    "ci-test",
    "consistency",
    "hil-build",
    "hil-i2c",
    "hil-spi",
    "release",
}


class PythonLockTests(unittest.TestCase):
    def test_all_committed_locks_match_exact_review_inputs(self) -> None:
        verify()
        self.assertEqual({path.stem for path in LOCK_ROOT.glob("*.in")}, LOCK_NAMES)
        self.assertEqual({path.stem for path in LOCK_ROOT.glob("*.txt")}, LOCK_NAMES)
        for source in LOCK_ROOT.glob("*.in"):
            self.assertGreater(len(parse_input(source)), 0)
            self.assertGreater(len(parse_lock(source.with_suffix(".txt"))), 0)

    def test_lock_inputs_reject_ranges_urls_indexes_and_duplicates(self) -> None:
        temporary = LOCK_ROOT / "invalid-policy-test.in"
        try:
            for content in (
                "pytest>=8\n",
                "pkg @ https://example.invalid/pkg.whl\n",
                "--extra-index-url https://example.invalid/simple\n",
                "pytest==8.4.2\npytest==8.4.2\n",
            ):
                temporary.write_text(content)
                with self.assertRaises(LockError):
                    parse_input(temporary)
        finally:
            temporary.unlink(missing_ok=True)

    def test_workflow_downloads_use_hash_locks(self) -> None:
        rendered = "\n".join(
            path.read_text() for path in sorted(WORKFLOWS.glob("*.yml"))
        )
        for package in (
            "pytest==",
            "ruff==",
            "mypy==",
            "build==",
            "spidev==",
            "smbus2==",
        ):
            self.assertNotIn(package, rendered)
        lock_installs = re.findall(
            r"python -m pip install(?P<body>.*?)-r requirements/python/[A-Za-z0-9-]+\.txt",
            rendered,
            flags=re.DOTALL,
        )
        self.assertGreaterEqual(len(lock_installs), 5)
        for command in lock_installs:
            self.assertIn("--require-hashes", command)
        self.assertIn("-r ../requirements/python/ci-test.txt", rendered)
        self.assertIn("-r ../requirements/python/ci-quality.txt", rendered)
        self.assertIn("--no-build-isolation --no-deps -e ./python", rendered)
        self.assertIn("--no-deps dist/*.whl", rendered)

    def test_lock_update_path_is_rate_limited(self) -> None:
        data = cast(dict[str, Any], yaml.safe_load(DEPENDABOT.read_text()))
        entry = next(
            update
            for update in data["updates"]
            if update["package-ecosystem"] == "pip"
            and update["directory"] == "/requirements/python"
        )
        self.assertEqual(entry["schedule"]["interval"], "weekly")
        self.assertEqual(entry["open-pull-requests-limit"], 1)
        self.assertEqual(entry["cooldown"], {"default-days": 7})
        self.assertIn("area/security", entry["labels"])

    def test_lock_files_contain_only_pypi_sha256_material(self) -> None:
        for path in sorted(LOCK_ROOT.glob("*.txt")):
            text = path.read_text()
            self.assertNotIn("https://", text)
            self.assertNotIn("--index-url", text)
            self.assertNotIn("--trusted-host", text)
            self.assertRegex(text, r"--hash=sha256:[0-9a-f]{64}")


if __name__ == "__main__":
    unittest.main()
