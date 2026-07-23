# ADXL355 Python Driver

Typed, transport-agnostic Python support for the Analog Devices ADXL355.

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
