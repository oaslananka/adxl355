import { describe, it, expect } from "vitest";
import { ADXL355 } from "../src/device.js";
import { Range, PowerMode, Reg, RESET_CODE } from "../src/registers.js";
import { Transport } from "../src/transport.js";
import { BusError, DataNotReadyError, InvalidConfigurationError } from "../src/errors.js";

class MockTransport implements Transport {
  private regs: Uint8Array;
  callCount = 0;
  calls: Array<{ isWrite: boolean; reg: number }> = [];

  constructor() {
    this.regs = new Uint8Array(128);
    // Set identity registers for probe to succeed
    this.regs[Reg.DEVID_AD] = 0xad;
    this.regs[Reg.DEVID_MST] = 0x1d;
    this.regs[Reg.PARTID] = 0xed;
    this.regs[Reg.RANGE] = Range.G2;
  }

  setRawXYZ(x: number, y: number, z: number) {
    const encode = (v: number, base: number) => {
      const uv = v & 0xfffff;
      this.regs[base] = (uv >> 12) & 0xff;
      this.regs[base + 1] = (uv >> 4) & 0xff;
      this.regs[base + 2] = (uv & 0x0f) << 4;
    };
    encode(x, Reg.XDATA3);
    encode(y, Reg.YDATA3);
    encode(z, Reg.ZDATA3);
  }

  async readRegister(reg: number, length: number): Promise<Uint8Array> {
    this.calls.push({ isWrite: false, reg });
    this.callCount++;
    return this.regs.slice(reg, reg + length);
  }

  async writeRegister(reg: number, data: Uint8Array): Promise<void> {
    this.calls.push({ isWrite: true, reg });
    this.callCount++;
    this.regs.set(data, reg);
    if (reg === Reg.RESET && data[0] === RESET_CODE) {
      this.regs[Reg.RANGE] = Range.G2;
    }
  }

  async delayMs(_ms: number): Promise<void> {
    // no-op
  }
}

class TemperatureSequenceTransport extends MockTransport {
  private readonly responses: Uint8Array[];

  constructor(responses: number[][]) {
    super();
    this.responses = responses.map((response) => Uint8Array.from(response));
  }

  override async readRegister(reg: number, length: number): Promise<Uint8Array> {
    if (reg === Reg.TEMP2 && this.responses.length > 0) {
      return this.responses.shift()!;
    }
    return super.readRegister(reg, length);
  }
}


