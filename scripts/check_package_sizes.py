#!/usr/bin/env python3
"""Record and enforce reviewed package and release-bundle size budgets."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "spec" / "compatibility" / "package-size-budgets.json"


class SizeBudgetError(RuntimeError):
    """Raised when artifact size evidence is missing or exceeds its budget."""


@dataclass(frozen=True)
class ArtifactBudget:
    name: str
    pattern: str
    max_bytes: int
    count: int = 1
    measured_bytes: int | None = None


def load_budgets(family: str) -> list[ArtifactBudget]:
    data = json.loads(DEFAULT_MANIFEST.read_text())
    if data.get("schema_version") != 1:
        raise SizeBudgetError("unsupported size-budget schema")
    try:
        entries = data["families"][family]
    except KeyError as exc:
        raise SizeBudgetError(f"unknown artifact family: {family}") from exc
    return [ArtifactBudget(**entry) for entry in entries]


def is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def trusted_artifact_roots() -> tuple[Path, ...]:
    roots = {REPO_ROOT.resolve(), Path(tempfile.gettempdir()).resolve()}
    runner_temp = os.environ.get("RUNNER_TEMP")
    if runner_temp:
        roots.add(Path(runner_temp).resolve())
    return tuple(sorted(roots, key=str))


def resolve_artifact_directory(path: Path) -> Path:
    candidate = path.expanduser().resolve(strict=True)
    if not candidate.is_dir():
        raise SizeBudgetError(f"artifact path is not a directory: {candidate}")
    if not any(is_within(candidate, root) for root in trusted_artifact_roots()):
        raise SizeBudgetError("artifact directory is outside trusted repository/temporary roots")
    return candidate


def resolve_report_path(path: Path, directory: Path) -> Path:
    candidate = path.expanduser().resolve(strict=False)
    if not is_within(candidate, directory):
        raise SizeBudgetError("report path must remain inside the artifact directory")
    if not candidate.parent.is_dir():
        raise SizeBudgetError(f"report parent directory does not exist: {candidate.parent}")
    return candidate


def evaluate(directory: Path, budgets: list[ArtifactBudget]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for budget in budgets:
        matches = sorted(path for path in directory.rglob(budget.pattern) if path.is_file())
        if len(matches) != budget.count:
            failures.append(
                f"{budget.name}: expected {budget.count} artifact(s) matching "
                f"{budget.pattern!r}, found {len(matches)}"
            )
            continue
        for path in matches:
            size = path.stat().st_size
            result = {
                "name": budget.name,
                "path": str(path.relative_to(directory)),
                "bytes": size,
                "max_bytes": budget.max_bytes,
                "remaining_bytes": budget.max_bytes - size,
                "utilization_percent": round(size * 100 / budget.max_bytes, 2),
                "measured_baseline_bytes": budget.measured_bytes,
                "growth_from_baseline_bytes": (
                    size - budget.measured_bytes if budget.measured_bytes is not None else None
                ),
            }
            results.append(result)
            if size > budget.max_bytes:
                failures.append(
                    f"{budget.name}: {result['path']} is {size} bytes, "
                    f"exceeding the reviewed {budget.max_bytes}-byte budget"
                )
    report = {"status": "failure" if failures else "ok", "artifacts": results}
    if failures:
        report["failures"] = failures
    return report


def measure(directory: Path) -> dict[str, int]:
    return {
        str(path.relative_to(directory)): path.stat().st_size
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--family")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--measure", action="store_true")
    args = parser.parse_args()

    directory = resolve_artifact_directory(args.directory)
    if args.measure:
        report: dict[str, Any] = {"status": "measured", "files": measure(directory)}
    else:
        if not args.family:
            raise SizeBudgetError("--family is required unless --measure is used")
        report = evaluate(directory, load_budgets(args.family))
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        resolve_report_path(args.report, directory).write_text(rendered)
    print(rendered, end="")
    if report["status"] == "failure":
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SizeBudgetError as exc:
        print(f"size budget error: {exc}", file=sys.stderr)
        raise SystemExit(1)
