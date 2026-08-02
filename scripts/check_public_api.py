#!/usr/bin/env python3
"""Generate and enforce additive public-API baselines for maintained surfaces."""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "spec" / "compatibility" / "public-api.json"
SCHEMA_VERSION = 1
BREAKING_MARKER = "**Breaking ("


class CompatibilityError(RuntimeError):
    """Raised when the maintained compatibility contract is violated."""


def normalize(text: str) -> str:
    """Normalize declaration whitespace without changing token order."""
    return " ".join(text.split())


def strip_comments(text: str) -> str:
    """Remove C-style and line comments with a bounded single-pass scanner."""
    output: list[str] = []
    index = 0
    in_block = False
    in_line = False
    in_string: str | None = None
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if in_block:
            if char == "*" and next_char == "/":
                in_block = False
                output.append(" ")
                index += 2
            else:
                output.append("\n" if char == "\n" else " ")
                index += 1
            continue
        if in_line:
            if char == "\n":
                in_line = False
                output.append(char)
            else:
                output.append(" ")
            index += 1
            continue
        if in_string:
            output.append(char)
            if char == "\\" and index + 1 < len(text):
                output.append(text[index + 1])
                index += 2
                continue
            if char == in_string:
                in_string = None
            index += 1
            continue
        if char in {'"', "'", "`"}:
            in_string = char
            output.append(char)
            index += 1
        elif char == "/" and next_char == "*":
            in_block = True
            output.append(" ")
            index += 2
        elif char == "/" and next_char == "/":
            in_line = True
            output.append(" ")
            index += 2
        else:
            output.append(char)
            index += 1
    return "".join(output)


def matching_brace(text: str, start: int) -> int:
    if start >= len(text) or text[start] != "{":
        raise CompatibilityError("block does not start with an opening brace")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    raise CompatibilityError("unbalanced declaration block")


def top_level_statements(text: str, delimiter: str = ";") -> Iterator[str]:
    """Yield delimiter-terminated statements outside nested braces/parentheses."""
    start = 0
    brace_depth = 0
    paren_depth = 0
    bracket_depth = 0
    for index, char in enumerate(text):
        if char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth = max(0, brace_depth - 1)
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif char == delimiter and brace_depth == paren_depth == bracket_depth == 0:
            statement = text[start : index + 1].strip()
            if statement:
                yield statement
            start = index + 1


def declaration_name_before_paren(statement: str) -> str | None:
    paren = statement.find("(")
    if paren < 0:
        return None
    prefix = statement[:paren].rstrip()
    if not prefix:
        return None
    token = prefix.split()[-1].lstrip("*&~")
    return token if token else None


def collect_until_semicolon(lines: list[str], start: int) -> tuple[str, int]:
    collected: list[str] = []
    index = start
    while index < len(lines):
        collected.append(lines[index].strip())
        if ";" in lines[index]:
            break
        index += 1
    return normalize(" ".join(collected)), index


def split_top_level_items(text: str, delimiter: str = ",") -> list[str]:
    """Split one declaration body without splitting nested expressions."""
    items: list[str] = []
    start = 0
    paren_depth = 0
    brace_depth = 0
    bracket_depth = 0
    for index, char in enumerate(text):
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
        elif char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth = max(0, brace_depth - 1)
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif char == delimiter and paren_depth == brace_depth == bracket_depth == 0:
            item = normalize(text[start:index])
            if item:
                items.append(item)
            start = index + 1
    final = normalize(text[start:])
    if final:
        items.append(final)
    return items


def c_type_entries(declaration: str) -> set[str]:
    """Represent trailing C enum additions without erasing older declarations."""
    if not declaration.startswith("typedef enum {"):
        return {f"type:{declaration}"}
    opening = declaration.find("{")
    try:
        closing = matching_brace(declaration, opening)
    except CompatibilityError:
        return {f"type:{declaration}"}
    members = split_top_level_items(declaration[opening + 1 : closing])
    suffix = declaration[closing + 1 :].strip()
    if not members or not suffix:
        return {f"type:{declaration}"}
    header = declaration[: opening + 1].strip()
    entries: set[str] = set()
    for count in range(1, len(members) + 1):
        body = ", ".join(members[:count])
        entries.add(f"type:{normalize(f'{header} {body} }} {suffix}')}")
    return entries


