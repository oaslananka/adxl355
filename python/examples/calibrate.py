"""ADXL355 offset measurement example using the mock transport."""

from adxl355 import ADXL355, PowerMode, Range
from adxl355.testing import MockTransport


def measure_offsets(device: ADXL355, samples: int = 100) -> tuple[float, float, float]:
    """Return average raw readings for each axis."""

    sum_x = sum_y = sum_z = 0
    for _ in range(samples):
        raw = device.read_raw()
        sum_x += raw.x
        sum_y += raw.y
        sum_z += raw.z
    divisor = float(samples)
    return (sum_x / divisor, sum_y / divisor, sum_z / divisor)


def main() -> None:
    transport = MockTransport()
    transport.set_identity_ok()
    device = ADXL355(transport)
    device.probe()

    device.set_range(Range.G4)
    device.set_power_mode(PowerMode.MEASUREMENT)
    offset_x, offset_y, offset_z = measure_offsets(device)

    scale_g = 7.8e-6
    print(
        f"Offsets (raw LSB):  x={offset_x:.1f}  "
        f"y={offset_y:.1f}  z={offset_z:.1f}"
    )
    print(
        f"Offsets (g):        x={offset_x * scale_g:.6f}  "
        f"y={offset_y * scale_g:.6f}  z={offset_z * scale_g:.6f}"
    )
    print("(Mock data — real hardware will show actual offsets)")


if __name__ == "__main__":
    main()
