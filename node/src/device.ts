import {
  Reg,
  Range,
  PowerMode,
  DEVID_AD_VALUE,
  DEVID_MST_VALUE,
  PARTID_VALUE,
  RESET_CODE,
  SCALE_2G_G_PER_LSB,
  SCALE_4G_G_PER_LSB,
  SCALE_8G_G_PER_LSB,
  STANDARD_GRAVITY_M_S2,
  RANGE_SEL_MASK,
  TEMP2_DATA_MASK,
  TEMP_INTERCEPT_C,
  TEMP_INTERCEPT_LSB,
  TEMP_READ_ATTEMPTS,
  TEMP_SLOPE_LSB_PER_C,
  Range as RangeEnum,
} from "./registers.js";
import { Transport } from "./transport.js";
import { RawXYZ, AccelXYZ } from "./types.js";
import {
  BusError,
  DataNotReadyError,
  DeviceNotFoundError,
  InvalidConfigurationError,
} from "./errors.js";

/**
 * ADXL355 accelerometer driver.
 */
export class ADXL355 {
  private readonly transport: Transport;
  private range: RangeEnum;
  private initialized: boolean;

  constructor(transport: Transport) {
    this.transport = transport;
    this.range = Range.G2;
    this.initialized = false;
  }

  // ------------------------------------------------------------------
  // Internal helpers
  // ------------------------------------------------------------------

  private async readU8(reg: number): Promise<number> {
    const data = await this.transport.readRegister(reg, 1);
    return data[0];
  }

  private async writeU8(reg: number, value: number): Promise<void> {
    await this.transport.writeRegister(reg, new Uint8Array([value]));
  }

  // ------------------------------------------------------------------
  // Core API
  // ------------------------------------------------------------------

  /** Probe for the ADXL355 and synchronize the cached hardware range. */
  async probe(): Promise<boolean> {
    const idAd = await this.readU8(Reg.DEVID_AD);
    const idMst = await this.readU8(Reg.DEVID_MST);
    const partId = await this.readU8(Reg.PARTID);

    if (idAd !== DEVID_AD_VALUE || idMst !== DEVID_MST_VALUE || partId !== PARTID_VALUE) {
      throw new DeviceNotFoundError(
        `ID mismatch: DEVID_AD=0x${idAd.toString(16)}, ` +
        `DEVID_MST=0x${idMst.toString(16)}, PARTID=0x${partId.toString(16)}`,
      );
    }

    const rangeBits = (await this.readU8(Reg.RANGE)) & RANGE_SEL_MASK;
    if (![Range.G2, Range.G4, Range.G8].includes(rangeBits as Range)) {
      throw new InvalidConfigurationError(
        `Invalid RANGE register encoding: 0x${rangeBits.toString(16).padStart(2, "0")}`,
      );
    }
    const detectedRange = rangeBits as Range;

    // Enter standby mode after probe. Commit state only after all bus operations succeed.
    await this.writeU8(Reg.POWER_CTL, PowerMode.Standby);
    this.range = detectedRange;
    this.initialized = true;
    return true;
  }

  /** Perform a software reset. */
  async reset(): Promise<void> {
    await this.writeU8(Reg.RESET, RESET_CODE);
    if (this.transport.delayMs) {
      await this.transport.delayMs(10);
    }
    this.range = Range.G2;
  }

  /** Set the acceleration range, preserving unrelated bits. */
  async setRange(range: Range): Promise<void> {
    if (![Range.G2, Range.G4, Range.G8].includes(range)) {
      throw new InvalidConfigurationError(`Invalid range: ${range}`);
    }
    const reg = (await this.readU8(Reg.RANGE)) & ~RANGE_SEL_MASK;
    await this.writeU8(Reg.RANGE, reg | (range & RANGE_SEL_MASK));
    this.range = range;
  }

  /** Read the currently configured range. */
  async getRange(): Promise<Range> {
    const rangeBits = (await this.readU8(Reg.RANGE)) & RANGE_SEL_MASK;
    if (![Range.G2, Range.G4, Range.G8].includes(rangeBits as Range)) {
      throw new InvalidConfigurationError(
        `Invalid RANGE register encoding: 0x${rangeBits.toString(16).padStart(2, "0")}`,
      );
    }
    return rangeBits as Range;
  }

