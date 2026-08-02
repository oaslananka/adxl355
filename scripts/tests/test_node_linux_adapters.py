from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT / "node"


class NodeLinuxAdapterTests(unittest.TestCase):
    def test_optional_dependencies_and_subpath_exports_are_exact(self) -> None:
        package = json.loads((NODE / "package.json").read_text())
        self.assertEqual(
            package["optionalDependencies"],
            {"i2c-bus": "5.2.3", "spi-device": "3.1.2"},
        )
        self.assertEqual(
            set(package["exports"]), {".", "./linux/spi", "./linux/i2c"}
        )
        self.assertEqual(package["devDependencies"]["@types/node"], "24.10.1")

    def test_spi_adapter_uses_one_mode_zero_message(self) -> None:
        source = (NODE / "src/linux/spi.ts").read_text()
        self.assertIn("mode: 0", source)
        self.assertIn("chipSelectChange: false", source)
        self.assertIn("const message: SpiMessage = [", source)
        self.assertIn("spiReadCmd(reg)", source)
        self.assertIn("spiWriteCmd(reg)", source)
        self.assertNotIn("transferSync", source)

    def test_i2c_adapter_limits_addresses_and_exact_counts(self) -> None:
        source = (NODE / "src/linux/i2c.ts").read_text()
        self.assertIn("I2C_DEFAULT_ADDR", source)
        self.assertIn("I2C_ALTERNATE_ADDR", source)
        self.assertIn("readI2cBlock", source)
        self.assertIn("writeI2cBlock", source)
        self.assertIn("result.bytesRead !== length", source)
        self.assertIn("result.bytesWritten !== data.length", source)

    def test_adapters_own_and_close_native_resources(self) -> None:
        for name in ("spi", "i2c"):
            source = (NODE / f"src/linux/{name}.ts").read_text()
            self.assertIn("private closed = false", source)
            self.assertIn("async close(): Promise<void>", source)
            self.assertIn("if (this.closed)", source)
            self.assertIn("transport is closed", source)

    def test_examples_are_finite_and_restore_standby(self) -> None:
        common = (NODE / "examples/common.mjs").read_text()
        self.assertIn("Date.now() < deadline", common)
        self.assertNotIn("while (true)", common)
        for name in ("linux-spi.mjs", "linux-i2c.mjs"):
            source = (NODE / f"examples/{name}").read_text()
            self.assertIn("finally", source)
            self.assertIn("PowerMode.Standby", source)
            self.assertIn("transport?.close()", source)
            self.assertIn('parseIntegerFlag("samples", 32', source)

    def test_public_api_baseline_covers_linux_subpaths(self) -> None:
        baseline = json.loads((ROOT / "spec/compatibility/public-api.json").read_text())
        node = "\n".join(baseline["surfaces"]["node"])
        self.assertIn("declaration:linux/spi.ts:export class LinuxSpiTransport", node)
        self.assertIn("declaration:linux/i2c.ts:export class LinuxI2cTransport", node)
        self.assertIn("member:LinuxSpiTransport:async close(): Promise<void>", node)
        self.assertIn("member:LinuxI2cTransport:async close(): Promise<void>", node)

    def test_core_only_smoke_omits_optional_dependencies(self) -> None:
        source = (NODE / "scripts/check-core-only-install.mjs").read_text()
        self.assertIn('"--omit=optional"', source)
        self.assertIn('"--ignore-scripts"', source)
        self.assertIn("LinuxSpiTransport", source)
        self.assertIn("LinuxI2cTransport", source)
        self.assertIn("instanceof BusError", source)


if __name__ == "__main__":
    unittest.main()
