# ADXL355 Register Map

> **Status**: Preliminary — register values need datasheet verification.

## Register Table

| Addr | Name | Type | Default | Description |
|------|------|------|---------|-------------|
| 0x00 | DEVID_AD | R | — | Analog Devices device ID (expected: 0xAD) |
| 0x01 | DEVID_MST | R | — | MEMS sensor ID (expected: 0x1D) |
| 0x02 | PARTID | R | — | Part ID (expected: 0xED) |
| 0x03 | REVID | R | — | Revision ID |
| 0x04 | STATUS | R | — | Status register (see below) |
| 0x05 | FIFO_ENTRIES | R | — | FIFO entry count |
| 0x06 | TEMP2 | R | — | Temperature bits 11:8 in bits 3:0; bits 7:4 reserved |
| 0x07 | TEMP1 | R | — | Temperature bits 7:0 |
| 0x08 | XDATA3 | R | — | X-axis acceleration MSB |
| 0x09 | XDATA2 | R | — | X-axis acceleration mid |
| 0x0A | XDATA1 | R | — | X-axis acceleration LSB |
| 0x0B | YDATA3 | R | — | Y-axis acceleration MSB |
| 0x0C | YDATA2 | R | — | Y-axis acceleration mid |
| 0x0D | YDATA1 | R | — | Y-axis acceleration LSB |
| 0x0E | ZDATA3 | R | — | Z-axis acceleration MSB |
| 0x0F | ZDATA2 | R | — | Z-axis acceleration mid |
| 0x10 | ZDATA1 | R | — | Z-axis acceleration LSB |
| 0x11 | FIFO_DATA | R | — | FIFO data read port |
| 0x1E | OFFSET_X_H | R/W | 0x00 | X-axis offset high |
| 0x1F | OFFSET_X_L | R/W | 0x00 | X-axis offset low |
| 0x20 | OFFSET_Y_H | R/W | 0x00 | Y-axis offset high |
| 0x21 | OFFSET_Y_L | R/W | 0x00 | Y-axis offset low |
| 0x22 | OFFSET_Z_H | R/W | 0x00 | Z-axis offset high |
| 0x23 | OFFSET_Z_L | R/W | 0x00 | Z-axis offset low |
| 0x24 | ACT_EN | R/W | 0x00 | Activity detection enable |
| 0x25 | ACT_THRESH_H | R/W | 0x00 | Activity threshold high |
| 0x26 | ACT_THRESH_L | R/W | 0x00 | Activity threshold low |
| 0x27 | ACT_COUNT | R/W | 0x00 | Activity count |
| 0x28 | FILTER | R/W | — | Filter / ODR control |
| 0x29 | FIFO_SAMPLES | R/W | 0x00 | FIFO sample threshold |
| 0x2A | INT_MAP | R/W | 0x00 | Interrupt mapping |
| 0x2B | SYNC | R/W | 0x00 | External sync control |
| 0x2C | RANGE | R/W | 0x01 | Acceleration range |
| 0x2D | POWER_CTL | R/W | 0x01 | Power control |
| 0x2E | SELF_TEST | R/W | 0x00 | Self-test control |
| 0x2F | RESET | W | — | Software reset (write 0x52) |

## SPI Protocol

The ADXL355 uses **SPI Mode 0** (`CPOL=0`, `CPHA=0`). The first byte of every
transaction contains the seven-bit register address in bits 7:1 and the
read/write flag in bit 0:

- Read command: `(register << 1) | 0x01`
- Write command: `register << 1`

Command and payload bytes must be sent as one transaction with chip select
asserted for the complete transfer. For example, reading `XDATA3` (`0x08`)
starts with `0x11`, while writing `POWER_CTL` (`0x2D`) starts with `0x5A`.

## Status Register (0x04)

| Bit | Name | Description |
|-----|------|-------------|
| 7 | NVM_BUSY | NVM ready (0 = ready) |
| 6 | ACTIVITY | Activity detection status |
| 5 | FIFO_OVR | FIFO overrun indicator |
| 4 | FIFO_FULL | FIFO full indicator |
| 3 | DATA_RDY | Data ready indicator |
| 2:0 | FIFO_ENTRY_COUNT | Number of FIFO entries (MSB bits) |

## Range Register (0x2C)

| Bits | Value | Description |
|------|-------|-------------|
| 1:0 | 00 | Reserved |
| 1:0 | 01 | ±2g (reset default) |
| 1:0 | 10 | ±4g |
| 1:0 | 11 | ±8g |

## Filter Register (0x28)

| Bits | Field | Description |
|------|-------|-------------|
| 7:4 | ODR | Output data rate (see below) |
| 3:0 | LPF_3DB | Low-pass filter 3dB corner |

### ODR Values

| Value | Rate |
|-------|------|
| 0 | 4000 Hz |
| 1 | 2000 Hz |
| 2 | 1000 Hz |
| 3 | 500 Hz |
| 4 | 250 Hz |
| 5 | 125 Hz |
| 6 | 62.5 Hz |
| 7 | 31.25 Hz |
| 8 | 15.625 Hz |
| 9 | 7.813 Hz |
| 10 | 3.906 Hz |

## Temperature Registers (0x06–0x07)

`TEMP2[3:0]` contains raw temperature bits 11:8 and `TEMP1[7:0]`
contains bits 7:0. `TEMP2[7:4]` is reserved and must be masked out.
Because the temperature registers are not double-buffered, drivers read
`TEMP2`/`TEMP1` as one two-byte burst, re-read `TEMP2`, and retry up to three
times if the high data nibble changed. Short reads are bus errors; persistent
rollover returns a not-ready error.

Nominal conversion:

`T(°C) = 25.0 + (raw - 1885.0) / -9.05`

## Power Control Register (0x2D)

| Bit | Value | Description |
|-----|-------|-------------|
| 0 | 0 | Standby mode |
| 0 | 1 | Measurement mode (default) |

## Datasheet Verification

The following fields have **not** been verified against the official ADXL355 datasheet:

- [ ] All register addresses
- [ ] Expected DEVID_AD value (0xAD)
- [ ] Expected DEVID_MST value (0x1D)
- [ ] Expected PARTID value (0xED)
- [ ] Reset command value (0x52)
- [x] Range register default (`RANGE[1:0] = 0b01` = ±2g)
- [ ] Scale factors (3.9, 7.8, 15.6 µg/LSB)
- [x] Temperature bit layout, coherent-read strategy, and nominal conversion formula
- [x] SPI Mode 0 and read/write command format
- [ ] I2C address options
- [ ] Status register bit definitions
- [ ] Filter register ODR/LPF field bit positions

Verify each against the official datasheet before the 1.0.0 release.
