//! ADXL355 device driver.

use alloc::vec::Vec;

use crate::error::Error;
use crate::registers::{self, PowerMode, Range};
use crate::types::{AccelXyz, RawXyz};

/// Transport abstraction for ADXL355 communication.
pub trait Transport {
    /// Read `len` bytes starting at register `reg`.
    fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Error>;
    /// Write `data` bytes starting at register `reg`.
    fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Error>;
    /// Blocking delay in milliseconds.
    fn delay_ms(&mut self, ms: u32);
}

/// ADXL355 accelerometer driver.
#[derive(Debug)]
pub struct Adxl355<T: Transport> {
    transport: T,
    range: Range,
    initialized: bool,
}

impl<T: Transport> Adxl355<T> {
    /// Create a new ADXL355 driver instance.
    pub fn new(transport: T) -> Self {
        Adxl355 {
            transport,
            range: Range::G2,
            initialized: false,
        }
    }

    /// Consume self and return the inner transport.
    pub fn into_inner(self) -> T {
        self.transport
    }

    // ------------------------------------------------------------------
    // Internal helpers
    // ------------------------------------------------------------------

    fn read_u8(&mut self, reg: u8) -> Result<u8, Error> {
        let data = self.transport.read_register(reg, 1)?;
        Ok(data[0])
    }

    fn write_u8(&mut self, reg: u8, val: u8) -> Result<(), Error> {
        self.transport.write_register(reg, &[val])
    }

    fn ensure_initialized(&self) -> Result<(), Error> {
        if self.initialized {
            Ok(())
        } else {
            Err(Error::InvalidState)
        }
    }

    fn enter_configuration_standby(&mut self) -> Result<Option<u8>, Error> {
        let original = self.read_u8(registers::reg::POWER_CTL)?;
        if original & 0x01 != 0 {
            return Ok(None);
        }
        self.write_u8(registers::reg::POWER_CTL, original | 0x01)?;
        Ok(Some(original))
    }

    fn finish_configuration(
        &mut self,
        original_power_ctl: Option<u8>,
        operation: Result<(), Error>,
    ) -> Result<(), Error> {
        if let Some(original) = original_power_ctl {
            self.write_u8(registers::reg::POWER_CTL, original)?;
        }
        operation
    }

    // ------------------------------------------------------------------
    // Core API
    // ------------------------------------------------------------------

    /// Probe for the ADXL355 and synchronize the cached hardware range.
    pub fn probe(&mut self) -> Result<bool, Error> {
        self.initialized = false;
        let id_ad = self.read_u8(registers::reg::DEVID_AD)?;
        let id_mst = self.read_u8(registers::reg::DEVID_MST)?;
        let part_id = self.read_u8(registers::reg::PARTID)?;

        if id_ad != registers::id::DEVID_AD
            || id_mst != registers::id::DEVID_MST
            || part_id != registers::id::PARTID
        {
            return Err(Error::BadDevice);
        }

        let range_value = self.read_u8(registers::reg::RANGE)?;
        let detected_range = Range::from_register(range_value).ok_or(Error::InvalidArgument)?;

        let power_ctl = self.read_u8(registers::reg::POWER_CTL)?;
        if power_ctl & 0x01 == 0 {
            self.write_u8(registers::reg::POWER_CTL, power_ctl | 0x01)?;
        }
        self.range = detected_range;
        self.initialized = true;
        Ok(true)
    }

    /// Perform a software reset.
    pub fn reset(&mut self) -> Result<(), Error> {
        self.ensure_initialized()?;
        self.write_u8(registers::reg::RESET, registers::RESET_CODE)?;
        self.transport.delay_ms(10);
        self.range = Range::G2;
        Ok(())
    }

