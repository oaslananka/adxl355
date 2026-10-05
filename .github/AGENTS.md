# CI, HIL, and Release Instructions

These instructions apply to `.github/**` and supplement the root instructions.

## CI integrity

- Preserve one stable primary quality job per maintained language and the final cross-language vector gate.
- Do not weaken warnings-as-errors, sanitizers, race checks, package smoke tests, dependency auditing, zero-skip vector verification, or coverage gates to make CI green.
- Keep third-party Actions pinned to reviewed immutable revisions and permissions least-privilege.
- A language-specific failure must not be bypassed by the aggregate cross-language job.

## HIL boundary

Physical HIL is separate from default PR CI.

- Keep HIL manual/dedicated-runner only unless the project intentionally changes that contract.
- HIL reports must be bounded and sanitized; do not dump environment variables, credentials, or unrelated host state.
- A HIL failure never causes normal CI to skip or weaken deterministic checks.
- Do not promote a feature-specific run into broader bus/language/board evidence.

## Release integrity

- Release preflight must bind tag, commit SHA, package versions, Go tag, artifact identities, and generated evidence to one release identity.
- Keep package dry-runs before publication.
- Preserve checksums, SPDX SBOM generation, high-severity vulnerability blocking, provenance/SBOM attestations, and exact clean-checkout verification.
- Trusted/OIDC publishing is the normal registry path; do not add long-lived token fallbacks.
- Released tags and bytes are immutable.

Workflow changes require focused policy/security review in addition to YAML validity.
