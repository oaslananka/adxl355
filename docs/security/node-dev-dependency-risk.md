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

## 2026-08-02 reassessment after Linux adapter addition

The optional Linux runtime adapters do not broaden this acceptance:

- `spi-device@3.1.2` and `i2c-bus@5.2.3` are exact `optionalDependencies`, not
  development-only WASM fallbacks.
- Both native addons were built from the lockfile and loaded successfully on
  Node.js 22.23.1, 24.18.0, and 26.5.0 on Linux x64.
- The combined native dependency closure reported zero npm audit findings at
  moderate or higher severity on all three runtimes.
- CI continues to begin with `npm ci --ignore-scripts`; it then explicitly runs
  only `npm rebuild spi-device i2c-bus --foreground-scripts` and verifies both
  module entry points.
- The published package contains only compiled repository output and metadata;
  dependency source and native build products are not embedded in the tarball.
- A separate clean-install smoke uses `--omit=optional --ignore-scripts` and
  proves the core and Linux subpath modules import without native packages.
- `npm ls @emnapi/runtime --all` remains empty on the supported Linux x64 install.

The original `@emnapi/runtime@1.11.1` decision therefore remains dev-tool-only,
expires on 2026-10-23, and is not used to suppress findings in either new native
adapter dependency.
