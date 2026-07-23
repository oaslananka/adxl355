# Calibration

> **Scope:** This document is a calibration procedure and design reference.
> There is no public calibration helper or offset-register programming API in
> the maintained drivers. Applications must collect samples and apply any
> correction externally until those APIs are implemented and tested.

## Overview

ADXL355 calibration adjusts:

1. **Offset** — zero-g bias per axis
2. **Scale** — sensitivity per axis (typically ±1% nominal)

The device provides dedicated offset registers (OFFSET_X_H/L, OFFSET_Y_H/L, OFFSET_Z_H/L) that can compensate for zero-g offset in hardware.

## Offset Calibration Procedure

1. Place the sensor on a level, stationary surface.
2. Measure the raw acceleration for each axis over N samples (e.g., 100 samples at 125 Hz).
3. Average the readings to get the offset for each axis.
4. For the X and Y axes, the offset should be near zero (ideally 0 LSB).
5. For the Z axis, the offset should be approximately +1g (since gravity pulls down).
6. Compute the offset register value:

```
offset_reg = -round(raw_offset / scale_factor)
```

Where `scale_factor` is the range-dependent sensitivity in g/LSB.

7. Write the offset value to the corresponding OFFSET_X_H/L registers.

## Scale Calibration

Scale calibration requires a known reference acceleration (e.g., by rotating the sensor ±1g). This is typically done by:
1. Aligning each axis with +1g and -1g.
2. Recording the raw output at both orientations.
3. Computing the actual scale:

```
actual_scale_g_per_lsb = 2.0 / (raw_positive - raw_negative)
```

Then adjusting the software scale factor accordingly.

## Temperature Effects

The ADXL355 has temperature-dependent offset drift. For high-accuracy applications:
- Measure offset at multiple temperatures
- Create a temperature compensation table
- Interpolate correction values during normal operation

## Implementation status

The register map includes offset registers, but register presence does not imply a public API. The offset registers are not implemented as a public driver method in this release line.

## TODO

- [ ] Verify offset register format from datasheet
- [ ] Verify offset LSB weight from datasheet
- [ ] Add calibration helper functions to Python package
- [ ] Add calibration example with data logging
- [ ] Document compensation for temperature effects
