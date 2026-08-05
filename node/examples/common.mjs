export const MEASUREMENT_SETTLE_MS = 20;

function delayMs(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export async function enterMeasurementAndSettle(
  device,
  measurementMode,
  sleep = delayMs,
) {
  await device.setPowerMode(measurementMode);
  await sleep(MEASUREMENT_SETTLE_MS);
}

export function parseIntegerFlag(name, fallback, { min = 0, max = Number.MAX_SAFE_INTEGER } = {}) {
  const index = process.argv.indexOf(`--${name}`);
  const raw = index >= 0 ? process.argv[index + 1] : String(fallback);
  const value = Number(raw);
  if (!Number.isInteger(value) || value < min || value > max) {
    throw new Error(`--${name} must be an integer in the range ${min}..${max}`);
  }
  return value;
}

export async function collectBoundedSamples(device, samples, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  const collected = [];
  while (collected.length < samples && Date.now() < deadline) {
    const status = await device.readStatus();
    if ((status & 0x01) !== 0) collected.push(await device.readRaw());
    else await new Promise((resolve) => setTimeout(resolve, 2));
  }
  if (collected.length !== samples) {
    throw new Error(`sample timeout: expected ${samples}, got ${collected.length}`);
  }
  return collected;
}

export function summarize(transport, temperatureC, samples) {
  const unique = new Set(samples.map(({ x, y, z }) => `${x},${y},${z}`)).size;
  return {
    transport,
    temperatureC: Number(temperatureC.toFixed(4)),
    sampleCount: samples.length,
    uniqueSamples: unique,
    first: samples[0],
    last: samples.at(-1),
  };
}