def c_surface(root: Path) -> set[str]:
    lines = strip_comments(
        (root / "c/include/adxl355/adxl355.h").read_text()
    ).splitlines()
    entries: set[str] = set()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith(("typedef enum {", "typedef struct {")):
            declaration, index = collect_until_semicolon(lines, index)
            entries.update(c_type_entries(declaration))
        elif "adxl355_" in line and "(" in line and not line.startswith("#"):
            declaration, index = collect_until_semicolon(lines, index)
            entries.add(f"function:{declaration}")
        index += 1
    return entries


def word_boundary(text: str, index: int, length: int) -> bool:
    before = text[index - 1] if index > 0 else " "
    after_index = index + length
    after = text[after_index] if after_index < len(text) else " "
    return not (before.isalnum() or before == "_") and not (
        after.isalnum() or after == "_"
    )


def named_blocks(text: str, keyword: str) -> Iterator[tuple[str, str, str]]:
    """Yield (header, name, body) for bounded named brace blocks."""
    cursor = 0
    while True:
        index = text.find(keyword, cursor)
        if index < 0:
            return
        cursor = index + len(keyword)
        if not word_boundary(text, index, len(keyword)):
            continue
        if keyword == "class" and text[max(0, index - 5) : index].strip() == "enum":
            continue
        brace = text.find("{", cursor)
        if brace < 0:
            return
        header = normalize(text[index:brace])
        parts = header.split()
        name_index = 2 if keyword == "enum class" else 1
        if len(parts) <= name_index:
            continue
        name = parts[name_index]
        end = matching_brace(text, brace)
        yield header, name, text[brace + 1 : end]
        cursor = end + 1


def class_public_statements(body: str, default_public: bool) -> Iterator[str]:
    current_public = default_public
    start = 0
    brace_depth = 0
    paren_depth = 0
    for index, char in enumerate(body):
        if char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth = max(0, brace_depth - 1)
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
        elif char == ":" and brace_depth == paren_depth == 0:
            label = body[start:index].strip()
            if label in {"public", "private", "protected"}:
                current_public = label == "public"
                start = index + 1
        elif char == ";" and brace_depth == paren_depth == 0:
            statement = normalize(body[start : index + 1])
            if current_public and statement:
                yield statement
            start = index + 1


def cpp_enum_entries(text: str) -> set[str]:
    return {
        f"enum:{name}:{header}:{{{normalize(body)}}}"
        for header, name, body in named_blocks(text, "enum class")
    }


def cpp_record_entries(text: str, keyword: str, default_public: bool) -> set[str]:
    entries: set[str] = set()
    for header, name, body in named_blocks(text, keyword):
        entries.add(f"{keyword}:{name}:{header}")
        entries.update(
            f"member:{name}:{item}"
            for item in class_public_statements(body, default_public)
        )
    return entries


def cpp_surface(root: Path) -> set[str]:
    text = strip_comments((root / "cpp/include/adxl355/adxl355.hpp").read_text())
    return (
        cpp_enum_entries(text)
        | cpp_record_entries(text, "struct", True)
        | cpp_record_entries(text, "class", False)
    )


def safe_signature(obj: Any) -> str | None:
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        return None


def class_signature_entries(name: str, obj: type[Any]) -> set[str]:
    entries: set[str] = set()
    if issubclass(obj, Enum):
        entries.update(f"enum:{name}.{member.name}={member.value!r}" for member in obj)
    for member_name, member in inspect.getmembers(obj):
        if member_name.startswith("_") or not (
            inspect.isfunction(member) or inspect.ismethod(member)
        ):
            continue
        signature = safe_signature(member)
        if signature is not None:
            entries.add(f"method:{name}.{member_name}{signature}")
    return entries


def object_signature(name: str, obj: Any) -> set[str]:
    entries = {f"export:{name}:{type(obj).__name__}"}
    signature = (
        safe_signature(obj) if inspect.isfunction(obj) or inspect.isclass(obj) else None
    )
    if inspect.isclass(obj) and issubclass(obj, Enum):
        entries.add(f"signature:{name}(*values)")
    elif signature is not None:
        entries.add(f"signature:{name}{signature}")
    if inspect.isclass(obj):
        entries.update(class_signature_entries(name, obj))
    elif isinstance(obj, (str, int, float, bool, type(None))):
        entries.add(f"value:{name}={obj!r}")
    return entries


