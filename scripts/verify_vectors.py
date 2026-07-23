#!/usr/bin/env python3
"""Deterministic cross-language verification for shared ADXL355 vectors.

The verifier performs direct Python golden-vector checks and then executes the
maintained C, C++, Python, Rust, Node.js, and Go test suites. C and C++ builds
are created under an isolated temporary directory. In ``--ci`` mode every
required toolchain and language check must run; missing tools are failures.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Type


REPO_ROOT = Path(__file__).resolve().parent.parent
VECTORS_PATH = REPO_ROOT / "spec" / "test_vectors.json"
OUTPUT_TAIL_LINES = 20


@dataclass(frozen=True)
class CommandSpec:
    """One deterministic command in a language verification plan."""

    argv: tuple[str, ...]
    cwd: Path


@dataclass(frozen=True)
class LanguageCheck:
    """Ordered commands required to verify one maintained language."""

    label: str
    commands: tuple[CommandSpec, ...]


@dataclass(frozen=True)
class CheckResult:
    """Final status for one verifier section."""

    label: str
    status: str
    detail: str


@dataclass(frozen=True)
class VectorResult:
    """Assertion-level result for direct Python golden-vector evaluation."""

    passed: int
    failed: int
    messages: tuple[str, ...]


def load_vectors(path: Path = VECTORS_PATH) -> dict[str, Any]:
    """Load the authoritative shared vector document."""

    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level JSON value must be an object")
    return data


def build_range_map(range_type: Type[Any]) -> dict[str, Any]:
    """Map vector range names to the language's real enum members."""

    return {
        "G2": range_type.G2,
        "G4": range_type.G4,
        "G8": range_type.G8,
    }


def build_language_checks(
    repo_root: Path,
    build_root: Path,
    python_executable: str,
) -> tuple[LanguageCheck, ...]:
    """Construct the complete, unit-testable command plan."""

    c_build = build_root / "c"
    cpp_build = build_root / "cpp"
    rust_target = build_root / "rust-target"
    node_workspace = build_root / "node-workspace"
    pytest_cache = build_root / "pytest-cache"
    c_library = c_build / "libadxl355.a"

    return (
        LanguageCheck(
            "C",
            (
                CommandSpec(
                    (
                        "cmake",
                        "-S",
                        str(repo_root / "c"),
                        "-B",
                        str(c_build),
                        "-DADXL355_BUILD_TESTS=ON",
                        "-DADXL355_BUILD_EXAMPLES=OFF",
                    ),
                    repo_root,
                ),
                CommandSpec(("cmake", "--build", str(c_build), "--parallel"), repo_root),
                CommandSpec(
                    ("ctest", "--test-dir", str(c_build), "--output-on-failure"),
                    repo_root,
                ),
            ),
        ),
        LanguageCheck(
            "C++",
            (
                CommandSpec(
                    (
                        "cmake",
                        "-S",
                        str(repo_root / "cpp"),
                        "-B",
                        str(cpp_build),
                        "-DADXL355_BUILD_TESTS=ON",
                        "-DADXL355_BUILD_EXAMPLES=OFF",
                        f"-DADXL355_C_LIB={c_library}",
                    ),
                    repo_root,
                ),
                CommandSpec(("cmake", "--build", str(cpp_build), "--parallel"), repo_root),
                CommandSpec(
                    ("ctest", "--test-dir", str(cpp_build), "--output-on-failure"),
                    repo_root,
                ),
            ),
        ),
        LanguageCheck(
            "Python",
            (
                CommandSpec(
                    (
                        python_executable,
                        "-B",
                        "-m",
                        "pytest",
                        "-q",
                        "-o",
                        f"cache_dir={pytest_cache}",
                    ),
                    repo_root / "python",
                ),
            ),
        ),
        LanguageCheck(
            "Rust",
            (
                CommandSpec(
                    (
                        "cargo",
                        "test",
                        "--target-dir",
                        str(rust_target),
                        "--all-features",
                        "--quiet",
                    ),
                    repo_root / "rust",
                ),
            ),
        ),
        LanguageCheck(
            "Node.js",
            (
                CommandSpec(("npm", "ci", "--ignore-scripts"), node_workspace),
                CommandSpec(("npm", "run", "build"), node_workspace),
                CommandSpec(("npm", "test", "--", "--run"), node_workspace),
            ),
        ),
        LanguageCheck(
            "Go",
            (
                CommandSpec(("go", "test", "./..."), repo_root / "go"),
            ),
        ),
    )


