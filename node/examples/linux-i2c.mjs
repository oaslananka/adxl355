import { ADXL355, PowerMode } from "@oaslananka/adxl355";
import { LinuxI2cTransport } from "@oaslananka/adxl355/linux/i2c";
import { collectBoundedSamples, parseIntegerFlag, summarize } from "./common.mjs";

const options = {
  busNumber: parseIntegerFlag("bus", 1),
  address: parseIntegerFlag("address", 0x1d, { min: 0, max: 0x7f }),
  busHz: parseIntegerFlag("bus-hz", 100_000, { min: 100_000, max: 3_400_000 }),
};
const sampleCount = parseIntegerFlag("samples", 32, { min: 1, max: 1000 });
const timeoutMs = parseIntegerFlag("timeout-ms", 5000, { min: 100, max: 60_000 });

let transport;
let device;
let probed = false;
try {
  transport = await LinuxI2cTransport.open(options);
  device = new ADXL355(transport);
  await device.probe();
  probed = true;
  await device.setPowerMode(PowerMode.Measurement);
  const temperatureC = await device.readTemperatureC();
  const samples = await collectBoundedSamples(device, sampleCount, timeoutMs);
  console.log(JSON.stringify(summarize("i2c", temperatureC, samples), null, 2));
} finally {
  if (probed && device) await device.setPowerMode(PowerMode.Standby).catch(() => undefined);
  await transport?.close().catch(() => undefined);
}
