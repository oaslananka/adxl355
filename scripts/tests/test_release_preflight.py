from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.release_preflight import (
    collect_version_sources,
    parse_release_tag,
    validate_git_state,
    validate_versions,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_FILES = (
    "python/pyproject.toml",
    "python/src/adxl355/_version.py",
    "rust/Cargo.toml",
    "rust/Cargo.lock",
    "node/package.json",
    "node/package-lock.json",
    "c/CMakeLists.txt",
    "cpp/CMakeLists.txt",
    "c/include/adxl355/adxl355_version.h",
    "spec/test_vectors.json",
    "go/go.mod",
)


class ReleasePreflightTests(unittest.TestCase):
    def make_fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="adxl355-release-preflight-"))
        self.addCleanup(shutil.rmtree, temp)
        for relative in FIXTURE_FILES:
            source = REPO_ROOT / relative
            target = temp / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return temp

    def test_parse_release_tag_accepts_semver(self) -> None:
        parsed = parse_release_tag("v1.2.3-alpha.4")
        self.assertEqual(parsed.full, "1.2.3-alpha.4")
        self.assertEqual(parsed.core, "1.2.3")

    def test_parse_release_tag_rejects_numeric_prerelease_leading_zero(self) -> None:
        with self.assertRaisesRegex(ValueError, "leading zeros"):
            parse_release_tag("v1.2.3-01")

    def test_current_fixture_matches_release_version(self) -> None:
        root = self.make_fixture()
        release = parse_release_tag("v0.1.0")
        errors = validate_versions(release, collect_version_sources(root))
        self.assertEqual(errors, [])

    def test_intentional_node_version_mismatch_fails(self) -> None:
        root = self.make_fixture()
        package_path = root / "node/package.json"
        package = json.loads(package_path.read_text())
        package["version"] = "0.1.1"
        package_path.write_text(json.dumps(package, indent=2) + "\n")

        release = parse_release_tag("v0.1.0")
        errors = validate_versions(release, collect_version_sources(root))

        self.assertTrue(any("node/package.json" in error and "0.1.1" in error for error in errors))

    def test_prerelease_requires_full_version_sources_to_match(self) -> None:
        root = self.make_fixture()
        release = parse_release_tag("v0.1.0-alpha.2")
        errors = validate_versions(release, collect_version_sources(root))
        self.assertTrue(any("python/pyproject.toml" in error for error in errors))
        self.assertFalse(any("c/CMakeLists.txt" in error for error in errors))

    def make_git_repository(self) -> tuple[Path, str]:
        root = Path(tempfile.mkdtemp(prefix="adxl355-release-git-"))
        self.addCleanup(shutil.rmtree, root)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Release Test"], cwd=root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "release-test@example.invalid"],
            cwd=root,
            check=True,
        )
        (root / "tracked.txt").write_text("release fixture\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=root, check=True)
        subprocess.run(["git", "tag", "v0.1.0"], cwd=root, check=True)
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return root, sha

    def test_tag_must_point_to_release_commit(self) -> None:
        root, tagged_sha = self.make_git_repository()
        self.assertEqual(validate_git_state(root, "v0.1.0", tagged_sha), tagged_sha)

        (root / "tracked.txt").write_text("second commit\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=root, check=True)
        current_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        with self.assertRaisesRegex(ValueError, "tag .* points to"):
            validate_git_state(root, "v0.1.0", current_sha)

    def test_dirty_release_tree_is_rejected(self) -> None:
        root, tagged_sha = self.make_git_repository()
        (root / "untracked.txt").write_text("dirty\n")
        with self.assertRaisesRegex(ValueError, "source tree is dirty"):
            validate_git_state(root, "v0.1.0", tagged_sha)


if __name__ == "__main__":
    unittest.main()
