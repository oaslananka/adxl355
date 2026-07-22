# TODO

## Pre-v0.1.0-alpha.1 Release

### General
- [x] Verify register addresses and bit fields against official ADXL355 Rev.D datasheet
- [x] Confirm temperature conversion formula from datasheet: `25+(raw-1885)/-9.05`
- [x] Verify scale factors (µg/LSB) from datasheet
- [x] Confirm SPI read/write command format: `(reg<<1)|0x01`
- [x] Confirm I2C 7-bit address options: `0x1D` (default), `0x53` (alternate)
- [x] Add CI configuration (GitHub Actions) — spec validation + cross-language consistency
- [x] Add enforceable release gate (required CI, tag/version validation, dry-run artifacts, checksums)
- [x] Fix copyright holder name in LICENSE

### C
- [ ] FIFO read API implementation
- [ ] Interrupt configuration API
- [ ] Self-test API hardware testing
- [ ] Continuous data acquisition example
- [ ] Verify CMake builds on Linux/GCC, ARM GCC, MinGW
- [ ] Add doxygen-style documentation comments to public headers
- [x] Core MVP (probe, read_raw, set_range, power modes, temperature, reset)
- [x] Mock bus testing (47 test assertions passing)
- [x] Linux SPI hardware example (spidev ioctl)

### Python
- [x] spidev adapter implementation
- [x] smbus2 adapter implementation
- [ ] Calibration helper utilities
- [ ] FIFO read support
- [ ] Hardware-in-the-loop test examples
- [ ] Verify ruff and mypy compliance
- [x] Add more device-level integration tests (75 tests passing)
- [x] Core MVP (full Device class, 75 tests passing)
- [x] I2C address constants

### Rust
- [ ] embedded-hal trait integration
- [ ] no_std support verification
- [ ] More comprehensive error types
- [x] Full device API (probe, set_range, read_raw, power modes, temperature, reset)
- [x] Mock transport with tests (31 tests passing — 12 unit + 12 mock_bus + 7 parse_raw)

### Node.js
- [ ] spi-device adapter
- [ ] i2c-bus adapter
- [ ] npm package.json publish configuration
- [x] Full device API (24 tests passing)

### Go
- [ ] spidev/Linux implementation
- [ ] Example with real hardware
- [x] Full device API (21 tests passing)

### C++
- [ ] Arduino/PlatformIO compatibility layer
- [ ] Exception-free error handling option
- [x] Full RAII device class with all C API methods (3 tests passing)

### Documentation
- [ ] Hardware wiring diagrams
- [ ] Raspberry Pi setup guide
- [ ] Hardware test plan with steps
- [ ] Interrupt and FIFO detailed documentation
- [ ] API reference docs for each language
- [ ] Video/images for hardware setup
- [x] Architecture documentation
- [x] Register map documentation
- [x] Testing guide
- [x] Calibration guide
- [x] Publishing guide

### Testing
- [x] Cross-language test vector verification (all languages produce same decode results)
- [ ] Hardware-in-the-loop test procedure
- [ ] Continuous integration with hardware test runner
