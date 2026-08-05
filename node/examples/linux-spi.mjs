import { ADXL355, PowerMode } from "@oaslananka/adxl355";
import { LinuxSpiTransport } from "@oaslananka/adxl355/linux/spi";
import {
  collectBoundedSamples,
  enterMeasurementAndSettle,
  parseIntegerFlag,
  summarize,
} from "./common.mjs";

const options = {
  busNumber: parseIntegerFlag("bus", 0),
  deviceNumber: parseIntegerFlag("device", 0),
  speedHz: parseIntegerFlag("speed-hz", 1_000_000, { min: 100_000, max: 10_000_000 }),
};
const sampleCount = parseIntegerFlag("samples", 32, { min: 1, max: 1000 });
const timeoutMs = parseIntegerFlag("timeout-ms", 5000, { min: 100, max: 60_000 });

let transport;
let device;
let probed = false;
try {
  transport = await LinuxSpiTransport.open(options);
  device = new ADXL355(transport);
  await device.probe();
  probed = true;
  await enterMeasurementAndSettle(device, PowerMode.Measurement);
  const temperatureC = await device.readTemperatureC();
  const samples = await collectBoundedSamples(device, sampleCount, timeoutMs);
  console.log(JSON.stringify(summarize("spi", temperatureC, samples), null, 2));
} finally {
  if (probed && device) await device.setPowerMode(PowerMode.Standby).catch(() => undefined);
  await transport?.close().catch(() => undefined);
}
