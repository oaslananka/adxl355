# ADXL355 Agent Instructions

These instructions apply repository-wide.

## Repository purpose

This repository maintains one ADXL355 driver family across C, C++, Python, Rust, Node.js/TypeScript, and Go.

The language implementations are separate bindings of the same hardware contract. Treat the shared register model, lifecycle rules, conversion behavior, test vectors, release identity, and hardware evidence as cross-language contracts.

Do not create nested `AGENTS.md` files merely because a language has its own directory. Add a nested boundary only if a future subtree develops materially different authority, release, or safety rules.

## First reads

Before changing behavior, read the relevant implementation/tests plus:

- `README.md`
- `CONTRIBUTING.md`
- `docs/architecture.md`
- `docs/testing.md`
- `docs/hardware-testing.md`
- `docs/versioning.md`
- `docs/security/supply-chain.md`
- `docs/publishing.md`
- `SECURITY.md`

## Product-truth and evidence rules

This is an alpha-stage hardware driver family.

- Do not claim production maturity, universal hardware support, factory qualification, safety certification, or fabrication readiness.
- Register presence does not imply a public API.
- A feature implemented in one language does not imply parity in every language.
- Mock/unit tests, compile fixtures, package dry runs, and physical HIL runs are different evidence classes. Do not describe one as another.
- Hardware claims must name the exact language, transport, board/fixture, commit/tag, and evidence actually exercised.
- Preserve the distinction between feature-specific historical HIL evidence and release-candidate HIL evidence.
- Do not invent sensor identity, timing, temperature, self-test, FIFO, interrupt, calibration, or bus evidence.

## Shared hardware contract

All implementations must preserve the common driver invariants documented and tested by the repository:

- object construction alone does not prove device presence;
- stateful operations require a successful probe first;
- stateless decode/conversion helpers may remain usable without a device;
- transport reads must return exactly the requested length;
- zero-length, truncated, and overlong responses are rejected before indexing;
- signed 20-bit acceleration decode and unit conversions must agree across maintained languages;
- range/power/configuration changes must preserve documented standby/restore semantics;
- bounded operations remain bounded: no unbounded polling, acquisition, retry, or background loops in core APIs unless explicitly designed and documented.

When shared behavior changes, update the canonical vectors/tests and every affected binding rather than patching one implementation in isolation.

## Language responsibilities

### C

- C99 core.
- No dynamic allocation in the core driver.
- No global mutable driver state.
- Preserve exact callback transfer-length semantics.
- Treat sanitizer, warnings-as-errors, package-install, FIFO/self-test/DRDY and calibration tests as part of the contract.

### C++

- C++17.
- Keep the wrapper thin over the C core unless an explicit C++-specific API is documented.
- Preserve both owning exception and no-exception/status APIs.
- Keep RAII/resource ownership explicit.
- Arduino/PlatformIO compile evidence is compile/package evidence, not physical HIL evidence.

### Python

- Python 3.10+ with type hints, Ruff, and strict mypy.
- Preserve typed error/progress behavior for bounded FIFO and GPIO-reference flows.
- Linux SPI/I2C/GPIO helpers remain adapters/reference flows, not a portable-core dependency.
- Keep timeouts, cleanup, and resource ownership explicit.

### Rust

- Preserve `no_std` compatibility where documented.
- Keep `embedded-hal` integration feature-gated and test both default and no-default-feature configurations.
- Do not add Linux-specific runtime assumptions to the portable crate without an explicit design decision.

### Node.js / TypeScript

- Strict TypeScript and ES modules.
- Core remains transport-agnostic.
- Linux SPI/I2C adapters stay optional and explicit about descriptor ownership and exact byte counts.
- Do not make optional native dependencies mandatory for core-only consumers.

### Go

- Follow `gofmt`, `go vet`, race detection, and standard Go error/resource conventions.
- Linux `spidev`/`i2c-dev` adapters own descriptors until `Close`; repeated close remains safe.
- Keep bounded hardware examples finite and restore standby before exit.

