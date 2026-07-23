"""Tests for configuration API."""

import pytest

from adxl355 import ADXL355, ODR
from adxl355.registers import Register
from adxl355.testing import MockTransport


class TestODR:
    def test_set_odr(self) -> None:
        transport = MockTransport()
        transport.set_identity_ok()
        dev = ADXL355(transport)
        dev.probe()

        dev.set_odr(ODR.HZ_125)
        # Should not raise
        assert True

    def test_set_invalid_odr(self) -> None:
        transport = MockTransport()
        transport.set_identity_ok()
        dev = ADXL355(transport)
        dev.probe()

        with pytest.raises(Exception):
            dev.set_odr(99)  # type: ignore[arg-type]

    def test_set_odr_writes_correct_filter_byte(self) -> None:
        """Verify ODR value ends up in bits 3:0 of FILTER register."""
        transport = MockTransport()
        transport.set_identity_ok()
        dev = ADXL355(transport)
        dev.probe()

        # Set FILTER register to known state: HPF=0x50 (bits 6:4 = 101), ODR=0x00
        transport.set_register(Register.FILTER, 0x50)

        dev.set_odr(ODR.HZ_125)  # ODR value 5 = 0x05
        (reg,) = transport.read_register(Register.FILTER, 1)
        # ODR in bits 3:0 should be 0x05, HPF bits 6:4 preserved (0x50)
        # Result: (0x50 & 0x70) | 0x05 = 0x50 | 0x05 = 0x55
        assert reg == 0x55, f"Expected FILTER=0x55 (HPF=0x50 | ODR=0x05), got 0x{reg:02X}"

    def test_hpf_preserved_when_setting_odr(self) -> None:
        """HPF corner bits (6:4) must not be touched when changing ODR."""
        transport = MockTransport()
        transport.set_identity_ok()
        dev = ADXL355(transport)
        dev.probe()

        transport.set_register(Register.FILTER, 0x70)  # HPF bits 6:4 = 111, ODR=0x00
        dev.set_odr(ODR.HZ_4000)  # ODR value 0
        (reg,) = transport.read_register(Register.FILTER, 1)
        # HPF=7 should still be in bits 6:4
        assert (reg & 0x70) == 0x70, f"HPF bits were clobbered: FILTER=0x{reg:02X}"
        assert (reg & 0x0F) == 0x00, f"ODR bits should be 0: FILTER=0x{reg:02X}"


class TestFilter:
    def test_set_odr_updates_only_low_nibble(self) -> None:
        """Confirm only bits 3:0 change when setting ODR."""
        transport = MockTransport()
        transport.set_identity_ok()
        dev = ADXL355(transport)
        dev.probe()

        transport.set_register(Register.FILTER, 0xFF)  # all bits set
        dev.set_odr(ODR.HZ_125)  # ODR = 5
        (reg,) = transport.read_register(Register.FILTER, 1)
        # HPF_MASK = 0x70, so bits 6:4 = 0x70 from 0xFF, ODR=5 in bits 3:0
        # Result: (0xFF & 0x70) | 0x05 = 0x70 | 0x05 = 0x75
        assert reg == 0x75, f"Expected 0x75, got 0x{reg:02X}"