    /// Set the acceleration range.
    pub fn set_range(&mut self, range: Range) -> Result<(), Error> {
        self.ensure_initialized()?;
        let original_power_ctl = self.enter_configuration_standby()?;
        let operation = (|| {
            let mut reg = self.read_u8(registers::reg::RANGE)?;
            reg = (reg & !registers::range_reg::SEL_MASK)
                | (range.to_register() & registers::range_reg::SEL_MASK);
            self.write_u8(registers::reg::RANGE, reg)?;
            self.range = range;
            Ok(())
        })();
        self.finish_configuration(original_power_ctl, operation)
    }

    /// Read the currently configured range.
    pub fn get_range(&mut self) -> Result<Range, Error> {
        self.ensure_initialized()?;
        let val = self.read_u8(registers::reg::RANGE)?;
        Range::from_register(val).ok_or(Error::InvalidArgument)
    }

    /// Set the power mode.
    pub fn set_power_mode(&mut self, mode: PowerMode) -> Result<(), Error> {
        self.ensure_initialized()?;
        let mut reg = self.read_u8(registers::reg::POWER_CTL)?;
        /* Datasheet Rev.D, Table 43: bit 0 = 1 => standby, bit 0 = 0 => measurement */
        if mode == PowerMode::Standby {
            reg |= 1 << registers::POWER_MODE_BIT;
        } else {
            reg &= !(1 << registers::POWER_MODE_BIT);
        }
        self.write_u8(registers::reg::POWER_CTL, reg)
    }

    // ------------------------------------------------------------------
    // Data readout
    // ------------------------------------------------------------------

    /// Read raw 20-bit acceleration for all three axes.
    pub fn read_raw(&mut self) -> Result<RawXyz, Error> {
        self.ensure_initialized()?;
        let data = self.transport.read_register(registers::reg::XDATA3, 9)?;
        if data.len() < 9 {
            return Err(Error::Bus);
        }
        Ok(RawXyz {
            x: decode_raw20(data[0], data[1], data[2]),
            y: decode_raw20(data[3], data[4], data[5]),
            z: decode_raw20(data[6], data[7], data[8]),
        })
    }

    /// Read acceleration in g.
    pub fn read_g(&mut self) -> Result<AccelXyz, Error> {
        let raw = self.read_raw()?;
        let scale = self.range.scale_g_per_lsb();
        Ok(AccelXyz {
            x: raw.x as f32 * scale,
            y: raw.y as f32 * scale,
            z: raw.z as f32 * scale,
        })
    }

    /// Read acceleration in m/s².
    pub fn read_mps2(&mut self) -> Result<AccelXyz, Error> {
        let accel = self.read_g()?;
        Ok(AccelXyz {
            x: accel.x * registers::STANDARD_GRAVITY_M_S2,
            y: accel.y * registers::STANDARD_GRAVITY_M_S2,
            z: accel.z * registers::STANDARD_GRAVITY_M_S2,
        })
    }

    /// Read a coherent 12-bit unsigned temperature sample.
    ///
    /// TEMP2/TEMP1 are not double-buffered. Both bytes are read together,
    /// then TEMP2 is re-read; the operation retries if its data nibble changed.
    pub fn read_temperature_raw(&mut self) -> Result<i16, Error> {
        self.ensure_initialized()?;
        for _ in 0..registers::temperature::READ_ATTEMPTS {
            let data = self.transport.read_register(registers::reg::TEMP2, 2)?;
            if data.len() != 2 {
                return Err(Error::Bus);
            }
            let confirm = self.transport.read_register(registers::reg::TEMP2, 1)?;
            if confirm.len() != 1 {
                return Err(Error::Bus);
            }

            let temp2 = data[0] & registers::temperature::TEMP2_DATA_MASK;
            if temp2 == (confirm[0] & registers::temperature::TEMP2_DATA_MASK) {
                return Ok(((temp2 as i16) << 8) | data[1] as i16);
            }
        }
        Err(Error::NotReady)
    }

