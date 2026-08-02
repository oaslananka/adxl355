from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from scripts.generate_python_locks import LOCK_ROOT, parse_lock


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CPP_HEADER = REPO_ROOT / "cpp" / "include" / "adxl355" / "adxl355.hpp"
ARDUINO_ADAPTER = (
    REPO_ROOT / "embedded" / "arduino" / "include" / "adxl355" / "arduino_spi.hpp"
)
PLATFORMIO_INI = REPO_ROOT / "embedded" / "platformio" / "uno" / "platformio.ini"
LIBRARY_JSON = REPO_ROOT / "library.json"


class CppEmbeddedTests(unittest.TestCase):
    def load_jobs(self) -> dict[str, Any]:
        workflow = cast(dict[str, Any], yaml.safe_load(CI_WORKFLOW.read_text()))
        return cast(dict[str, Any], workflow["jobs"])

    def test_cpp_header_exposes_odr_and_exception_free_surface(self) -> None:
        text = CPP_HEADER.read_text()
        for phrase in (
            "enum class Odr",
            "class NoexceptDevice",
            "struct Result",
            "Status setOdr(Odr odr) noexcept",
            "void setOdr(Odr odr)",
            "ADXL355_CPP_NO_EXCEPTIONS",
        ):
            self.assertIn(phrase, text)
        no_exception_prefix = text.split("#ifndef ADXL355_CPP_NO_EXCEPTIONS", 1)[0]
        self.assertNotIn("<memory>", no_exception_prefix)
        self.assertNotIn("<stdexcept>", no_exception_prefix)

    def test_noexcept_target_is_exported_and_compiled_without_exceptions(self) -> None:
        cmake = (REPO_ROOT / "cpp" / "CMakeLists.txt").read_text()
        tests = (REPO_ROOT / "cpp" / "tests" / "CMakeLists.txt").read_text()
        smoke = (REPO_ROOT / "cmake" / "smoke" / "cpp" / "CMakeLists.txt").read_text()
        self.assertIn("adxl355::cpp_noexcept", cmake)
        self.assertIn("ADXL355_CPP_NO_EXCEPTIONS=1", cmake)
        self.assertIn("adxl355_cpp_noexcept", cmake)
        self.assertIn("-fno-exceptions", tests)
        self.assertIn("-fno-rtti", tests)
        self.assertIn("adxl355::cpp_noexcept", smoke)
        self.assertIn("-fno-exceptions", smoke)

    def test_arduino_adapter_is_thin_and_mode_zero(self) -> None:
        text = ARDUINO_ADAPTER.read_text()
        self.assertIn("class SpiBus final : public BusInterface", text)
        self.assertIn("SPI_MODE0", text)
        self.assertIn("(reg << 1U) | 0x01U", text)
        self.assertIn("reg << 1U", text)
        self.assertNotIn("ADXL355_REG_", text)
        bridge = (
            REPO_ROOT / "embedded" / "arduino" / "src" / "adxl355_core.c"
        ).read_text()
        self.assertIn('#include "../../../c/src/adxl355.c"', bridge)
        self.assertNotIn("adxl355_probe", bridge)

    def test_platformio_manifest_and_uno_fixture_are_pinned(self) -> None:
        manifest = json.loads(LIBRARY_JSON.read_text())
        self.assertEqual(manifest["version"], "0.1.0-alpha.2")
        self.assertEqual(manifest["frameworks"], ["arduino"])
        self.assertEqual(manifest["platforms"], ["atmelavr"])
        self.assertEqual(manifest["build"]["srcDir"], "embedded/arduino/src")
        self.assertIn(
            "embedded/arduino/src/adxl355_core.c", manifest["export"]["include"]
        )
        fixture = PLATFORMIO_INI.read_text()
        self.assertIn("platform = atmelavr@5.3.0", fixture)
        self.assertIn("board = uno", fixture)
        self.assertIn("framework = arduino", fixture)
        self.assertIn("symlink://../../..", fixture)
        self.assertIn("ADXL355_CPP_NO_EXCEPTIONS=1", fixture)

    def test_embedded_job_is_hosted_hash_locked_and_required(self) -> None:
        jobs = self.load_jobs()
        embedded = jobs["embedded"]
        self.assertEqual(embedded["name"], "Embedded (Arduino Uno)")
        self.assertEqual(embedded["runs-on"], "ubuntu-24.04")
        self.assertEqual(embedded["timeout-minutes"], 12)
        rendered = str(embedded)
        self.assertNotIn("self-hosted", rendered)
        self.assertNotIn("secrets.", rendered)
        commands = "\n".join(str(step.get("run", "")) for step in embedded["steps"])
        self.assertIn("requirements/python/platformio.txt", commands)
        self.assertIn("--require-hashes", commands)
        self.assertIn("pio pkg pack", commands)
        self.assertIn("pio run -d embedded/platformio/uno", commands)
        self.assertIn("embedded", jobs["consistency"]["needs"])
        lock = parse_lock(LOCK_ROOT / "platformio.txt")
        self.assertEqual(lock["platformio"][0], "6.1.19")


if __name__ == "__main__":
    unittest.main()
