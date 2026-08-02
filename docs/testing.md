# Testing

## Overview

This project uses a dual testing strategy:

1. **Hardware-free tests** (default, mandatory)
2. **Hardware-in-the-loop tests** (manual-only, separated)

## C Tests

### Prerequisites

```bash
# CMake >= 3.14, C99 compiler
cmake -S c -B c/build -DADXL355_BUILD_TESTS=ON -DADXL355_BUILD_EXAMPLES=ON
cmake --build c/build
ctest --test-dir c/build --output-on-failure
```

### Test Structure

Tests use a minimal custom test framework (no external dependency):
- `tests/test_adxl355.c` — main test suite
- `tests/test_mock_bus.c` / `test_mock_bus.h` — mock transport

### What's Tested

- `decode_raw20` with zero, positive max, negative min, negative one
- `raw_to_g` at 2g/4g/8g ranges
- `raw_to_mps2` conversion
- Null pointer handling in public API
- Probe success and failure
- Register write verification (range writes to correct register)
- Read raw reads 9 bytes
- Status string mapping
- Power mode transitions
- Software reset

## Python Tests

### Prerequisites

```bash
python -m pip install --no-deps -e ./python
python -m pip install pytest ruff mypy
```

### Running

```bash
PYTHONPATH=python/src python -m pytest python/tests -v
```

### What's Tested

- Register/range/power enum correctness
- 20-bit raw decode (5 shared test vectors + parametrized)
- Raw-to-g and raw-to-m/s² conversion
- Mock transport probe (success and failure)
- Set/get range
- Set power mode
- Read raw data via mock
- Temperature readout
- Status register
- Software reset
- Invalid configuration handling

## Rust Tests

### Prerequisites

```bash
# Rust toolchain (rustc, cargo)
```

### Running

```bash
cd rust
cargo test
```

### What's Tested

- 20-bit raw decode vectors
- Raw-to-g conversion
- Raw-to-m/s² conversion
- Device probe via mock transport
- Set range via mock
- Power mode via mock
- Software reset

## Node.js Tests

### Prerequisites

```bash
# Node.js 22, 24, or 26
cd node
npm ci --ignore-scripts
```

### Running

```bash
cd node
npm test
```

### What's Tested

- 20-bit raw decode vectors
- Raw-to-g conversion
- Raw-to-m/s² conversion
- Device probe via mock transport
- Read raw via mock
- Set/get range via mock
- Power mode via mock

## Go Tests

### Prerequisites

```bash
# Go >= 1.21
```

### Running

```bash
cd go
go test ./...
```

### What's Tested

- 5 raw decode vectors
- Raw-to-g conversion
- Raw-to-m/s² conversion
- Device probe via mock transport
- Set/get range via mock
- Read raw via mock

## Cross-Language State Contract Tests

All language suites verify the same device-state behavior:

- pre-probe hardware operations fail without transport access;
- successful probe synchronizes range and leaves the sensor in standby;
- range and supported ODR/filter changes enter and restore measurement mode;
- already-standby configuration avoids redundant power writes;
- target-write failures restore the prior mode without changing cached state; and
- restore failures leave cached configuration consistent with the successful
  hardware write.

## Shared Negative Transport Checklist

`spec/transport_contract.json` defines the required malformed-response cases:

| IDs | Requested bytes | Invalid responses |
|---|---:|---:|
| `TR-1-ZERO`, `TR-1-OVERLONG` | 1 | 0, 2 |
| `TR-2-ZERO`, `TR-2-TRUNCATED` | 2 | 0, 1 |
| `TR-9-ZERO`, `TR-9-TRUNCATED` | 9 | 0, 8 |

C, Python, Rust, Node.js, and Go execute the same behavioral checklist. C++ verifies
the C core mapping through its exception wrapper. Tests additionally inject native
read/write failures and require the stable driver-level bus error rather than an
index exception, panic, or fabricated numeric result.

## Required CI Quality Gates

The primary workflow keeps stable language job names while enforcing more than
unit-test success:

- **C/C++:** warnings as errors, AddressSanitizer, UndefinedBehaviorSanitizer,
  and independent installed-package consumer builds through
  `scripts/smoke_cmake_packages.sh`.
- **Python:** 3.10/3.11/3.12 tests, Ruff, strict mypy for the package and public
  examples, sdist/wheel construction, isolated wheel installation, and example
  smoke execution.
