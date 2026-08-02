# Embedded C++ integration

The Arduino/PlatformIO layer is intentionally thin:

- `NoexceptDevice` is stack-owned, non-copyable, non-movable, and returns stable
  `Status` or `Result<T>` values. It does not allocate or throw.
- `adxl355::arduino::SpiBus` implements the existing bus contract with Arduino
  `SPIClass`, SPI Mode 0, and caller-selected chip select and clock.
- `embedded/arduino/src/adxl355_core.c` includes the authoritative
  `c/src/adxl355.c`; it does not copy register or conversion logic.
- forwarding headers preserve normal includes such as
  `<adxl355/adxl355.hpp>` while the package retains the repository layout.

The PlatformIO environment is intentionally command-scoped. It installs the
hash-locked build/pack closure but omits PlatformIO's vulnerable web/server stack
(`starlette`, `uvicorn`, `wsproto`, `anyio`, and `h11`). Only `pio --version`,
`pio pkg pack`, and `pio run` are supported by the CI environment.

The representative fixture is Arduino Uno (`atmelavr@5.3.0`) and is compile-only:

```bash
pio run -d embedded/platformio/uno
```

This proves AVR/Arduino compilation, `-fno-exceptions` compatibility, package
layout, and the SPI adapter surface. It does not claim a physical ADXL355 test on
Arduino Uno or compatibility with unbuilt boards. Physical HIL remains the Linux
Raspberry Pi fixture documented in `docs/hardware-testing.md`.
