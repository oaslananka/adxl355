# Shared Specification Instructions

These instructions apply to `spec/**` and supplement the root instructions.

This directory is the cross-language source of truth for datasheet-derived constants and deterministic behavior.

## Authority

- `adxl355.registers.yaml` is authoritative for register addresses, bit fields, and expected identity values.
- `test_vectors.json` is authoritative for shared decode/conversion golden cases.
- `transport_contract.json` is the shared negative exact-length transport checklist.

Do not change a shared value to match one implementation. Confirm the datasheet/contract, update every affected implementation, and add or update shared tests coherently.

## Product truth

Register presence does not create a public API. Do not add parity claims solely because a register or vector exists.

## Validation

Run schema/spec checks and `python scripts/verify_vectors.py --ci`. The CI mode must remain zero-skip and reject missing maintained-language coverage/toolchains.
