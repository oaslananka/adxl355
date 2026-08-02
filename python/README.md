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
Add `adxl355[gpio]` only for the Linux libgpiod v2 DRDY reference. The core
package remains dependency-free when no extra is selected.
See the repository root documentation for lifecycle, hardware wiring, and
cross-language behavior details.


## Data-ready routing and bounded GPIO acquisition

```python
from adxl355 import ADXL355, DataReadyConfig, InterruptPolarity

# Dedicated DRDY is a separate always-active-high output. INT polarity applies
# only when DATA_RDY is routed through INT1 or INT2.
device.configure_data_ready(
    DataReadyConfig(
        dedicated_drdy_enabled=True,
        route_to_int1=False,
        route_to_int2=False,
        interrupt_polarity=InterruptPolarity.ACTIVE_LOW,
    )
)
print(device.get_data_ready_config())
```

The maintained configuration API accepts only internal synchronization
(`SYNC` timing bits equal zero). External clock/synchronization modes multiplex
DRDY or INT2 differently and raise `UnsupportedConfigurationError`. The method
preserves unrelated `INT_MAP`, `RANGE`, and `POWER_CTL` bits, changes state in
standby, restores measurement mode, and attempts exact rollback after a failed
write. It does not read `STATUS`, so configuration itself does not clear a
pending `DATA_RDY` condition.

The repository's Linux reference uses the official libgpiod v2 Python binding and
blocking rising-edge waits rather than GPIO polling:

```bash
python -m pip install -e 'python[i2c,gpio]'
cd python
PYTHONPATH=src python -m examples.linux_drdy \
  --transport i2c --bus 1 --address 0x1D \
  --gpio-chip /dev/gpiochip0 --gpio-line 17 \
  --samples 32 --timeout-s 5 --max-missed-events 0
```

Every sample carries the kernel monotonic edge timestamp and GPIO line sequence
number. Sequence gaps, overall timeout, GPIO source failure, sensor bus failure,
and `STATUS.FIFO_OVR` are distinct and retain completed samples. The example is
finite, restores standby/±2 g/default ODR/default DRDY routing, and closes both
GPIO and bus resources. It is a reference command, not a background service.
Physical GPIO17/DRDY evidence remains pending until the optional wire is confirmed
on the dedicated fixture.

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

## Electrostatic self-test response

```python
from adxl355 import ADXL355, SelfTestConfig

result = device.run_self_test(SelfTestConfig(sample_count=64, settle_samples=8))
print(result.abs_delta_g)
```

The sequence measures an ST1-only baseline followed by ST1+ST2 stimulation using
bounded `DATA_RDY` polling. The driver temporarily uses ±2 g and 125 Hz, then
restores `SELF_TEST`, `RANGE`, `FILTER`, `POWER_CTL`, and the cached range.
Default configuration reports the measured response without inventing normative
pass/fail limits. Applications may provide fixture-specific thresholds when they
own and document that policy.


## Bounded FIFO sample reads

```python
from adxl355 import FifoReadError

try:
    result = device.read_fifo_samples(max_samples=8)
    for sample in result.samples:
        print(sample)
except FifoReadError as exc:
    print("valid prefix:", exc.partial_samples)
    print("exactly consumed locations:", exc.consumed_locations)
```

`FIFO_ENTRIES` counts axis locations, not XYZ samples: three locations form one
complete X/Y/Z sample and the hardware FIFO holds at most 96 locations (32
samples). One or two trailing locations are valid but remain unread until a
complete sample exists. The call is non-blocking and reads at most the
caller-provided bound.
Empty, overrun, marker-order, virtual-bit, truncated, and overlong conditions use
typed errors. When a later sample fails, already popped locations cannot be
restored; decode errors carry the valid prefix and exact consumed count. A bus
failure during FIFO_DATA sets `consumption_indeterminate=True`, requiring reset or
flush before the caller trusts FIFO alignment again.
