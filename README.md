# ADXL355

Cross-platform ADXL355 accelerometer driver for C, C++, Python, Rust, Node.js and Go.

Transport-agnostic, testable, production-ready driver family with shared register specification and consistent API across all languages.

## Status

| Language | Package | Status |
|---|---|---|
| C | CMake library | ✅ MVP |
| C++ | C++17 wrapper | ✅ MVP |
| Python | PyPI package | ✅ MVP |
| Rust | crates.io crate | ✅ MVP |
| Node.js | npm package | ✅ MVP |
| Go | Go module | ✅ MVP |

## Features

- Transport-agnostic design (SPI/I2C abstraction via bus interface)
- C core reference implementation
- Python package with type hints
- Rust, Node.js, Go and C++ packages with shared API design
- Mock transport testing (no hardware required)
- Raw 20-bit acceleration decoding with golden test vectors
- Range-based g and m/s² conversion
- Temperature sensor readout
- FIFO basic support
- Self-test and offset calibration API
- Register map specification and documentation

## Device Lifecycle Contract

Creating a driver object only stores the transport; it does not verify hardware.
Call `probe()` successfully before any stateful hardware operation such as reset,
range or filter configuration, status/data reads, or power-mode changes. Stateless
conversion helpers remain usable without a device.

| Language | Required startup | Pre-probe error |
|---|---|---|
| C | `adxl355_init()` → `adxl355_probe()` | `ADXL355_ERR_STATE` |
| C++ | construct `Device` → `probe()` | `InvalidStateError` |
| Python | construct `ADXL355` → `probe()` | `DeviceStateError` |
| Rust | `Adxl355::new()` → `probe()` | `Error::InvalidState` |
| Node.js | construct `ADXL355` → `await probe()` | `DeviceStateError` |
| Go | `New()` → `Probe()` | `ErrInvalidState` |

The datasheet requires range and filter changes in standby. If measurement mode is
active, the drivers automatically preserve the complete `POWER_CTL` byte, enter
standby, perform the configuration write, and restore the previous mode. No power
write is performed when the device is already in standby. A successful target
write updates cached state before restoration, so the cache continues to match the
hardware even if restoring measurement mode fails.

All transports must return exactly the requested read length. Zero, truncated, and
overlong responses are rejected as bus errors before data is indexed. C and C++
callbacks return the exact transferred byte count on success and a negative value
on failure; other language transports return the complete payload or raise/return
an error.

## Quick Start

### Python

```bash
cd python
pip install -e .
python examples/basic_read.py
```

### C

```bash
cmake -S c -B c/build -DADXL355_BUILD_TESTS=ON -DADXL355_BUILD_EXAMPLES=ON
cmake --build c/build
ctest --test-dir c/build --output-on-failure
./c/build/examples/basic_read
```

### Rust

```bash
cd rust
cargo test
cargo run --example basic
```

### Node.js

```bash
cd node
npm install
npm test
```

### Go

```bash
cd go
go test ./...
```

### C++

```bash
cmake -S cpp -B cpp/build -DADXL355_BUILD_TESTS=ON
cmake --build cpp/build
ctest --test-dir cpp/build --output-on-failure
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for detailed architecture documentation.

## Testing

See [docs/testing.md](docs/testing.md) for testing methodology.

## License

MIT
