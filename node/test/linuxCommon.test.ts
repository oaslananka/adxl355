import { describe, expect, it } from "vitest";

import { BusError, InvalidConfigurationError } from "../src/errors.js";
import {
  MAX_ADAPTER_TRANSFER_BYTES,
  delayMs,
  normalizeAdapterError,
  validateNonNegativeInteger,
  validateRegister,
  validateTransferLength,
} from "../src/linux/common.js";

describe("Linux transport shared validation", () => {
  it.each([0, 1, 123])("allows non-negative integer %i", (value) => {
    expect(() => validateNonNegativeInteger("bus", value)).not.toThrow();
  });

  it.each([-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY])(
    "rejects invalid non-negative integer %s",
    (value) => {
      expect(() => validateNonNegativeInteger("bus", value)).toThrowError(
        InvalidConfigurationError,
      );
    },
  );

  it.each([0, 0x3f])("accepts register boundary %i", (reg) => {
    expect(() => validateRegister(reg)).not.toThrow();
  });

  it.each([-1, 0x40, 1.5, Number.NaN])("rejects invalid register %s", (reg) => {
    expect(() => validateRegister(reg)).toThrowError(InvalidConfigurationError);
  });

  it("allows full adapter length and smaller custom bounds", () => {
    expect(() => validateTransferLength(1)).not.toThrow();
    expect(() => validateTransferLength(MAX_ADAPTER_TRANSFER_BYTES)).not.toThrow();
    expect(() => validateTransferLength(2, 2)).not.toThrow();
  });

  it.each([0, -1, 1.5, Number.NaN, MAX_ADAPTER_TRANSFER_BYTES + 1])(
    "rejects invalid transfer length %s",
    (length) => {
      expect(() => validateTransferLength(length)).toThrowError(
        InvalidConfigurationError,
      );
    },
  );

  it("enforces custom transfer limits", () => {
    expect(() => validateTransferLength(3, 2)).toThrowError(InvalidConfigurationError);
  });
});

describe("Linux native adapter failure normalization", () => {
  it("preserves the original BusError identity", () => {
    const original = new BusError("already contextualized");
    expect(normalizeAdapterError("read", original)).toBe(original);
  });

  it("preserves native Error as cause and includes operation", () => {
    const original = new TypeError("adapter unavailable");
    const normalized = normalizeAdapterError("read-register", original);
    expect(normalized).toBeInstanceOf(BusError);
    expect(normalized.message).toContain("read-register: adapter unavailable");
    expect((normalized as Error & { cause?: unknown }).cause).toBe(original);
  });

  it("normalizes a non-Error native rejection without losing its cause", () => {
    const normalized = normalizeAdapterError("write", "disconnected");
    expect(normalized).toBeInstanceOf(BusError);
    expect(normalized.message).toContain("write: disconnected");
    expect((normalized as Error & { cause?: unknown }).cause).toBe("disconnected");
  });
});

describe("Linux native adapter delay guard", () => {
  it.each([-1, Number.NaN, Number.POSITIVE_INFINITY])(
    "rejects invalid delay %s",
    async (delay) => {
      await expect(delayMs(delay)).rejects.toBeInstanceOf(InvalidConfigurationError);
    },
  );

  it("accepts a zero-length asynchronous delay", async () => {
    await expect(delayMs(0)).resolves.toBeUndefined();
  });
});
