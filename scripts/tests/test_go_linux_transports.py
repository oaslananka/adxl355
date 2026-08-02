from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GO_ROOT = REPO_ROOT / "go"
LINUXIO = GO_ROOT / "adxl355" / "linuxio"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"


class GoLinuxTransportTests(unittest.TestCase):
    def test_module_keeps_go_121_and_pins_compatible_x_sys(self) -> None:
        go_mod = (GO_ROOT / "go.mod").read_text()
        self.assertRegex(go_mod, r"(?m)^go 1\.21$")
        self.assertIn("golang.org/x/sys v0.30.0", go_mod)
        self.assertTrue((GO_ROOT / "go.sum").is_file())

    def test_ioctl_implementation_is_scoped_to_verified_64_bit_linux_abis(self) -> None:
        implementation = (LINUXIO / "transport_linux.go").read_text()
        tests = (LINUXIO / "transport_linux_test.go").read_text()
        fallback = (LINUXIO / "transport_other.go").read_text()
        self.assertTrue(
            implementation.startswith("//go:build linux && (amd64 || arm64)")
        )
        self.assertTrue(tests.startswith("//go:build linux && (amd64 || arm64)"))
        self.assertTrue(fallback.startswith("//go:build !linux || (!amd64 && !arm64)"))
        for phrase in (
            "SPI_IOC_MESSAGE(1)",
            "I2C_RDWR",
            "unsafe.Sizeof(spiIOCTransfer{})",
            "ErrShortTransfer",
        ):
            source = implementation + tests
            self.assertIn(phrase, source)

    def test_examples_are_finite_and_restore_standby(self) -> None:
        bounded = (GO_ROOT / "examples" / "internal" / "bounded" / "run.go").read_text()
        spi = (GO_ROOT / "examples" / "linux_spi" / "main.go").read_text()
        i2c = (GO_ROOT / "examples" / "linux_i2c" / "main.go").read_text()
        self.assertIn("context.WithTimeout", spi)
        self.assertIn("context.WithTimeout", i2c)
        self.assertIn("samples must be in 1..256", spi)
        self.assertIn("samples must be in 1..256", i2c)
        self.assertIn("sensor.SetPowerMode(adxl355.PowerStandby)", bounded)
        self.assertIn("time.NewTimer(limit)", bounded)
        self.assertNotRegex(spi + i2c, re.compile(r"for\s*\{"))

    def test_required_go_job_builds_all_supported_boundaries(self) -> None:
        workflow = yaml.safe_load(CI.read_text())
        job = workflow["jobs"]["go"]
        commands = "\n".join(str(step.get("run", "")) for step in job["steps"])
        for command in (
            "go mod verify",
            "go build ./...",
            "GOOS=linux GOARCH=arm64 go build ./...",
            "GOOS=linux GOARCH=arm go build ./...",
            "GOOS=windows GOARCH=amd64 go build ./...",
            "GOOS=darwin GOARCH=arm64 go build ./...",
            "go test -race ./...",
        ):
            self.assertIn(command, commands)


if __name__ == "__main__":
    unittest.main()
