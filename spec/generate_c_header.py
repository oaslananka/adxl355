#!/usr/bin/env python3
"""
Generate C register header from spec YAML.

Usage:
    python spec/generate_c_header.py                          # print to stdout
    python spec/generate_c_header.py --output path/to/file.h  # write to file
    python spec/generate_c_header.py --diff                   # diff vs current header
"""

import argparse
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install PyYAML")
    sys.exit(1)

HEADER_TEMPLATE = """/*
 * ADXL355 Register Map
 * AUTO-GENERATED from spec/adxl355.registers.yaml
 * Source: ADXL354/ADXL355 Rev.D Datasheet
 * Do not edit manually — edit the YAML spec and regenerate.
 *
 * Generated: {date}
 */

#ifndef ADXL355_REGISTERS_H
#define ADXL355_REGISTERS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {{
#endif

/* ------------------------------------------------------------------ */
/* Register addresses                                                  */
/* ------------------------------------------------------------------ */

{register_defines}

/* ------------------------------------------------------------------ */
/* STATUS register bit positions (datasheet Table 27)                  */
/* ------------------------------------------------------------------ */

{status_defines}

/* ------------------------------------------------------------------ */
/* FILTER register masks (datasheet Table 38)                          */
/* ------------------------------------------------------------------ */

{filter_defines}

/* ------------------------------------------------------------------ */
/* RANGE register field mask (datasheet Table 42)                      */
/* ------------------------------------------------------------------ */

{range_defines}

/* ------------------------------------------------------------------ */
/* SPI command format (datasheet SPI Protocol section)                 */
/* ------------------------------------------------------------------ */

/** Build SPI read command byte. */
#define ADXL355_SPI_READ_CMD(reg)  (((reg) << 1) | 0x01)

/** Build SPI write command byte. */
#define ADXL355_SPI_WRITE_CMD(reg) ((reg) << 1)

/* ------------------------------------------------------------------ */
/* I2C addresses (datasheet Table 8)                                   */
/* ------------------------------------------------------------------ */

#define ADXL355_I2C_ADDR_DEFAULT   0x1D
#define ADXL355_I2C_ADDR_ALTERNATE 0x53

{field_defines}

#ifdef __cplusplus
}}
#endif

#endif /* ADXL355_REGISTERS_H */
"""


def fmt_guard(s: str) -> str:
    """Format a register/field name as a C macro name."""
    return s.upper()


def generate(spec_path: Path) -> str:
    with open(spec_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    regs = data.get("registers", [])

    # — Register address defines —
    reg_lines: list[str] = []
    for r in regs:
        name = r.get("name", "")
        addr = r.get("address", 0)
        if isinstance(addr, str) and addr.startswith("0x"):
            addr_str = addr
        else:
            addr_str = f"0x{int(addr):02X}"
        desc = r.get("description", "")
        reg_lines.append(
            f"#define ADXL355_REG_{fmt_guard(name)} {addr_str}  /* {desc} */"
        )

    register_defines = "\n".join(reg_lines)

    # — STATUS bits —
    status_lines = [
        "#define ADXL355_STATUS_NVM_BUSY  (1u << 4)",
        "#define ADXL355_STATUS_ACTIVITY  (1u << 3)",
        "#define ADXL355_STATUS_FIFO_OVR  (1u << 2)",
        "#define ADXL355_STATUS_FIFO_FULL (1u << 1)",
        "#define ADXL355_STATUS_DATA_RDY  (1u << 0)",
    ]
    status_defines = "\n".join(status_lines)

    # — FILTER masks —
    filter_lines = [
        "#define ADXL355_FILTER_ODR_MASK  0x0F",
        "#define ADXL355_FILTER_ODR_SHIFT 0",
        "#define ADXL355_FILTER_HPF_MASK  0x70",
        "#define ADXL355_FILTER_HPF_SHIFT 4",
    ]
    filter_defines = "\n".join(filter_lines)

    # — RANGE mask —
    range_defines = "#define ADXL355_RANGE_SEL_MASK 0x03"

    # — Field-specific value defines (RANGE values, etc.) —
    field_defs: list[str] = []
    for r in regs:
        name = r.get("name", "")
        fields = r.get("fields")
        if not fields:
            continue
        for f in fields:
            fname = f.get("name")
            values = f.get("values")
            if not values:
                continue
            if name == "RANGE" and fname == "RANGE_SEL":
                for v in values:
                    v_val = v.get("value")
                    v_label = v.get("label", "")
                    field_defs.append(
                        f"#define ADXL355_RANGE_{fmt_guard(v_label.replace('±', '').replace('g', 'G'))} "
                        f"0x{v_val:02X}  /* {v_label} */"
                    )

    field_defines = (
        "\n".join(field_defs) if field_defs else "/* No field value defines. */"
    )

    from datetime import datetime

    return HEADER_TEMPLATE.format(
        date=datetime.now().strftime("%Y-%m-%d"),
        register_defines=register_defines,
        status_defines=status_defines,
        filter_defines=filter_defines,
        range_defines=range_defines,
        field_defines=field_defines,
    )


def diff_headers(generated: str, existing: Path):
    """Show unified diff between generated and existing header."""
    if not existing.exists():
        print(f"EXISTING HEADER NOT FOUND: {existing}")
        print(generated)
        return

    with open(existing, encoding="utf-8") as f:
        existing_content = f.read()

    # Use git diff if available
    try:
        import tempfile

        gen_path = Path(tempfile.mkdtemp()) / "generated.h"
        gen_path.write_text(generated, encoding="utf-8")
        result = subprocess.run(
            ["diff", "-u", str(existing), str(gen_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print("No differences — generated header matches existing.")
        else:
            print(result.stdout)
        gen_path.unlink()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # fallback: simple line comparison
        existing_lines = existing_content.splitlines()
        gen_lines = generated.splitlines()
        if existing_lines == gen_lines:
            print("No differences.")
        else:
            print("Generated header differs from existing (use --output to overwrite).")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--diff",
        action="store_true",
        help="compare generated output with the committed C header",
    )
    mode.add_argument(
        "--output",
        type=Path,
        help="write a .h file below the repository root",
    )
    return parser.parse_args(argv)


def validate_output_path(requested: Path, repository_root: Path) -> Path:
    """Resolve one generated header path without allowing repository escape."""
    root = repository_root.resolve(strict=True)
    candidate = requested if requested.is_absolute() else root / requested
    resolved = candidate.resolve(strict=False)
    if resolved == root or root not in resolved.parents:
        raise ValueError("output path must remain inside the repository")
    if resolved.suffix.lower() != ".h":
        raise ValueError("output path must name a C header (.h)")
    return resolved


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    spec_dir = Path(__file__).resolve().parent
    repository_root = spec_dir.parent
    spec_path = spec_dir / "adxl355.registers.yaml"
    generated = generate(spec_path)

    if args.diff:
        existing = repository_root / "c" / "include" / "adxl355" / "adxl355_registers.h"
        diff_headers(generated, existing)
        return

    if args.output is not None:
        try:
            out_path = validate_output_path(args.output, repository_root)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        out_path.write_text(generated, encoding="utf-8")
        print(f"Written: {out_path}")
        return

    print(generated)


if __name__ == "__main__":
    main()