    /// Read temperature in degrees Celsius.
    ///
    /// Datasheet Rev.D: 12-bit unsigned, nominal intercept 1885 LSB at 25°C,
    /// slope -9.05 LSB/°C. Formula: T(°C) = 25.0 + (raw - 1885.0) / -9.05
    pub fn read_temperature_c(&mut self) -> Result<f32, Error> {
        let raw = self.read_temperature_raw()?;
        Ok(registers::temperature::INTERCEPT_C
            + (raw as f32 - registers::temperature::INTERCEPT_LSB)
                / registers::temperature::SLOPE_LSB_PER_C)
    }

    /// Read the status register.
    pub fn read_status(&mut self) -> Result<u8, Error> {
        self.ensure_initialized()?;
        self.read_u8(registers::reg::STATUS)
    }
}

// ------------------------------------------------------------------
// Stateless conversion functions
// ------------------------------------------------------------------

/// Decode three bytes into a 20-bit two's complement integer.
///
/// Returns a value in the range [-524288, 524287].
pub fn decode_raw20(b0: u8, b1: u8, b2: u8) -> i32 {
    let raw = ((b0 as i32) << 12) | ((b1 as i32) << 4) | ((b2 as i32) >> 4);
    if raw & 0x80000 != 0 {
        raw - 0x100000
    } else {
        raw
    }
}

/// Convert a decoded raw value to g.
pub fn raw_to_g(raw: i32, range: Range) -> f32 {
    raw as f32 * range.scale_g_per_lsb()
}

