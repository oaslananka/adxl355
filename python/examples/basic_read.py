"""Basic ADXL355 read example using the hardware-free mock transport.

Run after installing the package::

    python examples/basic_read.py

Replace ``MockTransport`` with a hardware adapter for a real sensor.
"""

from adxl355 import ADXL355, PowerMode, Range
from adxl355.testing import MockTransport


def main() -> None:
    transport = MockTransport()
    transport.set_identity_ok()
    device = ADXL355(transport)
    device.probe()

    device.set_range(Range.G4)
    device.set_power_mode(PowerMode.MEASUREMENT)

    raw = device.read_raw()
    accel_g = device.read_acceleration_g()
    accel_mps2 = device.read_acceleration_mps2()
    temperature = device.read_temperature_c()
    status = device.read_status()

    print(f"Raw:  x={raw.x:7d}  y={raw.y:7d}  z={raw.z:7d}")
    print(
        f"Accel (g):     x={accel_g.x:10.6f}  "
        f"y={accel_g.y:10.6f}  z={accel_g.z:10.6f}"
    )
    print(
        f"Accel (m/s²):  x={accel_mps2.x:10.6f}  "
        f"y={accel_mps2.y:10.6f}  z={accel_mps2.z:10.6f}"
    )
    print(f"Temperature: {temperature:.2f} °C")
    print(f"Status:  0x{status:02X}")


if __name__ == "__main__":
    main()
