#!/usr/bin/env python3
"""
Cross-language test vector verification.

Loads spec/test_vectors.json and verifies the Python implementation
produces correct results. Optionally triggers other language test
suites to confirm consistency.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VECTORS_PATH = REPO_ROOT / "spec" / "test_vectors.json"


def load_vectors():
    with open(VECTORS_PATH) as f:
        return json.load(f)


def verify_python(vectors):
    """Verify Python adxl355 package against shared test vectors."""
    sys.path.insert(0, str(REPO_ROOT / "python" / "src"))
    try:
        from adxl355.device import _decode_raw20, raw_to_g, raw_to_mps2
    except ImportError:
        return 0, 0

    passed = 0
    failed = 0
    tol_g = vectors["acceleration_conversion"]["tolerance_g"]
    tol_m2 = vectors["acceleration_conversion"]["tolerance_mps2"]
    rng_map = {"G2": 0, "G4": 1, "G8": 2}

    for v in vectors["raw_decode"]:
        b = v["bytes"]
        got = _decode_raw20(b[0], b[1], b[2])
        if got == v["raw"]:
            passed += 1
        else:
            print(f"  FAIL decode20/{v['name']}: got {got}, want {v['raw']}")
            failed += 1

    for v in vectors["acceleration_conversion"]["vectors"]:
        rng = rng_map[v["range"]]
        ok_g = abs(raw_to_g(v["raw"], rng) - v["expected_g"]) < tol_g
        ok_m = abs(raw_to_mps2(v["raw"], rng) - v["expected_mps2"]) < tol_m2
        if ok_g:
            passed += 1
        else:
            print(f"  FAIL g/{v['name']}: got {raw_to_g(v['raw'], rng)}, want {v['expected_g']}")
            failed += 1
        if ok_m:
            passed += 1
        else:
            failed += 1

    return passed, failed


def run_test(cmd, cwd, label):
    """Run a test command and report pass/fail."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            print(f"  {label}: PASS")
            return label, 1, 0
        else:
            print(f"  {label}: FAIL (exit {result.returncode})")
            for line in result.stderr.splitlines()[-5:]:
                print(f"    {line}")
            return label, 0, 1
    except FileNotFoundError as e:
        print(f"  {label}: SKIP ({e})")
        return label, 0, 0
    except subprocess.TimeoutExpired:
        print(f"  {label}: TIMEOUT")
        return label, 0, 1


def main():
    vectors = load_vectors()
    n_decode = len(vectors["raw_decode"])
    n_conv = len(vectors["acceleration_conversion"]["vectors"])
    print(f"Spec: {VECTORS_PATH}")
    print(f"Vectors: {n_decode} decode + {n_conv} conversion")
    print()

    total_pass = 0
    total_fail = 0

    print("── Python vector verification ──")
    py_pass, py_fail = verify_python(vectors)
    total_pass += py_pass
    total_fail += py_fail
    print(f"  Python vectors: {py_pass}/{py_pass + py_fail} passed")

    print("\n── Language test suites ──")

    tests = [
        ("pytest",       ["python", "-m", "pytest", "-q", "--tb=short"],                 REPO_ROOT / "python"),
        ("cargo test",   ["cargo", "test", "-q"],                                         REPO_ROOT / "rust"),
        ("go test",      ["go", "test", "./..."],                                         REPO_ROOT / "go"),
        ("vitest",       ["npx", "vitest", "run"],                                        REPO_ROOT / "node"),
        ("ctest (C)",    ["ctest", "--test-dir", "build", "--output-on-failure"],          REPO_ROOT / "c"),
    ]
    c_core_built = (REPO_ROOT / "c" / "build").exists()
    if c_core_built:
        tests.append(("ctest (C++)", ["ctest", "--test-dir", "build", "-C", "Debug", "--output-on-failure"], REPO_ROOT / "cpp"))

    for label, cmd, cwd in tests:
        print(f"\n  {label}...")
        _, p, f = run_test(cmd, cwd, label)
        total_pass += p
        total_fail += f

    print(f"\n{'=' * 50}")
    total = total_pass + total_fail
    print(f"Total: {total_pass}/{total} passed")
    if total_fail:
        print(f"FAILURES: {total_fail}")
        return 1
    print("All checks passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

