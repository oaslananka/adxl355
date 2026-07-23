/**
 * Transport abstraction for ADXL355 communication.
 * Implementations wrap SPI, I2C, or mock backends.
 */
export interface Transport {
  /** Return exactly `length` bytes or reject; any other length is invalid. */
  readRegister(reg: number, length: number): Promise<Uint8Array>;
  /** Write the complete payload or reject; partial success is invalid. */
  writeRegister(reg: number, data: Uint8Array): Promise<void>;
  /** Blocking delay in milliseconds (optional). */
  delayMs?(ms: number): Promise<void>;
}
