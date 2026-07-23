"""Tests for 20-bit raw data decoding and conversion."""

import json
import math
from pathlib import Path

import pytest

from adxl355.constants import (
    SCALE_2G_G_PER_LSB,
    SCALE_4G_G_PER_LSB,
    SCALE_8G_G_PER_LSB,
    STANDARD_GRAVITY_M_S2,
)
from adxl355.device import _decode_raw20, raw_to_g, raw_to_mps2
from adxl355.registers import Range

# Load test vectors from shared spec
_SPEC_DIR = Path(__file__).resolve().parents[2] / "spec"
_TEST_VECTORS_PATH = _SPEC_DIR / "test_vectors.json"

if _TEST_VECTORS_PATH.exists():
    with open(_TEST_VECTORS_PATH) as f:
        _TEST_VECTORS = json.load(f)
else:
    _TEST_VECTORS = {"raw_decode": []}


class TestDecodeRaw20:
    """Verify 20-bit two's complement decoding."""

    @pytest.mark.parametrize(
        "b0,b1,b2,expected",
        [
            (0, 0, 0, 0),
            (0, 0, 16, 1),
            (127, 255, 240, 524287),
            (128, 0, 0, -524288),
            (255, 255, 240, -1),
        ],
    )
    def test_decode(self, b0: int, b1: int, b2: int, expected: int) -> None:
        assert _decode_raw20(b0, b1, b2) == expected

    @pytest.mark.parametrize("v", _TEST_VECTORS.get("raw_decode", []))
    def test_from_shared_vectors(self, v: dict) -> None:
        b = v["bytes"]
        result = _decode_raw20(b[0], b[1], b[2])
        assert result == v["raw"], f"{v['name']}: expected {v['raw']}, got {result}"

    def test_half_scale_positive(self) -> None:
        """bytes [64, 0, 0] → 262144 (half-scale positive)."""
        assert _decode_raw20(64, 0, 0) == 262144

    def test_half_scale_negative(self) -> None:
        """bytes [192, 0, 0] → -262144 (half-scale negative)."""
        assert _decode_raw20(192, 0, 0) == -262144


class TestRawToG:
    """Verify raw-to-g conversion."""

    def test_zero_raw(self) -> None:
        assert raw_to_g(0, Range.G2) == 0.0
        assert raw_to_g(0, Range.G4) == 0.0
        assert raw_to_g(0, Range.G8) == 0.0

    def test_positive_max_2g(self) -> None:
        expected = 524287 * SCALE_2G_G_PER_LSB
        assert math.isclose(raw_to_g(524287, Range.G2), expected, abs_tol=1e-6)

    def test_negative_min_2g(self) -> None:
        expected = -524288 * SCALE_2G_G_PER_LSB
        assert math.isclose(raw_to_g(-524288, Range.G2), expected, abs_tol=1e-6)

    def test_scale_consistency(self) -> None:
        """Raw value 1 should give exactly 1 LSB worth of g."""
        assert math.isclose(raw_to_g(1, Range.G2), SCALE_2G_G_PER_LSB, abs_tol=1e-12)
        assert math.isclose(raw_to_g(1, Range.G4), SCALE_4G_G_PER_LSB, abs_tol=1e-12)
        assert math.isclose(raw_to_g(1, Range.G8), SCALE_8G_G_PER_LSB, abs_tol=1e-12)


class TestRawToMps2:
    """Verify raw-to-m/s² conversion."""

    def test_zero(self) -> None:
        assert raw_to_mps2(0, Range.G2) == 0.0

    def test_positive(self) -> None:
        raw = 100000
        expected = raw * SCALE_2G_G_PER_LSB * STANDARD_GRAVITY_M_S2
        assert math.isclose(raw_to_mps2(raw, Range.G2), expected, abs_tol=1e-5)
