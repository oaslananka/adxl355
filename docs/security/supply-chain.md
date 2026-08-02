# Software supply-chain policy

This repository uses one primary control for each security category. External
services may provide supplementary review, but the repository does not add
multiple local scanners that enforce the same policy with duplicate findings.

## Control ownership

| Category | Primary control | Enforcement |
|---|---|---|
| Dependency updates | Dependabot | Weekly, grouped PRs for GitHub Actions, Python, Rust, Node.js, and Go; seven-day cooldown and at most two open version-update PRs per ecosystem |
| Changed dependencies in pull requests | GitHub Dependency Review | A newly introduced dependency finding at **high severity** or critical severity blocks the PR |
| Static application security testing | CodeQL | Required analysis for C/C++, Python, JavaScript/TypeScript, and Go on pull requests, `main`, and a weekly schedule |
| Secret prevention | GitHub secret scanning and push protection | Repository setting; secrets are blocked before push where GitHub can identify them |
| Release inventory | Syft through `anchore/sbom-action` | SPDX JSON SBOM generated from the verified release artifacts |
| Release vulnerability policy | Grype through `anchore/scan-action` | Any high severity or critical result blocks the release bundle, whether or not a fix is already published |
| Artifact integrity and provenance | SHA-256 checksums plus `actions/attest` | GitHub OIDC produces SLSA provenance and an SBOM attestation for the final release bundle |
| Private disclosure | GitHub Security Advisories | Private vulnerability reporting with the response targets in `SECURITY.md` |
| Project security health | OpenSSF Scorecard | Weekly, default-branch, and ruleset-change analysis; bounded SARIF is uploaded to code scanning and the intended public Scorecard API summary |

CodeQL is the primary SAST result for repository-owned workflow policy. Sonar,
Semgrep, DeepScan, and Socket may appear as supplementary hosted checks. Their
presence does not justify adding another overlapping scanner workflow here.

## OpenSSF project-health evidence

The official OpenSSF Scorecard Action runs on `main`, a weekly schedule, manual
dispatch, and branch-protection/ruleset changes. It uses only repository read,
SARIF upload, and OIDC publication permissions. The bounded five-day SARIF
artifact supports diagnosis; GitHub code scanning and the public Scorecard API
are the durable review surfaces. Raw scan dumps are not committed.

Scorecard is a project-health signal, not a replacement for CodeQL, dependency
review, release scanning, or physical HIL. Findings are triaged only when they
map to a reproducible repository setting or workflow gap. Numeric score changes
alone do not create release blockers.

For OSPS Baseline Level 1, live repository controls provide the principal
evidence: public version control and licensing, documented contribution and
security processes, protected `main`, required CI/security checks, dependency
maintenance, immutable action pins, private vulnerability reporting, and
checksummed/SBOM-attested release artifacts. OpenSSF Best Practices registration
is an external maintainer-owned project record; its registration status is
tracked in the implementation issue rather than represented by a repository
metadata or audit file.

## Dependabot maintenance policy

`.github/dependabot.yml` groups all version updates within each ecosystem into a
single weekly PR. Schedules are staggered in the `Europe/Istanbul` timezone,
`open-pull-requests-limit` is set to two per ecosystem, and newly published
versions wait seven days before Dependabot proposes them. GitHub security updates
are not delayed by this cooldown; vulnerability alerts and security updates remain
enabled in repository settings.

Dependency PRs must pass the same CI, CodeQL, dependency review, and package
checks as contributor PRs. Do not merge an update only because it is automated;
review release notes, lockfile changes, package contents, and any bot comments.

Compatibility caps must be narrow and documented. The Python package now requires
Python 3.10 or later so its build backend can use patched `setuptools>=83` rather
than retaining a vulnerable backend for Python 3.9 compatibility. Dependency
updates must not be capped below a security fix without a dated, reviewed exception.

## Hash-locked Python workflow tooling

Third-party Python packages downloaded by CI, release verification, and the
self-hosted HIL workflow are installed from reviewed files below
`requirements/python/` with `pip --require-hashes`. Separate lock groups reflect
the actual trust and runtime boundaries: the Python test matrix, Python 3.12
quality/build tools, Python 3.11 cross-language verification, Python 3.11 release
builds, HIL build tooling, and SPI/I2C adapters.

