# ADXL355 Node.js Driver

Typed ESM support for the Analog Devices ADXL355 with a transport-agnostic API.

```ts
import { ADXL355, PowerMode, Range } from "adxl355";

const device = new ADXL355(transport);
await device.probe();
await device.setRange(Range.G2);
await device.setPowerMode(PowerMode.Measurement);
console.log(await device.readAccelerationG());
```

A transport must return exactly the requested read length or reject. See the
repository root documentation for the lifecycle and hardware contracts.
