from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.hil_runner import (
    I2C_ADDRESSES,
    SPI_MAX_HZ,
    SPI_MIN_HZ,
    HilConfig,
    parse_i2c_address,
    run_hil,
    write_report,
)

from adxl355.constants import DEVID_AD, DEVID_MST, PARTID, RESET_CODE
from adxl355.registers import ODR, PowerMode, Range, Register, STATUS_DATA_RDY


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "spec" / "hil_report.schema.json"


class FakeHardwareTransport:
    mode = 0
    speed_hz = 1_000_000

    def __init__(self) -> None:
        self.regs = bytearray(0x40)
        self.regs[Register.DEVID_AD] = DEVID_AD
        self.regs[Register.DEVID_MST] = DEVID_MST
        self.regs[Register.PARTID] = PARTID
        self.regs[Register.REVID] = 0x02
        self.regs[Register.RANGE] = int(Range.G2)
        self.regs[Register.POWER_CTL] = int(PowerMode.STANDBY)
        self.regs[Register.FILTER] = int(ODR.HZ_4000)
        self.regs[Register.STATUS] = STATUS_DATA_RDY
        self.regs[Register.TEMP2] = 0x07
        self.regs[Register.TEMP1] = 0x5D
        self.samples = [
            (100, -200, 256_410),
            (101, -199, 256_409),
            (99, -201, 256_411),
            (102, -198, 256_408),
        ]
        self.sample_index = 0
        self.closed = False

    @staticmethod
    def _encode_raw20(value: int) -> bytes:
        encoded = value & 0xFFFFF
        return bytes(
            [
                (encoded >> 12) & 0xFF,
                (encoded >> 4) & 0xFF,
                (encoded & 0x0F) << 4,
            ]
        )

    def read_register(self, reg: int, length: int = 1) -> bytes:
        if reg == Register.XDATA3 and length == 9:
            sample = self.samples[self.sample_index % len(self.samples)]
            self.sample_index += 1
            return b"".join(self._encode_raw20(value) for value in sample)
        return bytes(self.regs[reg : reg + length])

    def write_register(self, reg: int, data: bytes) -> None:
        if reg == Register.RESET and data == bytes([RESET_CODE]):
            self.regs[Register.RANGE] = int(Range.G2)
            self.regs[Register.POWER_CTL] = int(PowerMode.STANDBY)
            self.regs[Register.FILTER] = int(ODR.HZ_4000)
            return
        self.regs[reg : reg + len(data)] = data

    def delay_ms(self, ms: int) -> None:
        del ms

    def close(self) -> None:
        self.closed = True


class HilConfigTests(unittest.TestCase):
    def test_spi_accepts_mode_zero_and_datasheet_clock_limits(self) -> None:
        for speed in (SPI_MIN_HZ, 1_000_000, SPI_MAX_HZ):
            config = HilConfig(transport="spi", spi_speed_hz=speed)
            config.validate()
            self.assertEqual(config.bus["mode"], 0)
            self.assertEqual(config.bus["speed_hz"], speed)

    def test_spi_rejects_clock_outside_datasheet_limits(self) -> None:
        for speed in (SPI_MIN_HZ - 1, SPI_MAX_HZ + 1):
            with self.assertRaisesRegex(ValueError, "100000.*10000000"):
                HilConfig(transport="spi", spi_speed_hz=speed).validate()

    def test_i2c_accepts_only_documented_addresses(self) -> None:
        self.assertEqual(I2C_ADDRESSES, (0x1D, 0x53))
        self.assertEqual(parse_i2c_address("0x1d"), 0x1D)
        self.assertEqual(parse_i2c_address("0x53"), 0x53)
        with self.assertRaisesRegex(ValueError, "0x1D.*0x53"):
            parse_i2c_address("0x20")

    def test_sample_count_and_timeout_are_bounded(self) -> None:
        with self.assertRaises(ValueError):
            HilConfig(transport="spi", samples=3).validate()
        with self.assertRaises(ValueError):
            HilConfig(transport="spi", sample_timeout_ms=49).validate()