def python_surface(root: Path) -> set[str]:
    source = str(root / "python/src")
    sys.path.insert(0, source)
    try:
        for module_name in tuple(sys.modules):
            if module_name == "adxl355" or module_name.startswith("adxl355."):
                del sys.modules[module_name]
        module = importlib.import_module("adxl355")
        entries: set[str] = set()
        for name in module.__all__:
            entries.update(object_signature(name, getattr(module, name)))
        return entries
    finally:
        sys.path.remove(source)


def declaration_header(lines: list[str], start: int) -> tuple[str, int]:
    collected: list[str] = []
    paren_depth = 0
    angle_depth = 0
    index = start
    while index < len(lines):
        line = lines[index].strip()
        collected.append(line)
        paren_depth += line.count("(") - line.count(")")
        angle_depth += line.count("<") - line.count(">")
        if (
            paren_depth <= 0
            and angle_depth <= 0
            and ("{" in line or ";" in line or "=" in line)
        ):
            break
        index += 1
    header = " ".join(collected)
    terminators = [
        position for symbol in "{;=" if (position := header.find(symbol)) >= 0
    ]
    if terminators:
        header = header[: min(terminators)]
    return normalize(header), index


def rust_surface(root: Path) -> set[str]:
    entries: set[str] = set()
    prefixes = (
        "pub use ",
        "pub struct ",
        "pub enum ",
        "pub trait ",
        "pub type ",
        "pub const ",
        "pub fn ",
    )
    for path in sorted((root / "rust/src").glob("*.rs")):
        lines = strip_comments(path.read_text()).splitlines()
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if line.startswith(prefixes):
                header, index = declaration_header(lines, index)
                entries.add(f"declaration:{path.name}:{header}")
            index += 1
    return entries


