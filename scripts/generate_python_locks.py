#!/usr/bin/env python3
"""Generate and verify reviewed SHA-256 Python tool lock files."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
LOCK_ROOT: Final = REPO_ROOT / "requirements" / "python"
EXACT_REQUIREMENT = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s;]+)"
)
HASH_LINE = re.compile(r"\s+--hash=sha256:(?P<digest>[0-9a-f]{64})(?: \\)?$")
UNSAFE_TOKENS = ("://", "--index-url", "--extra-index-url", "--trusted-host", "@")


class LockError(RuntimeError):
    """Raised when a lock input or output violates the repository policy."""


@dataclass(frozen=True, order=True)
class Requirement:
    name: str
    version: str

    @property
    def normalized_name(self) -> str:
        return re.sub(r"[-_.]+", "-", self.name).lower()

    @property
    def line(self) -> str:
        return f"{self.normalized_name}=={self.version}"


def lock_pairs() -> list[tuple[Path, Path]]:
    inputs = sorted(LOCK_ROOT.glob("*.in"))
    if not inputs:
        raise LockError(f"no lock inputs found below {LOCK_ROOT}")
    return [(path, path.with_suffix(".txt")) for path in inputs]


def parse_input(path: Path) -> list[Requirement]:
    requirements: list[Requirement] = []
    seen: set[str] = set()
    previous = ""
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if any(token in line for token in UNSAFE_TOKENS) or any(
            operator in line for operator in (">=", "<=", "~=", "!=", "===", "<", ">")
        ):
            raise LockError(
                f"{path}:{number}: requirement must be one exact public version"
            )
        match = EXACT_REQUIREMENT.fullmatch(line)
        if match is None:
            raise LockError(
                f"{path}:{number}: unsupported requirement syntax: {line!r}"
            )
        requirement = Requirement(match.group("name"), match.group("version"))
        if requirement.normalized_name in seen:
            raise LockError(
                f"{path}:{number}: duplicate package {requirement.normalized_name}"
            )
        if requirement.normalized_name < previous:
            raise LockError(
                f"{path}:{number}: inputs must be sorted by normalized package name"
            )
        previous = requirement.normalized_name
        seen.add(requirement.normalized_name)
        requirements.append(requirement)
    if not requirements:
        raise LockError(f"{path}: lock input is empty")
    return requirements


def pypi_json(url: str, context: str) -> dict[str, object]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "adxl355-lock-generator/1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise LockError(f"cannot read PyPI metadata for {context}: {error}") from error
    if not isinstance(payload, dict):
        raise LockError(f"PyPI metadata for {context} is not a JSON object")
    return payload


def release_hashes(requirement: Requirement) -> list[str]:
    package = urllib.parse.quote(requirement.normalized_name, safe="")
    version = urllib.parse.quote(requirement.version, safe="")
    url = f"https://pypi.org/pypi/{package}/{version}/json"
    payload = pypi_json(url, requirement.line)
    files = payload.get("urls")
    if not isinstance(files, list):
        raise LockError(f"PyPI metadata has no release files for {requirement.line}")
    hashes = sorted(
        {
            str(entry.get("digests", {}).get("sha256", ""))
            for entry in files
            if isinstance(entry, dict) and not bool(entry.get("yanked"))
        }
        - {""}
    )
    if not hashes or any(
        re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in hashes
    ):
        raise LockError(
            f"PyPI metadata has no valid SHA-256 files for {requirement.line}"
        )
    return hashes


def latest_release(requirement: Requirement) -> str:
    """Return the public PyPI release currently advertised for one package."""
    package = urllib.parse.quote(requirement.normalized_name, safe="")
    payload = pypi_json(
        f"https://pypi.org/pypi/{package}/json",
        requirement.normalized_name,
    )
    info = payload.get("info")
    if not isinstance(info, dict):
        raise LockError(
            f"PyPI metadata has no info object for {requirement.normalized_name}"
        )
    version = info.get("version")
    if not isinstance(version, str) or not version.strip():
        raise LockError(
            f"PyPI metadata has no latest version for {requirement.normalized_name}"
        )
    return version.strip()


def latest_report(
    lookup: Callable[[Requirement], str] = latest_release,
) -> dict[str, object]:
    """Build a read-only report; never rewrite reviewed manifests automatically."""
    cache: dict[str, str] = {}
    entries: list[dict[str, str]] = []
    for source, _lock in lock_pairs():
        for requirement in parse_input(source):
            latest = cache.get(requirement.normalized_name)
            if latest is None:
                latest = lookup(requirement)
                cache[requirement.normalized_name] = latest
            if latest == requirement.version:
                continue
            entries.append(
                {
                    "group": source.stem,
                    "package": requirement.normalized_name,
                    "current": requirement.version,
                    "latest": latest,
                }
            )
    entries.sort(key=lambda item: (item["package"], item["group"], item["current"]))
    return {
        "status": "outdated" if entries else "up-to-date",
        "outdated": entries,
        "packages_checked": len(cache),
        "groups_checked": len(lock_pairs()),
    }


def render_lock(source: Path, requirements: list[Requirement]) -> str:
    lines = [
        "# Generated by scripts/generate_python_locks.py.",
        f"# Source: {source.relative_to(REPO_ROOT).as_posix()}",
        "# Review package/version changes in the .in file and hash-set changes here.",
        "",
    ]
    for requirement in requirements:
        hashes = release_hashes(requirement)
        lines.append(f"{requirement.line} \\")
        for index, digest in enumerate(hashes):
            continuation = " \\" if index < len(hashes) - 1 else ""
            lines.append(f"    --hash=sha256:{digest}{continuation}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_lock(path: Path) -> dict[str, tuple[str, tuple[str, ...]]]:
    if not path.is_file():
        raise LockError(f"missing generated lock: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    packages: dict[str, tuple[str, tuple[str, ...]]] = {}
    index = 0
    previous = ""
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line or line.startswith("#"):
            continue
        if any(token in line for token in UNSAFE_TOKENS):
            raise LockError(f"{path}:{index}: unsafe lock directive")
        if not line.endswith("\\"):
            raise LockError(f"{path}:{index}: package line must continue to hashes")
        requirement_line = line[:-1].strip()
        match = EXACT_REQUIREMENT.fullmatch(requirement_line)
        if match is None:
            raise LockError(f"{path}:{index}: invalid locked requirement")
        requirement = Requirement(match.group("name"), match.group("version"))
        if requirement.normalized_name < previous:
            raise LockError(f"{path}:{index}: packages are not sorted")
        previous = requirement.normalized_name
        hashes: list[str] = []
        while index < len(lines):
            hash_line = lines[index]
            match_hash = HASH_LINE.fullmatch(hash_line)
            if match_hash is None:
                break
            hashes.append(match_hash.group("digest"))
            index += 1
        if not hashes:
            raise LockError(f"{path}:{index}: {requirement.line} has no SHA-256 hashes")
        if hashes != sorted(set(hashes)):
            raise LockError(
                f"{path}:{index}: {requirement.line} hashes are not sorted/unique"
            )
        if requirement.normalized_name in packages:
            raise LockError(
                f"{path}:{index}: duplicate package {requirement.normalized_name}"
            )
        packages[requirement.normalized_name] = (
            requirement.version,
            tuple(hashes),
        )
    if not packages:
        raise LockError(f"{path}: generated lock is empty")
    return packages


def verify_pair(source: Path, lock: Path) -> None:
    expected = {item.normalized_name: item.version for item in parse_input(source)}
    actual = {name: version for name, (version, _hashes) in parse_lock(lock).items()}
    if actual != expected:
        missing = sorted(expected.keys() - actual.keys())
        extra = sorted(actual.keys() - expected.keys())
        changed = sorted(
            name
            for name in expected.keys() & actual.keys()
            if expected[name] != actual[name]
        )
        raise LockError(
            f"{lock}: does not match {source.name}; missing={missing}, extra={extra}, changed={changed}"
        )


def generate() -> None:
    for source, lock in lock_pairs():
        content = render_lock(source, parse_input(source))
        lock.write_text(content, encoding="utf-8")
        print(f"wrote {lock.relative_to(REPO_ROOT)}")


def verify() -> None:
    for source, lock in lock_pairs():
        verify_pair(source, lock)
    orphaned = sorted(
        path for path in LOCK_ROOT.glob("*.txt") if not path.with_suffix(".in").exists()
    )
    if orphaned:
        raise LockError(f"orphaned generated locks: {[path.name for path in orphaned]}")
    print(f"verified {len(lock_pairs())} Python hash locks")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--verify", action="store_true", help="verify committed locks without network"
    )
    mode.add_argument(
        "--check-latest",
        action="store_true",
        help="report newer public PyPI versions without changing files",
    )
    parser.add_argument(
        "--fail-on-outdated",
        action="store_true",
        help="with --check-latest, return nonzero when updates are reported",
    )
    args = parser.parse_args(argv)
    if args.fail_on_outdated and not args.check_latest:
        parser.error("--fail-on-outdated requires --check-latest")
    try:
        if args.verify:
            verify()
        elif args.check_latest:
            report = latest_report()
            print(json.dumps(report, indent=2, sort_keys=True))
            if args.fail_on_outdated and report["status"] == "outdated":
                return 1
        else:
            generate()
            verify()
    except LockError as error:
        print(f"Python lock error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
