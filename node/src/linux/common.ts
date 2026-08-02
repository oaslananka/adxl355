import { BusError, InvalidConfigurationError } from "../errors.js";

export const MAX_ADAPTER_TRANSFER_BYTES = 4096;

export function validateNonNegativeInteger(name: string, value: number): void {
  if (!Number.isInteger(value) || value < 0) {
    throw new InvalidConfigurationError(`${name} must be a non-negative integer`);
  }
}

export function validateRegister(reg: number): void {
  if (!Number.isInteger(reg) || reg < 0 || reg > 0x3f) {
    throw new InvalidConfigurationError("register must be an integer in the range 0..63");
  }
}

export function validateTransferLength(length: number, max = MAX_ADAPTER_TRANSFER_BYTES): void {
  if (!Number.isInteger(length) || length < 1 || length > max) {
    throw new InvalidConfigurationError(`length must be in the range 1..${max}`);
  }
}

export function normalizeAdapterError(operation: string, error: unknown): BusError {
  if (error instanceof BusError) {
    return error;
  }
  const detail = error instanceof Error ? error.message : String(error);
  const normalized = new BusError(`${operation}: ${detail}`);
  (normalized as Error & { cause?: unknown }).cause = error;
  return normalized;
}

export async function delayMs(ms: number): Promise<void> {
  if (!Number.isFinite(ms) || ms < 0) {
    throw new InvalidConfigurationError("delay must be a non-negative number");
  }
  await new Promise<void>((resolve) => setTimeout(resolve, ms));
}
