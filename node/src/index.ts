export { ADXL355 } from "./device.js";
export { decodeRaw20, rawToG, rawToMps2 } from "./device.js";
export { Reg, Range, PowerMode, Odr, STANDARD_GRAVITY_M_S2 } from "./registers.js";
export type { Transport } from "./transport.js";
export type { RawXYZ, AccelXYZ } from "./types.js";
export {
  ADXL355Error,
  BusError,
  DeviceNotFoundError,
  DeviceStateError,
  InvalidConfigurationError,
  DataNotReadyError,
} from "./errors.js";
