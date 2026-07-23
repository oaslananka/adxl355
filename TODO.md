# TODO

## v0.1.0-alpha.2 readiness

### General
- [x] Verify register addresses and bit fields against official ADXL355 Rev.D datasheet
- [x] Confirm temperature conversion formula from datasheet: `25+(raw-1885)/-9.05`
- [x] Verify scale factors (µg/LSB) from datasheet
- [x] Confirm SPI read/write command format: `(reg<<1)|0x01`
- [x] Confirm I2C 7-bit address options: `0x1D` (default), `0x53` (alternate)
- [x] Add CI configuration (GitHub Actions) — spec validation + cross-language consistency
- [x] Add enforceable release gate (canonical version mapping, artifact inspection/smoke, checksums)
- [x] Canonical multi-ecosystem version and package-name strategy
- [x] Add required language quality gates (lint/type, sanitizers, package smoke, audit, race, coverage)
- [x] Group and rate-limit dependency updates across all maintained ecosystems
- [x] Add primary CodeQL SAST for supported repository languages
- [x] Pin external GitHub Actions to immutable commit SHAs
- [x] Add release SBOM, high-severity vulnerability gate, checksums, and OIDC attestations
- [x] Enable vulnerability alerts, Dependabot security updates, push protection, and private reporting
- [x] Fix copyright holder name in LICENSE

### C
- [ ] FIFO read API implementation
- [ ] Interrupt configuration API
- [ ] Self-test API hardware testing
- [ ] Continuous data acquisition example
- [ ] Verify CMake builds on Linux/GCC, ARM GCC, MinGW
- [ ] Add doxygen-style documentation comments to public headers
- [x] Core MVP (probe, read_raw, set_range, power modes, temperature, reset)
- [x] Mock bus and transport-contract regression testing
- [x] Linux SPI hardware example (spidev ioctl)

### Python
- [x] spidev adapter implementation
- [x] smbus2 adapter implementation
- [ ] Calibration helper utilities
- [x] FIFO entry-count helper
- [ ] FIFO sample-data decode/read API
- [x] Hardware-in-the-loop runner and failure-path tests
- [x] Verify Ruff and strict mypy compliance
- [x] Device-level lifecycle, transport, temperature, and configuration tests
- [x] Core device API (probe, range, power, ODR, raw/converted reads, temperature, status)
- [x] I2C address constants

### Rust
- [x] embedded-hal trait integration
- [x] no_std support verification
- [ ] More comprehensive error types
- [x] Full device API (probe, set_range, read_raw, power modes, temperature, reset)
- [x] Mock transport and shared-vector tests

### Node.js
- [ ] spi-device adapter
- [ ] i2c-bus adapter
- [x] npm package.json publish configuration
- [ ] Reassess the documented `@emnapi/runtime@1.11.1` dev-only risk by 2026-10-23
- [x] Core device API with transport-contract tests

### Go
- [ ] spidev/Linux implementation
- [ ] Example with real hardware
- [x] Core device API with race-tested transport-contract coverage

### C++
- [ ] Arduino/PlatformIO compatibility layer
- [ ] Exception-free error handling option
- [x] RAII wrapper for the implemented C++ core surface
- [ ] Add C++ ODR configuration wrapper

### Documentation
- [x] Hardware wiring tables and voltage/bus assumptions
- [x] Linux self-hosted SPI/I2C runner setup guide
- [x] Hardware test plan with identity/reset/configuration/data steps
- [ ] Interrupt and FIFO detailed documentation
- [ ] API reference docs for each language
- [ ] Video/images for hardware setup
- [x] Architecture documentation
- [x] Register map documentation
- [x] Testing guide
- [x] Calibration procedure (no public calibration helper yet)
- [x] Publishing guide

### Testing
- [x] Required clean-checkout vector gate (`scripts/verify_vectors.py --ci`) for C, C++, Python, Rust, Node.js, and Go with zero permitted skips
- [x] Hardware-in-the-loop test procedure
- [x] Manual-only self-hosted HIL workflow
- [ ] Publish a successful physical SPI and I2C HIL artifact for the release candidate
