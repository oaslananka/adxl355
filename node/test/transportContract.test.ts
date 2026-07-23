import { describe, expect, it } from "vitest";
import { ADXL355 } from "../src/device.js";
import { BusError } from "../src/errors.js";
import { Range, Reg } from "../src/registers.js";
import { Transport } from "../src/transport.js";

class ContractTransport implements Transport {
  private readonly regs = new Uint8Array(128);
  shortReg: number | undefined;
  shortLength = 0;
  failReadReg: number | undefined;
  failWriteReg: number | undefined;
  failDelay = false;

  constructor() {
    this.regs[Reg.DEVID_AD] = 0xad;
    this.regs[Reg.DEVID_MST] = 0x1d;
    this.regs[Reg.PARTID] = 0xed;
    this.regs[Reg.RANGE] = Range.G2;
    this.regs[Reg.POWER_CTL] = 1;
  }

  async readRegister(reg: number, length: number): Promise<Uint8Array> {
    if (this.failReadReg === reg) {
      throw new TypeError("native read failure");
    }
    const returned = this.shortReg === reg ? this.shortLength : length;
    return this.regs.slice(reg, reg + returned);
  }

  async writeRegister(reg: number, data: Uint8Array): Promise<void> {
    if (this.failWriteReg === reg) {
      throw new TypeError("native write failure");
    }
    this.regs.set(data, reg);
  }

  async delayMs(_ms: number): Promise<void> {
    if (this.failDelay) {
      throw new TypeError("native delay failure");
    }
  }
}

async function probedDevice(transport = new ContractTransport()): Promise<ADXL355> {
  const device = new ADXL355(transport);
  await device.probe();
  return device;
}

describe("shared transport contract", () => {
  for (const [name, returned] of [["TR-1-ZERO", 0], ["TR-1-OVERLONG", 2]] as const) {
    it(name, async () => {
      const transport = new ContractTransport();
      transport.shortReg = Reg.DEVID_AD;
      transport.shortLength = returned;
      await expect(new ADXL355(transport).probe()).rejects.toBeInstanceOf(BusError);
    });
  }

  for (const [name, returned] of [["TR-2-ZERO", 0], ["TR-2-TRUNCATED", 1]] as const) {
    it(name, async () => {
      const transport = new ContractTransport();
      const device = await probedDevice(transport);
      transport.shortReg = Reg.TEMP2;
      transport.shortLength = returned;
      await expect(device.readTemperatureRaw()).rejects.toBeInstanceOf(BusError);
    });
  }

  for (const [name, returned] of [["TR-9-ZERO", 0], ["TR-9-TRUNCATED", 8]] as const) {
    it(name, async () => {
      const transport = new ContractTransport();
      const device = await probedDevice(transport);
      transport.shortReg = Reg.XDATA3;
      transport.shortLength = returned;
      await expect(device.readRaw()).rejects.toBeInstanceOf(BusError);
    });
  }

  it("normalizes native read failures", async () => {
    const transport = new ContractTransport();
    transport.failReadReg = Reg.DEVID_AD;
    await expect(new ADXL355(transport).probe()).rejects.toBeInstanceOf(BusError);
  });

  it("normalizes native write failures", async () => {
    const transport = new ContractTransport();
    const device = await probedDevice(transport);
    transport.failWriteReg = Reg.RANGE;
    await expect(device.setRange(Range.G4)).rejects.toBeInstanceOf(BusError);
  });

  it("normalizes native delay failures", async () => {
    const transport = new ContractTransport();
    const device = await probedDevice(transport);
    transport.failDelay = true;
    await expect(device.reset()).rejects.toBeInstanceOf(BusError);
  });
});
