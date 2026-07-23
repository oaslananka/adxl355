# ADXL355

Cross-platform ADXL355 accelerometer driver family for C, C++, Python, Rust,
Node.js/TypeScript, and Go.

This repository is an **alpha-stage, hardware-focused driver project**. The
shared register model, conversion behavior, lifecycle contract, automated CI,
package dry runs, and an opt-in physical HIL framework are implemented. A
production maturity claim remains intentionally deferred until recent successful
physical HIL evidence exists for both SPI and I2C on the release-candidate
commit.

## Current status

All six implementations provide the tested core device path: probe, reset,
range and power-mode control, raw XYZ reads, acceleration conversion,
temperature, status, and stateless decode/conversion helpers. Feature coverage
outside that core is intentionally language-specific.

| Language | Core device API | ODR configuration | FIFO entry count | Linux SPI adapter | Linux I2C adapter | embedded-hal SPI/I2C | Packaging dry run | Physical HIL evidence |
|---|---|---|---|---|---|---|---|---|
| C | Yes | Yes | No public method | Example only | No | No | Yes, CMake install/export | Framework available; no recorded pass |
| C++ | Yes, C wrapper | No | No public method | User `BusInterface` | User `BusInterface` | No | Yes, CMake install/export | Framework available; no recorded pass |
| Python | Yes | Yes | Yes, count only | Yes, `spidev` | Yes, `smbus2` | No | Yes, sdist/wheel | HIL runner implementation; no recorded pass |
| Rust | Yes | No | No public method | No Linux-specific adapter | No Linux-specific adapter | Yes | Yes, `cargo package` | Framework available; no recorded pass |
| Node.js | Yes | No | No public method | User `Transport` | User `Transport` | No | Yes, `npm pack` | Framework available; no recorded pass |
| Go | Yes | No | No public method | User `Transport` | User `Transport` | No | Module/build checks | Framework available; no recorded pass |

“User transport” means the driver exposes a bus contract but does not ship a
Linux device adapter for that language. The repository contains buildable package metadata and verification artifacts, but packages are not published by this repository to PyPI, crates.io, npm, or a Go proxy.

## Implemented and verified

- Shared datasheet-derived register specification and golden test vectors.
- Exact-length transport validation and stable driver-level bus errors.
- Probe-before-use lifecycle and standby-safe range/configuration behavior.
- Raw 20-bit decode, g and m/s² conversion, temperature, and status reads.
- Mock-based tests in all six languages and a required zero-skip vector gate.
- CI quality gates for sanitizers, lint/type analysis, package smoke tests,
  dependency auditing, race detection, and coverage reporting.
- Manual-only Linux SPI/I2C HIL workflow with sanitized diagnostic evidence.

## Explicitly not claimed

Register constants document the chip, but **Register presence does not imply a public API**. `FIFO_DATA`, offset registers, and `SELF_TEST` are represented in
the register map; full FIFO sample decoding, hardware offset programming,
self-test control, interrupt configuration, and public calibration helpers are
not implemented consistently as public driver methods. The calibration document
is a procedure, not a callable calibration API.

## Hardware validation status

The HIL runner and self-hosted workflow are implemented and unit-tested, but no
successful physical HIL artifact is currently recorded in this repository.
Wiring, runner setup, supported SPI/I2C settings, diagnostics, and release
evidence requirements are documented in
[`docs/hardware-testing.md`](docs/hardware-testing.md).

## Device lifecycle contract

Creating a driver object only stores the transport; it does not verify hardware.
Call `probe()` successfully before stateful hardware operations. Stateless decode
and unit-conversion helpers remain usable without a device.

| Language | Required startup | Pre-probe error |
|---|---|---|
| C | `adxl355_init()` → `adxl355_probe()` | `ADXL355_ERR_STATE` |
| C++ | construct `Device` → `probe()` | `InvalidStateError` |
| Python | construct `ADXL355` → `probe()` | `DeviceStateError` |
| Rust | `Adxl355::new()` → `probe()` | `Error::InvalidState` |
| Node.js | construct `ADXL355` → `await probe()` | `DeviceStateError` |
| Go | `New()` → `Probe()` | `ErrInvalidState` |

All transports must return exactly the requested read length. Zero, truncated,
and overlong responses are rejected before indexing. C and C++ callbacks return
the exact transferred byte count on success and a negative value on failure.

## Quick start from the repository root

These commands are reproducible from a clean checkout and do not require real
hardware.

### Python

```bash
python -m pip install --no-deps -e ./python
PYTHONPATH=python/src python python/examples/basic_read.py
```

### C

```bash
cmake -S c -B build/c -DADXL355_BUILD_TESTS=ON -DADXL355_BUILD_EXAMPLES=ON
cmake --build build/c
ctest --test-dir build/c --output-on-failure
./build/c/examples/basic_read
```

### C++

```bash
cmake -S c -B build/c-core -DADXL355_BUILD_TESTS=OFF -DADXL355_BUILD_EXAMPLES=OFF
cmake --build build/c-core
cmake -S cpp -B build/cpp -DADXL355_BUILD_TESTS=ON -DADXL355_BUILD_EXAMPLES=ON -DCMAKE_PREFIX_PATH="$PWD/build/c-core"
cmake --build build/cpp
ctest --test-dir build/cpp --output-on-failure
```

### Rust

```bash
cargo test --manifest-path rust/Cargo.toml --all-features
cargo run --manifest-path rust/Cargo.toml --example basic
```

### Node.js

```bash
cd node
npm ci --ignore-scripts
npm run build
npm test
```

### Go

```bash
cd go
go test ./...
```

## Documentation

- [Architecture](docs/architecture.md)
- [Testing and CI](docs/testing.md)
- [Physical hardware validation](docs/hardware-testing.md)
- [Calibration procedure](docs/calibration.md)
- [Release verification and publishing](docs/publishing.md)

## License

MIT
