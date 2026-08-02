# Publishing Guide

> **Current state (2026-08-02):** [`v0.1.0-alpha.3`](https://github.com/oaslananka/adxl355/releases/tag/v0.1.0-alpha.3)
> is published as a GitHub prerelease from exact commit
> `71de69b8727a9f8eef254de586d9bce7bc8fa8ac`. PyPI `adxl355`, npm
> `@oaslananka/adxl355`, and crates.io `adxl355-driver` were re-checked and were
> not yet published. The repository release workflow contains protected OIDC
> publication jobs, but they remain disabled until all registry-side publisher
> bindings and first-release ownership prerequisites are complete.
> PyPI, npm, and crates.io remain unpublished. Final SPI run `30736413982`
> and I2C run `30736668298` passed on the release commit with device revision
> `0x01`; permanent sanitized reports remain attached to the GitHub release.

## Automated release verification and publication boundary

Pushing a root `v*` tag starts `.github/workflows/release.yml`. The workflow always:

1. re-runs required CI on the tagged commit;
2. verifies tag, commit, and ecosystem version identity;
3. builds each package exactly once;
4. inspects and smoke-tests the built artifacts;
5. records per-package checksums and size evidence;
6. creates and scans the aggregate SPDX release bundle; and
7. attests the final bundle with GitHub OIDC.

Registry publication is a later, separate phase in the same workflow. It runs only
when the repository variable `REGISTRY_PUBLISHING_ENABLED` equals `true`, after the
aggregate bundle succeeds, and after the protected `release` environment is
approved. The publication jobs download the already-verified artifacts from the
same workflow run; they do not rebuild Python or npm packages. The Rust job
repackages the exact tagged source and requires its `.crate` SHA-256 to equal the
previously verified artifact before requesting a short-lived crates.io credential.

Publication jobs use GitHub-hosted `ubuntu-24.04` runners with only:

```yaml
permissions:
  contents: read
  id-token: write
environment: release
```

No registry token secret is read by `.github/workflows/release.yml`. No long-lived registry token is required or permitted by the default design.

## Exact trusted-publisher bindings

Configure each registry with these exact values. A filename or environment change
requires updating the registry binding before publication is re-enabled.

| Registry | Package | GitHub owner | Repository | Workflow | Environment |
|---|---|---|---|---|---|
| PyPI | `adxl355` | `oaslananka` | `adxl355` | `release.yml` | `release` |
| npm | `@oaslananka/adxl355` | `oaslananka` | `adxl355` | `release.yml` | `release` |
| crates.io | `adxl355-driver` | `oaslananka` | `adxl355` | `release.yml` | `release` |

The GitHub `release` environment is restricted to tags matching `v[0-9]*` and
requires review by `@oaslananka`. Publication must remain disabled if that
protection or any registry binding drifts.

## Registry bootstrap sequence

### PyPI: `adxl355`

PyPI supports a pending Trusted Publisher for a project that does not yet exist.
Create the pending publisher with the exact binding above. No PyPI password or API
token belongs in GitHub secrets. After the binding exists, the protected workflow
can create the first project release through
`pypa/gh-action-pypi-publish` using GitHub OIDC.

The Python metadata publishes direct links to the repository, documentation,
changelog, security policy, and issue tracker. After the first release, verify the
page at `https://pypi.org/project/adxl355/` and install the exact version in a clean
environment.

### npm: `@oaslananka/adxl355`

npm requires the package to exist before a Trusted Publisher can be attached. The
first package reservation/publication is therefore a one-time maintainer bootstrap:

1. re-check that the `oaslananka` scope is controlled by the maintainer account;
2. publish the already-verified `.tgz` with a short-lived, least-privilege npm
   credential from a clean maintainer environment;
3. bind the package to the exact GitHub workflow/environment above;
4. revoke the bootstrap credential immediately; and
5. verify later releases use npm CLI 11.5.1 or newer and GitHub OIDC only.

Do not store the bootstrap credential in repository, environment, or organization
secrets. The package README links to the repository, changelog, security policy,
and license. Verify the first release at
`https://www.npmjs.com/package/@oaslananka/adxl355`.

### crates.io: `adxl355-driver`

crates.io also requires an initial crate release before Trusted Publishing can be
configured. Use the same one-time bootstrap pattern with the exact verified
`.crate`, then configure the binding above, enable trusted-publishing-only mode,
and revoke the bootstrap credential. Subsequent workflow runs obtain an ephemeral
token through `rust-lang/crates-io-auth-action`; the action revokes that token in
its post step.

The crate README links to the repository, changelog, security policy, and license.
Verify the first release at `https://crates.io/crates/adxl355-driver` and confirm
`docs.rs` builds the intended public surface.

## Enabling publication

Enable the repository variable only after all three registry-side prerequisites
are satisfied:

```text
REGISTRY_PUBLISHING_ENABLED=true
```

Create the next immutable release tag from a commit that already contains this
workflow, then let the tag-triggered release run reach the protected publication
jobs and approve the `release` environment. The existing `v0.1.0-alpha.3` tag
predates these jobs and must not be moved or recreated. Keep the variable `false`
while any package binding is absent; otherwise the corresponding publish job must
fail rather than silently fall back to a token.

## Idempotent retry and partial-publication recovery

`scripts/registry_release.py` compares the downloaded artifact to public registry
metadata before and after each publish operation:

- an absent version is eligible for publication;
- an existing version with the exact expected digest is treated as already
  published and skipped safely;
- a partial file set, changed digest, or identity mismatch is a hard failure.

If one registry succeeds and another fails, fix only the failed binding/service and
rerun the same workflow for the same immutable tag. Already-published exact
artifacts are skipped; missing artifacts are published. Never increment or move a
tag merely to retry an infrastructure failure.

If the registry contains the same version with a different digest, stop. Preserve
the evidence, disable `REGISTRY_PUBLISHING_ENABLED`, remove or disable the affected
publisher binding, and investigate through private security channels when tampering
is possible.

## Rollback and deprecation

Published artifacts are immutable. Do not delete or overwrite a released version
to hide a defect.

- **PyPI:** publish a corrected higher version. When appropriate, yank the
  affected release with a reason so existing locked installs remain resolvable.
- **npm:** publish a corrected higher version. Use `npm deprecate` with an
  actionable message for the affected version range; do not use `npm unpublish`
  as a routine rollback mechanism.
- **crates.io:** publish a corrected higher version and yank the affected crate
  version when necessary. Yanking prevents new resolution without breaking
  existing lockfiles.
- **Go module:** never move or recreate a public tag. Publish a higher `go/v...`
  tag. If a module version must be retracted, add a `retract` directive in a newer
  `go.mod` release with a reason.
- **GitHub artifacts/tags:** preserve checksums and the original tag. Mark the
  release as affected and point users to the replacement version.

Every rollback or deprecation must be recorded in the changelog and security
advisory process when the defect has security impact.

## Go module

The nested Go module uses its own immutable tag:

```bash
git tag go/v0.1.0-alpha.3
git push origin go/v0.1.0-alpha.3
```

The public Go proxy discovers the tag without a registry credential.

## Pre-publish checklist

- [ ] Registry names and account ownership were re-checked immediately before use
- [ ] Exact trusted-publisher bindings match the table above
- [ ] The protected `release` environment still restricts `v[0-9]*` tags and requires review
- [ ] `REGISTRY_PUBLISHING_ENABLED` is `true` only for an approved release attempt
- [ ] HIL evidence for both SPI and I2C is successful on the release-candidate commit and no older than 30 days
- [ ] Required CI and the aggregate high-severity vulnerability gate pass
- [ ] Package checksums, size reports, SBOM, and bundle attestations verify
- [ ] Python wheel, npm tarball, and Rust crate install from clean consumers
- [ ] Registry package pages expose repository, license, changelog, and security links
- [ ] No long-lived registry credential is configured in GitHub
- [ ] Partial-failure recovery preserves every immutable tag and version