def exported_typescript_header(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(
        (
            "export class ",
            "export interface ",
            "export enum ",
            "export type ",
            "export const ",
            "export function ",
            "export abstract class ",
        )
    )


def typescript_class_methods(name: str, body: str) -> set[str]:
    entries: set[str] = set()
    cursor = 0
    member_start = 0
    while cursor < len(body):
        char = body[cursor]
        if char == "{":
            header = normalize(body[member_start:cursor])
            end = matching_brace(body, cursor)
            if "(" in header and not header.startswith(("private ", "protected ")):
                entries.add(f"member:{name}:{header}")
            cursor = end + 1
            member_start = cursor
            continue
        if char == ";":
            declaration = normalize(body[member_start : cursor + 1])
            if declaration and not declaration.startswith(("private ", "protected ")):
                entries.add(f"member:{name}:{declaration}")
            member_start = cursor + 1
        cursor += 1
    return entries


def typescript_surface(root: Path) -> set[str]:
    entries: set[str] = set()
    for path in sorted((root / "node/src").glob("*.ts")):
        text = strip_comments(path.read_text())
        lines = text.splitlines()
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if line.startswith("export {"):
                header, index = declaration_header(lines, index)
                entries.add(f"declaration:{path.name}:{header}")
            elif exported_typescript_header(line):
                header, index = declaration_header(lines, index)
                entries.add(f"declaration:{path.name}:{header}")
            index += 1
        for header, name, body in named_blocks(text, "class"):
            prefix = text[max(0, text.find(header) - 16) : text.find(header)]
            if "export" in prefix or f"export {header}" in text:
                entries.update(typescript_class_methods(name, body))
    return entries


def go_exported_name(declaration: str, offset: int) -> str | None:
    remainder = declaration[offset:].lstrip()
    if not remainder:
        return None
    name = remainder.split(None, 1)[0].split("(", 1)[0]
    return name if name and name[0].isupper() else None


def go_named_declaration(
    line: str, lines: list[str], index: int
) -> tuple[str | None, int]:
    if line.startswith("type "):
        header, end = declaration_header(lines, index)
        return (
            f"declaration:{header}" if go_exported_name(header, len("type ")) else None,
            end,
        )
    if line.startswith("func "):
        header, end = declaration_header(lines, index)
        paren = header.find(")") if header.startswith("func (") else len("func ")
        return (
            f"declaration:{header}" if go_exported_name(header, paren + 1) else None,
            end,
        )
    if line.startswith(("const ", "var ")) and "(" not in line:
        header, end = declaration_header(lines, index)
        offset = len("const ") if line.startswith("const ") else len("var ")
        return (
            f"declaration:{header}" if go_exported_name(header, offset) else None,
            end,
        )
    return None, index


def go_group_entries(
    kind: str, lines: list[str], index: int, filename: str
) -> tuple[set[str], int]:
    entries: set[str] = set()
    cursor = index + 1
    while cursor < len(lines) and lines[cursor].strip() != ")":
        item = normalize(lines[cursor])
        if item and item[0].isupper():
            entries.add(f"{kind}:{filename}:{item}")
        cursor += 1
    return entries, cursor


def go_file_surface(path: Path) -> set[str]:
    entries: set[str] = set()
    lines = strip_comments(path.read_text()).splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line in {"const (", "var ("}:
            group, index = go_group_entries(line.split()[0], lines, index, path.name)
            entries.update(group)
        else:
            declaration, index = go_named_declaration(line, lines, index)
            if declaration:
                entries.add(
                    f"{declaration.split(':', 1)[0]}:{path.name}:{declaration.split(':', 1)[1]}"
                )
        index += 1
    return entries


def go_surface(root: Path) -> set[str]:
    entries: set[str] = set()
    for path in sorted((root / "go/adxl355").glob("*.go")):
        if not path.name.endswith("_test.go"):
            entries.update(go_file_surface(path))
    return entries


def snapshot(root: Path = REPO_ROOT) -> dict[str, Any]:
    surfaces = {
        "c": c_surface(root),
        "cpp": cpp_surface(root),
        "python": python_surface(root),
        "rust": rust_surface(root),
        "node": typescript_surface(root),
        "go": go_surface(root),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "version": (root / "VERSION").read_text().strip(),
        "surfaces": {name: sorted(values) for name, values in surfaces.items()},
    }


def compare(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for surface, expected_entries in baseline.get("surfaces", {}).items():
        current_entries = set(current.get("surfaces", {}).get(surface, []))
        failures.extend(
            f"{surface}: removed or changed public declaration: {missing}"
            for missing in sorted(set(expected_entries) - current_entries)
        )
    return failures


def git(
    *args: str, cwd: Path = REPO_ROOT, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def validate_baseline_update(
    old: dict[str, Any], new: dict[str, Any], changelog_diff: str
) -> None:
    removed = compare(old, new)
    if removed and BREAKING_MARKER.lower() not in changelog_diff.lower():
        details = "\n".join(f"- {entry}" for entry in removed[:20])
        raise CompatibilityError(
            "public API baseline removed/changed declarations without a changed "
            f"CHANGELOG Breaking entry:\n{details}"
        )


def baseline_update_policy(base_ref: str | None, root: Path = REPO_ROOT) -> None:
    if not base_ref:
        return
    probe = git("rev-parse", "--verify", base_ref, cwd=root, check=False)
    if probe.returncode != 0:
        return
    relative_baseline = BASELINE_PATH.relative_to(root)
    old_file = git("show", f"{base_ref}:{relative_baseline}", cwd=root, check=False)
    if old_file.returncode != 0:
        return
    old = json.loads(old_file.stdout)
    new = json.loads(BASELINE_PATH.read_text())
    changelog = git("diff", f"{base_ref}...HEAD", "--", "CHANGELOG.md", cwd=root).stdout
    validate_baseline_update(old, new, changelog)


def write_baseline(data: dict[str, Any]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def run(write: bool, base_ref: str | None) -> dict[str, int] | None:
    current = snapshot()
    if write:
        write_baseline(current)
        return None
    if not BASELINE_PATH.is_file():
        raise CompatibilityError(f"missing baseline: {BASELINE_PATH}")
    baseline = json.loads(BASELINE_PATH.read_text())
    failures = compare(baseline, current)
    if failures:
        raise CompatibilityError("\n".join(failures))
    baseline_update_policy(base_ref)
    return {name: len(items) for name, items in current["surfaces"].items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write", action="store_true", help="rewrite baseline from current source"
    )
    parser.add_argument("--base-ref", default=os.environ.get("GITHUB_BASE_REF"))
    args = parser.parse_args()
    counts = run(args.write, args.base_ref)
    if counts is None:
        print(f"wrote {BASELINE_PATH.relative_to(REPO_ROOT)}")
    else:
        print(json.dumps({"status": "ok", "surface_counts": counts}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except CompatibilityError as exc:
        print(f"compatibility error: {exc}", file=sys.stderr)
        raise SystemExit(1)
