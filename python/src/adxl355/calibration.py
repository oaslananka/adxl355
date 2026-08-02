"""Deterministic ADXL355 hardware-offset calibration helpers."""

from __future__ import annotations

from adxl355.errors import InvalidConfigurationError

RAW_MIN = -(1 << 19)
RAW_MAX = (1 << 19) - 1
OFFSET_MIN = -(1 << 15)
OFFSET_MAX = (1 << 15) - 1
OFFSET_RAW_LSB_PER_COUNT = 16


def calculate_offset(
    measured_raw: int,
    expected_raw: int,
    current_offset: int = 0,
    *,
    saturate: bool = False,
) -> int:
    """Calculate a signed 16-bit hardware offset from rounded raw means.

    One offset count has the significance of acceleration data bits [19:4],
    equivalent to 16 raw acceleration LSB. The result is the new absolute
    register value: ``current_offset +
    round_half_away_from_zero((measured_raw - expected_raw) / 16)``.
    Inputs must already be rounded to integer raw LSB and lie in the signed
    20-bit acceleration range.
    """
    for name, value in (("measured_raw", measured_raw), ("expected_raw", expected_raw)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidConfigurationError(f"{name} must be an integer raw-LSB value")
        if not RAW_MIN <= value <= RAW_MAX:
            raise InvalidConfigurationError(f"{name} is outside the signed 20-bit range")

    if isinstance(current_offset, bool) or not isinstance(current_offset, int):
        raise InvalidConfigurationError("current_offset must be an integer")
    if not OFFSET_MIN <= current_offset <= OFFSET_MAX:
        raise InvalidConfigurationError("current_offset is outside the signed 16-bit range")

    delta = measured_raw - expected_raw
    adjustment = (delta + 8) // 16 if delta >= 0 else -((-delta + 8) // 16)
    counts = current_offset + adjustment
    if counts > OFFSET_MAX:
        if not saturate:
            raise InvalidConfigurationError("required positive offset exceeds int16 range")
        return OFFSET_MAX
    if counts < OFFSET_MIN:
        if not saturate:
            raise InvalidConfigurationError("required negative offset exceeds int16 range")
        return OFFSET_MIN
    return counts
