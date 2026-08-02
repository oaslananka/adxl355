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

### Go Linux device ownership

The portable Go driver still depends only on the `Transport` interface. The
separate `adxl355/linuxio` package provides maintained Linux amd64/arm64 adapters:

- `OpenSPI` owns one `/dev/spidevB.D` descriptor, configures Mode 0, 8-bit words,
  and a validated 100 kHz–10 MHz clock, and uses one full-duplex
  `SPI_IOC_MESSAGE(1)` transaction per register operation.
- `OpenI2C` owns one `/dev/i2c-N` descriptor, accepts only addresses `0x1D` or
  `0x53`, verifies combined-I2C capability, and uses `I2C_RDWR` so the register
  pointer write and payload read remain one combined transaction.
- `Close` is caller-visible and idempotent. No hidden goroutine or finalizer owns
  device lifetime. `OpError` preserves operation/path context and unwraps the
  kernel errno or stable package sentinel for `errors.Is`/`errors.As`.
- I2C adapter speed is global platform state. `I2CConfig.BusHz` validates and
  records the expected external setting; it does not claim to reconfigure the
  Linux controller.

Unsupported operating systems and Linux architectures use the same public
constructors but return `ErrUnsupported`, preserving portable core builds without
pretending an unverified ioctl ABI is supported.

### Node.js: TypeScript Interface

```ts
export interface Transport {
    readRegister(reg: number, length: number): Promise<Uint8Array>;
    writeRegister(reg: number, data: Uint8Array): Promise<void>;
    delayMs?(ms: number): Promise<void>;
}
```

## Device Lifecycle and Configuration State

Every maintained implementation follows the same two-state lifecycle for its implemented core device methods:

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
| `ADXL355_ERR_STATE` | `InvalidStateError` / `Status::InvalidState` | `DeviceStateError` | `Error::InvalidState` | `DeviceStateError` | `ErrInvalidState` |

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
ODR/filter configuration APIs currently provided by C, C++, and Python. Other methods
and adapter coverage are not assumed to be identical across languages; see the
root feature matrix. Explicit
power-mode changes are not wrapped by the guard because changing that mode is the
operation requested by the caller.

## C++ hosted and embedded ownership models

The C++ package remains a thin wrapper over the C core and provides two explicit
error/ownership models:

- `adxl355::Device` owns a `std::unique_ptr<BusInterface>` and maps stable C
  statuses to typed C++ exceptions for hosted applications.
- `adxl355::NoexceptDevice` borrows a caller-owned `BusInterface`, is non-copyable
  and non-movable, performs no dynamic allocation, and returns `Status` or
  `Result<T>`. The installed `adxl355::cpp_noexcept` target defines
  `ADXL355_CPP_NO_EXCEPTIONS` and is compiled in tests with exceptions and RTTI
  disabled.

Both wrappers call the same C lifecycle, range, ODR, read, and conversion
functions. They do not duplicate register constants or formulas. The Arduino
layer adds only a Mode 0 `SPIClass` bus adapter and forwarding headers; its bridge
compiles the authoritative `c/src/adxl355.c` once.

The representative embedded build is Arduino Uno with PlatformIO Core 6.1.19 and
`atmelavr@5.3.0`. It is a required GitHub-hosted compile/package fixture, not a
physical hardware test. Boards, frameworks, interrupt behavior, and electrical
fixtures not built or measured here remain unsupported claims.

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

### FIFO ownership and partial progress

The ADXL355 FIFO stores 96 axis locations, not 96 complete samples. One complete
X/Y/Z sample consumes three 24-bit locations. Each location contains signed
20-bit acceleration in bits 23:4, virtual zero bits 3:2, an empty/invalid marker
in bit 1, and the x-axis marker in bit 0. C and Python require the marker sequence
X/Y/Z and reject empty, malformed, truncated, and overlong payloads.

FIFO reads are non-blocking and caller-bounded to 1..32 complete samples. A
FIFO_ENTRIES remainder of one or two is valid but remains unread until a complete
XYZ sample exists. C uses a fixed nine-byte stack buffer and caller-owned output
storage; Python returns an immutable tuple. A successful FIFO_DATA transaction
physically pops three locations. If a later decode fails, earlier samples remain
valid and exact consumption is reported. If the transport fails during FIFO_DATA,
consumption is conservatively marked indeterminate because hardware may have
popped bytes before the backend failed; reset or flush before trusting alignment.
C reports this through `adxl355_fifo_read_result_t`; Python errors carry
`partial_samples`, `consumed_locations`, and `consumption_indeterminate`.

## Register definitions versus public API

The shared register model documents the device even when a high-level method is
not present. Register presence does not imply a public API. For example,
`FIFO_DATA`, offset registers, and `SELF_TEST` are defined for consistency, but
high-level support remains language-specific. C and Python expose signed offset
programming, bounded self-test-response measurement, and bounded FIFO
count/decode/read methods. C++, Rust, Node.js, and Go do not currently expose
those high-level methods.

