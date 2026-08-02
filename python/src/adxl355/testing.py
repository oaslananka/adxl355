"""
Mock transport for ADXL355 testing without hardware.

Usage:
    from adxl355.testing import MockTransport

    transport = MockTransport()
    transport.set_identity_ok()
    transport.set_xyz_raw(x=1000, y=-2000, z=32000)
"""

from __future__ import annotations

import time
from typing import Optional

from adxl355.constants import DEVID_AD, DEVID_MST, PARTID, RESET_CODE
from adxl355.registers import SELF_TEST_MASK, STATUS_DATA_RDY, Range, Register
from adxl355.types import RawXYZ


class MockTransport:
    """
    Mock bus transport that simulates ADXL355 register behaviour.

    Maintains an internal register file that records all writes and
    provides pre-configured values for reads.
    """

    NUM_REGS = 128
    MAX_CALL_LOG = 256

    def __init__(self) -> None:
        self._regs = [0] * self.NUM_REGS
        self._regs[Register.RANGE] = int(Range.G2)
        self._force_error: Optional[Exception] = None
        self._short_read_reg: Optional[int] = None
        self._short_read_length = 0
        self.fail_write_reg: Optional[int] = None
        self.fail_write_occurrence = 0
        self._matching_writes = 0
        self._self_test_baseline: RawXYZ | None = None
        self._self_test_stimulated: RawXYZ | None = None
        self.call_count = 0
        self.calls: list[dict[str, object]] = []

    # ------------------------------------------------------------------
    # Transport protocol
    # ------------------------------------------------------------------

    def read_register(self, reg: int, length: int = 1) -> bytes:
        if self._force_error is not None:
            raise self._force_error
        self._log_call(False, reg, length)
        if (
            reg == Register.XDATA3
            and length == 9
            and self._self_test_baseline is not None
            and self._self_test_stimulated is not None
        ):
            mode = self._regs[Register.SELF_TEST] & SELF_TEST_MASK
            if mode == SELF_TEST_MASK:
                data = self._encode_xyz(self._self_test_stimulated)
            elif mode == 0x01:
                data = self._encode_xyz(self._self_test_baseline)
            else:
                data = bytes(self._regs[reg : reg + length])
        else:
            data = bytes(self._regs[reg : reg + length])
        # Pad if beyond register file size
        if len(data) < length:
            data += b"\x00" * (length - len(data))
        if self._short_read_reg == reg:
            if self._short_read_length <= len(data):
                return data[: self._short_read_length]
            return data + bytes(self._short_read_length - len(data))
        return data

    def write_register(self, reg: int, data: bytes) -> None:
        if self._force_error is not None:
            raise self._force_error
        if self.fail_write_reg == reg:
            self._matching_writes += 1
            if (
                self.fail_write_occurrence == 0
                or self._matching_writes == self.fail_write_occurrence
            ):
                raise RuntimeError(f"injected write failure at register 0x{reg:02X}")
        self._log_call(True, reg, len(data), data[0] if data else None)
        for i, b in enumerate(data):
            if reg + i < self.NUM_REGS:
                self._regs[reg + i] = b
        if reg == Register.RESET and data and data[0] == RESET_CODE:
            self._regs[Register.RANGE] = int(Range.G2)

    def delay_ms(self, ms: int) -> None:
        if self._force_error is not None:
            raise self._force_error
        time.sleep(ms / 1000.0)

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def _log_call(self, is_write: bool, reg: int, length: int, data: int | None = None) -> None:
        if self.call_count < self.MAX_CALL_LOG:
            self.calls.append(
                {
                    "is_write": is_write,
                    "reg": reg,
                    "length": length,
                    "data": data,
                }
            )
        self.call_count += 1

    def set_register(self, reg: int, value: int) -> None:
        """Set a specific register value."""
        if 0 <= reg < self.NUM_REGS:
            self._regs[reg] = value & 0xFF

    def register(self, reg: int) -> int:
        """Return one register value for test assertions."""
        return self._regs[reg]

    def inject_write_error(self, reg: int, occurrence: int = 0) -> None:
        """Fail every matching write, or one 1-based matching occurrence."""
        if occurrence < 0:
            raise ValueError("occurrence must be non-negative")
        self.fail_write_reg = reg
        self.fail_write_occurrence = occurrence
        self._matching_writes = 0

    def clear_write_error(self) -> None:
        """Restore normal writes after a targeted failure injection."""
        self.fail_write_reg = None
        self.fail_write_occurrence = 0
        self._matching_writes = 0

    def set_identity_ok(self) -> None:
        """Pre-set identity registers so probe() succeeds."""
        self._regs[Register.DEVID_AD] = DEVID_AD
        self._regs[Register.DEVID_MST] = DEVID_MST
        self._regs[Register.PARTID] = PARTID

    def set_xyz_raw(self, x: int = 0, y: int = 0, z: int = 0) -> None:
        """
        Set raw 20-bit acceleration data into the register file.

        Values are masked to 20 bits and split across 3 data registers each.
        """

        def _encode(v: int, base: int) -> None:
            uv = v & 0xFFFFF
            self._regs[base] = (uv >> 12) & 0xFF
            self._regs[base + 1] = (uv >> 4) & 0xFF
            self._regs[base + 2] = (uv & 0x0F) << 4

        _encode(x, Register.XDATA3)
        _encode(y, Register.YDATA3)
        _encode(z, Register.ZDATA3)

    @staticmethod
    def _encode_xyz(raw: RawXYZ) -> bytes:
        """Encode one raw XYZ sample into the nine data-register bytes."""

        def encode_axis(value: int) -> bytes:
            encoded = value & 0xFFFFF
            return bytes(
                (
                    (encoded >> 12) & 0xFF,
                    (encoded >> 4) & 0xFF,
                    (encoded & 0x0F) << 4,
                )
            )

        return encode_axis(raw.x) + encode_axis(raw.y) + encode_axis(raw.z)

    def set_self_test_xyz(self, baseline: RawXYZ, stimulated: RawXYZ) -> None:
        """Enable deterministic ST1-only and ST1+ST2 sample responses."""
        self._self_test_baseline = baseline
        self._self_test_stimulated = stimulated
        self._regs[Register.STATUS] = STATUS_DATA_RDY

    def inject_error(self, error: Exception) -> None:
        """Make all subsequent bus calls raise the given error."""
        self._force_error = error

    def clear_error(self) -> None:
        """Clear forced error condition."""
        self._force_error = None

    def inject_short_read(self, reg: int, returned_length: int) -> None:
        """Return a malformed payload length for reads starting at `reg`."""
        if returned_length < 0:
            raise ValueError("returned_length must be non-negative")
        self._short_read_reg = reg
        self._short_read_length = returned_length

    def clear_short_read(self) -> None:
        """Restore exact-length read behavior."""
        self._short_read_reg = None
        self._short_read_length = 0

    def clear_call_log(self) -> None:
        """Reset call tracking."""
        self.call_count = 0
        self.calls.clear()