## Verification

Run the narrow language checks first, then the relevant repository/release gates.

Representative commands:

### C

```bash
cmake -S c -B build/c -DADXL355_BUILD_TESTS=ON -DADXL355_BUILD_EXAMPLES=ON -DADXL355_WARNINGS_AS_ERRORS=ON -DADXL355_ENABLE_SANITIZERS=ON
cmake --build build/c --parallel
ctest --test-dir build/c --output-on-failure
```

### C++

```bash
cmake -S c -B build/c-core -DADXL355_BUILD_TESTS=OFF -DADXL355_BUILD_EXAMPLES=OFF
cmake --build build/c-core --parallel
cmake -S cpp -B build/cpp -DADXL355_BUILD_TESTS=ON -DADXL355_BUILD_EXAMPLES=ON -DADXL355_WARNINGS_AS_ERRORS=ON -DCMAKE_PREFIX_PATH="$PWD/build/c-core"
cmake --build build/cpp --parallel
ctest --test-dir build/cpp --output-on-failure
```

### Python

```bash
PYTHONPATH=python/src python -m pytest -q python/tests
ruff check python/src python/tests python/examples
mypy python/src python/examples
```

### Rust

```bash
cargo fmt --manifest-path rust/Cargo.toml --all -- --check
cargo clippy --manifest-path rust/Cargo.toml --all-targets --all-features -- -D warnings
cargo test --manifest-path rust/Cargo.toml --all-features
cargo test --manifest-path rust/Cargo.toml --no-default-features
```

### Node.js

```bash
cd node
npm ci --ignore-scripts
npm run build
npm test
```

### Go

```bash
cd go
go mod verify
go test ./...
go test -race ./...
go vet ./...
go build ./...
```

Use `docs/testing.md` and CI as the authoritative complete matrix. Do not disable a language lane, sanitizer, race check, packaging check, or zero-skip/vector gate to land unrelated work.

## Hardware-in-the-loop

Physical HIL is opt-in and hardware-dependent.

- Do not run or claim HIL without the required sensor/fixture.
- Keep HIL finite, bounded, and safe to interrupt.
- Sanitize diagnostics before preserving artifacts.
- Record exact commit/tag and transport configuration.
- Preserve standby/cleanup restoration.
- Do not convert one successful bus/language run into a cross-language or cross-transport claim.

## Packaging and release

This repository publishes multiple package families from one release identity.

- Keep Python, Rust, Node, Go, C/C++ version/tag mapping aligned with `docs/versioning.md`.
- Do not hand-edit release artifacts.
- Package verification, checksums, SBOMs, attestations, package contents, package-size policy, and release metadata must refer to the same source identity.
- Publishing must remain under the repository's protected release workflows.
- Third-party Actions remain pinned to reviewed commit SHAs.
- Do not weaken high-severity vulnerability gates, provenance, tag/commit preflight, or clean-checkout requirements.
- Released artifacts are immutable; publish a new version rather than replacing bytes.

## Dependencies and generated state

- Preserve hash-locked Python requirements and reviewed native/toolchain pins.
- Keep optional dependencies optional where the public package contract says they are.
- Do not update baselines, support tables, golden vectors, generated API docs, or package metadata merely to hide a regression.
- Change the owning source/generator and regenerate deliberately.

## Change discipline

- Keep diffs focused.
- Do not weaken tests, warnings, sanitizers, race detection, package checks, dependency audits, security scans, or release checks for convenience.
- Add regression coverage for behavioral fixes.
- Keep cross-language behavior deterministic where the repository promises parity.
- Update README/docs/support tables when public feature support actually changes.

## Definition of done

A change is ready when the affected language implementation, shared contract/vector evidence, focused tests, packaging behavior, documentation, and exact-head CI agree. State clearly which hardware-dependent checks were not run.
