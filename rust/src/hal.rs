//! embedded-hal adapters for the ADXL355 Transport trait.
//!
//! Provides SPI and I2C transport implementations that wrap
//! embedded-hal trait implementations.
//!
//! Requires feature `hal`: `cargo build --features hal`

use alloc::{vec, vec::Vec};

use crate::Error;
use crate::Transport;

/// SPI-based transport using embedded-hal 1.0 `SpiDevice`.
pub struct SpiTransport<SPI, D> {
    spi: SPI,
    delay: D,
    buf: [u8; 12],
}

impl<SPI, D> SpiTransport<SPI, D>
where
    SPI: embedded_hal::spi::SpiDevice,
    D: embedded_hal::delay::DelayNs,
{
    /// Create a new SPI transport.
    ///
    /// `spi` must be configured for ADXL355 SPI Mode 0 (CPOL=0, CPHA=0).
    pub fn new(spi: SPI, delay: D) -> Self {
        SpiTransport {
            spi,
            delay,
            buf: [0u8; 12],
        }
    }
}

impl<SPI, D> Transport for SpiTransport<SPI, D>
where
    SPI: embedded_hal::spi::SpiDevice,
    D: embedded_hal::delay::DelayNs,
{
    fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Error> {
        let addr = crate::registers::spi::read_cmd(reg);
        let count = len as usize;
        if count > self.buf.len() {
            return Err(Error::Bus);
        }
        let mut read_buf = vec![0u8; count];
        let mut ops = [
            embedded_hal::spi::Operation::Write(&[addr]),
            embedded_hal::spi::Operation::Read(&mut read_buf),
        ];
        self.spi.transaction(&mut ops).map_err(|_| Error::Bus)?;
        Ok(read_buf)
    }

    fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Error> {
        if data.len() > self.buf.len() - 1 {
            return Err(Error::Bus);
        }
        self.buf[0] = crate::registers::spi::write_cmd(reg);
        self.buf[1..=data.len()].copy_from_slice(data);
        let mut ops = [embedded_hal::spi::Operation::Write(
            &self.buf[..=data.len()],
        )];
        self.spi.transaction(&mut ops).map_err(|_| Error::Bus)?;
        Ok(())
    }

    fn delay_ms(&mut self, ms: u32) {
        self.delay.delay_ms(ms);
    }
}

/// I2C-based transport using embedded-hal 1.0 `I2c`.
pub struct I2cTransport<I2C> {
    i2c: I2C,
    addr: u8,
}

impl<I2C> I2cTransport<I2C>
where
    I2C: embedded_hal::i2c::I2c,
{
    /// Create a new I2C transport.
    ///
    /// `addr` is the 7-bit I2C address (default 0x1D for ADXL355).
    pub fn new(i2c: I2C, addr: u8) -> Self {
        I2cTransport { i2c, addr }
    }
}

impl<I2C> Transport for I2cTransport<I2C>
where
    I2C: embedded_hal::i2c::I2c,
{
    fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Error> {
        let mut buf = vec![0u8; len as usize];
        self.i2c
            .write_read(self.addr, &[reg], &mut buf)
            .map_err(|_| Error::Bus)?;
        Ok(buf)
    }

    fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Error> {
        let mut buf = Vec::with_capacity(1 + data.len());
        buf.push(reg);
        buf.extend_from_slice(data);
        self.i2c.write(self.addr, &buf).map_err(|_| Error::Bus)?;
        Ok(())
    }

    fn delay_ms(&mut self, _ms: u32) {
        // I2C typically does not need delay between register operations.
    }
}
