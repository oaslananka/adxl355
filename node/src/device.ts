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
  DeviceStateError,
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

  private normalizeBusError(operation: string, error: unknown): BusError {
    if (error instanceof BusError) {
      return error;
    }
    const detail = error instanceof Error ? error.message : String(error);
    return new BusError(`${operation}: ${detail}`);
  }

  private async readExact(reg: number, length: number): Promise<Uint8Array> {
    let data: Uint8Array;
    try {
      data = await this.transport.readRegister(reg, length);
    } catch (error) {
      throw this.normalizeBusError(`Transport read failed at register 0x${reg.toString(16)}`, error);
    }
    if (data.length !== length) {
      throw new BusError(
        `Invalid read length at register 0x${reg.toString(16)}: ` +
        `expected ${length}, got ${data.length}`,
      );
    }
    return data;
  }

  private async readU8(reg: number): Promise<number> {
    return (await this.readExact(reg, 1))[0];
  }

  private async writeU8(reg: number, value: number): Promise<void> {
    try {
      await this.transport.writeRegister(reg, new Uint8Array([value]));
    } catch (error) {
      throw this.normalizeBusError(`Transport write failed at register 0x${reg.toString(16)}`, error);
    }
  }

  private async delayMs(ms: number): Promise<void> {
    if (!this.transport.delayMs) {
      return;
    }
    try {
      await this.transport.delayMs(ms);
    } catch (error) {
      throw this.normalizeBusError(`Transport delay failed for ${ms} ms`, error);
    }
  }

  private ensureInitialized(): void {
    if (!this.initialized) {
      throw new DeviceStateError("Device has not been probed. Call probe() first.");
    }
  }

  private async enterConfigurationStandby(): Promise<number | undefined> {
    const originalPowerCtl = await this.readU8(Reg.POWER_CTL);
    if ((originalPowerCtl & 0x01) !== 0) {
      return undefined;
    }
    await this.writeU8(Reg.POWER_CTL, originalPowerCtl | 0x01);
    return originalPowerCtl;
  }

  private async restoreConfigurationMode(originalPowerCtl: number | undefined): Promise<void> {
    if (originalPowerCtl !== undefined) {
      await this.writeU8(Reg.POWER_CTL, originalPowerCtl);
    }
  }

  // ------------------------------------------------------------------
  // Core API
  // ------------------------------------------------------------------

  /** Probe for the ADXL355 and synchronize the cached hardware range. */
  async probe(): Promise<boolean> {
    this.initialized = false;
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

    const powerCtl = await this.readU8(Reg.POWER_CTL);
    if ((powerCtl & 0x01) === 0) {
      await this.writeU8(Reg.POWER_CTL, powerCtl | 0x01);
    }
    this.range = detectedRange;
    this.initialized = true;
    return true;
  }

  /** Perform a software reset. */
  async reset(): Promise<void> {
    this.ensureInitialized();
    await this.writeU8(Reg.RESET, RESET_CODE);
    await this.delayMs(10);
    this.range = Range.G2;
  }

  /** Set the acceleration range, preserving unrelated bits. */
  async setRange(range: Range): Promise<void> {
    this.ensureInitialized();
    if (![Range.G2, Range.G4, Range.G8].includes(range)) {
      throw new InvalidConfigurationError(`Invalid range: ${range}`);
    }

    const originalPowerCtl = await this.enterConfigurationStandby();
    try {
      const reg = (await this.readU8(Reg.RANGE)) & ~RANGE_SEL_MASK;
      await this.writeU8(Reg.RANGE, reg | (range & RANGE_SEL_MASK));
      this.range = range;
    } finally {
      await this.restoreConfigurationMode(originalPowerCtl);
    }
  }

  /** Read the currently configured range. */
  async getRange(): Promise<Range> {
    this.ensureInitialized();
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
    this.ensureInitialized();
    if (![PowerMode.Standby, PowerMode.Measurement].includes(mode)) {
      throw new InvalidConfigurationError(`Invalid power mode: ${mode}`);
    }
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
    this.ensureInitialized();
    const data = await this.readExact(Reg.XDATA3, 9);
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
    this.ensureInitialized();
    for (let attempt = 0; attempt < TEMP_READ_ATTEMPTS; attempt++) {
      const data = await this.readExact(Reg.TEMP2, 2);
      const confirm = await this.readExact(Reg.TEMP2, 1);

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
    this.ensureInitialized();
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
