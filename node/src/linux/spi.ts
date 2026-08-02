import { Buffer } from "node:buffer";
import { BusError, InvalidConfigurationError } from "../errors.js";
import { spiReadCmd, spiWriteCmd } from "../registers.js";
import type { Transport } from "../transport.js";
import {
  delayMs,
  MAX_ADAPTER_TRANSFER_BYTES,
  normalizeAdapterError,
  validateNonNegativeInteger,
  validateRegister,
  validateTransferLength,
} from "./common.js";

export interface SpiOpenOptions {
  mode: 0;
  chipSelectHigh: false;
  lsbFirst: false;
  threeWire: false;
  noChipSelect: false;
  bitsPerWord: 8;
  maxSpeedHz: number;
}

export interface SpiTransfer {
  byteLength: number;
  sendBuffer?: Buffer;
  receiveBuffer?: Buffer;
  speedHz?: number;
  bitsPerWord?: number;
  chipSelectChange?: boolean;
}

export type SpiMessage = SpiTransfer[];

export interface LinuxSpiOptions {
  busNumber?: number;
  deviceNumber?: number;
  speedHz?: number;
}

export interface SpiDeviceBackend {
  transfer(
    message: SpiMessage,
    callback: (error: Error | null | undefined, message: SpiMessage) => void,
  ): unknown;
  close(callback: (error: Error | null | undefined) => void): void;
}

export interface SpiModuleBackend {
  open(
    busNumber: number,
    deviceNumber: number,
    options: SpiOpenOptions,
    callback: (error: Error | null | undefined) => void,
  ): SpiDeviceBackend;
}

export type SpiModuleLoader = () => Promise<SpiModuleBackend>;

const MIN_SPI_SPEED_HZ = 100_000;
const MAX_SPI_SPEED_HZ = 10_000_000;

async function defaultSpiLoader(): Promise<SpiModuleBackend> {
  try {
    const imported = await import("spi-device");
    return ((imported as { default?: unknown }).default ?? imported) as SpiModuleBackend;
  } catch (error) {
    throw normalizeAdapterError(
      "Optional dependency spi-device is unavailable; install optional dependencies on Linux",
      error,
    );
  }
}

function validateOptions(options: Required<LinuxSpiOptions>): void {
  validateNonNegativeInteger("busNumber", options.busNumber);
  validateNonNegativeInteger("deviceNumber", options.deviceNumber);
  if (
    !Number.isInteger(options.speedHz) ||
    options.speedHz < MIN_SPI_SPEED_HZ ||
    options.speedHz > MAX_SPI_SPEED_HZ
  ) {
    throw new InvalidConfigurationError(
      `speedHz must be in the range ${MIN_SPI_SPEED_HZ}..${MAX_SPI_SPEED_HZ}`,
    );
  }
}

export class LinuxSpiTransport implements Transport {
  private closed = false;

  private constructor(
    private readonly device: SpiDeviceBackend,
    readonly busNumber: number,
    readonly deviceNumber: number,
    readonly speedHz: number,
  ) {}

  static async open(
    options: LinuxSpiOptions = {},
    loader: SpiModuleLoader = defaultSpiLoader,
  ): Promise<LinuxSpiTransport> {
    const resolved: Required<LinuxSpiOptions> = {
      busNumber: options.busNumber ?? 0,
      deviceNumber: options.deviceNumber ?? 0,
      speedHz: options.speedHz ?? 1_000_000,
    };
    validateOptions(resolved);
    let module: SpiModuleBackend;
    try {
      module = await loader();
    } catch (error) {
      throw normalizeAdapterError("Failed to load optional spi-device backend", error);
    }
    return new Promise((resolve, reject) => {
      let device: SpiDeviceBackend;
      try {
        device = module.open(
          resolved.busNumber,
          resolved.deviceNumber,
          {
            mode: 0,
            chipSelectHigh: false,
            lsbFirst: false,
            threeWire: false,
            noChipSelect: false,
            bitsPerWord: 8,
            maxSpeedHz: resolved.speedHz,
          },
          (error) => {
            queueMicrotask(() => {
              if (error) {
                reject(normalizeAdapterError("Failed to open Linux SPI device", error));
                return;
              }
              if (!device) {
                reject(new BusError("Linux SPI backend did not return a device handle"));
                return;
              }
              resolve(
                new LinuxSpiTransport(
                  device,
                  resolved.busNumber,
                  resolved.deviceNumber,
                  resolved.speedHz,
                ),
              );
            });
          },
        );
      } catch (error) {
        reject(normalizeAdapterError("Failed to open Linux SPI device", error));
      }
    });
  }

  private ensureOpen(): void {
    if (this.closed) {
      throw new BusError("Linux SPI transport is closed");
    }
  }

  private async transfer(sendBuffer: Buffer): Promise<Buffer> {
    this.ensureOpen();
    validateTransferLength(sendBuffer.length, MAX_ADAPTER_TRANSFER_BYTES + 1);
    const receiveBuffer = Buffer.alloc(sendBuffer.length);
    const message: SpiMessage = [
      {
        sendBuffer,
        receiveBuffer,
        byteLength: sendBuffer.length,
        speedHz: this.speedHz,
        bitsPerWord: 8,
        chipSelectChange: false,
      },
    ];
    const returned = await new Promise<SpiMessage>((resolve, reject) => {
      try {
        this.device.transfer(message, (error, completed) => {
          if (error) {
            reject(normalizeAdapterError("Linux SPI transfer failed", error));
          } else {
            resolve(completed);
          }
        });
      } catch (error) {
        reject(normalizeAdapterError("Linux SPI transfer failed", error));
      }
    });
    if (returned.length !== 1) {
      throw new BusError(`Invalid SPI message count: expected 1, got ${returned.length}`);
    }
    const completed = returned[0];
    if (completed.byteLength !== sendBuffer.length || completed.receiveBuffer?.length !== sendBuffer.length) {
      throw new BusError(
        `Invalid SPI transfer length: expected ${sendBuffer.length}, got ` +
          `${completed.receiveBuffer?.length ?? 0}`,
      );
    }
    return completed.receiveBuffer;
  }

  async readRegister(reg: number, length: number): Promise<Uint8Array> {
    validateRegister(reg);
    validateTransferLength(length);
    const send = Buffer.alloc(length + 1);
    send[0] = spiReadCmd(reg);
    const receive = await this.transfer(send);
    return Uint8Array.from(receive.subarray(1));
  }

  async writeRegister(reg: number, data: Uint8Array): Promise<void> {
    validateRegister(reg);
    validateTransferLength(data.length);
    const send = Buffer.alloc(data.length + 1);
    send[0] = spiWriteCmd(reg);
    Buffer.from(data).copy(send, 1);
    await this.transfer(send);
  }

  async delayMs(ms: number): Promise<void> {
    await delayMs(ms);
  }

  async close(): Promise<void> {
    if (this.closed) {
      return;
    }
    this.closed = true;
    await new Promise<void>((resolve, reject) => {
      try {
        this.device.close((error) => {
          if (error) {
            reject(normalizeAdapterError("Failed to close Linux SPI device", error));
          } else {
            resolve();
          }
        });
      } catch (error) {
        reject(normalizeAdapterError("Failed to close Linux SPI device", error));
      }
    });
  }
}
