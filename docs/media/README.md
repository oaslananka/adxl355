# Hardware media

`raspberry-pi-5-spi-adxl355.svg` is an original, repository-authored schematic-style
diagram of the physically verified Raspberry Pi 5 SPI fixture. It is released
under the repository MIT license. It does not include vendor logos, product
photographs, or copied datasheet artwork.

The SVG contains a `<title>` and detailed `<desc>` text alternative. The same pin
mapping is also available as text in `docs/hardware-testing.md`, so users do not
need color or image rendering to reproduce the setup.

I2C media is intentionally not present yet. The repository has not recorded a
physical I2C HIL pass, and issue #41 owns that validation. Add an I2C diagram only
after the real fixture wiring, address strap, bus number, clock, and identity read
have been verified and recorded without exposing host identifiers or secrets.
