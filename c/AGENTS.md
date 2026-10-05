# C Core Instructions

These instructions apply to `c/**` and supplement the root instructions.

The C implementation is the behavioral reference for the shared core.

- Keep C99 compatibility, no dynamic allocation in the portable core, and no global mutable state.
- Validate pointers, lengths, enum/config values, lifecycle state, and transport byte counts before using data.
- Transport callbacks return the exact requested byte count on success and a negative value on failure.
- Preserve caller-owned output on failed reads where the contract requires it.
- Keep configuration changes standby-safe, preserve unrelated bits, and attempt exact power-state restoration.
- FIFO/self-test/DRDY behavior is bounded and must preserve documented partial-progress/rollback semantics.
- Do not introduce Linux/device-specific dependencies into the portable C core.

Run C tests with warnings-as-errors and sanitizers as described in `docs/testing.md`.
