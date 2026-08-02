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

| Language | Core device API | ODR configuration | FIFO entry count | Self-test response | Linux SPI adapter | Linux I2C adapter | embedded-hal SPI/I2C | Packaging dry run | Physical HIL evidence |
|---|---|---|---|---|---|---|---|---|---|
| C | Yes | Yes | No public method | Yes, bounded measured response | Example only | No | No | Yes, CMake install/export | Raspberry Pi 5 SPI response pass |
| C++ | Yes, C wrapper | Yes | No public method | No public wrapper | User `BusInterface` | User `BusInterface` | Arduino SPI compile fixture | Yes, CMake install/export plus PlatformIO pack | No language-specific physical pass |
| Python | Yes | Yes | Yes, count only | Yes, bounded measured response | Yes, `spidev` | Yes, `smbus2` | No | Yes, sdist/wheel | SPI pass on Raspberry Pi 5; I2C pending |
| Rust | Yes | No | No public method | No public method | No Linux-specific adapter | No Linux-specific adapter | Yes | Yes, `cargo package` | No language-specific physical pass |
| Node.js | Yes | No | No public method | No public method | User `Transport` | User `Transport` | No | Yes, `npm pack` | No language-specific physical pass |
| Go | Yes | No | No public method | No public method | Yes, `adxl355/linuxio` on Linux amd64/arm64 | Yes, `adxl355/linuxio` on Linux amd64/arm64 | No | Module/build and cross-build checks | Raspberry Pi 5 SPI bounded example pass; I2C pending |

“User transport” means the driver exposes a bus contract but does not ship a
Linux device adapter for that language. The repository contains buildable package metadata and verification artifacts, but packages are not published by this repository to PyPI, crates.io, npm, or a Go proxy. Intended distribution names are `adxl355` (PyPI), `adxl355-driver` (crates.io, imported as `adxl355`), and `@oaslananka/adxl355` (npm).

## Implemented and verified

- Shared datasheet-derived register specification and golden test vectors.
- Exact-length transport validation and stable driver-level bus errors.
- Probe-before-use lifecycle and standby-safe range/configuration behavior.
- Raw 20-bit decode, g and m/s² conversion, temperature, and status reads.
- C/Python signed hardware-offset APIs and deterministic raw-LSB calibration helpers.
- C/Python electrostatic self-test response APIs with bounded `DATA_RDY` polling,
  exact register restoration, and optional caller-owned thresholds.
- C++ ODR configuration, an owning exception API, a stack-owned `Status`/`Result<T>` no-exception API, and a hash-locked Arduino Uno PlatformIO compile fixture.
- Mock-based tests in all six languages and a required zero-skip vector gate.
- CI quality gates for sanitizers, lint/type analysis, package smoke tests,
  dependency auditing, CodeQL, race detection, and coverage reporting.
- Grouped dependency updates, immutable workflow action pins, release SBOM and
  high-severity vulnerability gates, and OIDC-backed artifact attestations.
- Manual-only Linux SPI/I2C HIL workflow with sanitized diagnostic evidence.
- Go `adxl355/linuxio` transports for 64-bit Linux spidev and i2c-dev, with explicit descriptor ownership, inspectable operation errors, exact transfer validation, and bounded SPI/I2C examples.

## Explicitly not claimed

Register constants document the chip, but **Register presence does not imply a public API**. `FIFO_DATA`, offset registers, and `SELF_TEST` are represented in
the register map. Full FIFO sample decoding and interrupt configuration are not
implemented consistently as public driver methods. Signed offset programming,
calibration helpers, and electrostatic self-test response measurement are
implemented only in C and Python. The self-test APIs report measured response;
they do not apply undocumented factory acceptance limits or imply parity in the
other languages. The Arduino Uno fixture proves package and exception-free AVR
compilation only; it is not physical Arduino hardware evidence and does not imply
support for boards or frameworks that are not built in CI.

## Hardware validation status

