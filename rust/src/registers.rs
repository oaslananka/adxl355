//! ADXL355 register addresses and bit masks.
//!
//! Based on ADXL354/ADXL355 Rev.D datasheet.
//! Register map: Table 22 onwards.

/// Register addresses.
#[allow(non_snake_case, non_upper_case_globals)]
pub mod reg {
    /// Device ID (Analog Devices). Datasheet Table 23.
    pub const DEVID_AD: u8 = 0x00;
    /// MEMS sensor ID. Datasheet Table 24.
    pub const DEVID_MST: u8 = 0x01;
    /// Part ID. Datasheet Table 25.
    pub const PARTID: u8 = 0x02;
    /// Revision ID. Datasheet Table 26.
    pub const REVID: u8 = 0x03;
    /// Status register. Datasheet Table 27.
    pub const STATUS: u8 = 0x04;
    /// FIFO entry count.
    pub const FIFO_ENTRIES: u8 = 0x05;
    /// Temperature high nibble in bits 3:0; bits 7:4 are reserved.
    pub const TEMP2: u8 = 0x06;
    /// Temperature low byte.
    pub const TEMP1: u8 = 0x07;
    /// X-axis acceleration MSB.
    pub const XDATA3: u8 = 0x08;
    /// X-axis acceleration mid byte.
    pub const XDATA2: u8 = 0x09;
    /// X-axis acceleration LSB.
    pub const XDATA1: u8 = 0x0A;
    /// Y-axis acceleration MSB.
    pub const YDATA3: u8 = 0x0B;
    /// Y-axis acceleration mid byte.
    pub const YDATA2: u8 = 0x0C;
    /// Y-axis acceleration LSB.
    pub const YDATA1: u8 = 0x0D;
    /// Z-axis acceleration MSB.
    pub const ZDATA3: u8 = 0x0E;
    /// Z-axis acceleration mid byte.
    pub const ZDATA2: u8 = 0x0F;
    /// Z-axis acceleration LSB.
    pub const ZDATA1: u8 = 0x10;
    /// FIFO data read.
    pub const FIFO_DATA: u8 = 0x11;
    /// X-axis offset high byte.
    pub const OFFSET_X_H: u8 = 0x1E;
    /// X-axis offset low byte.
    pub const OFFSET_X_L: u8 = 0x1F;
    /// Y-axis offset high byte.
    pub const OFFSET_Y_H: u8 = 0x20;
    /// Y-axis offset low byte.
    pub const OFFSET_Y_L: u8 = 0x21;
    /// Z-axis offset high byte.
    pub const OFFSET_Z_H: u8 = 0x22;
    /// Z-axis offset low byte.
    pub const OFFSET_Z_L: u8 = 0x23;
    /// Activity detection enable. Datasheet Table 35.
    pub const ACT_EN: u8 = 0x24;
    /// Activity threshold high byte.
    pub const ACT_THRESH_H: u8 = 0x25;
    /// Activity threshold low byte.
    pub const ACT_THRESH_L: u8 = 0x26;
    /// Activity count.
    pub const ACT_COUNT: u8 = 0x27;
    /// Filter / output data rate control. Datasheet Table 38.
    pub const FILTER: u8 = 0x28;
    /// FIFO sample count threshold.
    pub const FIFO_SAMPLES: u8 = 0x29;
    /// Interrupt mapping. Datasheet Table 40.
    pub const INT_MAP: u8 = 0x2A;
    /// External synchronization control.
    pub const SYNC: u8 = 0x2B;
    /// Acceleration range selection. Datasheet Table 42.
    pub const RANGE: u8 = 0x2C;
    /// Power control. Datasheet Table 43.
    pub const POWER_CTL: u8 = 0x2D;
    /// Self-test control.
    pub const SELF_TEST: u8 = 0x2E;
    /// Software reset (write 0x52). Datasheet Table 45.
    pub const RESET: u8 = 0x2F;
}

/// Expected device identity values (datasheet Rev.D, Tables 23-25).
pub mod id {
    pub const DEVID_AD: u8 = 0xAD;
    pub const DEVID_MST: u8 = 0x1D;
    pub const PARTID: u8 = 0xED;
}