  /** Set power mode. Datasheet Rev.D, Table 43: bit 0 = 1 => standby. */
  async setPowerMode(mode: PowerMode): Promise<void> {
    let reg = await this.readU8(Reg.POWER_CTL);
    if (mode === PowerMode.Standby) {
      reg |= 1;
    } else {
      reg &= ~1;
    }
    await this.writeU8(Reg.POWER_CTL, reg);
  }

  // ------------------------------------------------------------------
  // Data readout
  // ------------------------------------------------------------------

  /** Read raw 20-bit acceleration data for all three axes. */
  async readRaw(): Promise<RawXYZ> {
    const data = await this.transport.readRegister(Reg.XDATA3, 9);
    return {
      x: decodeRaw20(data[0], data[1], data[2]),
      y: decodeRaw20(data[3], data[4], data[5]),
      z: decodeRaw20(data[6], data[7], data[8]),
    };
  }

  /** Read acceleration in g (gravity multiples). */
  async readAccelerationG(): Promise<AccelXYZ> {
    const raw = await this.readRaw();
    const scale = rangeToScale(this.range);
    return {
      x: raw.x * scale,
      y: raw.y * scale,
      z: raw.z * scale,
    };
  }

  /** Read acceleration in m/s². */
  async readAccelerationMps2(): Promise<AccelXYZ> {
    const accel = await this.readAccelerationG();
    return {
      x: accel.x * STANDARD_GRAVITY_M_S2,
      y: accel.y * STANDARD_GRAVITY_M_S2,
      z: accel.z * STANDARD_GRAVITY_M_S2,
    };
  }

  /** Read a coherent 12-bit unsigned temperature sample. */
  async readTemperatureRaw(): Promise<number> {
    for (let attempt = 0; attempt < TEMP_READ_ATTEMPTS; attempt++) {
      const data = await this.transport.readRegister(Reg.TEMP2, 2);
      if (data.length !== 2) {
        throw new BusError(`Short temperature read: expected 2 bytes, got ${data.length}`);
      }
      const confirm = await this.transport.readRegister(Reg.TEMP2, 1);
      if (confirm.length !== 1) {
        throw new BusError(`Short TEMP2 confirmation read: expected 1 byte, got ${confirm.length}`);
      }

      const temp2 = data[0] & TEMP2_DATA_MASK;
      if (temp2 === (confirm[0] & TEMP2_DATA_MASK)) {
        return (temp2 << 8) | data[1];
      }
    }
    throw new DataNotReadyError("Temperature sample changed during all read attempts");
  }

  /**
   * Read temperature in degrees Celsius.
   * Datasheet Rev.D: T(°C) = 25.0 + (raw - 1885.0) / -9.05
   */
  async readTemperatureC(): Promise<number> {
    const raw = await this.readTemperatureRaw();
    return TEMP_INTERCEPT_C + (raw - TEMP_INTERCEPT_LSB) / TEMP_SLOPE_LSB_PER_C;
  }

  /** Read status register. */
  async readStatus(): Promise<number> {
    return this.readU8(Reg.STATUS);
  }
}

// ------------------------------------------------------------------
// Conversion functions
// ------------------------------------------------------------------

/** Decode three bytes into a 20-bit two's complement integer. */
export function decodeRaw20(b0: number, b1: number, b2: number): number {
  let raw = (b0 << 12) | (b1 << 4) | (b2 >> 4);
  if (raw & 0x80000) {
    raw -= 0x100000;
  }
  return raw;
}

/** Convert a decoded raw value to g. */
export function rawToG(raw: number, range: Range): number {
  return raw * rangeToScale(range);
}

/** Convert a decoded raw value to m/s². */
export function rawToMps2(raw: number, range: Range): number {
  return raw * rangeToScale(range) * STANDARD_GRAVITY_M_S2;
}

function rangeToScale(range: Range): number {
  switch (range) {
    case Range.G2: return SCALE_2G_G_PER_LSB;
    case Range.G4: return SCALE_4G_G_PER_LSB;
    case Range.G8: return SCALE_8G_G_PER_LSB;
    default: return SCALE_4G_G_PER_LSB;
  }
}