def build_spec_check(repo_root: Path, python_executable: str) -> LanguageCheck:
    """Build the shared-spec preflight executed by the vector gate."""

    return LanguageCheck(
        "Shared spec",
        (
            CommandSpec(
                (python_executable, "spec/validate_spec.py"),
                repo_root,
            ),
            CommandSpec(
                (python_executable, "spec/check_language_consistency.py"),
                repo_root,
            ),
        ),
    )


def verify_python_vectors(
    vectors: Mapping[str, Any],
    repo_root: Path = REPO_ROOT,
) -> VectorResult:
    """Evaluate decode and acceleration vectors with the Python implementation."""

    source_path = str(repo_root / "python" / "src")
    if source_path not in sys.path:
        sys.path.insert(0, source_path)

    try:
        from adxl355.device import (  # type: ignore[import-untyped]
            _decode_raw20,
            raw_to_g,
            raw_to_mps2,
        )
        from adxl355.registers import Range  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - exercised as a CLI failure path
        return VectorResult(0, 1, (f"Python import failed: {exc}",))

    passed = 0
    failed = 0
    messages: list[str] = []
    range_map = build_range_map(Range)

    raw_vectors = vectors.get("raw_decode")
    conversion = vectors.get("acceleration_conversion")
    if not isinstance(raw_vectors, list) or not isinstance(conversion, dict):
        return VectorResult(0, 1, ("Malformed raw_decode or acceleration_conversion data",))

    tolerance_g = float(conversion["tolerance_g"])
    tolerance_mps2 = float(conversion["tolerance_mps2"])

    for vector in raw_vectors:
        byte_values = vector["bytes"]
        actual = _decode_raw20(byte_values[0], byte_values[1], byte_values[2])
        expected = vector["raw"]
        if actual == expected:
            passed += 1
        else:
            failed += 1
            messages.append(
                f"decode20/{vector['name']}: got {actual}, expected {expected}"
            )

    for vector in conversion["vectors"]:
        range_value = range_map[vector["range"]]
        actual_g = raw_to_g(vector["raw"], range_value)
        actual_mps2 = raw_to_mps2(vector["raw"], range_value)
        expected_g = vector["expected_g"]
        expected_mps2 = vector["expected_mps2"]

        if math.isclose(actual_g, expected_g, rel_tol=0.0, abs_tol=tolerance_g):
            passed += 1
        else:
            failed += 1
            messages.append(
                f"g/{vector['name']}: got {actual_g}, expected {expected_g}"
            )

        if math.isclose(
            actual_mps2,
            expected_mps2,
            rel_tol=0.0,
            abs_tol=tolerance_mps2,
        ):
            passed += 1
        else:
            failed += 1
            messages.append(
                f"mps2/{vector['name']}: got {actual_mps2}, expected {expected_mps2}"
            )

    return VectorResult(passed, failed, tuple(messages))


def _executable_available(executable: str) -> bool:
    """Return whether a command executable can be launched."""

    if os.sep in executable or (os.altsep is not None and os.altsep in executable):
        path = Path(executable)
        return path.is_file() and os.access(path, os.X_OK)
    return shutil.which(executable) is not None


def _print_failure_output(result: subprocess.CompletedProcess[str]) -> None:
    """Print a bounded tail of captured command output."""

    combined = [*result.stdout.splitlines(), *result.stderr.splitlines()]
    for line in combined[-OUTPUT_TAIL_LINES:]:
        print(f"      {line}")