/// Software reset code (datasheet Rev.D, Table 45).
pub const RESET_CODE: u8 = 0x52;

/// Temperature sensor constants (datasheet Rev.D, Table 29 and sensor section).
pub mod temperature {
    pub const TEMP2_DATA_MASK: u8 = 0x0F;
    pub const READ_ATTEMPTS: usize = 3;
    pub const INTERCEPT_LSB: f32 = 1885.0;
    pub const INTERCEPT_C: f32 = 25.0;
    pub const SLOPE_LSB_PER_C: f32 = -9.05;
}

/// Power mode bit (datasheet Rev.D, Table 43: bit 0 = 1 => standby).
pub const POWER_MODE_BIT: u8 = 0;

/// STATUS register bit positions (datasheet Rev.D, Table 27).
pub mod status {
    pub const NVM_BUSY: u8 = 4;
    pub const ACTIVITY: u8 = 3;
    pub const FIFO_OVR: u8 = 2;
    pub const FIFO_FULL: u8 = 1;
    pub const DATA_RDY: u8 = 0;
}

/// FILTER register masks (datasheet Rev.D, Table 38).
pub mod filter {
    /// ODR_LPF in bits 3:0
    pub const ODR_MASK: u8 = 0x0F;
    pub const ODR_SHIFT: u8 = 0;
    /// HPF_CORNER in bits 6:4
    pub const HPF_MASK: u8 = 0x70;
    pub const HPF_SHIFT: u8 = 4;
}

/// RANGE register constants (datasheet Rev.D, Table 42).
pub mod range_reg {
    /// Range field mask (bits 1:0)
    pub const SEL_MASK: u8 = 0x03;
    /// ±2g register value
    pub const G2_VAL: u8 = 0x01;
    /// ±4g register value
    pub const G4_VAL: u8 = 0x02;
    /// ±8g register value
    pub const G8_VAL: u8 = 0x03;
}

/// SPI command byte helpers (datasheet Rev.D, SPI Protocol section).
pub mod spi {
    pub fn read_cmd(reg: u8) -> u8 {
        (reg << 1) | 0x01
    }
    pub fn write_cmd(reg: u8) -> u8 {
        reg << 1
    }
}

/// I2C addresses (datasheet Rev.D, Table 8).
pub mod i2c {
    pub const DEFAULT_ADDR: u8 = 0x1D;
    pub const ALTERNATE_ADDR: u8 = 0x53;
}

/// Acceleration range selection.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Range {
    /// ±2g (register value 0x01)
    G2 = 0x01,
    /// ±4g (register value 0x02)
    G4 = 0x02,
    /// ±8g (register value 0x03)
    G8 = 0x03,
}

impl Range {
    /// Convert to register value.
    pub fn to_register(self) -> u8 {
        self as u8
    }

    /// Create from register value (masked to bits 1:0).
    pub fn from_register(val: u8) -> Option<Self> {
        match val & range_reg::SEL_MASK {
            0x01 => Some(Range::G2),
            0x02 => Some(Range::G4),
            0x03 => Some(Range::G8),
            _ => None,
        }
    }

    /// Scale factor in g per LSB.
    pub fn scale_g_per_lsb(self) -> f32 {
        match self {
            Range::G2 => 0.0000039,
            Range::G4 => 0.0000078,
            Range::G8 => 0.0000156,
        }
    }
}

/// Power mode.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum PowerMode {
    /// Standby mode (bit 0 = 1)
    Standby = 1,
    /// Measurement mode (bit 0 = 0)
    Measurement = 0,
}

/// Output data rate.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Odr {
    Hz4000 = 0,
    Hz2000 = 1,
    Hz1000 = 2,
    Hz500 = 3,
    Hz250 = 4,
    Hz125 = 5,
    Hz62_5 = 6,
    Hz31_25 = 7,
    Hz15_625 = 8,
    Hz7_813 = 9,
    Hz3_906 = 10,
}

/// Standard gravity (m/s²).
pub const STANDARD_GRAVITY_M_S2: f32 = 9.80665;
