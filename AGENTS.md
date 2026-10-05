# ADXL355 Agent Instructions

These instructions apply repository-wide. A nested `AGENTS.md` adds or narrows implementation rules for its subtree; repository-wide safety, cross-language parity, product-truth, release, and evidence rules remain mandatory.

## Repository contract

ADXL355 is an alpha-stage, cross-platform hardware driver family for C, C++, Python, Rust, Node.js/TypeScript, Go, and embedded Arduino/PlatformIO integration.

The C implementation is the behavioral reference for the shared core contract, while each language remains idiomatic and self-contained. Shared register definitions and golden vectors are authoritative cross-language evidence.

Do not claim unsupported feature parity, hardware validation, production maturity, manufacturer approval, or physical behavior that is not backed by the repository's exact tests/evidence.

## Nested boundaries

- `.github/AGENTS.md` — CI, HIL, release, publishing, provenance, and supply-chain automation.
- `spec/AGENTS.md` — authoritative register model, transport contract, and golden vectors.
- `c/AGENTS.md` — C reference core and memory/transport safety.
- `cpp/AGENTS.md` — thin C++ wrappers over the C core.
- `python/AGENTS.md` — Python driver, Linux SPI/I2C/GPIO adapters, and typed partial-progress behavior.
- `rust/AGENTS.md` — no_std/embedded-hal Rust implementation.
- `node/AGENTS.md` — TypeScript core and optional Linux native adapters.
- `go/AGENTS.md` — Go core and Linux device adapters.
- `embedded/AGENTS.md` — Arduino/PlatformIO compile integration.

## Global invariants

- Construction/init does not prove device identity. Stateful hardware methods require a successful probe.
- Exact transport lengths are mandatory. Zero, truncated, or overlong reads are errors before indexing or measurement construction.
- Configuration changes preserve unrelated register bits and the exact prior power mode; failed writes do not fabricate cache state.
- Register presence does not imply a public high-level API.
- Keep shared constants, decode formulas, lifecycle behavior, and `spec/test_vectors.json` expectations aligned across maintained languages.
- Feature additions are language-specific until implemented and tested in each claimed language.
- Mock/CI results are not physical HIL evidence.
- HIL evidence applies only to the exact bus, fixture, language/path, commit, and run recorded.
- Hardware examples remain finite, bounded, and restore safe state/resources before exit.

## Product truth

The root README feature matrix and explicit non-claims are part of the public contract. Do not convert compile coverage, mocks, one bus result, one language's implementation, or a historical HIL run into broader support claims.

## Verification

Use the narrowest language checks while developing, then the relevant repository gates.

The required cross-language clean-checkout gate is:

```bash
python scripts/verify_vectors.py --ci
```

Consult `docs/testing.md` for language commands and `docs/hardware-testing.md` for manual HIL. Do not report a missing toolchain or skipped HIL as passing evidence.

## Package artifact boundary

These `AGENTS.md` files are repository governance metadata, not runtime API.

- Keep curated package payloads narrow when a package manager has an explicit file manifest. The existing npm `files` list and Cargo `include` list must not be broadened just to carry agent instructions.
- Python wheel/sdist contents remain governed by setuptools/MANIFEST configuration and package checks; do not add agent instructions to package data.
- Go module/source archives may include repository Markdown as non-runtime source metadata. That does not create an exported API or a compatibility claim.
- Do not weaken package allowlists, install-smoke checks, or release verification to accommodate these instructions.

## Generated and release state

- Do not hand-edit generated API/reference output when an owning generator exists.
- Do not alter release evidence, package manifests, checksums, SBOMs, attestations, HIL reports, or version metadata merely to satisfy a gate.
- Version changes must stay aligned across all published package surfaces and the release preflight.
- Use trusted publishing/release workflows; do not publish from ordinary development work.

## Definition of done

A change is ready only when the touched language/API, shared spec/vector contract, docs/feature matrix, package surface, relevant safety tests, and exact-head CI evidence agree.
