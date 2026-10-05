# Rust Driver Instructions

These instructions apply to `rust/**` and supplement the root instructions.

- Preserve `no_std` compatibility and optional `embedded-hal` integration.
- Keep the public transport/device model portable; do not add Linux-only assumptions to core APIs.
- Preserve probe-before-use, exact transport semantics, typed errors, conversion parity, and standby-safe range behavior.
- Do not claim FIFO, self-test, offset, DRDY, or other C/Python-only features until implemented and tested in Rust.
- Avoid unnecessary allocation or std-only dependencies in code intended for embedded use.

Run `cargo test --all-features`, relevant no-default/no_std checks, clippy/rustfmt gates, package dry-run, and shared vectors.
