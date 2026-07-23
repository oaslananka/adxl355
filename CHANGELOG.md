# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-alpha.2] - Unreleased

### Fixed

- Synchronized reset and constructor range state with the ADXL355 reset default
  across all maintained drivers.
- Corrected Python and Rust SPI command framing and kept command/payload bytes in
  one chip-select transaction.
- Corrected Linux C multi-byte SPI reads to use one sustained transfer.
- Preserved unrelated `RANGE` register bits and committed cached state only after
  successful hardware writes.
- Added coherent temperature sampling, reserved-nibble masking, and bounded
  rollover retries.
- Rejected zero, truncated, and overlong transport responses before indexing and
  normalized backend failures to stable bus errors.
- Required a successful probe before stateful hardware operations and made
  supported configuration writes standby-safe.
- Corrected public documentation that overstated feature parity, package
  publication, FIFO/self-test/calibration APIs, and hardware maturity.

### Added

- Required clean-checkout shared-vector verification for C, C++, Python, Rust,
  Node.js, and Go with zero permitted CI skips.
- C/C++ sanitizer, warning-as-error, install/export, and consumer smoke gates.
- Python lint/type/package/example gates, Rust format/HAL/package/doc gates,
  Node.js package-content and audit gates, and Go race/coverage reporting.
- Enforceable release preflight with a canonical `VERSION` source, ecosystem-
  specific prerelease mapping, package identity validation, clean artifact
  installation smoke tests, checksums, and least-privilege workflow permissions.
- Manual-only Linux SPI/I2C HIL runner and self-hosted workflow with bounded,
  sanitized JSON evidence and public wiring/troubleshooting guidance.
- Regression tests for lifecycle, transport contracts, release automation,
  package metadata, HIL behavior, and public documentation claims.

### Changed

- **Breaking (C/C++):** Transport read/write callbacks return the exact
  transferred byte count on success and a negative value on failure.
- The repository now describes package outputs as verified build artifacts, not
  as registry-published packages; Rust uses the `adxl355-driver` distribution
  name and npm uses `@oaslananka/adxl355`.
- Language-specific API and adapter differences are documented explicitly rather
  than described as full feature parity.

## [0.1.0-alpha.1] - 2026-06-16

First public alpha tag. It established the initial six-language driver family,
datasheet-derived register/spec infrastructure, shared vectors, package metadata,
mock tests, the original CI matrix, release-gate skeleton, Python I2C support,
and the C Linux SPI example. Historical details are preserved in the tagged
source at `v0.1.0-alpha.1`.
