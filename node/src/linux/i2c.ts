import { Buffer } from "node:buffer";
import { BusError, InvalidConfigurationError } from "../errors.js";
import { I2C_ALTERNATE_ADDR, I2C_DEFAULT_ADDR } from "../registers.js";
import type { Transport } from "../transport.js";
import {
  delayMs,
  normalizeAdapterError,
  validateNonNegativeInteger,
  validateRegister,
  validateTransferLength,
} from "./common.js";

export interface LinuxI2cOptions {
  busNumber?: number;
  address?: number;
  busHz?: number;
}

export interface I2cBusBackend {
  readI2cBlock(
    address: number,
    command: number,
    length: number,
    buffer: Buffer,
  ): Promise<{ bytesRead: number; buffer: Buffer }>;
  writeI2cBlock(
    address: number,
    command: number,
    length: number,
    buffer: Buffer,
  ): Promise<{ bytesWritten: number; buffer: Buffer }>;
  close(): Promise<void>;
}

export interface I2cModuleBackend {
  openPromisified(busNumber: number): Promise<I2cBusBackend>;
}

export type I2cModuleLoader = () => Promise<I2cModuleBackend>;

const SUPPORTED_BUS_RATES = new Set([100_000, 400_000, 1_000_000, 3_400_000]);
const MAX_I2C_BLOCK_BYTES = 32;

async function defaultI2cLoader(): Promise<I2cModuleBackend> {
  try {
    const imported = await import("i2c-bus");
    return ((imported as { default?: unknown }).default ?? imported) as I2cModuleBackend;
  } catch (error) {
    throw normalizeAdapterError(
      "Optional dependency i2c-bus is unavailable; install optional dependencies on Linux",
      error,
    );
  }
}

function validateOptions(options: Required<LinuxI2cOptions>): void {
  validateNonNegativeInteger("busNumber", options.busNumber);
  if (options.address !== I2C_DEFAULT_ADDR && options.address !== I2C_ALTERNATE_ADDR) {
    throw new InvalidConfigurationError("address must be 0x1D or 0x53");
  }
  if (!SUPPORTED_BUS_RATES.has(options.busHz)) {
    throw new InvalidConfigurationError(
      "busHz must be one of 100000, 400000, 1000000, or 3400000",
    );
  }
}

export class LinuxI2cTransport implements Transport {
  private closed = false;

  private constructor(
    private readonly bus: I2cBusBackend,
    readonly busNumber: number,
    readonly address: number,
    readonly busHz: number,
  ) {}

  static async open(
    options: LinuxI2cOptions = {},
    loader: I2cModuleLoader = defaultI2cLoader,
  ): Promise<LinuxI2cTransport> {
    const resolved: Required<LinuxI2cOptions> = {
      busNumber: options.busNumber ?? 1,
      address: options.address ?? I2C_DEFAULT_ADDR,
      busHz: options.busHz ?? 100_000,
    };
    validateOptions(resolved);
    try {
      const module = await loader();
      const bus = await module.openPromisified(resolved.busNumber);
      return new LinuxI2cTransport(bus, resolved.busNumber, resolved.address, resolved.busHz);
    } catch (error) {
      throw normalizeAdapterError("Failed to open Linux I2C bus", error);
    }
  }

  private ensureOpen(): void {
    if (this.closed) {
      throw new BusError("Linux I2C transport is closed");
    }
  }

  async readRegister(reg: number, length: number): Promise<Uint8Array> {
    this.ensureOpen();
    validateRegister(reg);
    validateTransferLength(length, MAX_I2C_BLOCK_BYTES);
    const target = Buffer.alloc(length);
    let result: { bytesRead: number; buffer: Buffer };
    try {
      result = await this.bus.readI2cBlock(this.address, reg, length, target);
    } catch (error) {
      throw normalizeAdapterError("Linux I2C register read failed", error);
    }
    if (result.bytesRead !== length || result.buffer.length !== length) {
      throw new BusError(
        `Invalid I2C read length: expected ${length}, got ${result.bytesRead}/${result.buffer.length}`,
      );
    }
    return Uint8Array.from(result.buffer);
  }

  async writeRegister(reg: number, data: Uint8Array): Promise<void> {
    this.ensureOpen();
    validateRegister(reg);
    validateTransferLength(data.length, MAX_I2C_BLOCK_BYTES);
    let result: { bytesWritten: number; buffer: Buffer };
    try {
      const buffer = Buffer.from(data);
      result = await this.bus.writeI2cBlock(this.address, reg, buffer.length, buffer);
    } catch (error) {
      throw normalizeAdapterError("Linux I2C register write failed", error);
    }
    if (result.bytesWritten !== data.length || result.buffer.length !== data.length) {
      throw new BusError(
        `Invalid I2C write length: expected ${data.length}, got ` +
          `${result.bytesWritten}/${result.buffer.length}`,
      );
    }
  }

  async delayMs(ms: number): Promise<void> {
    await delayMs(ms);
  }

  async close(): Promise<void> {
    if (this.closed) {
      return;
    }
    this.closed = true;
    try {
      await this.bus.close();
    } catch (error) {
      throw normalizeAdapterError("Failed to close Linux I2C bus", error);
    }
  }
}
