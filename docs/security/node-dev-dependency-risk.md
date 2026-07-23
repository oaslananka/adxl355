# Node Development Dependency Risk Acceptance

## Decision

The repository temporarily accepts Socket's obfuscated-code warning for
`@emnapi/runtime@1.11.1` until **2026-10-23**.

## Scope

- The package is not a direct dependency. It appears only in `package-lock.json`
  beneath the optional `@rolldown/binding-wasm32-wasi` development path used by
  Vitest 4.
- It is not installed on the supported Linux x64 CI runner (`npm ls
  @emnapi/runtime` returns no installed dependency).
- It is not part of the published `adxl355` npm package. The package allow-list
  permits only compiled `dist` output and package metadata.
- CI installs locked dependencies with `npm ci --ignore-scripts`, and
  `npm audit --audit-level=moderate` currently reports zero vulnerabilities.
- The warning is a heuristic obfuscation signal, not a published vulnerability.

## Rationale

Vitest 4 removes the known vulnerable Vite/esbuild chain present in the previous
Vitest 2 lockfile. Reverting would restore known audit findings, while replacing
the test framework solely for an optional, non-installed WASM fallback would add
substantial migration risk without reducing shipped-package exposure.

## Review and Expiry

The maintainer must reassess this acceptance no later than **2026-10-23**, and
sooner when Vitest/Rolldown changes the optional WASM dependency or Socket changes
its classification. The acceptance must be removed when a supported test-tool
version no longer carries the alert, or the test runner must be replaced.

This acceptance is limited to `@emnapi/runtime@1.11.1`; it is not a blanket ignore
for Socket alerts or Node development dependencies.
