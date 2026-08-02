# Hardware media

The SVG files in this directory are original, repository-authored schematic-style
diagrams of the physically verified Raspberry Pi 5 fixtures:

- `raspberry-pi-5-spi-adxl355.svg` — SPI Mode 0 at 1 MHz;
- `raspberry-pi-5-i2c-adxl355.svg` — I2C bus 1 at 100 kHz, `MISO/ASEL`
  grounded for address `0x1D`.

They are released under the repository MIT license and contain no vendor logos,
product photographs, or copied datasheet artwork.

Each SVG contains a `<title>` and detailed `<desc>` text alternative. The same pin
mappings are available as text tables in `docs/hardware-testing.md`, so users do
not need color or image rendering to reproduce either setup.

The I2C diagram records only the physically tested `0x1D` strap. Address `0x53`
requires powering down and moving `MISO/ASEL` to `VDDIO`; it is not represented as
verified until that separate physical configuration is tested.