- **Rust:** rustfmt, all-feature and optional-HAL clippy, all-feature and
  no-default-feature tests, documentation tests, and `cargo package` verification.
- **Node.js:** supported Node 22/24/26 tests, TypeScript build/type checking,
  allow-listed npm package contents, and an audit gate at moderate severity.
- **Go:** gofmt, vet, the race detector, and a full coverage profile plus
  function report. Coverage is reported as evidence and is not reduced to an
  arbitrary pass/fail percentage.

Run the native package smoke locally with:

```bash
./scripts/smoke_cmake_packages.sh
```

## Bounded fuzzing

The required `Fuzz smoke` job runs only on a GitHub-hosted Ubuntu runner. It never
uses the Raspberry Pi HIL runner, registry credentials, Doppler configuration, or
production secrets. `Cross-language Consistency` depends on this job, so a fuzz
failure blocks merge through the existing stable required check.

The C target uses Clang libFuzzer with AddressSanitizer and
UndefinedBehaviorSanitizer. It mutates raw decode inputs and exact, zero, partial,
overlong, and failed transport responses across probe, raw XYZ, temperature,
configuration, offset, and reset paths. Pull-request execution is bounded to
10,000 runs or 30 seconds, a two-second per-input timeout, 1,024 MiB RSS, and
1,024-byte inputs.

The Python target uses a fixed seed to mutate raw 20-bit decode, exact-length
transport responses, and release archive member/path classification. It requires
both accepted and rejected paths in every CI run and writes one minimal JSON
reproducer only when an unexpected failure occurs.

Local deterministic commands:

```bash
# Python and release-tool boundary mutations
PYTHONPATH=python/src python scripts/fuzz_python_boundaries.py   --iterations 10000 --seed 355 --artifact-dir artifacts/fuzz

# Clang/libFuzzer target
cmake -S c -B build/fuzz   -DCMAKE_C_COMPILER=clang   -DADXL355_BUILD_FUZZERS=ON   -DADXL355_ENABLE_SANITIZERS=ON   -DADXL355_WARNINGS_AS_ERRORS=ON
cmake --build build/fuzz --target fuzz_adxl355
build/fuzz/fuzz/fuzz_adxl355   -runs=10000 -max_total_time=30 -timeout=2 -rss_limit_mb=1024   -max_len=1024 scripts/fuzz_corpus/raw
```

The small committed corpus contains only reviewed seed inputs. Generated corpora,
coverage profiles, and raw service dumps are not committed. A confirmed crash is
reduced to the smallest useful reproducer, fixed, and preserved as a normal
regression test. CI uploads crash reproducers only on failure and retains them for
five days. Continuous-service enrollment such as OSS-Fuzz remains a separate
maintainer decision after target ownership and signal quality are stable.


### Required status-check lifecycle

The active `main` ruleset requires the repository-owned C, C++, Python, Rust,
Node.js, Go, cross-language consistency, dependency-review, and primary CodeQL
job contexts. Physical HIL and optional third-party SaaS checks are intentionally
not required on every pull request.

A required job must never be renamed or removed in one step. Use this sequence:

1. add the replacement job/context while the old context still exists;
2. verify both contexts complete on a pull request;
3. update the live ruleset to require the replacement context while retaining
   the old context until the workflow change is merged;
4. merge the workflow rename/removal and verify the replacement on both a pull
   request and `main`;
5. remove the retired context from the ruleset and re-read the ruleset through
   the GitHub API.

Before every ruleset mutation, export the current ruleset JSON. If a valid pull
request cannot satisfy the new gate, restore that captured required-check set
and investigate the workflow/context mismatch without bypassing CI.

## Verified native build matrix

The portable C and C++ surfaces are required to build, test, install, and pass
downstream CMake consumer smoke checks on these GitHub-hosted environments:

| Environment | Compiler / architecture | Verification |
|---|---|---|
| Ubuntu 24.04 x64 | GCC | warnings, ASan/UBSan, unit tests, install/export |
| Ubuntu 24.04 x64 | Clang | warnings, ASan/UBSan, unit tests, install/export |
| Ubuntu 24.04 ARM64 | GCC / AArch64 | native unit tests and install/export |
| macOS 15 ARM64 | AppleClang | native unit tests and install/export |
| Windows Server 2025 x64 | MSVC | native unit tests and install/export |

