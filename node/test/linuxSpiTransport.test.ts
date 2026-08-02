import { Buffer } from "node:buffer";
import { describe, expect, it } from "vitest";

import { BusError, InvalidConfigurationError } from "../src/errors.js";
import { spiReadCmd, spiWriteCmd } from "../src/registers.js";
import {
  LinuxSpiTransport,
  type SpiDeviceBackend,
  type SpiMessage,
  type SpiModuleBackend,
  type SpiOpenOptions,
} from "../src/linux/spi.js";

class FakeSpiDevice implements SpiDeviceBackend {
  readonly messages: SpiMessage[] = [];
  closeCount = 0;
  transferError: Error | undefined;
  closeError: Error | undefined;
  returnedLength: number | undefined;

  transfer(
    message: SpiMessage,
    callback: (error: Error | null | undefined, message: SpiMessage) => void,
  ): unknown {
    this.messages.push(message);
    if (this.transferError) {
      callback(this.transferError, message);
      return this;
    }
    const entry = message[0];
    const expected = entry.byteLength;
    const receive = Buffer.alloc(this.returnedLength ?? expected);
    for (let index = 0; index < receive.length; index++) {
      receive[index] = 0xa0 + index;
    }
    callback(null, [{ ...entry, receiveBuffer: receive }]);
    return this;
  }

  close(callback: (error: Error | null | undefined) => void): void {
    this.closeCount++;
    callback(this.closeError);
  }
}

class FakeSpiModule implements SpiModuleBackend {
  readonly device = new FakeSpiDevice();
  opened:
    | { busNumber: number; deviceNumber: number; options: SpiOpenOptions }
    | undefined;
  openError: Error | undefined;

  open(
    busNumber: number,
    deviceNumber: number,
    options: SpiOpenOptions,
    callback: (error: Error | null | undefined) => void,
  ): SpiDeviceBackend {
    this.opened = { busNumber, deviceNumber, options };
    queueMicrotask(() => callback(this.openError));
    return this.device;
  }
}

async function openedTransport(module = new FakeSpiModule()): Promise<{
  transport: LinuxSpiTransport;
  module: FakeSpiModule;
}> {
  const transport = await LinuxSpiTransport.open(
    { busNumber: 2, deviceNumber: 1, speedHz: 2_000_000 },
    async () => module,
  );
  return { transport, module };
}

describe("LinuxSpiTransport", () => {
  it("opens mode 0 with bounded explicit options", async () => {
    const { transport, module } = await openedTransport();
    expect(module.opened).toEqual({
      busNumber: 2,
      deviceNumber: 1,
      options: {
        mode: 0,
        chipSelectHigh: false,
        lsbFirst: false,
        threeWire: false,
        noChipSelect: false,
        bitsPerWord: 8,
        maxSpeedHz: 2_000_000,
      },
    });
    await transport.close();
  });

  it("supports a backend that invokes the open callback synchronously", async () => {
    const module = new FakeSpiModule();
    const synchronous: SpiModuleBackend = {
      open(busNumber, deviceNumber, options, callback) {
        module.opened = { busNumber, deviceNumber, options };
        callback(undefined);
        return module.device;
      },
    };
    const transport = await LinuxSpiTransport.open({}, async () => synchronous);
    await expect(transport.readRegister(0x08, 1)).resolves.toEqual(Uint8Array.from([0xa1]));
    await transport.close();
  });

  it("keeps read command and dummy payload in one chip-select transaction", async () => {
    const { transport, module } = await openedTransport();
    const result = await transport.readRegister(0x08, 3);

    expect(module.device.messages).toHaveLength(1);
    expect(module.device.messages[0]).toHaveLength(1);
    const transfer = module.device.messages[0][0];
    expect([...transfer.sendBuffer!]).toEqual([spiReadCmd(0x08), 0, 0, 0]);
    expect(transfer.byteLength).toBe(4);
    expect(transfer.chipSelectChange).toBe(false);
    expect([...result]).toEqual([0xa1, 0xa2, 0xa3]);
    await transport.close();
  });

  it("keeps write command and payload in one chip-select transaction", async () => {
    const { transport, module } = await openedTransport();
    await transport.writeRegister(0x2c, Uint8Array.from([0x02, 0x03]));

    expect(module.device.messages).toHaveLength(1);
    expect(module.device.messages[0]).toHaveLength(1);
    expect([...module.device.messages[0][0].sendBuffer!]).toEqual([
      spiWriteCmd(0x2c),
      0x02,
      0x03,
    ]);
    await transport.close();
  });

  it.each([0, 3, 5])("rejects invalid returned length %i", async (returnedLength) => {
    const { transport, module } = await openedTransport();
    module.device.returnedLength = returnedLength;
    await expect(transport.readRegister(0x08, 3)).rejects.toBeInstanceOf(BusError);
    await transport.close();
  });

  it("normalizes backend and loader failures", async () => {
    const module = new FakeSpiModule();
    module.device.transferError = new TypeError("native transfer failed");
    const transport = await LinuxSpiTransport.open({}, async () => module);
    await expect(transport.readRegister(0x08, 1)).rejects.toBeInstanceOf(BusError);
    await transport.close();

    await expect(
      LinuxSpiTransport.open({}, async () => {
        throw new Error("module missing");
      }),
    ).rejects.toBeInstanceOf(BusError);
  });

  it("closes idempotently and rejects later operations", async () => {
    const { transport, module } = await openedTransport();
    await transport.close();
    await transport.close();
    expect(module.device.closeCount).toBe(1);
    await expect(transport.readRegister(0x00, 1)).rejects.toBeInstanceOf(BusError);
  });

  it.each([
    [{ speedHz: 99_999 }, "speed"],
    [{ speedHz: 10_000_001 }, "speed"],
    [{ busNumber: -1 }, "bus"],
    [{ deviceNumber: 1.5 }, "device"],
  ] as const)("rejects invalid options %o", async (options) => {
    await expect(LinuxSpiTransport.open(options, async () => new FakeSpiModule())).rejects.toBeInstanceOf(
      InvalidConfigurationError,
    );
  });

  it("rejects invalid register and transfer lengths", async () => {
    const { transport } = await openedTransport();
    await expect(transport.readRegister(-1, 1)).rejects.toBeInstanceOf(InvalidConfigurationError);
    await expect(transport.readRegister(0x40, 1)).rejects.toBeInstanceOf(
      InvalidConfigurationError,
    );
    await expect(transport.readRegister(0x00, 0)).rejects.toBeInstanceOf(
      InvalidConfigurationError,
    );
    await transport.close();
  });
});
