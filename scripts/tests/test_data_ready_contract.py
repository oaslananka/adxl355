from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[2]


class DataReadyContractTests(unittest.TestCase):
    def test_shared_spec_matches_rev_d_interrupt_fields(self) -> None:
        constants = yaml.safe_load(
            (REPO_ROOT / "spec/adxl355.constants.yaml").read_text()
        )["data_ready_interrupts"]
        self.assertEqual(
            {
                "INT_MAP_RDY_EN1": constants["INT_MAP_RDY_EN1"],
                "INT_MAP_RDY_EN2": constants["INT_MAP_RDY_EN2"],
                "RANGE_INT_POL": constants["RANGE_INT_POL"],
                "POWER_CTL_DRDY_OFF": constants["POWER_CTL_DRDY_OFF"],
                "SYNC_TIMING_MASK": constants["SYNC_TIMING_MASK"],
                "dedicated_drdy_active_high": constants["dedicated_drdy_active_high"],
            },
            {
                "INT_MAP_RDY_EN1": 0,
                "INT_MAP_RDY_EN2": 4,
                "RANGE_INT_POL": 6,
                "POWER_CTL_DRDY_OFF": 2,
                "SYNC_TIMING_MASK": 0x07,
                "dedicated_drdy_active_high": True,
            },
        )

        registers = {
            register["name"]: register
            for register in yaml.safe_load(
                (REPO_ROOT / "spec/adxl355.registers.yaml").read_text()
            )["registers"]
        }
        fields = {
            name: {
                field["name"]: str(field["bit"]) for field in registers[name]["fields"]
            }
            for name in ("INT_MAP", "SYNC", "RANGE", "POWER_CTL")
        }
        self.assertEqual(fields["INT_MAP"]["RDY_EN1"], "0")
        self.assertEqual(fields["INT_MAP"]["RDY_EN2"], "4")
        self.assertEqual(fields["SYNC"]["EXT_SYNC"], "1..0")
        self.assertEqual(fields["SYNC"]["EXT_CLK"], "2")
        self.assertEqual(fields["RANGE"]["INT_POL"], "6")
        self.assertEqual(fields["POWER_CTL"]["DRDY_OFF"], "2")

    def test_c_and_python_expose_separate_drdy_and_int_routing(self) -> None:
        c_header = (REPO_ROOT / "c/include/adxl355/adxl355.h").read_text()
        c_source = (REPO_ROOT / "c/src/adxl355.c").read_text()
        python_device = (REPO_ROOT / "python/src/adxl355/device.py").read_text()
        python_types = (REPO_ROOT / "python/src/adxl355/types.py").read_text()

        for token in (
            "dedicated_drdy_enabled",
            "route_to_int1",
            "route_to_int2",
            "interrupt_polarity",
            "adxl355_configure_data_ready",
            "adxl355_get_data_ready_config",
        ):
            self.assertIn(token, c_header)
        self.assertIn("ADXL355_SYNC_TIMING_MASK", c_source)
        self.assertIn("restore_data_ready_registers", c_source)
        self.assertNotIn(
            "ADXL355_REG_STATUS",
            c_source[
                c_source.index("adxl355_configure_data_ready") : c_source.index(
                    "adxl355_read_offset"
                )
            ],
        )

        self.assertIn("class DataReadyConfig", python_types)
        self.assertIn("def configure_data_ready", python_device)
        self.assertIn("def get_data_ready_config", python_device)
        configuration = python_device[
            python_device.index("def configure_data_ready") : python_device.index(
                "def _offset_register"
            )
        ]
        self.assertNotIn("Register.STATUS", configuration)

    def test_linux_reference_is_bounded_event_driven_and_restores_state(self) -> None:
        acquisition = (REPO_ROOT / "python/examples/drdy_acquisition.py").read_text()
        linux = (REPO_ROOT / "python/examples/linux_drdy.py").read_text()
        combined = acquisition + linux

        for token in (
            "wait_edge_events",
            "read_edge_events",
            "timestamp_ns",
            "line_seqno",
            "max_missed_events",
            "STATUS_FIFO_OVR",
            "PowerMode.STANDBY",
            "source.close",
            "transport.close",
        ):
            self.assertIn(token, combined)
        self.assertNotIn("while True", combined)
        self.assertNotIn("time.sleep", combined)
        self.assertIn("sample_count <= 4096", acquisition)
        self.assertIn("timeout_s <= 3600.0", acquisition)

    def test_gpio_extra_is_linux_scoped_and_core_remains_dependency_free(self) -> None:
        with (REPO_ROOT / "python/pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]
        self.assertNotIn("dependencies", project)
        self.assertEqual(
            project["optional-dependencies"]["gpio"],
            ["gpiod>=2.2,<3; platform_system == 'Linux'"],
        )


if __name__ == "__main__":
    unittest.main()