The Linux `spidev` example is built only when `CMAKE_SYSTEM_NAME` is `Linux`.
Platform jobs validate portable library behavior; they are not physical sensor
validation. Only the manual HIL workflow may establish SPI/I2C hardware evidence.
All native platform jobs are dependencies of the required
`Cross-language Consistency` check, so a platform failure blocks merge without
adding unstable matrix-generated ruleset context names.

Run the Windows package consumer smoke locally from PowerShell with:

```powershell
./scripts/smoke_cmake_packages.ps1
```

## Public API compatibility baseline

`spec/compatibility/public-api.json` is generated from the maintained C/C++
headers, Python exports and signatures, Rust public declarations, TypeScript
exports, and Go exported declarations. The required `Cross-language Consistency`
job verifies that every baseline declaration still exists with the same
normalized signature. Additive API entries do not fail the check.

Refresh the baseline only after reviewing the generated diff:

```bash
python scripts/check_public_api.py --write
python scripts/check_public_api.py
```

An additive baseline expansion needs normal tests and documentation. Removing or
changing a baseline declaration requires an intentional baseline edit and a
changed `CHANGELOG.md` entry with an explicit `**Breaking (<surface>):**`
marker. Pull-request CI compares the new baseline with the base commit and rejects
a removal/signature change without that evidence. Do not edit declarations in
the JSON by hand to hide a compatibility failure.

The source-based extractors are compatibility tripwires, not full language ABI
proofs. C/C++ binary ABI, Python behavioral compatibility, Rust SemVer legality,
TypeScript structural typing, and Go module compatibility still require the
language-specific package and consumer tests. New language features that cannot
be normalized safely must document that limitation and add an independent
consumer fixture before baseline coverage is weakened.

## Package and release size budgets

`spec/compatibility/package-size-budgets.json` records reviewed compressed-size
budgets for Python wheel/sdist, Rust crate, npm tarball, Go module archive,
native C/C++ archive, and the aggregate release bundle. Release jobs write a
`SIZE_REPORT.json` beside each package; the final bundle writes
`RELEASE_SIZE_REPORT.json`. Missing, duplicate, or oversized artifacts fail the
release gate.

Measure a local artifact directory without enforcing a budget:

```bash
python scripts/check_package_sizes.py --directory /path/to/artifacts --measure
```

A budget increase requires a clean-checkout before/after measurement, an
explanation of the added package content, and review of whether generated files,
tests, maps, debug symbols, or unrelated assets leaked into the archive. Do not
raise a limit merely to make CI green. Size budgets are regression signals, not
claims about memory use, runtime allocation, or embedded flash/RAM suitability.

## Hardware-in-the-Loop Tests

Physical validation is implemented as the explicit CLI
`scripts/hil_runner.py` and the manual-only `.github/workflows/hil.yml`
workflow. Neither is part of default unit-test discovery or pull-request CI.
The runner supports Linux SPI and I2C fixtures, validates identity, device
revision, reset, range/ODR configuration, temperature, raw XYZ, and a bounded
continuous-read sequence, then writes a sanitized JSON evidence report.

The runner framework and failure paths are covered by ordinary unit tests, but a
real HIL result is valid only when the workflow runs on a connected ADXL355. See
[`docs/hardware-testing.md`](hardware-testing.md) for voltage limits, wiring,
self-hosted runner setup, commands, report contents, and troubleshooting.

```bash
# Explicit local SPI example; requires a physical /dev/spidev0.0 fixture
python scripts/hil_runner.py --transport spi --spi-bus 0 --spi-device 0

# Explicit local I2C example; requires a physical /dev/i2c-1 fixture
python scripts/hil_runner.py --transport i2c --i2c-bus 1 --i2c-address 0x1D
```

## Cross-Language Test Vector Verification

`spec/test_vectors.json` is the authoritative decode and acceleration reference.
The required CI gate runs the same verifier from a clean checkout:

```bash
python scripts/verify_vectors.py --ci
```

The verifier evaluates the Python implementation directly against all golden
values, validates the shared specs, and runs C, C++, Python, Rust, Node.js, and Go.
C/C++ build trees, the Rust target directory, the Node workspace, and the pytest
cache are isolated under a temporary build root. In `--ci` mode, a missing
required toolchain or any skipped language is a failure. A per-language summary
and nonzero process status make conversion or constant divergence visible to the
required `Cross-language Consistency` check.

For local diagnosis, omit `--ci` to allow unavailable toolchains to be reported as
explicit `SKIP` entries, or retain build output with:

```bash
python scripts/verify_vectors.py --build-root /tmp/adxl355-vector-debug
```
