# Architecture

## Why C Core?

The C implementation is the reference for all other language ports:

- C is the *lingua franca* of embedded systems. An ADXL355 driver in C can be used on any microcontroller with a C compiler, from 8-bit MCUs to ARM Cortex devices.
- C has no runtime dependency. No VM, no interpreter, no package manager required on the target.
- C functions can be called directly from C++, Python (via ctypes/cffi), Rust (via FFI), and other languages.
- The C API sets the behavioral contract: all other languages must produce identical results from the same register values.

Other languages do **not** bind to C via FFI by default (though they could). Instead, each language reimplements the same register logic, same decode formulas, and same test vectors. This keeps each package self-contained and idiomatic.

## Transport Abstraction

The ADXL355 driver does **not** know about SPI or I2C details. Instead, it operates through a minimal bus interface:

```
┌──────────┐     read_register(write_register(delay_ms      ┌──────────────┐
│ ADXL355  │ ──▶                                ──────────▶ │ SPI / I2C    │
│ Driver   │ ◀──                                ◀────────── │ (hardware)   │
└──────────┘     data bytes / error codes                   └──────────────┘
```

### C: Function pointer table

```c
typedef struct {
    int (*read)(void *ctx, uint8_t reg, uint8_t *data, size_t len);
    int (*write)(void *ctx, uint8_t reg, const uint8_t *data, size_t len);
    void (*delay_ms)(void *ctx, uint32_t ms);
    void *ctx;
} adxl355_bus_t;
```

### Python: Protocol / ABC

```python
class Transport(Protocol):
    def read_register(self, reg: int, length: int = 1) -> bytes: ...
    def write_register(self, reg: int, data: bytes) -> None: ...
    def delay_ms(self, ms: int) -> None: ...
```

### Rust: Trait

```rust
pub trait Transport {
    fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Error>;
    fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Error>;
    fn delay_ms(&mut self, ms: u32);
}
```

### Go: Interface

```go
type Transport interface {
    ReadRegister(reg byte, length int) ([]byte, error)
    WriteRegister(reg byte, data []byte) error
    DelayMs(ms uint32)
}
```

### Node.js: TypeScript Interface

```ts
export interface Transport {
    readRegister(reg: number, length: number): Promise<Uint8Array>;
    writeRegister(reg: number, data: Uint8Array): Promise<void>;
    delayMs?(ms: number): Promise<void>;
}
```

## Device Lifecycle and Configuration State

Every implementation exposes the same two-state lifecycle:

```text
constructed / unprobed -- successful probe --> probed + standby
          ^                    |
          |---- failed probe --|
```

Construction or C `adxl355_init()` only stores the transport and initializes local
cache defaults. `probe()` validates all identity registers, synchronizes the cached
range, and enters standby with a read-modify-write of `POWER_CTL` so unrelated bits
are preserved. A failed or repeated unsuccessful probe leaves the handle
uninitialized.

After a successful probe, all methods that access hardware are enabled. Before
probe, they fail without touching the transport. Stateless decode and unit
conversion helpers are intentionally exempt. The language-specific state errors
are:

| C | C++ | Python | Rust | Node.js | Go |
|---|---|---|---|---|---|
| `ADXL355_ERR_STATE` | `InvalidStateError` | `DeviceStateError` | `Error::InvalidState` | `DeviceStateError` | `ErrInvalidState` |

### Standby Configuration Guard

Datasheet configuration guidance requires range and ODR/filter changes in standby.
Each supported configuration method uses the same guard:

1. Read and retain the complete original `POWER_CTL` value.
2. If measurement mode is active, set only the standby bit.
3. Apply the target register update.
4. Restore the exact original `POWER_CTL` value when a transition was made.

If the device is already in standby, steps 2 and 4 perform no bus writes. If the
target operation fails, restoration is still attempted and the associated cache is
not changed. If the target write succeeds but restoration fails, the method reports
a bus error, hardware remains in standby, and the cache retains the successfully
written target value so software and hardware remain consistent.

The guard applies to `set_range` in every implementation and to the public
ODR/filter configuration APIs currently provided by C and Python. Explicit
power-mode changes are not wrapped by the guard because changing that mode is the
operation requested by the caller.

## Exact Transport Contract

Every transport read must return exactly the requested payload length. A successful
read of one, two, or nine bytes may not return zero bytes, a truncated payload, or
an overlong payload. The driver validates length before indexing and converts any
contract violation or backend exception/error into its language-level bus error.
Identity mismatches, invalid configuration values, and invalid device state remain
distinct errors.

Write operations must transfer the complete payload or fail. Python and Node.js also
normalize backend delay exceptions during reset. Rust and Go transports expose
infallible delay methods, while C retains a `void` delay callback.

The C/C++ callback ABI reports byte counts explicitly: read and write callbacks
return exactly the requested byte count on success and a negative value on bus
failure. The C core rejects zero, partial, and overlong counts. This makes partial
reads detectable instead of relying on an ambiguous `0 == success` convention.

`spec/transport_contract.json` is the shared negative checklist. The maintained
language suites cover its `TR-1-*`, `TR-2-*`, and `TR-9-*` scenarios and verify that
failed reads do not modify caller-provided output values or fabricate measurements.

## Register Specification as Single Source of Truth

Register addresses, bit fields, and expected ID values are defined in `spec/adxl355.registers.yaml`. This YAML file is the authoritative reference. Every language package duplicates these values in its native format (header files, enums, constants), but they must all match the YAML.

**Verification status**: All register values in the spec are marked `datasheet_verified: false` until confirmed against the official ADXL355 datasheet.

## Test Vectors

`spec/test_vectors.json` contains golden inputs and expected outputs for:

- 20-bit raw data decoding (5 vectors: zero, positive one, positive max, negative min, negative one)
- Acceleration conversion (raw to g, raw to m/s²)
- Temperature decoding and conversion, including reserved TEMP2 bits and raw boundaries

Every language must pass the same test vectors. Floating-point tolerance:
- g conversion: ±1e-6
- m/s² conversion: ±1e-5
- temperature conversion: ±0.01°C

`scripts/verify_vectors.py --ci` is the required clean-checkout gate. It maps
range names to each implementation's real enum values, validates shared specs,
constructs isolated C/C++ builds, and executes every maintained language suite.
The required mode rejects missing toolchains and skips, so a constant or conversion
regression cannot be silently omitted from CI.

## Testing Strategy

### Hardware-free tests (required, run by default)

- Mock bus simulation
- Raw 20-bit decode verification
- Range scale conversion
- Sign extension correctness
- Config register write verification
- Status register readback
- Coherent 12-bit temperature read and nominal conversion

### Hardware tests (optional, separated)

- Located in `tests/hardware/` or language-specific hardware test files
- Require real ADXL355 connected via SPI or I2C
- Not executed during default test suite
- Methods described in `docs/hardware-test-plan.md`

## Cross-Language Consistency

| Function | C | Python | Rust | Node | Go | C++ |
|---|---|---|---|---|---|---|
| decode_raw20 | `adxl355_decode_raw20` | `_decode_raw20` | `decode_raw20` | `decodeRaw20` | `DecodeRaw20` | `Device::decodeRaw20` |
| raw to g | `adxl355_raw_to_g` | `raw_to_g` | `raw_to_g` | `rawToG` | `RawToG` | `Device::rawToG` |
| raw to m/s² | `adxl355_raw_to_mps2` | `raw_to_mps2` | `raw_to_mps2` | `rawToMps2` | `RawToMps2` | `Device::rawToMps2` |