/// Convert a decoded raw value to m/s².
pub fn raw_to_mps2(raw: i32, range: Range) -> f32 {
    raw as f32 * range.scale_g_per_lsb() * registers::STANDARD_GRAVITY_M_S2
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::registers::Range;

    struct MockTransport {
        regs: [u8; 128],
    }

    impl MockTransport {
        fn new() -> Self {
            let mut transport = MockTransport { regs: [0; 128] };
            transport.regs[registers::reg::RANGE as usize] = Range::G2.to_register();
            transport
        }

        fn set_identity_ok(&mut self) {
            self.regs[registers::reg::DEVID_AD as usize] = registers::id::DEVID_AD;
            self.regs[registers::reg::DEVID_MST as usize] = registers::id::DEVID_MST;
            self.regs[registers::reg::PARTID as usize] = registers::id::PARTID;
        }

        fn set_xyz_raw(&mut self, x: i32, y: i32, z: i32) {
            let mut encode = |v: i32, base: u8| {
                let uv = (v as u32) & 0xFFFFF;
                self.regs[base as usize] = ((uv >> 12) & 0xFF) as u8;
                self.regs[(base + 1) as usize] = ((uv >> 4) & 0xFF) as u8;
                self.regs[(base + 2) as usize] = ((uv & 0x0F) << 4) as u8;
            };
            encode(x, registers::reg::XDATA3);
            encode(y, registers::reg::YDATA3);
            encode(z, registers::reg::ZDATA3);
        }
    }

    impl Transport for MockTransport {
        fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Error> {
            let reg = reg as usize;
            let len = len as usize;
            Ok(self.regs[reg..reg + len].to_vec())
        }

        fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Error> {
            let reg = reg as usize;
            for (i, &b) in data.iter().enumerate() {
                if reg + i < self.regs.len() {
                    self.regs[reg + i] = b;
                }
            }
            if reg == registers::reg::RESET as usize && data.first() == Some(&registers::RESET_CODE)
            {
                self.regs[registers::reg::RANGE as usize] = Range::G2.to_register();
            }
            Ok(())
        }

        fn delay_ms(&mut self, _ms: u32) {
            // no-op in tests
        }
    }

    #[test]
    fn test_decode_raw20_zero() {
        assert_eq!(decode_raw20(0, 0, 0), 0);
    }

    #[test]
    fn test_decode_raw20_positive_one() {
        assert_eq!(decode_raw20(0, 0, 16), 1);
    }

    #[test]
    fn test_decode_raw20_positive_max() {
        assert_eq!(decode_raw20(127, 255, 240), 524287);
    }

    #[test]
    fn test_decode_raw20_negative_min() {
        assert_eq!(decode_raw20(128, 0, 0), -524288);
    }

    #[test]
    fn test_decode_raw20_negative_one() {
        assert_eq!(decode_raw20(255, 255, 240), -1);
    }

    #[test]
    fn test_raw_to_g_zero() {
        let g = raw_to_g(0, Range::G2);
        assert!(g.abs() < 1e-6);
    }

    #[test]
    fn test_raw_to_g_positive() {
        let g = raw_to_g(524287, Range::G2);
        let expected = 524287.0 * 0.0000039;
        assert!((g - expected).abs() < 1e-6);
    }

    #[test]
    fn test_raw_to_mps2() {
        let v = raw_to_mps2(100000, Range::G2);
        let expected = 100000.0 * 0.0000039 * 9.80665;
        assert!((v - expected).abs() < 1e-5);
    }

    #[test]
    fn test_new_defaults_to_2g() {
        let dev = Adxl355::new(MockTransport::new());
        assert_eq!(dev.range, Range::G2);
    }

    #[test]
    fn test_probe_synchronizes_hardware_range() {
        let mut mock = MockTransport::new();
        mock.set_identity_ok();
        mock.regs[registers::reg::RANGE as usize] = Range::G8.to_register();
        let mut dev = Adxl355::new(mock);

        assert_eq!(dev.probe(), Ok(true));
        assert_eq!(dev.range, Range::G8);
    }

    #[test]
    fn test_probe_rejects_reserved_range() {
        let mut mock = MockTransport::new();
        mock.set_identity_ok();
        mock.regs[registers::reg::RANGE as usize] = 0;
        let mut dev = Adxl355::new(mock);

        assert_eq!(dev.probe(), Err(Error::InvalidArgument));
        assert!(!dev.initialized);
        assert_eq!(dev.range, Range::G2);
    }

    #[test]
    fn test_reset_restores_2g_cache() {
        let mut mock = MockTransport::new();
        mock.set_identity_ok();
        mock.regs[registers::reg::RANGE as usize] = Range::G8.to_register();
        let mut dev = Adxl355::new(mock);
        dev.probe().unwrap();

        dev.reset().unwrap();
        assert_eq!(dev.range, Range::G2);
    }

    #[test]
    fn test_reset_range_converts_raw_value_to_one_g() {
        let mut mock = MockTransport::new();
        mock.set_identity_ok();
        mock.regs[registers::reg::RANGE as usize] = Range::G2.to_register();
        mock.set_xyz_raw(256410, 0, 0);
        let mut dev = Adxl355::new(mock);

        dev.probe().unwrap();
        let accel = dev.read_g().unwrap();
        assert!((accel.x - 1.0).abs() < 0.001);
    }

    #[test]
    fn test_probe_success() {
        let mut mock = MockTransport::new();
        mock.set_identity_ok();
        let mut dev = Adxl355::new(mock);
        assert!(dev.probe().is_ok());
    }

    #[test]
    fn test_probe_fail() {
        let mock = MockTransport::new(); // identity NOT set
        let mut dev = Adxl355::new(mock);
        assert!(dev.probe().is_err());
    }

    #[test]
    fn test_read_raw() {
        let mut mock = MockTransport::new();
        mock.set_identity_ok();
        mock.set_xyz_raw(100, -200, 300);
        let mut dev = Adxl355::new(mock);
        dev.probe().unwrap();
        let raw = dev.read_raw().unwrap();
        assert_eq!(raw.x, 100);
        assert_eq!(raw.y, -200);
        assert_eq!(raw.z, 300);
    }

    #[test]
    fn test_set_range() {
        let mut mock = MockTransport::new();
        mock.set_identity_ok();
        let mut dev = Adxl355::new(mock);
        dev.probe().unwrap();
        dev.set_range(Range::G8).unwrap();
        assert_eq!(dev.get_range().unwrap(), Range::G8);
    }
}
