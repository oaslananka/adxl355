# Node.js Driver Instructions

These instructions apply to `node/**` and supplement the root instructions.

- Keep the core package transport-agnostic and strict ESM/TypeScript.
- Linux SPI/I2C adapters remain optional subpaths backed by exact optional native dependencies.
- Core imports and public declaration files must not require `spi-device` or `i2c-bus`.
- SPI register operations stay one transfer message/chip-select assertion.
- I2C reads/writes validate exact returned byte counts and only the supported addresses.
- Adapter handles are explicitly owned; use-after-close fails and repeated `close()` stays safe.
- `busHz` records/validates externally configured I2C speed; do not claim it changes kernel controller timing.
- Preserve original backend failures as causes while exposing stable package-level `BusError`.

Run build, tests, native adapter checks, core-only install smoke, package dry-run, audit, and shared vectors as applicable.
