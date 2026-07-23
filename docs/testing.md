# Testing

## Overview

This project uses a dual testing strategy:

1. **Hardware-free tests** (default, mandatory)
2. **Hardware-in-the-loop tests** (optional, separated)

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
cd python
pip install -e .[dev]   # installs pytest
```

### Running

```bash
cd python
python -m pytest -v
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
# Node.js >= 18
cd node
npm install
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

## Hardware-in-the-Loop Tests

**Not yet implemented.** Hardware tests will be located in:

```
c/tests/hardware/
python/tests/hardware/
```

Hardware tests require:
- Real ADXL355 breakout board
- SPI (e.g., via spidev on Raspberry Pi)
- Or I2C (e.g., via smbus2)
- Proper wiring as described in `docs/wiring.md`

Hardware tests are excluded from the default test suite. Run them explicitly:
```bash
pytest python/tests/hardware/
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
