# Publishing Guide

> **Current state (2026-08-02):** [`v0.1.0-alpha.3`](https://github.com/oaslananka/adxl355/releases/tag/v0.1.0-alpha.3)
> is published as a GitHub prerelease from exact commit
> `71de69b8727a9f8eef254de586d9bce7bc8fa8ac`. Matching package versions are
> public as PyPI `adxl355==0.1.0a3`, npm `@oaslananka/adxl355@0.1.0-alpha.3`,
> and crates.io `adxl355-driver@0.1.0-alpha.3`. Release Gate run
> `30748595754` published the verified Python wheel and sdist through PyPI
> Trusted Publishing; their public SHA-256 digests match the workflow artifacts
> byte-for-byte. npm and crates.io were bootstrap-published from the same release
> tag and were subsequently verified idempotently by the workflow. TestPyPI is
> not published and is not part of the production release workflow.
> Final SPI run `30736413982` and I2C run `30736668298` passed on the release
> commit with device revision `0x01`; permanent sanitized reports remain attached
> to the GitHub release. `REGISTRY_PUBLISHING_ENABLED` is returned to `false`
> after each controlled publication attempt.

## Risk-based physical HIL policy

**Daily CI, code review, dependency updates, builds and package dry runs do
not require a connected ADXL355.** Physical HIL is an opt-in activity for
sensor-facing changes, not a recurring developer task.

The tag-triggered release workflow uses `hil-policy` **before any registry
publication**. Its baseline is the previously published release with verified
paired SPI/I2C evidence (see `docs/hil-validated-baseline.json`). Both archived
reports are addressed by immutable SHA-256 hashes. The gate uses the exact
tagged release commit and its ancestry, not a moving branch.

- **Software-only changes:** documentation, conventional maintenance, safe
  test-only changes and selected CI metadata may reuse prior physical HIL.
  They still must pass the complete protected release CI/security/package
  gates.
- **Sensor-facing or unrecognized changes:** the driver, buses/adapters,
  register definitions, HIL workflow, or release acceptance mechanism cannot
  inherit previous HIL. The release publication gate stops, clearly reporting
  the affected paths. Restore a physical fixture *only then*, run paired SPI
  and I2C against a known candidate SHA, verify and archive both reports, and
  update the immutable accepted baseline under normal code review before
  publishing a subsequent candidate. The new baseline names the exact tested
  ancestor `validated_commit`, both released HIL report file names and
  SHA-256 digests, and the authoritative two GitHub HIL workflow run URLs.
  Do **not** invent a release tag for an as-yet-unpublished candidate or
  rewrite earlier evidence. The new run reports must independently confirm
  `success: true`, the tested commit and safe standby restoration.
  After the baseline update is merged, only documentation/evidence changes
  may separate the accepted SHA from the eventual release SHA.
- **No silent waiver:** an absent sensor, failed scan, missing baseline, or
  changed evidence-validation policy never turns into a successful HIL result.
  Modifying `VERSION` alone is not proof that the existing `0.1.0` candidate
  preserves its previously tested hardware behavior.

Run `bash scripts/check_hil_release.sh "$(git rev-parse HEAD)"` in Git
Bash or Linux to evaluate the exact checked-out commit. The check exits with
status 2 and lists the changed hardware-facing paths if new HIL is needed. The report contains no secrets or external uploads.
This rule does not automatically publish a release and does not change the
protected publishing environment or `REGISTRY_PUBLISHING_ENABLED=false`.

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
That bootstrap path was used for `adxl355`; no PyPI password or API token was added
to GitHub. Release Gate run `30748595754` exchanged GitHub OIDC through
`pypa/gh-action-pypi-publish` and created `adxl355==0.1.0a3` from the previously
verified wheel and sdist.

Independent verification downloaded both public files, matched their SHA-256
values to the workflow artifacts, installed the exact version in a clean virtual
environment, and imported `adxl355`. The production page is
`https://pypi.org/project/adxl355/`. TestPyPI is a separate registry and remains
outside this workflow.

### npm: `@oaslananka/adxl355`

npm requires the package to exist before a Trusted Publisher can be attached. The
first package reservation/publication for `0.1.0-alpha.3` used a one-time
maintainer bootstrap. The maintained sequence is:

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
configured. That initial crate release, `adxl355-driver@0.1.0-alpha.3`, was
bootstrap-published from the exact
verified `.crate`. Configure the binding above, enable trusted-publishing-only
mode, and keep the bootstrap credential revoked. Subsequent new-version workflow
runs obtain an ephemeral token through `rust-lang/crates-io-auth-action`; the
action revokes that token in its post step.

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
jobs and approve the `release` environment. The existing `v0.1.0-alpha.3` tag was
never moved or recreated; a controlled manual verification run used that immutable
tag to complete the PyPI bootstrap while npm and crates.io were safely recognized
as already published. Keep the variable `false` outside an approved release
attempt; a missing or drifting publisher binding must fail rather than silently
fall back to a token.

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
- [ ] Risk-based HIL check is green: if sensor behavior changed, paired SPI/I2C evidence is recorded on the validated candidate and no older than 30 days; otherwise reuse the unchanged validated physical baseline
- [ ] Required CI and the aggregate high-severity vulnerability gate pass
- [ ] Package checksums, size reports, SBOM, and bundle attestations verify
- [ ] Python wheel, npm tarball, and Rust crate install from clean consumers
- [ ] Registry package pages expose repository, license, changelog, and security links
- [ ] No long-lived registry credential is configured in GitHub
- [ ] Partial-failure recovery preserves every immutable tag and version

### Deterministic source archives

Before checksums and attestations, the release workflow normalizes the Python
sdist tar and gzip metadata using `scripts/normalize_sdist.py` and the commit's
`SOURCE_DATE_EPOCH`. This preserves source file contents while fixing nonsemantic
archive timestamps, owner IDs and entry order. The Python wheel, Rust crate,
npm package and C static library were reproduced byte-for-byte in independent
local builds on 2026-11-04. The evidence and the opt-in repeat command live in
[quality evidence](quality-evidence.md). Bitwise identity on a single controlled
Linux toolchain does not prove cross-platform reproducibility or hardware behavior.
