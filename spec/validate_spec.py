#!/usr/bin/env python3
"""
ADXL355 spec YAML validator & viewer.

Parses and validates spec/adxl355.registers.yaml and
spec/adxl355.constants.yaml against datasheet-defined schemas.

Usage:
    python spec/validate_spec.py          # validate both files
    python spec/validate_spec.py --dump   # dump parsed register table
    python spec/validate_spec.py --strict # fail on warnings too
"""

import json
import math
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install PyYAML")
    sys.exit(1)


REQUIRED_REGISTER_FIELDS = {"name", "address", "type", "description"}
VALID_TYPES = {"read-only", "write-only", "read-write"}
VALID_BIT_RANGE_RE = re.compile(r"^(\d+)(?:\.\.(\d+))?$")


# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

REGISTER_SCHEMA = {
    "required": ["name", "address", "type", "description"],
    "field_validators": {
        "address": lambda v, ctx: (
            isinstance(v, int) or (isinstance(v, str) and v.startswith("0x"))
        ),
        "type": lambda v, ctx: v in VALID_TYPES,
        "default": lambda v, ctx: v is None or isinstance(v, (int, type(None))),
    },
}


def parse_bit_range(s: str) -> tuple[int, int]:
    """Parse '7', '3..0', '6..4' into (msb, lsb). Returns (bit, bit) for single. """
    m = VALID_BIT_RANGE_RE.match(s)
    if not m:
        raise ValueError(f"Invalid bit range: {s!r}")
    hi = int(m.group(1))
    lo = int(m.group(2)) if m.group(2) else hi
    return (hi, lo) if hi >= lo else (lo, hi)


