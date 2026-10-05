# Python Driver Instructions

These instructions apply to `python/**` and supplement the root instructions.

- Keep Python >=3.10 typing strict and the portable driver transport-agnostic.
- Linux `spidev`, `smbus2`, and libgpiod behavior stays in explicit platform adapters/reference flows.
- Preserve exact-length validation, typed driver errors, probe-before-use, standby-safe configuration, and cache consistency.
- FIFO failures must preserve documented partial samples/consumption state rather than fabricate all-or-nothing success.
- The GPIO DRDY reference is finite and caller-bounded: no hidden thread, callback registry, busy-spin loop, or daemon API.
- Distinguish dedicated DRDY from DATA_RDY routing to INT1/INT2; do not invent unsupported external sync behavior.
- Hardware references must restore device/bus/GPIO state they own.

Run pytest, Ruff, strict mypy, package build checks, and shared vectors as applicable.
