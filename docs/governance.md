# Project governance and responsibilities

ADXL355 is an openly developed, **single-maintainer** alpha-stage hardware
sensor-driver project. This document describes the current operating model,
not an agreement to appoint additional maintainers.

## Roles and decision-making

- **Project owner/maintainer:** The owner of
  [oaslananka/adxl355](https://github.com/oaslananka/adxl355) prioritizes
  issues, accepts and rejects feature scope, reviews potentially breaking or
  security-sensitive changes, maintains release credentials, and decides if
  physical test evidence is sufficient for an alpha release.
- **Contributors:** Anyone may suggest changes through an issue or pull
  request. Contributors are responsible for the changes they propose, the
  source they are authorized to submit, tests, and compatibility documentation.
  No outside contributor is currently required to operate the repository.
- **Automation:** Renovate opens limited dependency PRs; GitHub Actions runs
  the test, quality, security and dependency checks; Mergify may merge only
  eligible, policy-labeled updates after the protected branch gates pass.
  Automation has no authority to waive those gates or claim hardware testing.

Issues and pull requests are the decision record. The maintainer can accept a
proposal after the required automated checks are successful and any review
threads are resolved. **An independent human review is not required.** Major,
security-sensitive and release changes need an explicit maintainer decision;
minor eligible dependency fixes may follow the protected automated queue.

## Security and releases

Security vulnerabilities use [private reporting](../SECURITY.md) rather than
public issue disclosure. The maintainer triages reports according to the
published response targets, coordinates a fix, and gives reporter credit unless
anonymity is requested. Releases follow [verified release procedures](publishing.md)
and are not implied by a successful development PR.

## Continuity limits

At present a single person controls the repository and publication rights.
There is **no independently verified successor/credential escrow or second
maintainer**. The project does not claim a bus factor of two or satisfy
OpenSSF's one-week single-person-loss continuity requirement. Those are
explicit, unresolved constraints, not policies that should be bypassed.

See [CONTRIBUTING.md](../CONTRIBUTING.md), [testing](testing.md), and the
[roadmap](roadmap.md) for the contributor and development contracts.