def run_language_check(
    check: LanguageCheck,
    *,
    ci_mode: bool,
    timeout: int,
) -> CheckResult:
    """Run every command for one language, stopping on its first failure."""

    for command in check.commands:
        executable = command.argv[0]
        if not _executable_available(executable):
            status = "FAIL" if ci_mode else "SKIP"
            detail = f"missing required executable: {executable}"
            print(f"    {status}: {detail}")
            return CheckResult(check.label, status, detail)

        print(f"    $ {' '.join(command.argv)}")
        try:
            result = subprocess.run(
                command.argv,
                cwd=command.cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            detail = f"command timed out after {timeout}s"
            print(f"    FAIL: {detail}")
            return CheckResult(check.label, "FAIL", detail)
        except OSError as exc:
            status = "FAIL" if ci_mode else "SKIP"
            detail = f"could not execute {executable}: {exc}"
            print(f"    {status}: {detail}")
            return CheckResult(check.label, status, detail)

        if result.returncode != 0:
            detail = f"command exited with {result.returncode}"
            print(f"    FAIL: {detail}")
            _print_failure_output(result)
            return CheckResult(check.label, "FAIL", detail)

    return CheckResult(check.label, "PASS", f"{len(check.commands)} command(s)")


def _print_summary(results: Sequence[CheckResult]) -> None:
    """Print a compact deterministic summary table."""

    print("\n" + "=" * 72)
    print("Cross-language verification summary")
    print("=" * 72)
    width = max(len(result.label) for result in results)
    for result in results:
        print(f"  {result.label:<{width}}  {result.status:<4}  {result.detail}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Treat every missing toolchain or skipped language as a failure.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Per-command timeout in seconds (default: 300).",
    )
    parser.add_argument(
        "--build-root",
        type=Path,
        help="Optional persistent build root; otherwise a temporary directory is used.",
    )
    return parser.parse_args(argv)


def _prepare_isolated_workspaces(build_root: Path) -> None:
    """Copy source-only workspaces without inheriting directory metadata."""

    source_root = REPO_ROOT / "node"
    node_workspace = build_root / "node-workspace"
    if node_workspace.exists():
        shutil.rmtree(node_workspace)
    node_workspace.mkdir(parents=True)

    ignored_directories = {"node_modules", "dist", "coverage"}
    for source in source_root.rglob("*"):
        relative = source.relative_to(source_root)
        if any(part in ignored_directories for part in relative.parts):
            continue
        if source.suffix == ".log":
            continue

        target = node_workspace / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def _run_with_build_root(args: argparse.Namespace, build_root: Path) -> int:
    _prepare_isolated_workspaces(build_root)
    vectors = load_vectors()
    raw_count = len(vectors["raw_decode"])
    conversion_count = len(vectors["acceleration_conversion"]["vectors"])
    print(f"Spec: {VECTORS_PATH}")
    print(f"Vectors: {raw_count} decode + {conversion_count} acceleration conversion")
    print(f"Build root: {build_root}")
    print(f"Mode: {'required CI' if args.ci else 'local (missing tools may skip)'}")

    vector_result = verify_python_vectors(vectors)
    for message in vector_result.messages:
        print(f"  FAIL: {message}")
    results: list[CheckResult] = [
        CheckResult(
            "Python vectors",
            "PASS" if vector_result.failed == 0 else "FAIL",
            f"{vector_result.passed}/{vector_result.passed + vector_result.failed} assertions",
        )
    ]

    checks = (
        build_spec_check(REPO_ROOT, sys.executable),
        *build_language_checks(REPO_ROOT, build_root, sys.executable),
    )
    for check in checks:
        print(f"\n── {check.label} ──")
        results.append(
            run_language_check(check, ci_mode=args.ci, timeout=args.timeout)
        )

    _print_summary(results)
    failures = [result for result in results if result.status == "FAIL"]
    skipped = [result for result in results if result.status == "SKIP"]
    if failures or (args.ci and skipped):
        print(f"\nVerification failed: {len(failures)} failure(s), {len(skipped)} skip(s)")
        return 1
    print(f"\nVerification passed: {len(results) - len(skipped)} check(s), {len(skipped)} skip(s)")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.timeout <= 0:
        print("ERROR: --timeout must be positive", file=sys.stderr)
        return 2

    if args.build_root is not None:
        build_root = args.build_root.resolve()
        build_root.mkdir(parents=True, exist_ok=True)
        return _run_with_build_root(args, build_root)

    with tempfile.TemporaryDirectory(prefix="adxl355-vector-build-") as temp:
        return _run_with_build_root(args, Path(temp))


if __name__ == "__main__":
    raise SystemExit(main())
