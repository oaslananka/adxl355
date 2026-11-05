# Release gate

The release workflow always performs verification, packaging, aggregate scanning,
and attestation before any registry operation. Protected PyPI, npm, and crates.io
publication jobs are present but run only when the repository variable
`REGISTRY_PUBLISHING_ENABLED` equals `true`. They require approval through the
`release` environment and GitHub OIDC; no stored registry credential is used. The
Go module continues to publish through an immutable `go/v...` tag.

The `v0.1.0-alpha.3` artifacts are public on PyPI, npm, and crates.io. Controlled
Release Gate run `30748595754` performed the first PyPI OIDC publication and
verified the already-published exact npm and crates.io artifacts. TestPyPI is not
part of this production workflow.

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

**Normal CI and package dry runs do not require an ADXL355 or physical runner.**
For registry publication, the `hil-policy` job compares the exact release commit
with the last physical HIL-validated baseline. If only documentation, tests or
known hardware-neutral maintenance changed, previous paired SPI/I2C evidence
may be reused. Any sensor-facing, unknown, or release policy change fails
closed until paired physical SPI/I2C acceptance is verified and the baseline
is updated under the protected repository rules. See
[`publishing.md`](publishing.md#risk-based-physical-hil-policy).

The packaging workflow cannot schedule a physical lab fixture. A
**production-ready hardware certification claim** remains stricter: successful
manual HIL evidence for both SPI and I2C must reference the exact candidate,
include the device revision, and be no more than 30 days old. No CI status
alone supplies a physical certification. See
[`hardware-testing.md`](hardware-testing.md) for fixture and address
coverage requirements.

## Current evidence status

The Raspberry Pi 5 SPI fixture has passed on `main` in workflow run
[30725059679](https://github.com/oaslananka/adxl355/actions/runs/30725059679), and
the `0x1D` I2C fixture has passed in workflow run
[30734635341](https://github.com/oaslananka/adxl355/actions/runs/30734635341).
These are feature and fixture evidence. New paired SPI and I2C runs are
required for sensor-affecting changes; software-only changes may reuse
verified historical acceptance under the release `hil-policy` gate. The
current `0.1.0` candidate still has hardware-affecting changes relative to
the accepted physical baseline, so the gate reports HIL REQUIRED. Do not
present that state as a completed physical validation.

## Enforced gates

The workflow calls the repository CI workflow on the release commit. Package
jobs require both CI and the preflight job, so a failed test or version mismatch
prevents artifact generation.

Each package job checks out the preflight SHA explicitly, performs a clean-tree
check, builds without publishing, inspects archive contents, installs or consumes
the built artifact in a clean temporary environment, generates SHA-256 checksums,
and uploads an inspectable artifact. Optional publication jobs download these exact
artifacts only after the final bundle succeeds. Registry preflight treats an exact
existing digest as an idempotent success and rejects partial or changed releases.
Each package job also enforces the reviewed compressed-size budget and uploads a
machine-readable `SIZE_REPORT.json`. The final bundle is checked separately and
publishes `RELEASE_SIZE_REPORT.json`. A size-limit change is a reviewed release
policy change, not an automatic response to a failing build; see
[`testing.md`](testing.md) for measurement and update rules.

The final job downloads every verified package artifact, creates aggregate
checksums and metadata, generates an SPDX JSON SBOM, and scans that SBOM with
Grype. A high severity or critical vulnerability blocks bundle creation even when
no upstream fix is available. It then creates a final compressed release bundle,
records its SHA-256 digest, and uses GitHub OIDC to persist SLSA provenance and an
SBOM attestation. Only that final job receives `attestations` and
`artifact-metadata` write permissions. The three optional registry jobs separately
receive only `contents: read` and `id-token: write`, run on GitHub-hosted runners,
and are protected by the `release` environment.

Verify a downloaded final bundle with:

```bash
gh attestation verify adxl355-release-*.tar.gz --repo oaslananka/adxl355
sha256sum --check RELEASE_BUNDLE_SHA256SUMS
```

See [`security/supply-chain.md`](security/supply-chain.md) for scanner ownership,
exception rules, immutable action updates, and trusted publishing policy.

## Version-mismatch fixture

`scripts/tests/test_release_preflight.py` copies the maintained version files to
a temporary fixture, intentionally changes `node/package.json` from `0.1.0`
to `0.1.1`, and verifies that preflight fails with a path-specific mismatch. The
fixture runs in normal CI and in the release preflight job.

Run the release automation tests locally with:

```bash
python -m unittest discover -s scripts/tests -p 'test_*.py' -v
```
