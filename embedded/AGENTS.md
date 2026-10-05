# Embedded Integration Instructions

These instructions apply to `embedded/**` and supplement the root instructions.

The maintained embedded integration is a compile/package contract, not broad physical hardware evidence.

- The Arduino layer must forward to the authoritative C/C++ implementation rather than duplicate register logic.
- Preserve the exception-free AVR path and pinned PlatformIO/toolchain fixture.
- The representative Arduino Uno compile proves package/ABI/build compatibility only.
- Do not claim physical Arduino validation, other boards/frameworks, interrupts, electrical behavior, or bus timing from a compile-only fixture.
- Keep generated bridge/source ownership explicit and avoid compiling the C core more than once.

Run the pinned PlatformIO Uno fixture and relevant C/C++ package checks for embedded changes.
