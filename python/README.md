# ADXL355 Python Driver

Typed, transport-agnostic Python 3.10+ support for the Analog Devices ADXL355.

```python
from adxl355 import ADXL355, PowerMode, Range
from adxl355.testing import MockTransport

transport = MockTransport()
transport.set_identity_ok()
device = ADXL355(transport)
device.probe()
device.set_range(Range.G2)
device.set_power_mode(PowerMode.MEASUREMENT)
print(device.read_acceleration_g())
```

Install optional Linux adapters with `adxl355[spi]` or `adxl355[i2c]`.
See the repository root documentation for lifecycle, hardware wiring, and
cross-language behavior details.

## Hardware offset calibration

```python
from adxl355 import ADXL355, Axis, calculate_offset

current = device.read_offset(Axis.X)
offset = calculate_offset(measured_raw=1200, expected_raw=0, current_offset=current)
device.write_offset(Axis.X, offset)
print(device.read_offset(Axis.X))
```

One offset count equals 16 raw acceleration LSB. Writes are volatile, require a
successful probe, enter standby when necessary, and restore the prior power mode.
See `../docs/calibration.md` for orientation, sampling, temperature, rollback,
and accuracy limitations.
