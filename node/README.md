# ADXL355 Node.js Driver

Typed ESM support for the Analog Devices ADXL355 with a transport-agnostic API.

```ts
import { ADXL355, PowerMode, Range } from "@oaslananka/adxl355";

const device = new ADXL355(transport);
await device.probe();
await device.setRange(Range.G2);
await device.setPowerMode(PowerMode.Measurement);
console.log(await device.readAccelerationG());
```

A transport must return exactly the requested read length or reject. See the
repository root documentation for the lifecycle and hardware contracts.


## Optional Linux SPI and I2C adapters

The core package still accepts any user-provided `Transport`. Maintained Linux
adapters are available through subpath exports:

```ts
import { ADXL355 } from "@oaslananka/adxl355";
import { LinuxSpiTransport } from "@oaslananka/adxl355/linux/spi";
import { LinuxI2cTransport } from "@oaslananka/adxl355/linux/i2c";
```

`spi-device@3.1.2` and `i2c-bus@5.2.3` are exact optional dependencies. A default
npm install attempts to build them with `node-gyp`; Linux users need Python, a C++
compiler, make, and kernel device access. Core-only consumers can avoid native
builds:

```bash
npm install --omit=optional @oaslananka/adxl355
```

### SPI

```ts
const transport = await LinuxSpiTransport.open({
  busNumber: 0,
  deviceNumber: 0,
  speedHz: 1_000_000,
});
const device = new ADXL355(transport);
try {
  await device.probe();
  // Use the device.
} finally {
  await transport.close();
}
```

SPI is fixed to Mode 0, 8-bit words, MSB-first, and 100 kHz–10 MHz. Every register
operation uses one `spi-device.transfer()` message containing both command and
payload/dummy bytes, so chip select remains asserted for the complete operation.

### I2C

```ts
const transport = await LinuxI2cTransport.open({
  busNumber: 1,
  address: 0x1d,
  busHz: 100_000,
});
```

Only the documented `0x1D` and `0x53` addresses are accepted. Reads and writes use
`readI2cBlock`/`writeI2cBlock` and reject zero, truncated, or overlong byte counts.
`busHz` validates and records the externally configured adapter rate; it does not
reprogram the Linux adapter clock.

Both adapters own their native descriptor until idempotent `close()`. Operations
after close and backend/load failures use the package `BusError` hierarchy. The
repository examples `examples/linux-spi.mjs` and `examples/linux-i2c.mjs` enter
measurement mode, wait through a bounded 20 ms settle interval, collect a finite
sample count, enforce a timeout, restore standby, and close resources.

Both bounded adapters are physically verified on Raspberry Pi 5 with Node.js 24
ARM64. The I2C run at address `0x1D` captured 8/8 unique samples. The SPI Mode 0
run at 1 MHz captured 32/32 unique samples and measured 29.3094 °C. Independent
readback after each command confirmed standby, ±2 g, and the default ODR.

## Project links

- [Repository](https://github.com/oaslananka/adxl355)
- [Changelog](https://github.com/oaslananka/adxl355/blob/main/CHANGELOG.md)
- [Security policy](https://github.com/oaslananka/adxl355/security/policy)
- [MIT license](https://github.com/oaslananka/adxl355/blob/main/LICENSE)
