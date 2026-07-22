# Publishing Guide

> ⚠️ **Do not publish until the 1.0.0 release.**
> All register values must be verified against the ADXL355 datasheet first.

## Automated release verification

Pushing a root `v*` tag starts `.github/workflows/release.yml`. The workflow
re-runs the required CI workflow, verifies that the tag points to the packaged
commit, validates every maintained version declaration, builds all package
formats without publishing, and uploads checksummed artifacts for inspection.

The workflow has read-only repository permissions and intentionally has no
registry credentials or provenance identity permissions. See
[`docs/releasing.md`](releasing.md) for the enforced checks and local fixture.

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

Requires:
- PyPI account with API token
- `~/.pypirc` configured with token

## Node.js (npm)

```bash
cd node
npm build
npm publish

# For scoped package:
npm publish --access public
```

Requires:
- npm account
- `npm login` completed

## Rust (crates.io)

```bash
cd rust
cargo publish --dry-run
cargo publish
```

Requires:
- `cargo login` with crates.io API token

## Go Module

```bash
cd go
# Tag the release
git tag go/v0.1.0
git push origin go/v0.1.0
# The Go module proxy will pick up the new version automatically
```

## Versioning

This project follows Semantic Versioning:

- **0.x** (current): API may change; changes documented in CHANGELOG.
- **1.0.0**: All core APIs stable across all languages.

## Pre-Publish Checklist

- [ ] All register values verified against datasheet
- [ ] All test vectors confirmed across all languages
- [ ] C library builds with CMake on Linux, macOS, Windows
- [ ] Python package installs cleanly from PyPI
- [ ] Rust crate compiles with `no_std` and `std`
- [ ] Node package builds and tests pass
- [ ] Go module tests pass
- [ ] README updated with correct version
- [ ] CHANGELOG updated
- [ ] Tag created in git
