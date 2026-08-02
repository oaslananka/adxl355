//! `embedded-hal` adapters for the ADXL355 [`crate::Transport`] trait.
//!
//! Requires feature `hal`: `cargo build --features hal`.

use alloc::{vec, vec::Vec};
use core::fmt;

use crate::Transport;

/// Error produced by an `embedded-hal` transport adapter.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AdapterError<E> {
    /// Error returned by the underlying `embedded-hal` implementation.
    Backend(E),
    /// A write payload exceeds the adapter's bounded transaction buffer.
    PayloadTooLong {
        /// Requested payload bytes, excluding the register command.
        requested: usize,
        /// Maximum supported payload bytes.
        maximum: usize,
    },
}

impl<E> AdapterError<E> {
    /// Return the underlying `embedded-hal` cause when available.
    pub fn backend_cause(&self) -> Option<&E> {
        match self {
            Self::Backend(source) => Some(source),
            Self::PayloadTooLong { .. } => None,
        }
    }
}

impl<E: fmt::Display> fmt::Display for AdapterError<E> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Backend(source) => write!(f, "embedded-hal backend error: {source}"),
            Self::PayloadTooLong { requested, maximum } => write!(
                f,
                "adapter payload too long: requested {requested} bytes, maximum {maximum}"
            ),
        }
    }
}

#[cfg(feature = "std")]
impl<E> std::error::Error for AdapterError<E>
where
    E: std::error::Error + 'static,
{
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Backend(source) => Some(source),
            Self::PayloadTooLong { .. } => None,
        }
    }
}

/// SPI-based transport using `embedded-hal` 1.0 `SpiDevice`.
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
        Self {
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
    type Error = AdapterError<SPI::Error>;

    fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Self::Error> {
        let addr = crate::registers::spi::read_cmd(reg);
        let mut read_buf = vec![0u8; len as usize];
        let mut ops = [
            embedded_hal::spi::Operation::Write(&[addr]),
            embedded_hal::spi::Operation::Read(&mut read_buf),
        ];
        self.spi
            .transaction(&mut ops)
            .map_err(AdapterError::Backend)?;
        Ok(read_buf)
    }

    fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Self::Error> {
        let maximum = self.buf.len() - 1;
        if data.len() > maximum {
            return Err(AdapterError::PayloadTooLong {
                requested: data.len(),
                maximum,
            });
        }
        self.buf[0] = crate::registers::spi::write_cmd(reg);
        self.buf[1..=data.len()].copy_from_slice(data);
        let mut ops = [embedded_hal::spi::Operation::Write(
            &self.buf[..=data.len()],
        )];
        self.spi
            .transaction(&mut ops)
            .map_err(AdapterError::Backend)?;
        Ok(())
    }

    fn delay_ms(&mut self, ms: u32) {
        self.delay.delay_ms(ms);
    }
}

/// I2C-based transport using `embedded-hal` 1.0 `I2c`.
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
    /// `addr` is the 7-bit I2C address (0x1D or 0x53 for ADXL355).
    pub fn new(i2c: I2C, addr: u8) -> Self {
        Self { i2c, addr }
    }
}

impl<I2C> Transport for I2cTransport<I2C>
where
    I2C: embedded_hal::i2c::I2c,
{
    type Error = AdapterError<I2C::Error>;

    fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Self::Error> {
        let mut buf = vec![0u8; len as usize];
        self.i2c
            .write_read(self.addr, &[reg], &mut buf)
            .map_err(AdapterError::Backend)?;
        Ok(buf)
    }

    fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Self::Error> {
        let mut buf = Vec::with_capacity(1 + data.len());
        buf.push(reg);
        buf.extend_from_slice(data);
        self.i2c
            .write(self.addr, &buf)
            .map_err(AdapterError::Backend)?;
        Ok(())
    }

    fn delay_ms(&mut self, _ms: u32) {
        // I2C adapters do not require an inter-register delay here.
    }
}
