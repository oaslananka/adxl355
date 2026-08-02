# Calibration

> **Scope:** C and Python expose opt-in hardware offset read/write APIs and a
> deterministic offset helper. This is a field calibration aid, not factory
> certification. Register presence and successful programming do not imply a
> specified absolute accuracy after calibration.

## Hardware offset format

ADXL355 Rev.D defines each axis offset as a signed 16-bit two's-complement value
stored high byte first in `OFFSET_X_H/L`, `OFFSET_Y_H/L`, or `OFFSET_Z_H/L`.
The datasheet describes the trim value in the post-processing path and states
that its bit significance matches acceleration data bits `[19:4]`. On the
maintained Rev.D SPI fixture, programming a positive offset count reduced the
reported acceleration by 16 raw LSB. The correction API therefore uses:

```text
1 offset-register count = 16 raw acceleration LSB
new_offset = current_offset + round_half_away_from_zero(
    (measured_raw - expected_raw) / 16
)
```

The helper inputs are rounded integer raw-LSB means in the signed 20-bit range
`[-524288, 524287]`. The output range is signed 16-bit
`[-32768, 32767]`. Strict mode rejects a correction outside that range;
explicit saturation mode clamps it. Offset writes themselves never silently
clamp an out-of-range caller value.

Offsets are volatile device state. A power cycle or software reset returns them
to their reset values. Persisting calibration belongs to caller-owned storage;
the driver does not write files, flash, or cloud state.

## C API

```c
int16_t offset;
adxl355_calculate_offset(measured_raw, expected_raw, false, &offset);
adxl355_write_offset(&device, ADXL355_AXIS_X, offset);
adxl355_read_offset(&device, ADXL355_AXIS_X, &offset);
```

`adxl355_read_offset()` and `adxl355_write_offset()` require a successful probe.
Writes use one two-byte register transaction, temporarily enter standby when the
device is measuring, and restore the exact previous `POWER_CTL` value. If the
offset write succeeds but mode restoration fails, the API returns a bus error,
the new offset remains applied, and the device remains in safe standby.

## Python API

```python
from adxl355 import ADXL355, Axis, calculate_offset

current = device.read_offset(Axis.X)
offset = calculate_offset(measured_raw, expected_raw, current_offset=current)
device.write_offset(Axis.X, offset)
assert device.read_offset(Axis.X) == offset
```

`calculate_offset(..., saturate=True)` must be an explicit caller decision. C and
Python use the same half-away-from-zero rounding and signed range checks.

## Repeatable stationary-axis procedure

1. Mount the sensor rigidly and keep it stationary. Record the board identifier,
   mounting orientation, configured range, ODR/filter, supply, and fixture.
2. Allow the board and sensor temperature to settle. Record the ADXL355
   temperature before and after sampling.
3. Read and save all three existing signed offsets so rollback is always
   possible.
4. Select an orientation with one axis aligned to gravity. The expected raw mean
   is zero for the two transverse axes and approximately `+1 g` or `-1 g` for
   the aligned axis. Convert the expected acceleration using the active range's
   documented raw scale.
5. Collect at least 100 samples; 256 or more is preferred for low-frequency
   measurements. Reject runs with movement, FIFO overflow, changing range/ODR,
   or a material temperature drift.
6. Average each axis, round each mean to the nearest raw LSB, and calculate each
   new absolute offset from the saved current offset.
7. Write the new offsets, then collect the same number of samples under unchanged
   conditions. Compare the transverse zero-g residuals and the aligned-axis
   error to the pre-calibration values.
8. Accept the result only when the residual error improves repeatably. Restore the saved offsets on failure, interruption, or unexpected orientation.
9. Repeat at `+1 g` and `-1 g` orientations when scale error matters. Hardware
   offsets correct bias; they do not correct sensitivity, nonlinearity,
   cross-axis response, mounting strain, vibration, or temperature dependence.


## Physical sign and rollback validation

A Raspberry Pi 5 SPI fixture test against commit `24cb2c5` programmed trial
offsets and collected 256 samples before and after. The first formula candidate
used the opposite sign; `+116` counts on X shifted the mean by approximately
`-1870` raw LSB, matching `-116 × 16`, and increased the bias norm. The test
rejected that result and restored all three offsets to zero and `POWER_CTL` to
its original standby value. This failure-path evidence is why the public helper
uses `(measured_raw - expected_raw) / 16`. A corrected pre/post run is required
before claiming repeatable calibration improvement.

## Temperature and residual error

The datasheet specifies offset drift with temperature, so one room-temperature
measurement is not a universal calibration. High-accuracy applications should
characterize multiple temperatures and orientations and apply caller-owned
software compensation. Quantization alone leaves up to approximately half an
offset count (8 raw LSB) after rounding, before noise and physical effects.

A calibration report should record pre/post means and standard deviations,
temperature, orientation, sample count, range, ODR, offset values, driver commit,
and fixture identifier. Do not record secrets, host credentials, or unrelated
machine data.

## Current implementation coverage

- C: signed offset read/write and deterministic calculation helper.
- Python: signed offset read/write and deterministic calculation helper.
- C++, Rust, Node.js, and Go: register constants may exist, but no maintained
  public offset-calibration method is claimed yet.
- Physical repeatability evidence is required before describing these helpers as
  validated for a particular board or mounting configuration.