Each `.in` file is an explicit, sorted list of exact direct and transitive package
versions. `scripts/generate_python_locks.py` uses only the Python standard library
to read the public PyPI JSON API and records every non-yanked release-file SHA-256
for each reviewed version. It rejects ranges, direct URLs, alternate indexes,
trusted hosts, credentials, duplicates, and unsorted inputs. Generated `.txt`
files contain no timestamp, index URL, or environment-specific secret. Workflows
ignore host pip configuration and explicitly use only `https://pypi.org/simple`,
so an inherited mirror or extra index cannot silently supply a different file.

Check public PyPI for newer versions, then regenerate only after reviewing the
intended update:

```bash
python scripts/generate_python_locks.py --check-latest
# Edit the exact versions in the relevant requirements/python/*.in files.
python scripts/generate_python_locks.py
python scripts/generate_python_locks.py --verify
python -m unittest scripts.tests.test_python_locks -v
```

`--check-latest` is read-only and reports every group/current/latest tuple. It does
not choose compatibility policy or rewrite files. Review both sides of the final
change: `.in` files prove which package versions are intended, while `.txt` files
show the authenticated PyPI artifact set. Unexpected new packages, removed hashes,
yanked-only releases, source-only substitutions, or large platform expansion
require investigation before merge.

Dependabot remains weekly and rate-limited for the normal `/python` package
metadata. It is intentionally **not** configured for `/requirements/python`:
Dependabot edits both reviewed `.in` manifests and generated `.txt` files without
running this repository's generator, which can remove required build backends or
leave the pair inconsistent. Custom lock updates therefore use the documented
report/edit/regenerate workflow and must pass the offline verifier, dependency
review, and full CI.

Workflow installs use `--only-binary=:all:` where every package has a compatible
wheel. The SPI adapter is the narrow source-build exception because `spidev` is
distributed as a source archive; HIL installs the locked build tools first, then
installs the hash-verified adapter with `--no-build-isolation --no-deps`.

The PlatformIO lock is a second, command-scoped exception to a full upstream
runtime closure. PlatformIO Core 6.1.19 declares `starlette<0.53`, `uvicorn<0.41`,
and `wsproto==1.*` for its web/server features. Starlette versions below 1.1.0 are
affected by [GHSA-wqp7-x3pw-xc5r](https://github.com/advisories/GHSA-wqp7-x3pw-xc5r),
and versions below 1.3.1 are affected by
[GHSA-82w8-qh3p-5jfq](https://github.com/advisories/GHSA-82w8-qh3p-5jfq), so no
patched Starlette release satisfies PlatformIO's declared range. The required CI
job therefore installs a reviewed 16-package closure only for `pio --version`,
`pio pkg pack`, and `pio run`. It explicitly verifies that Starlette, Uvicorn,
wsproto, AnyIO, and h11 are absent. PlatformIO Home, web/server, remote-agent, and
other commands outside that tested surface are not supported by this environment.
A future PlatformIO release may restore a full dependency closure only after its
metadata permits patched packages and the same package/build tests pass.

Repository-local editable installs and locally built wheel smoke tests are not
external downloads; they remain separate, dependency-free, and use
`--no-build-isolation` or `--no-deps` as appropriate. No private index or registry
credential is used.

## Immutable GitHub Actions

Every external `uses:` reference is pinned to a **full commit SHA**. A version
comment beside the SHA records the reviewed upstream release.

Dependabot groups GitHub Actions updates. When reviewing an action update:

1. confirm the commit belongs to the expected upstream release tag;
2. read release notes and breaking changes;
3. inspect permission or runtime changes, including the minimum self-hosted
   runner version required by the action's Node.js runtime;
4. run actionlint and the workflow contract tests;
5. retain the full commit SHA rather than a mutable major tag.

Local reusable workflows under `./.github/workflows/` are repository content and
do not require an external SHA.

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

## Supplementary local audits

Hosted checks remain the merge authority, but maintainers can reproduce targeted
security audits locally without adding duplicate required workflows:

```bash
semgrep scan --config p/default --config p/security-audit --config p/secrets --metrics off .
osv-scanner scan source -r --call-analysis=go .
sonar analyze secrets $(git ls-files)
```

Use Semgrep for source and configuration patterns, OSV-Scanner for known dependency
vulnerabilities, and SonarQube CLI for an independent secret scan. Run OSV with a
supported Go toolchain so call analysis can suppress unreferenced standard-library
advisories. General SonarQube code analysis requires an authenticated project and
organization entitlement; lack of that entitlement is not a code finding.

These commands are supplementary evidence. CodeQL remains the primary SAST gate,
GitHub Dependency Review remains the pull-request dependency gate, and the release
SBOM/Grype job remains the release vulnerability gate.

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