The manual HIL workflow has a successful Raspberry Pi 5 SPI result on `main`
([run 30725059679](https://github.com/oaslananka/adxl355/actions/runs/30725059679)): the ADXL355 returned revision `0x01` and 32 unique samples. The Go
`adxl355/linuxio` SPI example was independently exercised at 1 MHz from exact code
commit `08273bff4611a33f1b88dae6a08c92d5199eab28`. The bounded run reported
`28.0939 °C`, captured 32 nonzero samples with 29 unique XYZ tuples, and an
independent post-run register read confirmed `POWER_CTL=0x01` (standby). The
C/Python self-test implementation was also exercised over SPI on code commit
`12d6206393223439e14b8e36b97e567751e8f8bb`: two independent 64-sample runs
measured approximately 0.342 g X, 0.339 g Y, and 1.419 g Z response, and a third
run passed the Rev.D min/max windows. Every run restored `SELF_TEST`, `RANGE`,
`FILTER`, and `POWER_CTL` exactly. This is feature evidence, not final
release-candidate HIL evidence. I2C physical evidence is still pending. Both SPI
and I2C must be rerun against the final release-candidate commit before
publication. Wiring, runner setup, supported bus settings, diagnostics, and
evidence requirements are documented in
[`docs/hardware-testing.md`](docs/hardware-testing.md).

## Device lifecycle contract

Creating a driver object only stores the transport; it does not verify hardware.
Call `probe()` successfully before stateful hardware operations. Stateless decode
and unit-conversion helpers remain usable without a device.

| Language | Required startup | Pre-probe error |
|---|---|---|
| C | `adxl355_init()` → `adxl355_probe()` | `ADXL355_ERR_STATE` |
| C++ | construct `Device` or `NoexceptDevice` → `probe()` | `InvalidStateError` or `Status::InvalidState` |
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

Installed consumers can select `adxl355::cpp` for the owning exception API or
`adxl355::cpp_noexcept` for the stack-owned `Status`/`Result<T>` API.

The representative Arduino compile fixture uses the repository's hash-locked
PlatformIO toolchain and does not require sensor hardware:

```bash
python3 -m venv .venv-platformio
. .venv-platformio/bin/activate
export PIP_CONFIG_FILE=/dev/null
export PIP_INDEX_URL=https://pypi.org/simple
export PIP_EXTRA_INDEX_URL=
python -m pip install --require-hashes --no-deps --only-binary=:all: \
  -r requirements/python/platformio.txt
PLATFORMIO_CORE_DIR="$PWD/.platformio" pio run -d embedded/platformio/uno
```

This compile proves only the pinned Arduino Uno/AVR package surface. It is not a
physical Arduino HIL result.

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
go mod verify
go test ./...
go test -race ./...
go build ./...
```

The maintained `adxl355/linuxio` package supports Linux amd64 and arm64. Each
transport owns its opened device descriptor until `Close`; repeated `Close` calls
are safe. The I2C `BusHz` field records and validates the externally configured
adapter rate but does not reprogram the kernel adapter clock.

Bounded hardware examples require a connected sensor and never run indefinitely:

```bash
cd go
go run ./examples/linux_spi --bus 0 --device 0 --speed-hz 1000000 --samples 8 --timeout 10s
go run ./examples/linux_i2c --bus 1 --address 0x1D --bus-hz 400000 --samples 8 --timeout 10s
```

Both commands probe identity, read temperature, collect a finite sample count, and
restore standby before closing the descriptor. The SPI command is physically verified on Raspberry Pi 5 at commit `08273bf`; I2C remains pending the dedicated fixture evidence in #41.

## Documentation

- [Generated public API references for all maintained languages](docs/api/README.md)
- [Architecture](docs/architecture.md)
- [Testing and CI](docs/testing.md)
- [Physical hardware validation](docs/hardware-testing.md)
- [Calibration procedure](docs/calibration.md)
- [Versioning and package names](docs/versioning.md)
- [Security and supply-chain policy](docs/security/supply-chain.md)
- [Release verification and publishing](docs/publishing.md)

## License

MIT
