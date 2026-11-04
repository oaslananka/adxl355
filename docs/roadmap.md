# ADXL355 maintenance roadmap — November 2026 to October 2027

This is the current, bounded direction for the open-source alpha driver family;
priorities may be revised by the maintainer when tests, user reports and available
hardware evidence change. It is **not** a commitment to commercial service,
production certification, additional maintainers, or any particular release date.

## November 2026 – January 2027

- Keep supported language toolchains and external dependencies updated via the
  existing Renovate, vulnerability and CI gates; prioritize actionable security
  defects, not score-only findings.
- Ensure current six-language API references and regression tests accurately
  reflect each *implemented* feature, without claiming false parity.
- Evaluate [trusted registry publishing (#55)](https://github.com/oaslananka/adxl355/issues/55)
  only after actual registry-account and OIDC prerequisites are verified.

## February – April 2027

- Fix issues found in malformed SPI/I2C frames, lifecycle state handling,
  bounds checks and supported Linux transports; add exact regression tests.
- Assess statement coverage on the real maintained modules before establishing
  any cross-language coverage claim; avoid expensive duplicate scanning.
- Keep first-run installation, API reference and security-expectation docs current.

## May – July 2027

- Add physical device acceptance evidence for changes affecting actual SPI/I2C
  timing or interrupts **only when** supported fixtures are available. Keep
  simulated and physical evidence clearly distinct.
- Review alpha API compatibility and remaining language-specific gaps against
  concrete requests rather than implementing speculative feature parity.

## August – October 2027

- Reassess readiness for a subsequent prerelease from exact-commit regression,
  packaging, security and bounded physical test evidence.
- Retire stale technical debt and update this roadmap based on shipped work,
  incoming issues, and maintained dependency health.

## Explicitly outside this plan

Automatic production deployment, paid hosting, fabricated hardware evidence,
mandatory independent human code approval, an additional maintainer, a stable
1.0 promise, and safety-critical or production qualification are **not** goals.
See [the current limitations](../README.md) and [the release guide](publishing.md).
