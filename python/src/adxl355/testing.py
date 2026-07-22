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
from adxl355.registers import Range, Register


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
        self.call_count = 0
        self.calls: list[dict] = []

    # ------------------------------------------------------------------
    # Transport protocol
    # ------------------------------------------------------------------

    def read_register(self, reg: int, length: int = 1) -> bytes:
        if self._force_error is not None:
            raise self._force_error
        self._log_call(False, reg, length)
        data = bytes(self._regs[reg : reg + length])
        # Pad if beyond register file size
        if len(data) < length:
            data += b"\x00" * (length - len(data))
        return data

    def write_register(self, reg: int, data: bytes) -> None:
        if self._force_error is not None:
            raise self._force_error
        self._log_call(True, reg, len(data))
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

    def _log_call(self, is_write: bool, reg: int, length: int) -> None:
        if self.call_count < self.MAX_CALL_LOG:
            self.calls.append({
                "is_write": is_write,
                "reg": reg,
                "length": length,
            })
        self.call_count += 1

    def set_register(self, reg: int, value: int) -> None:
        """Set a specific register value."""
        if 0 <= reg < self.NUM_REGS:
            self._regs[reg] = value & 0xFF

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

    def inject_error(self, error: Exception) -> None:
        """Make all subsequent bus calls raise the given error."""
        self._force_error = error

    def clear_error(self) -> None:
        """Clear forced error condition."""
        self._force_error = None

    def clear_call_log(self) -> None:
        """Reset call tracking."""
        self.call_count = 0
        self.calls.clear()
