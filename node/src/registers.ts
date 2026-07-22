/**
 * ADXL355 register addresses and constants.
 * Based on ADXL354/ADXL355 Rev.D datasheet.
 */

/** Register addresses */
export const enum Reg {
  DEVID_AD = 0x00,
  DEVID_MST = 0x01,
  PARTID = 0x02,
  REVID = 0x03,
  STATUS = 0x04,
  FIFO_ENTRIES = 0x05,
  TEMP2 = 0x06,
  TEMP1 = 0x07,
  XDATA3 = 0x08,
  XDATA2 = 0x09,
  XDATA1 = 0x0a,
  YDATA3 = 0x0b,
  YDATA2 = 0x0c,
  YDATA1 = 0x0d,
  ZDATA3 = 0x0e,
  ZDATA2 = 0x0f,
  ZDATA1 = 0x10,
  FIFO_DATA = 0x11,
  OFFSET_X_H = 0x1e,
  OFFSET_X_L = 0x1f,
  OFFSET_Y_H = 0x20,
  OFFSET_Y_L = 0x21,
  OFFSET_Z_H = 0x22,
  OFFSET_Z_L = 0x23,
  ACT_EN = 0x24,
  ACT_THRESH_H = 0x25,
  ACT_THRESH_L = 0x26,
  ACT_COUNT = 0x27,
  FILTER = 0x28,
  FIFO_SAMPLES = 0x29,
  INT_MAP = 0x2a,
  SYNC = 0x2b,
  RANGE = 0x2c,
  POWER_CTL = 0x2d,
  SELF_TEST = 0x2e,
  RESET = 0x2f,
}

/** Expected device identity values (datasheet Rev.D, Tables 23-25) */
export const DEVID_AD_VALUE = 0xad;
export const DEVID_MST_VALUE = 0x1d;
export const PARTID_VALUE = 0xed;

/** Software reset code (datasheet Rev.D, Table 45) */
export const RESET_CODE = 0x52;

/** Temperature sensor constants (datasheet Rev.D, Table 29 and sensor section) */
export const TEMP2_DATA_MASK = 0x0f;
export const TEMP_READ_ATTEMPTS = 3;
export const TEMP_INTERCEPT_LSB = 1885.0;
export const TEMP_INTERCEPT_C = 25.0;
export const TEMP_SLOPE_LSB_PER_C = -9.05;

/** STATUS register bit positions (datasheet Rev.D, Table 27) */
export const STATUS_NVM_BUSY = 4;
export const STATUS_ACTIVITY = 3;
export const STATUS_FIFO_OVR = 2;
export const STATUS_FIFO_FULL = 1;
export const STATUS_DATA_RDY = 0;

/** FILTER register masks (datasheet Rev.D, Table 38) */
export const FILTER_ODR_MASK = 0x0f;
export const FILTER_ODR_SHIFT = 0;
export const FILTER_HPF_MASK = 0x70;
export const FILTER_HPF_SHIFT = 4;

/** RANGE register mask for bits 1:0 (datasheet Rev.D, Table 42) */
export const RANGE_SEL_MASK = 0x03;

/** SPI command helpers (datasheet Rev.D, SPI Protocol section) */
export function spiReadCmd(reg: number): number { return (reg << 1) | 0x01; }
export function spiWriteCmd(reg: number): number { return reg << 1; }

/** I2C addresses (datasheet Rev.D, Table 8) */
export const I2C_DEFAULT_ADDR = 0x1d;
export const I2C_ALTERNATE_ADDR = 0x53;

/** Acceleration range (datasheet Rev.D, Table 42) */
export enum Range {
  G2 = 0x01,
  G4 = 0x02,
  G8 = 0x03,
}

/** Power mode (datasheet Rev.D, Table 43: bit 0 = 1 => standby) */
export enum PowerMode {
  Standby = 1,
  Measurement = 0,
}

/** Output data rate */
export enum Odr {
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

/** Scaling constants (g per LSB) */
export const SCALE_2G_G_PER_LSB = 0.0000039;
export const SCALE_4G_G_PER_LSB = 0.0000078;
export const SCALE_8G_G_PER_LSB = 0.0000156;

/** Standard gravity (m/s²) */
export const STANDARD_GRAVITY_M_S2 = 9.80665;
