# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-alpha.3] - Unreleased

### Fixed

- Added a bounded 20 ms measurement-settle step to the Node.js Linux SPI and I2C
  examples before temperature and acceleration reads, with an ordering regression
  test and Raspberry Pi 5 SPI validation.
- Corrected the C/C++ release job to expose the already-built C core through `CMAKE_PREFIX_PATH` before configuring the C++ package.
- Preserved safe executable intent while extracting native release artifacts so packaged smoke binaries run, while stripping setuid, setgid, and sticky permission bits.
- Refreshed the reviewed Go module archive baseline to 17,388 bytes after verifying that the growth consists only of maintained Linux SPI/I2C adapters, bounded examples, tests, and module metadata.
- Hardened release artifact extraction by rejecting links and special archive
  members and copying only validated regular files and directories.
- Updated the Python build backend to `setuptools==83.0.0` to resolve
  GHSA-h35f-9h28-mq5c / CVE-2026-59890.
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

- Added protected, opt-in PyPI, npm, and crates.io publication jobs that reuse
  verified release artifacts, authenticate with GitHub OIDC, reject partial or
  changed immutable releases, and support idempotent recovery after a registry
  succeeds while another fails.
- Added C/Python internal-clock data-ready configuration that separates the always-active-high dedicated DRDY output from DATA_RDY routing to INT1/INT2, preserves unrelated register state, rejects external pin-multiplexing modes, and performs exact rollback on failure.
- Added a finite Linux Python libgpiod v2 DRDY reference with blocking rising-edge waits, kernel monotonic timestamps, GPIO sequence-gap accounting, bounded sample/deadline controls, explicit timeout/overrun/transport errors, and safe standby/resource cleanup. Raspberry Pi 5 I2C + dedicated GPIO17/DRDY evidence passed at commit `002173d0c8dae8b15261b6d00cf011011cf8db7c` with 32/32 unique samples, zero sequence gaps, zero FIFO overruns, and verified safe restoration.
- Added optional Node.js Linux SPI and I2C subpath adapters with exact native
  dependencies, explicit resource ownership, one-message SPI framing, exact I2C
  byte-count checks, core-only installation smoke tests, and bounded examples.
  Raspberry Pi 5 bounded examples are physically verified for SPI Mode 0 at
  1 MHz and I2C address `0x1D`.
- Added shared C/Python FIFO location and complete XYZ sample contracts with
  bounded reads, marker/empty/framing validation, partial-progress reporting,
  caller-owned C storage, and a documented later physical validation plan.
- Added C and Python signed hardware-offset read/write APIs and deterministic raw-LSB calibration helpers with standby-safe writes and documented physical rollback procedures.
- Added C and Python bounded electrostatic self-test response APIs with ST1-only baseline acquisition, ST1+ST2 stimulation, exact state restoration, distinct timeout/threshold/restore errors, optional caller-owned policy, and repeatable Raspberry Pi 5 SPI validation against the Rev.D response windows.
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
  package metadata, HIL behavior, public documentation, and supply-chain policy.
- Required bounded C libFuzzer and deterministic Python/release-tool mutation smoke with sanitizer coverage and short-lived failure reproducers.
- Added reviewed SHA-256 lock groups for Python CI, release, and HIL tooling, an offline policy verifier, deterministic PyPI hash regeneration, and a rate-limited Dependabot update path.
- Added source-derived public API references for all six maintained languages, required drift verification, completed public C error documentation, and accessible MIT-licensed Raspberry Pi 5 SPI and I2C wiring diagrams matched to physical fixtures.
- Added C++ ODR configuration, an installed no-exception `Status`/`Result<T>` target, a thin Arduino SPI adapter, command-scoped hash-locked PlatformIO tooling without its vulnerable web/server stack, and a required Arduino Uno package/compile fixture.
- Added maintained Go Linux amd64/arm64 spidev and i2c-dev transports with explicit close ownership, exact ioctl transaction checks, inspectable wrapped errors, cross-platform stubs, and bounded hardware examples.
- Grouped weekly Dependabot updates for GitHub Actions, Python, Rust, Node.js,
  and Go, plus primary CodeQL analysis for C/C++, Python, JavaScript/TypeScript,
  and Go.
- SPDX SBOM generation, a high-severity Grype release gate, immutable workflow
  action pins, GitHub OIDC provenance/SBOM attestations, and a private security
  disclosure process with response targets.

### Changed

- **Breaking (Python metadata):** The public `adxl355.__version__` value and Python distribution version advance from `0.1.0a2` to `0.1.0a3` for the corrected prerelease.
- The immutable `v0.1.0-alpha.2` and `go/v0.1.0-alpha.2` tags are retained as failed release-gate evidence and were not published as a GitHub release; `0.1.0-alpha.3` supersedes that candidate.
- **Breaking (Rust):** Transport implementations now expose an associated backend error type, and driver methods return generic structured errors that preserve transport and restore causes.
- Updated core GitHub Actions to their reviewed Node.js 24 major releases,
  standardized checkout on `v7.0.1`, and documented the HIL runner minimum.
- Added a seven-day Dependabot cooldown for version updates across all maintained
  ecosystems; security updates remain immediate.
- Kept custom Python tool hash locks on the repository generator instead of Dependabot after verified bot PRs produced inconsistent manifest/hash pairs.
- **Breaking (Python):** Raised the minimum supported Python version from 3.9 to
  3.10 so release builds do not depend on a vulnerable legacy setuptools line.
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
