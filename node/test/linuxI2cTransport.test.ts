import { Buffer } from "node:buffer";
import { describe, expect, it } from "vitest";

import { BusError, InvalidConfigurationError } from "../src/errors.js";
import { I2C_ALTERNATE_ADDR, I2C_DEFAULT_ADDR } from "../src/registers.js";
import {
  LinuxI2cTransport,
  type I2cBusBackend,
  type I2cModuleBackend,
} from "../src/linux/i2c.js";

class FakeI2cBus implements I2cBusBackend {
  reads: Array<{ address: number; command: number; length: number }> = [];
  writes: Array<{ address: number; command: number; data: number[] }> = [];
  closeCount = 0;
  readError: Error | undefined;
  writeError: Error | undefined;
  closeError: Error | undefined;
  readCountOverride: number | undefined;
  writeCountOverride: number | undefined;
  readBufferLengthOverride: number | undefined;
  writeBufferLengthOverride: number | undefined;

  async readI2cBlock(
    address: number,
    command: number,
    length: number,
    _buffer: Buffer,
  ): Promise<{ bytesRead: number; buffer: Buffer }> {
    if (this.readError) throw this.readError;
    this.reads.push({ address, command, length });
    const returned = Buffer.alloc(this.readBufferLengthOverride ?? length);
    for (let index = 0; index < returned.length; index++) returned[index] = 0x10 + index;
    return { bytesRead: this.readCountOverride ?? length, buffer: returned };
  }

  async writeI2cBlock(
    address: number,
    command: number,
    length: number,
    buffer: Buffer,
  ): Promise<{ bytesWritten: number; buffer: Buffer }> {
    if (this.writeError) throw this.writeError;
    this.writes.push({ address, command, data: [...buffer.subarray(0, length)] });
    const returned = Buffer.from(buffer.subarray(0, this.writeBufferLengthOverride ?? length));
    return { bytesWritten: this.writeCountOverride ?? length, buffer: returned };
  }

  async close(): Promise<void> {
    this.closeCount++;
    if (this.closeError) throw this.closeError;
  }
}

class FakeI2cModule implements I2cModuleBackend {
  readonly bus = new FakeI2cBus();
  openedBus: number | undefined;
  openError: Error | undefined;

  async openPromisified(busNumber: number): Promise<I2cBusBackend> {
    this.openedBus = busNumber;
    if (this.openError) throw this.openError;
    return this.bus;
  }
}

async function openedTransport(
  address = I2C_DEFAULT_ADDR,
  module = new FakeI2cModule(),
): Promise<{ transport: LinuxI2cTransport; module: FakeI2cModule }> {
  const transport = await LinuxI2cTransport.open(
    { busNumber: 3, address, busHz: 400_000 },
    async () => module,
  );
  return { transport, module };
}

describe("LinuxI2cTransport", () => {
  it.each([I2C_DEFAULT_ADDR, I2C_ALTERNATE_ADDR])(
    "uses documented address 0x%s",
    async (address) => {
      const { transport, module } = await openedTransport(address);
      const result = await transport.readRegister(0x08, 3);
      expect(module.openedBus).toBe(3);
      expect(module.bus.reads).toEqual([{ address, command: 0x08, length: 3 }]);
      expect([...result]).toEqual([0x10, 0x11, 0x12]);
      await transport.close();
    },
  );

  it("uses one register block write with exact byte count", async () => {
    const { transport, module } = await openedTransport();
    await transport.writeRegister(0x2c, Uint8Array.from([0x02, 0x03]));
    expect(module.bus.writes).toEqual([
      { address: I2C_DEFAULT_ADDR, command: 0x2c, data: [0x02, 0x03] },
    ]);
    await transport.close();
  });

  it.each([
    [0, 3],
    [2, 3],
    [4, 3],
    [3, 2],
    [3, 4],
  ])("rejects read count/buffer mismatch %i/%i", async (bytesRead, bufferLength) => {
    const { transport, module } = await openedTransport();
    module.bus.readCountOverride = bytesRead;
    module.bus.readBufferLengthOverride = bufferLength;
    await expect(transport.readRegister(0x08, 3)).rejects.toBeInstanceOf(BusError);
    await transport.close();
  });

  it.each([
    [0, 2],
    [1, 2],
    [3, 2],
    [2, 1],
  ])("rejects write count/buffer mismatch %i/%i", async (bytesWritten, bufferLength) => {
    const { transport, module } = await openedTransport();
    module.bus.writeCountOverride = bytesWritten;
    module.bus.writeBufferLengthOverride = bufferLength;
    await expect(
      transport.writeRegister(0x2c, Uint8Array.from([0x02, 0x03])),
    ).rejects.toBeInstanceOf(BusError);
    await transport.close();
  });

  it("normalizes backend and loader failures", async () => {
    const module = new FakeI2cModule();
    module.bus.readError = new TypeError("native read failed");
    const transport = await LinuxI2cTransport.open({}, async () => module);
    await expect(transport.readRegister(0x08, 1)).rejects.toBeInstanceOf(BusError);
    await transport.close();

    await expect(
      LinuxI2cTransport.open({}, async () => {
        throw new Error("module missing");
      }),
    ).rejects.toBeInstanceOf(BusError);
  });

  it("closes idempotently and rejects later operations", async () => {
    const { transport, module } = await openedTransport();
    await transport.close();
    await transport.close();
    expect(module.bus.closeCount).toBe(1);
    await expect(transport.readRegister(0x00, 1)).rejects.toBeInstanceOf(BusError);
  });

  it.each([
    [{ address: 0x1e }, "address"],
    [{ busNumber: -1 }, "bus"],
    [{ busHz: 123_456 }, "speed"],
  ] as const)("rejects invalid options %o", async (options) => {
    await expect(LinuxI2cTransport.open(options, async () => new FakeI2cModule())).rejects.toBeInstanceOf(
      InvalidConfigurationError,
    );
  });

  it("rejects invalid register and block lengths", async () => {
    const { transport } = await openedTransport();
    await expect(transport.readRegister(-1, 1)).rejects.toBeInstanceOf(InvalidConfigurationError);
    await expect(transport.readRegister(0x40, 1)).rejects.toBeInstanceOf(
      InvalidConfigurationError,
    );
    await expect(transport.readRegister(0x00, 33)).rejects.toBeInstanceOf(
      InvalidConfigurationError,
    );
    await transport.close();
  });
});
