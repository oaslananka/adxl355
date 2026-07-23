# Security Policy

## Supported versions

Security fixes are developed against the latest commit on `main` and the most
recent public alpha tag. Older alpha snapshots may receive guidance, but they
are not maintained as parallel security branches.

## Report a vulnerability privately

Do not open a public issue, discussion, or pull request for a suspected
vulnerability.

Use GitHub private vulnerability reporting:

https://github.com/oaslananka/adxl355/security/advisories/new

The private report should include the affected revision or package, impact,
reproduction steps, and any proposed mitigation. Avoid attaching real secrets,
private keys, or data captured from systems you do not own.

## Response expectations

These are response targets rather than guarantees:

- acknowledge a complete report within **48 hours**;
- provide an initial severity and scope assessment within **7 calendar days**;
- coordinate a fix and disclosure within **90 days** when practical;
- communicate material timeline changes through the private advisory.

Critical issues that are actively exploited may require an accelerated release.
Reporters are asked to keep details private until a coordinated disclosure date
or an explicit maintainer release.

## Scope

Examples of in-scope security concerns include:

- memory safety, bounds, integer, and transport-length handling in the C/C++ core;
- malformed device or bus input that causes a panic, crash, or fabricated reading;
- package, release, workflow, dependency, or provenance weaknesses;
- credential exposure or unsafe GitHub Actions permissions;
- public API validation that creates a meaningful integrity or availability risk.

## Usually out of scope

- attacks requiring unrestricted physical access to the sensor or bus;
- side-channel research requiring specialized instrumentation;
- availability impact caused only by an already-authorized caller intentionally
  saturating its own SPI/I2C bus;
- unsupported versions without a reproducible impact on the current release line.

## Disclosure and credit

After a fix is available, the project may publish a GitHub Security Advisory and
release notes. Reporter credit is optional and will follow the preference stated
in the private report.

Supply-chain controls and exception policy are documented in
[`docs/security/supply-chain.md`](docs/security/supply-chain.md).
