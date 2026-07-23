# Software supply-chain policy

This repository uses one primary control for each security category. External
services may provide supplementary review, but the repository does not add
multiple local scanners that enforce the same policy with duplicate findings.

## Control ownership

| Category | Primary control | Enforcement |
|---|---|---|
| Dependency updates | Dependabot | Weekly, grouped PRs for GitHub Actions, Python, Rust, Node.js, and Go; at most two open version-update PRs per ecosystem |
| Changed dependencies in pull requests | GitHub Dependency Review | A newly introduced dependency finding at **high severity** or critical severity blocks the PR |
| Static application security testing | CodeQL | Required analysis for C/C++, Python, JavaScript/TypeScript, and Go on pull requests, `main`, and a weekly schedule |
| Secret prevention | GitHub secret scanning and push protection | Repository setting; secrets are blocked before push where GitHub can identify them |
| Release inventory | Syft through `anchore/sbom-action` | SPDX JSON SBOM generated from the verified release artifacts |
| Release vulnerability policy | Grype through `anchore/scan-action` | Any high severity or critical result blocks the release bundle, whether or not a fix is already published |
| Artifact integrity and provenance | SHA-256 checksums plus `actions/attest` | GitHub OIDC produces SLSA provenance and an SBOM attestation for the final release bundle |
| Private disclosure | GitHub Security Advisories | Private vulnerability reporting with the response targets in `SECURITY.md` |

CodeQL is the primary SAST result for repository-owned workflow policy. Sonar,
Semgrep, DeepScan, and Socket may appear as supplementary hosted checks. Their
presence does not justify adding another overlapping scanner workflow here.

## Dependabot maintenance policy

`.github/dependabot.yml` groups all version updates within each ecosystem into a
single weekly PR. Schedules are staggered in the `Europe/Istanbul` timezone and
`open-pull-requests-limit` is set to two per ecosystem. Security updates and
vulnerability alerts are enabled in repository settings.

Dependency PRs must pass the same CI, CodeQL, dependency review, and package
checks as contributor PRs. Do not merge an update only because it is automated;
review release notes, lockfile changes, package contents, and any bot comments.

Compatibility caps must be narrow and documented. The Python package now requires
Python 3.10 or later so its build backend can use patched `setuptools>=83` rather
than retaining a vulnerable backend for Python 3.9 compatibility. Dependency
updates must not be capped below a security fix without a dated, reviewed exception.

## Immutable GitHub Actions

Every external `uses:` reference is pinned to a **full commit SHA**. A version
comment beside the SHA records the reviewed upstream release.

Dependabot groups GitHub Actions updates. When reviewing an action update:

1. confirm the commit belongs to the expected upstream release tag;
2. read release notes and breaking changes;
3. inspect permission or runtime changes;
4. run actionlint and the workflow contract tests;
5. retain the full commit SHA rather than a mutable major tag.

Local reusable workflows under `./.github/workflows/` are repository content and
do not require an external SHA. Node.js 24-based official actions require
self-hosted GitHub Actions Runner 2.327.1 or newer; the HIL fixture must be upgraded
before those action revisions are merged.

## Release dependency gate

The release workflow first builds and smoke-tests every package artifact. It
then generates `release.spdx.json`, scans that SBOM with Grype, and fails when a
high severity or critical vulnerability is present. The gate does not use
`only-fixed`; lack of a published fix is not a reason to ship an unreviewed high
severity finding.

A temporary exception requires all of the following in a public tracking issue
or private advisory, depending on sensitivity:

- affected package and advisory identifier;
- exploitability and impact analysis for this repository;
- named owner;
- compensating controls;
- explicit expiry or reassessment date;
- release notes when users need to take action.

Do not add a blanket ignore or silently lower the severity threshold.

## SBOM, checksums, and attestations

The release bundle contains:

- every verified ecosystem artifact;
- per-package and aggregate SHA-256 checksums;
- an SPDX JSON SBOM;
- the JSON vulnerability scan result;
- release metadata identifying the tag and commit;
- a checksum for the final aggregate tarball.

The final tarball receives both SLSA build provenance and an SBOM attestation
through GitHub OIDC. The workflow grants `id-token: write`, `attestations: write`,
and `artifact-metadata: write` only to the bundle job. Package build jobs retain
read-only repository permissions.

After downloading a bundle, verify its GitHub attestation with a command such as:

```bash
gh attestation verify adxl355-release-*.tar.gz --repo oaslananka/adxl355
sha256sum --check RELEASE_BUNDLE_SHA256SUMS
```

## Trusted publishing design

Registry publishing remains disabled by default. When publication is explicitly
enabled, it must use a protected GitHub environment and **trusted publishing**
or an equivalent short-lived credential flow. The default design requires no long-lived registry token.

- **PyPI:** configure this repository and the dedicated release workflow as a
  PyPI Trusted Publisher. Publishing uses GitHub OIDC and a short-lived token.
- **npm:** configure `@oaslananka/adxl355` with npm trusted publishing on a
  GitHub-hosted runner. npm trusted publishing provides package provenance
  automatically for a public package from a public repository.
- **crates.io:** configure trusted publishing for `adxl355-driver` and enable
  trusted-publishing-only mode after the first verified release. Do not fall
  back to a stored `CARGO_REGISTRY_TOKEN` in the default workflow.
- **Go:** publication uses the immutable `go/v...` Git tag and the public module
  proxy; it does not require a registry credential.

Registry trust must be bound to the exact repository, workflow filename, and
protected environment. A change to the release workflow or environment is a
security-sensitive change and requires maintainer review.

## Verification commands

```bash
python -m unittest scripts.tests.test_supply_chain -v
python -m unittest discover -s scripts/tests -p 'test_*.py' -v
actionlint .github/workflows/*.yml
```
