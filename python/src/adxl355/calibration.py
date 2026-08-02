"""Deterministic ADXL355 hardware-offset calibration helpers."""

from __future__ import annotations

from adxl355.errors import InvalidConfigurationError

RAW_MIN = -(1 << 19)
RAW_MAX = (1 << 19) - 1
OFFSET_MIN = -(1 << 15)
OFFSET_MAX = (1 << 15) - 1
OFFSET_RAW_LSB_PER_COUNT = 16


def _bounded_integer(name: str, value: int, minimum: int, maximum: int, unit: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidConfigurationError(f"{name} must be an integer {unit}")
    if not minimum <= value <= maximum:
        raise InvalidConfigurationError(f"{name} is outside the {unit} range")
    return value


def _round_raw_delta_to_offset(delta: int) -> int:
    half_count = OFFSET_RAW_LSB_PER_COUNT // 2
    if delta >= 0:
        return (delta + half_count) // OFFSET_RAW_LSB_PER_COUNT
    return -((-delta + half_count) // OFFSET_RAW_LSB_PER_COUNT)


def _limit_offset(value: int, saturate: bool) -> int:
    if OFFSET_MIN <= value <= OFFSET_MAX:
        return value
    if saturate:
        return max(OFFSET_MIN, min(OFFSET_MAX, value))
    direction = "positive" if value > OFFSET_MAX else "negative"
    raise InvalidConfigurationError(f"required {direction} offset exceeds int16 range")


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
    measured = _bounded_integer("measured_raw", measured_raw, RAW_MIN, RAW_MAX, "raw-LSB")
    expected = _bounded_integer("expected_raw", expected_raw, RAW_MIN, RAW_MAX, "raw-LSB")
    current = _bounded_integer(
        "current_offset", current_offset, OFFSET_MIN, OFFSET_MAX, "signed 16-bit"
    )
    adjustment = _round_raw_delta_to_offset(measured - expected)
    return _limit_offset(current + adjustment, saturate)
