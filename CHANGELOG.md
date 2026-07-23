# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-alpha.1] - Unreleased

### Fixed

- **Breaking (all languages)**: Corrected `Range` enum values from `0/1/2` to `0x01/0x02/0x03` per datasheet Rev.D Table 42
- **Breaking (all languages)**: Corrected `PowerMode` values — `Standby=1/Measurement=0` per datasheet Rev.D Table 43 (was inverted)
- **Breaking (all languages)**: Corrected `STATUS` register bit positions per datasheet Rev.D Table 27 (DATA_RDY=0, FIFO_FULL=1, FIFO_OVR=2, ACTIVITY=3, NVM_BUSY=4)
- **Breaking (all languages)**: Corrected `FILTER` register — ODR in bits 3:0, HPF in bits 6:4 per datasheet Rev.D Table 38 (ODR mask was 0xF0, now 0x0F)
- **Breaking (all languages)**: Corrected temperature conversion formula from `raw/100+25` to `25+(raw-1885)/-9.05` per datasheet Rev.D
- **Breaking (all languages)**: Required a successful probe before stateful hardware operations and added explicit state errors; range and supported ODR/filter writes now use a bounded standby/configure/restore transaction that preserves the complete `POWER_CTL` value and cache consistency on failures
- Masked reserved `TEMP2[7:4]` bits, added exact-length validation, and implemented coherent temperature sampling with bounded high-byte rollover retries across C, Python, Rust, Node.js, and Go
- **Breaking (Python/Rust SPI adapters)**: Corrected command framing to read `(reg << 1) | 0x01` and write `reg << 1`, kept command and payload in one chip-select transaction, and documented SPI Mode 0 (`CPOL=0`, `CPHA=0`)
- Corrected `RANGE` register writes in every implementation, including the C reference driver, to preserve unrelated bits (`INT_POL`, `I2C_HS`) and update cached state only after successful writes
- Corrected the Linux spidev example to perform sustained multi-byte reads in one command-plus-payload transaction and discard the command-phase receive byte
- Updated all test assertions to match new enum values and temperature formula
- Marked all datasheet-derived values with traceable datasheet section references

### Added

#### Stage 1: Datasheet correctness (initial addition)
- Initial C driver with full API (init, probe, reset, range, power mode, raw/g/mps² read, temperature)
- Mock bus C test infrastructure with register map simulation
- C CMake build system with test/example options
- Python package with type-safe API and mock transport
- Python pytest test suite for register decode, raw conversion, and device flows
- Shared register specification in YAML
- Shared test vectors (JSON) for 20-bit raw decode across all languages
- Rust crate skeleton with raw decode and conversion functions
- Node.js/TypeScript package skeleton with ES module support
- Go module skeleton with interface-based transport abstraction
- C++ RAII wrapper skeleton on top of C core
- Architecture, register map, testing, calibration, and publishing docs
- Root project metadata (README, LICENSE, CHANGELOG, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT)
- Pre-commit configuration with formatting hooks
- .editorconfig and .clang-format for consistent style

#### Stage 2: Spec infrastructure
- `STATUS` register bit position constants (all languages)
- `FILTER` register mask constants: `ODR_MASK`, `HPF_MASK` (all languages)
- `SPI` read/write command helpers (C, Rust, Node/TS, Go)
- `I2C` address constants (default `0x1D`, alternate `0x53`) per datasheet Rev.D Table 8
- `register-map.md` with complete register documentation
- `spec/validate_spec.py` — structural YAML spec validator (register overlap detection, cross-reference validation)
- `spec/generate_c_header.py` — C header generator from spec YAML with `--diff` mode for safe regeneration
- `spec/check_language_consistency.py` — cross-language consistency checker

#### Stage 3: Test expansions
- Python: +36 tests (75 total) — temperature edge cases, FIFO entries, activity status, bus errors, I2C constants, filter ODR/HPF preservation, half-scale boundary decode, reset verification
- C: +30 test assertions (47 total) — temperature raw/celsius, status register, FIFO entries, filter ODR/HPF preservation, bus error handling, half-scale boundary decode
- Rust: +9 tests (31 total) — temperature raw/celsius nominal+50°C, status register (all clear/data ready/FIFO full), filter default ODR/HPF, half-scale decode
- Node/TS: +16 tests (24 total) — temperature raw/celsius nominal+50°C, status register, filter default, reset call logging, half-scale decode
- Go: +10 tests (21 total) — temperature raw/celsius nominal+50°C, status register, filter default, reset code verification, half-scale decode

#### Stage 4: CI release gates
- `.github/workflows/release.yml` — enforceable release gate that reuses required CI, validates tag/commit/version consistency, builds Python/Rust/npm/Go/C/C++ dry-run artifacts from one SHA, and uploads per-package plus aggregate SHA-256 checksums

#### Stage 5: Hardware adapters
- `python/src/adxl355/adapters/smbus2.py` — Linux I2C transport (smbus2)
- `c/examples/linux_spi.c` — Linux SPI hardware example using spidev ioctl

### Changed

- `spec/adxl355.registers.yaml` — complete rewrite with datasheet Rev.D references
- `spec/adxl355.constants.yaml` — corrected all constants with datasheet citations
- All C, Python, Rust, Node/TS, and Go register headers — synchronized with corrected spec YAML
- CI workflow now runs spec validation (`validate_spec.py`) and cross-language consistency check (`check_language_consistency.py`) on every push/PR
- `python/src/adxl355/device.py`: Added `read_fifo_entries()`, `read_activity_status()`, I2C address constants
- `python/tests/`: Expanded from 39→75 tests covering temperature, FIFO, bus errors, filter, boundary decode
- `c/tests/test_adxl355.c`: Expanded from 17→47 test assertions covering temperature, status, FIFO, filter, bus errors
- `rust/tests/mock_bus.rs`: Expanded from 3→12 tests covering temperature, status, filter, half-scale decode
- `rust/tests/parse_raw.rs`: Expanded from 5→7 tests with half-scale boundary cases
- `node/test/deviceMock.test.ts`: Expanded from 5→14 tests
- `node/test/parseRaw.test.ts`: Expanded from 5→10 tests
- `go/adxl355/device_test.go`: Expanded from 6→15 tests
- `go/adxl355/parse_raw_test.go`: Expanded from 4→6 tests
- `c/examples/CMakeLists.txt`: Added `linux_spi` target
