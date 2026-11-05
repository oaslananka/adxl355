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
import sys
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
    """Release cannot reuse the historical HIL baseline safely."""


def requires_hil(path: str) -> bool:
    """Fail closed on all unknown or hardware-impacting file changes."""
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
    return not (path.startswith("go/") and path.endswith("_test.go"))


def _check_provenance(data: dict[str, object]) -> None:
    tag, url, runs = (
        data.get("source_release_tag"),
        data.get("source_release_url"),
        data.get("evidence_run_urls"),
    )
    if tag is not None:
        if runs is not None:
            raise PolicyError(
                "baseline cannot mix release tag and workflow run provenance"
            )
        if (
            not isinstance(tag, str)
            or re.fullmatch(r"v\d+\.\d+\.\d+(?:-[a-z0-9.]+)?", tag, flags=re.ASCII)
            is None
        ):
            raise PolicyError("baseline release tag must be SemVer")
        if url != f"https://github.com/oaslananka/adxl355/releases/tag/{tag}":
            raise PolicyError("baseline release URL must match this repository and tag")
        return
    if url is not None or not isinstance(runs, dict) or set(runs) != {"spi", "i2c"}:
        raise PolicyError("both HIL workflow run URLs required for a new baseline")
    for mode in ("spi", "i2c"):
        link = runs[mode]
        if (
            not isinstance(link, str)
            or re.fullmatch(
                r"https://github\.com/oaslananka/adxl355/actions/runs/\d+",
                link,
                flags=re.ASCII,
            )
            is None
        ):
            raise PolicyError(f"invalid {mode.upper()} evidence run URL")


def _check_evidence(data: dict[str, object]) -> None:
    evidence = data.get("recorded_evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"spi", "i2c"}:
        raise PolicyError("paired SPI and I2C evidence references are required")
    for mode in ("spi", "i2c"):
        entry = evidence[mode]
        if not isinstance(entry, dict):
            raise PolicyError(f"invalid {mode.upper()} HIL evidence record")
        digest = entry.get("sha256")
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[a-f0-9]{64}", digest, flags=re.ASCII) is None
        ):
            raise PolicyError(f"invalid {mode.upper()} HIL evidence SHA-256")
        name = entry.get("asset")
        if (
            not isinstance(name, str)
            or re.fullmatch(rf"hil-{mode}-\d+\.json", name, flags=re.ASCII) is None
        ):
            raise PolicyError(f"invalid {mode.upper()} HIL evidence asset")


def load_baseline(path: Path = BASELINE) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError("HIL baseline is missing or malformed") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise PolicyError("unsupported HIL baseline schema")
    sha = data.get("validated_commit")
    if not isinstance(sha, str) or SHA_RE.fullmatch(sha) is None:
        raise PolicyError("HIL baseline commit must be an immutable full SHA")
    _check_provenance(data)
    _check_evidence(data)
    return data


def paths_from_git_diff(raw: bytes) -> list[str]:
    """Consume only NUL-delimited git diff --name-only -z paths."""
    if raw and not raw.endswith(b"\0"):
        raise PolicyError("git diff input is not complete NUL-delimited output")
    try:
        paths = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    except UnicodeDecodeError as exc:
        raise PolicyError("git diff contains invalid UTF-8") from exc
    if len(paths) != len(set(paths)):
        raise PolicyError("duplicate git diff paths")
    return sorted(paths)


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
            "paired historical HIL evidence on unchanged sensor-facing sources"
            if not risky
            else "fresh verified paired SPI and I2C acceptance required before publication"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metadata",
        action="store_true",
        help="print validated SHA and baseline release tag",
    )
    parser.add_argument("--head", help="exact 40-character release SHA")
    parser.add_argument("--require-software-only", action="store_true")
    args = parser.parse_args()
    try:
        baseline = load_baseline()
        base = str(baseline["validated_commit"])
        if args.metadata:
            print(base)
            print(baseline.get("source_release_tag") or "-")
            return 0
        if not isinstance(args.head, str) or SHA_RE.fullmatch(args.head) is None:
            raise PolicyError("--head must be an immutable full SHA")
        paths = paths_from_git_diff(sys.stdin.buffer.read())
        report = assess(base, args.head, paths)
    except PolicyError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    if args.require_software_only and report["requires_fresh_hil"]:
        print("HIL REQUIRED: sensor-facing changes since last accepted baseline.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