## Register Specification as Single Source of Truth

Register addresses, bit fields, and expected ID values are defined in `spec/adxl355.registers.yaml`. This YAML file is the authoritative reference. Every language package duplicates these values in its native format (header files, enums, constants), but they must all match the YAML.

**Verification status**: Datasheet-derived register values and constants are traced to the ADXL354/ADXL355 Rev. D tables in the shared YAML specifications and are checked for cross-language consistency in CI.

## Test Vectors

`spec/test_vectors.json` contains golden inputs and expected outputs for:

- 20-bit raw data decoding (5 vectors: zero, positive one, positive max, negative min, negative one)
- Acceleration conversion (raw to g, raw to m/s²)
- Temperature decoding and conversion, including reserved TEMP2 bits and raw boundaries
- FIFO signed boundaries, X/Y/Z marker order, empty markers, virtual bits, and exact payload lengths

Every language must pass the same test vectors. Floating-point tolerance:
- g conversion: ±1e-6
- m/s² conversion: ±1e-5
- temperature conversion: ±0.01°C

`scripts/verify_vectors.py --ci` is the required clean-checkout gate. It maps
range names to each implementation's real enum values, validates shared specs,
constructs isolated C/C++ builds, and executes every maintained language suite.
The required mode rejects missing toolchains and skips, so a constant or conversion
regression cannot be silently omitted from CI.

## Node.js Linux adapter boundary

The transport-agnostic Node core does not import native modules. The Linux
subpaths dynamically load exact optional dependencies only when `open()` is
called. Public declaration files expose repository-owned backend interfaces and
do not reference `spi-device` or `i2c-bus` types, so core-only installations can
import the package and both subpaths without native modules.

`LinuxSpiTransport` owns one `spi-device` handle and performs every register
operation as one transfer message with one transfer element. The command byte and
all payload/dummy bytes therefore share one chip-select assertion. Mode 0, 8-bit
words, MSB-first ordering, and the datasheet clock range are fixed by the adapter.

`LinuxI2cTransport` owns one promisified `i2c-bus` handle and supports only `0x1D`
and `0x53`. Register operations use block APIs with exact returned byte counts.
The `busHz` value is a validated declaration of the externally configured Linux
adapter rate, not a request to change kernel clock configuration.

Both transports reject use after close and make `close()` idempotent. Optional
module load failures, native backend errors, and exact-length violations are
normalized to `BusError` while preserving the original error as `cause`.

## CI Quality Architecture

Each maintained language retains one stable primary job name for branch
protection. Runtime safety, static analysis, package-consumer validation,
dependency auditing, race detection, and coverage generation are steps in those
jobs rather than parallel duplicate scanners. The final cross-language job still
depends on all language jobs, so the shared-vector gate cannot pass around a
failed language-specific quality check.

## Hardware Evidence Boundary

Mock transports and required CI verify deterministic register behavior, but they
cannot prove Linux device-node permissions, electrical mode, chip-select timing,
address straps, or physical signal integrity. The HIL layer therefore remains an
explicit boundary: `scripts/hil_runner.py` exercises the public Python hardware
adapters on one physical sensor, while `.github/workflows/hil.yml` schedules the
sequence only on a dedicated `adxl355-hil` self-hosted runner. The runner emits a
bounded, sanitized JSON report containing device revision and bus context rather
than environment dumps or credentials. A hardware failure never weakens or skips
normal CI; it produces separate diagnostic evidence.

## Testing Strategy

### Hardware-free tests (required, run by default)

- Mock bus simulation
- Raw 20-bit decode verification
- Range scale conversion
- Sign extension correctness
- Config register write verification
- Status register readback
- Coherent 12-bit temperature read and nominal conversion

### Hardware tests (manual-only, separated)

- Run through `scripts/hil_runner.py` and `.github/workflows/hil.yml`
- Require a real ADXL355 connected through Linux SPI or I2C
- Are not executed during default tests or pull-request CI
- Follow `docs/hardware-testing.md`; only the exact recorded fixture runs establish physical claims

## Cross-Language Consistency

| Function | C | Python | Rust | Node | Go | C++ |
|---|---|---|---|---|---|---|
| decode_raw20 | `adxl355_decode_raw20` | `_decode_raw20` | `decode_raw20` | `decodeRaw20` | `DecodeRaw20` | `Device::decodeRaw20` |
| raw to g | `adxl355_raw_to_g` | `raw_to_g` | `raw_to_g` | `rawToG` | `RawToG` | `Device::rawToG` |
| raw to m/s² | `adxl355_raw_to_mps2` | `raw_to_mps2` | `raw_to_mps2` | `rawToMps2` | `RawToMps2` | `Device::rawToMps2` |