def bits_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Check if two bit ranges overlap."""
    return not (a[1] < b[0] or b[1] < a[0])


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class SpecValidator:
    def __init__(self, spec_dir: Path):
        self.spec_dir = spec_dir
        self.registers_path = spec_dir / "adxl355.registers.yaml"
        self.constants_path = spec_dir / "adxl355.constants.yaml"
        self.vectors_path = spec_dir / "test_vectors.json"
        self.transport_contract_path = spec_dir / "transport_contract.json"
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str):
        self.errors.append(f"ERROR: {msg}")

    def warn(self, msg: str):
        self.warnings.append(f"WARN:  {msg}")

    def validate_all(self) -> bool:
        """Run all validators. Returns True if no errors."""
        self._check_files_exist()
        if self.errors:
            return False

        registers = self._load_yaml(self.registers_path)
        constants = self._load_yaml(self.constants_path)
        vectors = self._load_json(self.vectors_path)
        transport_contract = self._load_json(self.transport_contract_path)
        if (
            registers is None
            or constants is None
            or vectors is None
            or transport_contract is None
        ):
            return False

        self._validate_registers(registers)
        self._validate_constants(constants)
        self._validate_cross_references(registers, constants)
        self._validate_test_vectors(vectors)
        self._validate_transport_contract(transport_contract)

        return len(self.errors) == 0

    def _check_files_exist(self):
        for p in [
            self.registers_path,
            self.constants_path,
            self.vectors_path,
            self.transport_contract_path,
        ]:
            if not p.exists():
                self.error(f"File not found: {p}")

    def _load_yaml(self, path: Path):
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data is None:
                self.error(f"{path.name}: empty file")
                return None
            return data
        except yaml.YAMLError as e:
            self.error(f"{path.name}: YAML parse error: {e}")
            return None

    def _load_json(self, path: Path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            self.error(f"{path.name}: JSON parse error: {e}")
            return None

    def _validate_registers(self, data: dict):
        regs = data.get("registers", [])
        if not isinstance(regs, list):
            self.error("registers.yaml: 'registers' key must be a list")
            return

        seen_addresses: dict[int, str] = {}
        for i, reg in enumerate(regs):
            prefix = f"registers.yaml: register[{i}]"
            if not isinstance(reg, dict):
                self.error(f"{prefix}: not a dictionary")
                continue

            name = reg.get("name", f"<unnamed #{i}>")
            rprefix = f"{prefix} ({name})"

            # Required fields
            missing = REQUIRED_REGISTER_FIELDS - set(reg.keys())
            if missing:
                self.error(f"{rprefix}: missing fields: {missing}")
                continue

            # Type check
            rtype = reg.get("type")
            if rtype not in VALID_TYPES:
                self.error(f"{rprefix}: invalid type '{rtype}'")

            # Address uniqueness
            addr = reg.get("address")
            if addr is not None:
                try:
                    addr_int = int(str(addr), 16) if isinstance(addr, str) and addr.startswith("0x") else int(addr)
                except (ValueError, TypeError):
                    self.error(f"{rprefix}: invalid address '{addr}'")
                    addr_int = None
                if addr_int is not None:
                    if addr_int < 0 or addr_int > 0xFF:
                        self.error(f"{rprefix}: address 0x{addr_int:02X} out of range")
                    if addr_int in seen_addresses:
                        self.error(f"{rprefix}: duplicate address 0x{addr_int:02X} (conflicts with {seen_addresses[addr_int]})")
                    else:
                        seen_addresses[addr_int] = name

            # Validate fields
            fields = reg.get("fields")
            if fields is not None:
                self._validate_fields(fields, rprefix, name)

    def _validate_fields(self, fields: list, prefix: str, reg_name: str):
        if not isinstance(fields, list):
            self.error(f"{prefix}: 'fields' must be a list")
            return

        parsed_ranges: list[tuple[str, tuple[int, int]]] = []
        for j, field in enumerate(fields):
            if not isinstance(field, dict):
                self.error(f"{prefix}: fields[{j}] not a dictionary")
                continue

            fname = field.get("name", f"<unnamed #{j}>")
            bit_s = field.get("bit")
            if bit_s is None:
                self.error(f"{prefix}: field '{fname}' missing 'bit'")
                continue

            try:
                br = parse_bit_range(str(bit_s))
            except ValueError as e:
                self.error(f"{prefix}: field '{fname}': {e}")
                continue

            # Check bit bounds
            if br[0] > 7 or br[1] < 0:
                self.error(f"{prefix}: field '{fname}': bit range {bit_s} out of 0..7")
                continue

            # Check overlap
            for other_name, other_br in parsed_ranges:
                if bits_overlap(br, other_br):
                    self.error(f"{prefix}: field '{fname}' ({bit_s}) overlaps with '{other_name}'")

            parsed_ranges.append((fname, br))

            # Validate field values if present
            values = field.get("values")
            if values is not None:
                if not isinstance(values, list):
                    self.warn(f"{prefix}: field '{fname}': 'values' should be a list")
                else:
                    seen_vals = set()
                    for v_entry in values:
                        v = v_entry.get("value") if isinstance(v_entry, dict) else None
                        if v is not None:
                            if v in seen_vals:
                                self.warn(f"{prefix}: field '{fname}': duplicate value {v}")
                            seen_vals.add(v)

    def _validate_constants(self, data: dict):
        """Validate constants YAML structure."""
        # device_id
        did = data.get("device_id", {})
        if not isinstance(did, dict):
            self.error("constants.yaml: 'device_id' must be a dictionary")

        # power_mode
        pm = data.get("power_mode", {})
        if not isinstance(pm, dict):
            self.error("constants.yaml: 'power_mode' must be a dictionary")
        else:
            if pm.get("STANDBY") != 1:
                self.error("constants.yaml: power_mode.STANDBY must be 1")
            if pm.get("MEASUREMENT") != 0:
                self.error("constants.yaml: power_mode.MEASUREMENT must be 0")

        # range
        rng = data.get("range", {})
        if not isinstance(rng, dict):
            self.error("constants.yaml: 'range' must be a dictionary")
        else:
            for label in ["G2", "G4", "G8"]:
                entry = rng.get(label)
                if not isinstance(entry, dict):
                    self.error(f"constants.yaml: range.{label} missing or not a dict")
                    continue
                expected_vals = {"G2": 0x01, "G4": 0x02, "G8": 0x03}
                if entry.get("value") != expected_vals[label]:
                    self.error(f"constants.yaml: range.{label}.value should be {expected_vals[label]}")

        # status_register
        sr = data.get("status_register", {})
        if not isinstance(sr, dict):
            self.error("constants.yaml: 'status_register' must be a dictionary")
        else:
            expected_bits = {"DATA_RDY": 0, "FIFO_FULL": 1, "FIFO_OVR": 2, "ACTIVITY": 3, "NVM_BUSY": 4}
            for name, expected_bit in expected_bits.items():
                if sr.get(name) != expected_bit:
                    self.error(f"constants.yaml: status_register.{name} should be {expected_bit}")

        # filter_register
        fr = data.get("filter_register", {})
        if not isinstance(fr, dict):
            self.error("constants.yaml: 'filter_register' must be a dictionary")
        else:
            if fr.get("ODR_LPF_MASK") != 0x0F:
                self.error("constants.yaml: filter_register.ODR_LPF_MASK should be 0x0F")

        # spi_command
        sc = data.get("spi_command", {})
        if not isinstance(sc, dict):
            self.error("constants.yaml: 'spi_command' must be a dictionary")

        # i2c_address
        i2c = data.get("i2c_address", {})
        if not isinstance(i2c, dict):
            self.error("constants.yaml: 'i2c_address' must be a dictionary")
        else:
            if i2c.get("default") != 0x1D:
                self.error("constants.yaml: i2c_address.default should be 0x1D")
            if i2c.get("alternate") != 0x53:
                self.error("constants.yaml: i2c_address.alternate should be 0x53")

        # gravity
        grav = data.get("gravity", {})
        if not isinstance(grav, dict):
            self.error("constants.yaml: 'gravity' must be a dictionary")
        else:
            if grav.get("STANDARD_GRAVITY_M_S2") != 9.80665:
                self.error("constants.yaml: gravity.STANDARD_GRAVITY_M_S2 should be 9.80665")

        # temperature
        temp = data.get("temperature", {})
        if not isinstance(temp, dict):
            self.error("constants.yaml: 'temperature' must be a dictionary")
        else:
            if temp.get("TEMP2_DATA_MASK") != 0x0F:
                self.error("constants.yaml: temperature.TEMP2_DATA_MASK should be 0x0F")
            if temp.get("coherent_read_attempts") != 3:
                self.error("constants.yaml: temperature.coherent_read_attempts should be 3")
            self._validate_float_constant(
                temp, "intercept_lsb", 1885.0, "temperature.intercept_lsb"
            )
            self._validate_float_constant(
                temp, "intercept_c", 25.0, "temperature.intercept_c"
            )
            self._validate_float_constant(
                temp, "slope_lsb_per_c", -9.05, "temperature.slope_lsb_per_c"
            )

    def _validate_float_constant(
        self, values: dict, key: str, expected: float, label: str
    ) -> None:
        value = values.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            self.error(f"constants.yaml: {label} must be numeric")
            return
        if not math.isclose(float(value), expected, rel_tol=0.0, abs_tol=1e-12):
            self.error(f"constants.yaml: {label} should be {expected}")

    def _validate_temperature_vector(self, vector: object, index: int) -> tuple[int | None, bool]:
        prefix = f"test_vectors.json: temperature vector[{index}]"
        if not isinstance(vector, dict):
            self.error(f"{prefix}: must be an object")
            return None, False

        required = {"name", "temp2", "temp1", "expected_raw", "expected_c"}
        missing = required - set(vector)
        if missing:
            self.error(f"{prefix}: missing fields {missing}")
            return None, False

        temp2 = vector["temp2"]
        temp1 = vector["temp1"]
        if not self._validate_temperature_byte(temp2, "temp2", prefix):
            return None, False
        if not self._validate_temperature_byte(temp1, "temp1", prefix):
            return None, False

        raw = ((temp2 & 0x0F) << 8) | temp1
        if vector["expected_raw"] != raw:
            self.error(f"{prefix}: expected_raw should be {raw}")
        self._validate_temperature_celsius(vector["expected_c"], raw, prefix)
        return raw, (temp2 & 0xF0) != 0

    def _validate_temperature_byte(self, value: object, name: str, prefix: str) -> bool:
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 0xFF:
            return True
        self.error(f"{prefix}: {name} must be a byte")
        return False

    def _validate_temperature_celsius(self, value: object, raw: int, prefix: str) -> None:
        expected = 25.0 + (raw - 1885.0) / -9.05
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            self.error(f"{prefix}: expected_c must be numeric")
            return
        if not math.isclose(float(value), expected, rel_tol=0.0, abs_tol=1e-9):
            self.error(f"{prefix}: expected_c does not match nominal formula")

    def _validate_test_vectors(self, data: dict):
        temperature = data.get("temperature_conversion")
        if not isinstance(temperature, dict):
            self.error("test_vectors.json: missing temperature_conversion object")
            return

        tolerance = temperature.get("tolerance_c")
        if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) or tolerance <= 0:
            self.error("test_vectors.json: temperature tolerance_c must be positive")

        vectors = temperature.get("vectors")
        if not isinstance(vectors, list) or not vectors:
            self.error("test_vectors.json: temperature vectors must be a non-empty list")
            return

        validated = [self._validate_temperature_vector(vector, index) for index, vector in enumerate(vectors)]
        raw_values = {raw for raw, _ in validated if raw is not None}
        if not {0, 4095}.issubset(raw_values):
            self.error("test_vectors.json: temperature vectors must include raw boundaries 0 and 4095")
        if not any(has_reserved_nibble for _, has_reserved_nibble in validated):
            self.error("test_vectors.json: temperature vectors must include a nonzero reserved TEMP2 nibble")

    def _validate_transport_contract(self, data: dict) -> None:
        prefix = "transport_contract.json"
        if data.get("schema_version") != 1:
            self.error(f"{prefix}: schema_version must be 1")
        if data.get("expected_error") != "bus":
            self.error(f"{prefix}: expected_error must be 'bus'")

        scenarios = data.get("scenarios")
        if not isinstance(scenarios, list):
            self.error(f"{prefix}: scenarios must be a list")
            return

        required_ids = {
            "TR-1-ZERO",
            "TR-1-OVERLONG",
            "TR-2-ZERO",
            "TR-2-TRUNCATED",
            "TR-9-ZERO",
            "TR-9-TRUNCATED",
        }
        seen_ids = set()
        for index, scenario in enumerate(scenarios):
            scenario_id = self._validate_transport_scenario(scenario, index)
            if scenario_id is not None:
                if scenario_id in seen_ids:
                    self.error(f"{prefix}: duplicate scenario id {scenario_id}")
                seen_ids.add(scenario_id)

        missing = required_ids - seen_ids
        extra = seen_ids - required_ids
        if missing:
            self.error(f"{prefix}: missing required scenarios {sorted(missing)}")
        if extra:
            self.error(f"{prefix}: unexpected scenarios {sorted(extra)}")

    def _validate_transport_scenario(self, scenario: object, index: int):
        prefix = f"transport_contract.json: scenario[{index}]"
        if not isinstance(scenario, dict):
            self.error(f"{prefix}: must be an object")
            return None

        required = {"id", "operation", "expected_length", "returned_length"}
        missing = required - set(scenario)
        if missing:
            self.error(f"{prefix}: missing fields {sorted(missing)}")
            return None

        scenario_id = scenario["id"]
        operation = scenario["operation"]
        expected = scenario["expected_length"]
        returned = scenario["returned_length"]
        if not isinstance(scenario_id, str) or not scenario_id:
            self.error(f"{prefix}: id must be a non-empty string")
            return None
        if operation not in {"single_register", "temperature_burst", "xyz_burst"}:
            self.error(f"{prefix}: unsupported operation {operation!r}")
        if not isinstance(expected, int) or isinstance(expected, bool) or expected not in {1, 2, 9}:
            self.error(f"{prefix}: expected_length must be 1, 2, or 9")
        if not isinstance(returned, int) or isinstance(returned, bool) or returned < 0:
            self.error(f"{prefix}: returned_length must be a non-negative integer")
        elif returned == expected:
            self.error(f"{prefix}: negative scenario must violate the expected length")
        return scenario_id

    def _validate_cross_references(self, registers: dict, constants: dict):
        """Check references between the two spec files."""
        regs = {r["name"]: r for r in registers.get("registers", []) if isinstance(r, dict) and "name" in r}

        # Verify register names referenced in constants exist
        if "FILTER" not in regs:
            self.warn("constants.yaml references FILTER register but it's not in registers.yaml")

        if "STATUS" not in regs:
            self.warn("constants.yaml references STATUS register but it's not in registers.yaml")

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def print_report(self):
        if self.errors:
            print(f"\n{'=' * 60}")
            print(f"VALIDATION FAILED — {len(self.errors)} error(s)")
            print(f"{'=' * 60}")
            for e in self.errors:
                print(f"  {e}")
        else:
            print(f"\n{'=' * 60}")
            print("VALIDATION PASSED — 0 errors")
            print(f"{'=' * 60}")

        if self.warnings:
            print(f"\n{'=' * 60}")
            print(f"Warnings: {len(self.warnings)}")
            print(f"{'=' * 60}")
            for w in self.warnings:
                print(f"  {w}")

    def dump_register_table(self):
        """Print a human-readable register table."""
        data = self._load_yaml(self.registers_path)
        if data is None:
            return

        print(f"\n{'ADDR':>6}  {'TYPE':12}  {'NAME':20}  {'DEFAULT':>8}  DESCRIPTION")
        print(f"{'─' * 6}  {'─' * 12}  {'─' * 20}  {'─' * 8}  ─────────────────────────────────────")
        for reg in data.get("registers", []):
            if not isinstance(reg, dict):
                continue
            addr = reg.get("address", "??")
            if isinstance(addr, str) and addr.startswith("0x"):
                addr_str = addr
            elif isinstance(addr, int):
                addr_str = f"0x{addr:02X}"
            else:
                addr_str = "??"
            rtype = reg.get("type", "??")
            name = reg.get("name", "??")
            default = reg.get("default", "—")
            if default is None:
                default = "—"
            elif isinstance(default, int):
                default = f"0x{default:02X}"
            desc = reg.get("description", "")[:55]
            print(f"  {addr_str:>4}  {rtype:12}  {name:20}  {str(default):>8}  {desc}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    spec_dir = Path(__file__).resolve().parent

    validator = SpecValidator(spec_dir)
    success = validator.validate_all()

    if "--dump" in sys.argv:
        validator.dump_register_table()

    validator.print_report()

    strict = "--strict" in sys.argv
    if strict and validator.warnings:
        print(f"\nSTRICT MODE: {len(validator.warnings)} warning(s) promoted to errors")
        success = False

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
