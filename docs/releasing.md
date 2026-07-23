# Release gate

The release workflow is a **verification and packaging dry run**. It does not
publish to PyPI, crates.io, npm, GitHub Releases, or any Go proxy.

## Preconditions

A release tag must:

1. use strict SemVer with a leading `v`;
2. point to the exact commit selected by the workflow;
3. match the canonical root `VERSION` file after ecosystem mapping, including
   Python PEP 440, Rust/npm SemVer, CMake core versions, lockfiles, shared
   vectors, and the generated C version header;
4. be checked out from a clean source tree.

CMake project versions are compared to the numeric `major.minor.patch` portion
because CMake's `project(VERSION ...)` field does not represent prerelease
metadata. Rust, npm, shared vectors, and `ADXL355_VERSION_STRING` match the complete
SemVer value. Python uses the equivalent PEP 440 value. See
[`versioning.md`](versioning.md) for the source of truth and Go submodule tag.

## External hardware evidence prerequisite

The packaging workflow cannot safely schedule a physical lab fixture. Before a
production-ready release claim, maintainers must attach successful manual HIL
evidence for both SPI and I2C to the release record. Each artifact must reference
the release-candidate commit, include the device revision, and be no more than 30
days old. See [`hardware-testing.md`](hardware-testing.md) for fixture and address
coverage requirements.

## Enforced gates

The workflow calls the repository CI workflow on the release commit. Package
jobs require both CI and the preflight job, so a failed test or version mismatch
prevents artifact generation.

Each package job checks out the preflight SHA explicitly, performs a clean-tree
check, builds without publishing, inspects archive contents, installs or consumes
the built artifact in a clean temporary environment, generates SHA-256 checksums,
and uploads an inspectable artifact.

The final job downloads every verified package artifact, creates aggregate
checksums and metadata, generates an SPDX JSON SBOM, and scans that SBOM with
Grype. A high severity or critical vulnerability blocks bundle creation even when
no upstream fix is available. It then creates a final compressed release bundle,
records its SHA-256 digest, and uses GitHub OIDC to persist SLSA provenance and an
SBOM attestation. Only that final job receives `id-token`, `attestations`, and
`artifact-metadata` write permissions.

Verify a downloaded final bundle with:

```bash
gh attestation verify adxl355-release-*.tar.gz --repo oaslananka/adxl355
sha256sum --check RELEASE_BUNDLE_SHA256SUMS
```

See [`security/supply-chain.md`](security/supply-chain.md) for scanner ownership,
exception rules, immutable action updates, and trusted publishing policy.

## Version-mismatch fixture

`scripts/tests/test_release_preflight.py` copies the maintained version files to
a temporary fixture, intentionally changes `node/package.json` from `0.1.0-alpha.2` to
`0.1.1`, and verifies that preflight fails with a path-specific mismatch. The
fixture runs in normal CI and in the release preflight job.

Run the release automation tests locally with:

```bash
python -m unittest discover -s scripts/tests -p 'test_*.py' -v
```