class HilExecutionTests(unittest.TestCase):
    def test_success_report_covers_identity_reset_configuration_and_samples(self) -> None:
        transport = FakeHardwareTransport()
        config = HilConfig(
            transport="spi",
            samples=8,
            runner_id="lab-a",
            git_sha="0123456789abcdef",
        )

        report = run_hil(config, transport=transport, sleep=lambda _: None)

        self.assertTrue(report["success"])
        self.assertEqual(report["device"]["identity"], {
            "devid_ad": "0xAD",
            "devid_mst": "0x1D",
            "partid": "0xED",
        })
        self.assertEqual(report["device"]["revision"], "0x02")
        self.assertEqual(report["bus"]["mode"], 0)
        self.assertEqual(report["configuration"]["verified_range"], "G4")
        self.assertEqual(report["configuration"]["odr"], "HZ_125")
        self.assertEqual(report["temperature"]["raw"], 1885)
        self.assertAlmostEqual(report["temperature"]["celsius"], 25.0)
        self.assertEqual(report["samples"]["count"], 8)
        self.assertEqual(report["samples"]["status_or"], "0x01")
        self.assertGreaterEqual(report["samples"]["unique"], 2)
        self.assertEqual(
            [step["name"] for step in report["steps"]],
            [
                "bus-configuration",
                "identity",
                "probe",
                "reset",
                "configuration",
                "temperature",
                "continuous-read",
                "restore-standby",
            ],
        )
        self.assertTrue(transport.closed)
        self.assertEqual(transport.regs[Register.POWER_CTL] & 0x01, 1)
        self.assertEqual(transport.regs[Register.RANGE] & 0x03, int(Range.G2))

    def test_failure_after_measurement_restores_safe_configuration(self) -> None:
        transport = FakeHardwareTransport()
        transport.samples = [(7, 7, 7)]

        report = run_hil(
            HilConfig(transport="spi", samples=4),
            transport=transport,
            sleep=lambda _: None,
        )

        self.assertFalse(report["success"])
        self.assertIn("repeated sample", report["error"]["message"])
        self.assertEqual(transport.regs[Register.POWER_CTL] & 0x01, 1)
        self.assertEqual(transport.regs[Register.RANGE] & 0x03, int(Range.G2))
        self.assertEqual(transport.regs[Register.FILTER] & 0x0F, int(ODR.HZ_4000))
        self.assertNotIn("cleanup_errors", report)

    def test_failure_report_is_sanitized_and_closes_transport(self) -> None:
        class FailingTransport(FakeHardwareTransport):
            def read_register(self, reg: int, length: int = 1) -> bytes:
                raise OSError("token=super-secret\npermission denied")

        transport = FailingTransport()
        report = run_hil(HilConfig(transport="spi"), transport=transport)

        self.assertFalse(report["success"])
        serialized = json.dumps(report)
        self.assertNotIn("super-secret", serialized)
        self.assertIn("token=[REDACTED]", serialized)
        self.assertTrue(report["diagnostic_hints"])
        self.assertTrue(transport.closed)

    def test_public_runner_label_redacts_secret_like_input(self) -> None:
        report = run_hil(
            HilConfig(
                transport="spi",
                samples=4,
                runner_id="token=must-not-leak",
                git_sha="secret:also-hidden",
            ),
            transport=FakeHardwareTransport(),
            sleep=lambda _: None,
        )

        serialized = json.dumps(report)
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("also-hidden", serialized)
        self.assertIn("REDACTED", serialized)

    def test_report_environment_does_not_copy_process_secrets(self) -> None:
        previous = os.environ.get("ADXL355_TEST_TOKEN")
        os.environ["ADXL355_TEST_TOKEN"] = "must-not-leak"
        self.addCleanup(self._restore_env, "ADXL355_TEST_TOKEN", previous)

        report = run_hil(
            HilConfig(transport="spi", samples=4),
            transport=FakeHardwareTransport(),
            sleep=lambda _: None,
        )

        self.assertNotIn("must-not-leak", json.dumps(report))
        self.assertEqual(
            set(report["runner"]),
            {"id", "git_sha", "os", "kernel", "architecture", "python"},
        )

    def test_success_report_matches_declared_top_level_schema(self) -> None:
        report = run_hil(
            HilConfig(transport="spi", samples=4),
            transport=FakeHardwareTransport(),
            sleep=lambda _: None,
        )
        schema = json.loads(SCHEMA_PATH.read_text())

        self.assertEqual(report["schema_version"], schema["properties"]["schema_version"]["const"])
        self.assertTrue(set(schema["required"]).issubset(report))
        self.assertEqual(schema["properties"]["bus"]["properties"]["mode"]["const"], 0)

    def test_write_report_is_atomic_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "nested" / "hil.json"
            report = {"schema_version": 1, "success": True}
            write_report(target, report)
            self.assertEqual(json.loads(target.read_text()), report)
            self.assertFalse(target.with_suffix(".json.tmp").exists())

    @staticmethod
    def _restore_env(name: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