describe("ADXL355", () => {
  it("should default cached range to 2g", () => {
    const dev = new ADXL355(new MockTransport());
    expect((dev as unknown as { range: Range }).range).toBe(Range.G2);
  });

  it("should synchronize cached range during probe", async () => {
    const transport = new MockTransport();
    transport["regs"][Reg.RANGE] = Range.G8;
    const dev = new ADXL355(transport);

    await expect(dev.probe()).resolves.toBe(true);
    expect((dev as unknown as { range: Range }).range).toBe(Range.G8);
  });

  it("should reject reserved range encoding during probe", async () => {
    const transport = new MockTransport();
    transport["regs"][Reg.RANGE] = 0x00;
    const dev = new ADXL355(transport);

    await expect(dev.probe()).rejects.toBeInstanceOf(InvalidConfigurationError);
    expect((dev as unknown as { initialized: boolean }).initialized).toBe(false);
    expect((dev as unknown as { range: Range }).range).toBe(Range.G2);
  });

  it("should restore cached range to 2g after reset", async () => {
    const transport = new MockTransport();
    transport["regs"][Reg.RANGE] = Range.G8;
    const dev = new ADXL355(transport);
    await dev.probe();

    await dev.reset();
    expect((dev as unknown as { range: Range }).range).toBe(Range.G2);
  });

  it("should convert reset-range raw data to approximately one g", async () => {
    const transport = new MockTransport();
    transport["regs"][Reg.RANGE] = Range.G2;
    transport.setRawXYZ(256410, 0, 0);
    const dev = new ADXL355(transport);

    await dev.probe();
    const accel = await dev.readAccelerationG();
    expect(accel.x).toBeCloseTo(1.0, 3);
  });

  it("should probe successfully", async () => {
    const transport = new MockTransport();
    const dev = new ADXL355(transport);
    const result = await dev.probe();
    expect(result).toBe(true);
  });

  it("should read raw data", async () => {
    const transport = new MockTransport();
    transport.setRawXYZ(100, -200, 300);
    const dev = new ADXL355(transport);
    await dev.probe();
    const raw = await dev.readRaw();
    expect(raw.x).toBe(100);
    expect(raw.y).toBe(-200);
    expect(raw.z).toBe(300);
  });

  it("should set range", async () => {
    const transport = new MockTransport();
    const dev = new ADXL355(transport);
    await dev.probe();
    await dev.setRange(Range.G8);
    const range = await dev.getRange();
    expect(range).toBe(Range.G8);
  });

  it("should set power mode", async () => {
    const transport = new MockTransport();
    const dev = new ADXL355(transport);
    await dev.probe();
    await dev.setPowerMode(PowerMode.Measurement);
    await dev.setPowerMode(PowerMode.Standby);
  });

  it("should read acceleration in g", async () => {
    const transport = new MockTransport();
    transport.setRawXYZ(524287, 0, -524288);
    const dev = new ADXL355(transport);
    await dev.probe();
    const accel = await dev.readAccelerationG();
    expect(accel.x).toBeGreaterThan(0);
    expect(accel.y).toBe(0);
    expect(accel.z).toBeLessThan(0);
  });

  it("should ignore reserved TEMP2 high bits", async () => {
    const transport = new MockTransport();
    transport["regs"][Reg.TEMP2] = 0xf7;
    transport["regs"][Reg.TEMP1] = 0x5d;
    const dev = new ADXL355(transport);
    await expect(dev.readTemperatureRaw()).resolves.toBe(1885);
    await expect(dev.readTemperatureC()).resolves.toBeCloseTo(25.0, 2);
  });

  it("should reject short temperature reads", async () => {
    const dev = new ADXL355(new TemperatureSequenceTransport([[0x07]]));
    await expect(dev.readTemperatureRaw()).rejects.toBeInstanceOf(BusError);
  });

  it("should retry a temperature high-byte rollover", async () => {
    const dev = new ADXL355(
      new TemperatureSequenceTransport([[0x07, 0xff], [0x08], [0x08, 0x00], [0x08]]),
    );
    await expect(dev.readTemperatureRaw()).resolves.toBe(2048);
  });

  it("should reject persistently unstable temperature samples", async () => {
    const dev = new ADXL355(
      new TemperatureSequenceTransport([
        [0x07, 0xff], [0x08],
        [0x08, 0xff], [0x09],
        [0x09, 0xff], [0x0a],
      ]),
    );
    await expect(dev.readTemperatureRaw()).rejects.toBeInstanceOf(DataNotReadyError);
  });

  it("should decode temperature boundary vectors", async () => {
    const transport = new MockTransport();
    const dev = new ADXL355(transport);
    await expect(dev.readTemperatureRaw()).resolves.toBe(0);

    transport["regs"][Reg.TEMP2] = 0x0f;
    transport["regs"][Reg.TEMP1] = 0xff;
    await expect(dev.readTemperatureRaw()).resolves.toBe(4095);
    await expect(dev.readTemperatureC()).resolves.toBeCloseTo(-219.198895, 2);
  });

  it("should read temperature raw nominal", async () => {
    const transport = new MockTransport();
    transport["regs"][Reg.TEMP2] = 0x07;
    transport["regs"][Reg.TEMP1] = 0x5d;
    const dev = new ADXL355(transport);
    const raw = await dev.readTemperatureRaw();
    expect(raw).toBe(1885);
  });

  it("should read temperature celsius nominal", async () => {
    const transport = new MockTransport();
    transport["regs"][Reg.TEMP2] = 0x07;
    transport["regs"][Reg.TEMP1] = 0x5d;
    const dev = new ADXL355(transport);
    const temp = await dev.readTemperatureC();
    expect(temp).toBeCloseTo(25.0, 1);
  });

  it("should read temperature celsius 50C", async () => {
    const transport = new MockTransport();
    transport["regs"][Reg.TEMP2] = 0x06;
    transport["regs"][Reg.TEMP1] = 0x7b;
    const dev = new ADXL355(transport);
    const temp = await dev.readTemperatureC();
    expect(temp).toBeCloseTo(50.0, 1);
  });

  it("should read status all clear", async () => {
    const transport = new MockTransport();
    transport["regs"][Reg.STATUS] = 0x00;
    const dev = new ADXL355(transport);
    const status = await dev.readStatus();
    expect(status).toBe(0);
  });

  it("should read status data ready", async () => {
    const transport = new MockTransport();
    transport["regs"][Reg.STATUS] = 0x01;
    const dev = new ADXL355(transport);
    const status = await dev.readStatus();
    expect(status).toBe(1);
  });

  it("should read status fifo full", async () => {
    const transport = new MockTransport();
    transport["regs"][Reg.STATUS] = 0x02;
    const dev = new ADXL355(transport);
    const status = await dev.readStatus();
    expect(status).toBe(2);
  });

  it("should filter default odr", async () => {
    const transport = new MockTransport();
    const dev = new ADXL355(transport);
    const regs = transport["regs"];
    expect(regs[Reg.FILTER] & 0x0f).toBe(0x00);
    expect(regs[Reg.FILTER] & 0x70).toBe(0x00);
  });

  it("should reset call log", async () => {
    const transport = new MockTransport();
    const dev = new ADXL355(transport);
    await dev.reset();
    expect(transport.callCount).toBeGreaterThanOrEqual(1);
    expect(transport.calls[0].isWrite).toBe(true);
    expect(transport.calls[0].reg).toBe(Reg.RESET);
  });

  it("should decode half-scale via read", async () => {
    const transport = new MockTransport();
    transport.setRawXYZ(262144, 0, 0);
    const dev = new ADXL355(transport);
    await dev.probe();
    const raw = await dev.readRaw();
    expect(raw.x).toBe(262144);
  });
});
