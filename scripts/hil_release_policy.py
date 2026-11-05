#!/usr/bin/env python3
"""Classify release changes against the last accepted paired physical HIL baseline.

Normal CI and package verification never require physical hardware. Optional
registry publication fails closed on changed sensor-facing implementation until
new, independently verified paired SPI/I2C evidence advances the baseline.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/hil-validated-baseline.json"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")

# Only confidently software-only changes may inherit previous physical evidence.
# Unknown or new paths default to hardware-impact: this is an allowlist, not a
# filename suffix-based broad exclusion for implementation code.
SAFE_EXACT = frozenset(
    {
        ".bestpractices.json",
        ".gitignore",
        ".mergify.yml",
        "AGENTS.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "README.md",
        "SECURITY.md",
        "VERSION",
        "codecov.yml",
        "renovate.json",
        "sonar-project.properties",
        "python/src/adxl355/_version.py",
        "c/include/adxl355/adxl355_version.h",
    }
)
SAFE_PREFIX = (
    "docs/",
    ".github/ISSUE_TEMPLATE/",
    "scripts/tests/",
    "python/tests/",
    "c/tests/",
    "cpp/tests/",
    "node/test/",
)
SAFE_WORKFLOW_FILES = frozenset(
    {
        "ci.yml",
        "codeql.yml",
        "coverage.yml",
        "dependency-audit.yml",
        "dependency-review.yml",
        "scorecard.yml",
        "sonar.yml",
        "auto-assign.yml",
    }
)


class PolicyError(ValueError):
    """Missing, inconsistent, or unverifiable baseline or commit identity."""


def requires_hil(path: str) -> bool:
    """Conservatively classify every changed tracked path, including removals."""
    if not path or "\\" in path:
        return True
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        return True
    if path in SAFE_EXACT or any(path.startswith(prefix) for prefix in SAFE_PREFIX):
        return False
    if path.startswith(".github/workflows/"):
        return path.removeprefix(".github/workflows/") not in SAFE_WORKFLOW_FILES
    if path.endswith(("/README.md", "/LICENSE")):
        return False
    # Outside the narrow allowlist, unknown files are considered hardware-
    # sensitive. This includes new release/build tooling and HIL test runners.
    return not (path.startswith("go/") and path.endswith("_test.go"))


def load_baseline(path: Path = BASELINE) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError("HIL baseline is missing or malformed") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise PolicyError("unsupported HIL baseline schema")
    sha = data.get("validated_commit")
    if not isinstance(sha, str) or SHA_RE.fullmatch(sha) is None:
        raise PolicyError("HIL baseline commit must be a full immutable SHA")
    tag = data.get("source_release_tag")
    url = data.get("source_release_url")
    runs = data.get("evidence_run_urls")
    if tag is not None:
        # Historical evidence may be anchored to an immutable published tag.
        if runs is not None:
            raise PolicyError("baseline provenance cannot mix tag and workflow runs")
        if not isinstance(tag, str) or not re.fullmatch(
            r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.]+)?", tag
        ):
            raise PolicyError("baseline release tag must be SemVer")
        if url != f"https://github.com/oaslananka/adxl355/releases/tag/{tag}":
            raise PolicyError("baseline release URL must match this repository and tag")
    else:
        # A future HIL acceptance runs on a real candidate commit, not
        # necessarily a published release tag. A tag requirement would prevent
        # future baselines from ever advancing without a circular Git SHA.
        if url is not None or not isinstance(runs, dict) or set(runs) != {"spi", "i2c"}:
            raise PolicyError("both HIL workflow run URLs required for a new baseline")
        for transport in ("spi", "i2c"):
            run = runs[transport]
            if not isinstance(run, str) or not re.fullmatch(
                r"https://github\.com/oaslananka/adxl355/actions/runs/[0-9]+", run
            ):
                raise PolicyError(f"invalid {transport.upper()} evidence run URL")
    evidence = data.get("recorded_evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"spi", "i2c"}:
        raise PolicyError("paired SPI and I2C evidence references are required")
    for mode in ("spi", "i2c"):
        item = evidence[mode]
        if not isinstance(item, dict):
            raise PolicyError("invalid HIL evidence entry")
        digest = item.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise PolicyError(f"missing immutable {mode.upper()} report digest")
        if not isinstance(item.get("asset"), str) or not item["asset"].startswith(
            f"hil-{mode}-"
        ):
            raise PolicyError(f"missing {mode.upper()} release report reference")
    return data


def resolve_commit(revision: str) -> str:
    if revision != "HEAD" and SHA_RE.fullmatch(revision) is None:
        raise PolicyError(
            "only HEAD or an immutable 40-character commit SHA is accepted"
        )
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    sha = result.stdout.strip()
    if result.returncode != 0 or SHA_RE.fullmatch(sha) is None:
        raise PolicyError("release revision is not a valid local commit")
    return sha


def resolve_commit_from_tag(tag: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    sha = result.stdout.strip()
    if result.returncode != 0 or SHA_RE.fullmatch(sha) is None:
        raise PolicyError("recorded baseline tag is missing from the release checkout")
    return sha


def changed_paths(base: str, head: str) -> list[str]:
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, head],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if ancestor.returncode != 0:
        raise PolicyError("recorded HIL baseline is not an ancestor of the release")
    diff = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", base, head],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if diff.returncode != 0:
        raise PolicyError("git diff could not establish changed release paths")
    return sorted(path.decode("utf-8") for path in diff.stdout.split(b"\0") if path)


def assess(base: str, head: str, paths: list[str]) -> dict[str, object]:
    risky = sorted(path for path in paths if requires_hil(path))
    return {
        "baseline_sha": base,
        "release_sha": head,
        "requires_fresh_hil": bool(risky),
        "classification": "hardware-change" if risky else "software-only",
        "changed_paths": len(paths),
        "hardware_sensitive_paths": risky,
        "reuse_scope": (
            "historical paired SPI/I2C evidence on the unchanged hardware contract"
            if not risky
            else "new paired SPI/I2C acceptance required before registry publication"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--head", default="HEAD", help="HEAD or exact release commit SHA"
    )
    parser.add_argument(
        "--output", type=Path, help="write machine-readable JSON report"
    )
    parser.add_argument("--require-software-only", action="store_true")
    args = parser.parse_args()
    try:
        baseline = load_baseline()
        base_sha = resolve_commit(str(baseline["validated_commit"]))
        if baseline.get("source_release_tag") is not None:
            tag_sha = resolve_commit_from_tag(str(baseline["source_release_tag"]))
            if tag_sha != base_sha:
                raise PolicyError(
                    "baseline SHA does not match its immutable release tag"
                )
        head_sha = resolve_commit(args.head)
        report = assess(base_sha, head_sha, changed_paths(base_sha, head_sha))
    except PolicyError as exc:
        parser.error(str(exc))
    encoded = json.dumps(report, indent=2) + "\n"
    print(encoded, end="")
    if args.output is not None:
        args.output.write_text(encoded, encoding="utf-8")
    if args.require_software_only and report["requires_fresh_hil"]:
        print("HIL REQUIRED: sensor-facing changes since last accepted baseline.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
