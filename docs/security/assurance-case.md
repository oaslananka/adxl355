# ADXL355 security requirements and assurance argument

This document records the *scope and evidence* for the open-source, alpha-stage
ADXL355 sensor driver family. It is not a safety/security certification. See
[SECURITY.md](../../SECURITY.md) for disclosure, supported revisions and response
commitments, and the [architecture](../architecture.md) for driver contracts.

## Security properties and threats

The maintained driver APIs aim to preserve memory safety or bounded C/C++
accesses, reject invalid configuration and malformed bus responses, and avoid
surprising sensor state changes. A hardware driver cannot authenticate raw
sensor readings. Malicious physical bus devices, spoofed sensors, compromised
kernel drivers, adversarial hosts and loss of power are outside its trust boundary.

Threats considered include truncated/excess SPI/I2C frames, invalid register
addresses and sample counts, arithmetic overflow in sensor conversion, stale
pre-probe lifecycle use, mode restoration errors, resource leaks and unsafe
dependency/release inputs. Compromised user-supplied callbacks and privileged
hardware access are not isolated by this library.

## Trust boundaries and mitigating controls

| Boundary | Requirement and implemented argument | Evidence |
| --- | --- | --- |
| Caller → driver | Validate public inputs and reject unsupported modes, addresses or lengths before hazardous I/O | [transport contract](../../spec/transport_contract.json), [shared tests](../testing.md) |
| Sensor/bus → driver | Check exact transfer lengths, sensor identity and register framing; report errors instead of inventing data | [SPI/I2C contracts](../architecture.md), [negative tests](../testing.md) |
| Driver → sensor lifecycle | Fail hardware operations before probe; enter standby during sensitive configuration; restore earlier mode or return an explicit error | [lifecycle design](../architecture.md), [state tests](../testing.md) |
| Memory-unsafe C/C++ | Reject bad pointers/lengths and run ASan/UBSan, bounded fuzzing and warnings-as-errors in CI | [CI workflow](../../.github/workflows/ci.yml), [fuzzer](../../c/fuzz/fuzz_adxl355.c) |
| Dependencies → software build | Inspect dependency updates, scan vulnerabilities, run source/ABI compatibility tests before merge | [supply-chain policy](supply-chain.md), [Dependency Audit](../../.github/workflows/dependency-audit.yml) |
| Build → release | Verify exact source/version, package contents, checksums, SBOM and OIDC attestations before a published artifact is trusted | [publishing guide](../publishing.md), [release workflow](../../.github/workflows/release.yml) |

## Secure-design rationale

The device layer is deliberately isolated behind narrow bus interfaces rather
than assuming the transport is trusted. Invalid inputs and failed transfers
produce errors; callers must decide how to safely handle stale or unavailable
sensor data. The portable library does not expose a network service, identity
system, password store or cryptographic protocol, so TLS/password requirements
are not product features. Hosted package registries have independent security
requirements; they are not substitutes for sensor integrity.

## Residual risks and evidence boundaries

- This is **alpha** software; a test that uses mock registers is not physical
  validation. Language-specific capabilities, operating-system adapters and
  tested fixtures are explicitly listed in [README](../../README.md).
- A sensor reading alone cannot be used as authenticated or safety-certified
  evidence, and the project provides no fail-operational guarantee.
- The existing fuzz smoke and unit tests are not proof of full input coverage
  or 80% statement coverage of all maintained languages.
- Some releases and tags may predate current provenance and scanning checks.
  Do not assume every historical artifact is signed or attested.
- The issue tracker, private advisory process and required CI provide a way to
  correct discovered flaws; findings are evaluated for *actual impact* rather
  than suppressed to increase badge scores.
