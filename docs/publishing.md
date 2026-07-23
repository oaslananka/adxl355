# Publishing Guide

> **Current state:** The repository provides a verification and packaging dry run.
> It does not publish to PyPI, npm, crates.io, GitHub Releases, or a Go proxy.
> Registry publication requires an explicit maintainer decision after version,
> physical HIL, security, and release-evidence gates are satisfied.

## Automated release verification

Pushing a root `v*` tag starts `.github/workflows/release.yml`. The workflow
re-runs the required CI workflow, verifies that the tag points to the packaged
commit, validates every maintained version declaration, builds all package
formats without publishing, and uploads checksummed artifacts for inspection.

Package jobs have read-only repository permissions and no registry credentials.
The final bundle job receives narrowly scoped GitHub OIDC and attestation
permissions to generate provenance and an SBOM attestation. See
[`releasing.md`](releasing.md) and
[`security/supply-chain.md`](security/supply-chain.md) for the enforced gates.

## Python (PyPI)

```bash
cd python

# Build
pip install build
python -m build

# Check
twine check dist/*

# Upload to TestPyPI (for testing)
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*
```

Publication is not enabled by this repository. Before enabling it, configure a
PyPI Trusted Publisher bound to the protected release environment and exact
workflow. Do not add a stored PyPI API token to the default workflow.

## Node.js (npm)

```bash
cd node
npm run build
npm publish --access public
```

Publication is not enabled by this repository. Before enabling it, configure
npm trusted publishing for `@oaslananka/adxl355` on a GitHub-hosted runner and a
protected environment. Do not add a stored npm token to the default workflow.

## Rust (crates.io: `adxl355-driver`)

```bash
cd rust
cargo publish --dry-run
cargo publish
```

Publication is not enabled by this repository. Before enabling it, configure
crates.io trusted publishing for `adxl355-driver` and enable
trusted-publishing-only mode after the first verified release. Do not add a
stored Cargo registry token to the default workflow.

## Go Module

```bash
cd go
# Tag the release
git tag go/v0.1.0-alpha.2
git push origin go/v0.1.0-alpha.2
# The Go module proxy will pick up the new version automatically
```

## Registry names and versioning

The canonical version and package-name decisions are documented in
[`versioning.md`](versioning.md). The current intended names are `adxl355` on
PyPI, `@oaslananka/adxl355` on npm, and `adxl355-driver` on crates.io. Registry
availability must be re-checked immediately before publication.

## Rollback and deprecation

Published artifacts are immutable. Do not delete or overwrite a released
version to hide a defect.

- **PyPI:** publish a corrected higher version. When appropriate, yank the
  affected release with a reason so existing locked installs remain resolvable.
- **npm:** publish a corrected higher version. Use `npm deprecate` with an
  actionable message for the affected version range; do not use `npm unpublish`
  as a routine rollback mechanism.
- **crates.io:** publish a corrected higher version and yank the affected crate
  version when necessary. Yanking prevents new resolution without breaking
  existing lockfiles.
- **Go module:** never move or recreate a public tag. Publish a higher
  `go/v...` tag. If a module version must be retracted, add a `retract` directive
  in a newer `go.mod` release with a reason.
- **GitHub artifacts/tags:** preserve checksums and the original tag. Mark the
  release as affected and point users to the replacement version.

Every rollback or deprecation must be recorded in the changelog and security
advisory process when the defect has security impact.

## Versioning

This project follows Semantic Versioning:

- **0.x** (current): API may change; changes documented in CHANGELOG.
- **1.0.0**: Each published language surface is documented and stable; exact feature parity is not implied.

## Pre-Publish Checklist

- [ ] HIL evidence for both SPI and I2C is successful on the release-candidate commit and no older than 30 days
- [ ] Each HIL artifact records the device revision, tested bus settings, workflow URL, and fixture identifier
- [ ] Both I2C addresses (`0x1D` and `0x53`) are validated where the release hardware permits changing the address strap
- [ ] All register values verified against datasheet
- [ ] All test vectors confirmed across all languages
- [ ] Release SBOM contains every verified artifact and the high-severity scan passes
- [ ] Final bundle checksum and GitHub provenance/SBOM attestations verify successfully
- [ ] Trusted publishers are bound to the protected environment and exact workflow
- [ ] No long-lived registry token is configured in the default release workflow
- [ ] C library builds with CMake on Linux, macOS, Windows
- [ ] Python wheel installs cleanly from the release artifact; registry publication is separately approved
- [ ] Rust crate compiles with `no_std` and `std`
- [ ] Node package builds and tests pass
- [ ] Go module tests pass
- [ ] README updated with correct version
- [ ] CHANGELOG updated
- [ ] Tag created in git
