#!/usr/bin/env python3
"""Merge Syft dependency results with verified release artifact identities."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


class SbomFinalizeError(ValueError):
    """Raised when an SPDX document or release artifact manifest is invalid."""


def _purl(package: dict[str, Any]) -> str | None:
    for reference in package.get("externalRefs", []):
        if (
            reference.get("referenceCategory") == "PACKAGE-MANAGER"
            and reference.get("referenceType") == "purl"
        ):
            return str(reference.get("referenceLocator"))
    return None


def _spdx_id(kind: str, purl: str) -> str:
    digest = hashlib.sha256(purl.encode()).hexdigest()[:16]
    safe_kind = "".join(character if character.isalnum() else "-" for character in kind)
    return f"SPDXRef-ReleaseArtifact-{safe_kind}-{digest}"


def _artifact_package(entry: dict[str, Any]) -> dict[str, Any]:
    required = ("kind", "archive", "name", "version", "purl", "sha256")
    missing = [field for field in required if not entry.get(field)]
    if missing:
        raise SbomFinalizeError(
            "release artifact manifest entry is missing: " + ", ".join(missing)
        )
    checksum = str(entry["sha256"])
    if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
        raise SbomFinalizeError(f"invalid SHA-256 for {entry['archive']!r}")
    purl = str(entry["purl"])
    return {
        "name": str(entry["name"]),
        "SPDXID": _spdx_id(str(entry["kind"]), purl),
        "versionInfo": str(entry["version"]),
        "supplier": "NOASSERTION",
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": "NOASSERTION",
        "copyrightText": "NOASSERTION",
        "primaryPackagePurpose": "LIBRARY",
        "checksums": [{"algorithm": "SHA256", "checksumValue": checksum}],
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": purl,
            }
        ],
        "comment": f"Verified release artifact archive: {entry['archive']}",
    }


def _ensure_artifact_fields(package: dict[str, Any], entry: dict[str, Any]) -> None:
    checksum = str(entry["sha256"])
    checksums = package.setdefault("checksums", [])
    if not any(
        item.get("algorithm") == "SHA256" and item.get("checksumValue") == checksum
        for item in checksums
    ):
        checksums.append({"algorithm": "SHA256", "checksumValue": checksum})
    package["comment"] = f"Verified release artifact archive: {entry['archive']}"
    package.setdefault("primaryPackagePurpose", "LIBRARY")


def finalize_release_sbom(
    syft_document: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    if syft_document.get("spdxVersion") != "SPDX-2.3":
        raise SbomFinalizeError("expected an SPDX-2.3 document from Syft")
    packages = syft_document.get("packages")
    relationships = syft_document.get("relationships")
    if not isinstance(packages, list) or not isinstance(relationships, list):
        raise SbomFinalizeError("SPDX document is missing packages or relationships")
    entries = manifest.get("archives")
    if not isinstance(entries, list) or len(entries) != 5:
        raise SbomFinalizeError("release artifact manifest must contain exactly five archives")

    by_purl = {purl: package for package in packages if (purl := _purl(package)) is not None}
    document_id = str(syft_document.get("SPDXID", "SPDXRef-DOCUMENT"))
    required_purls: list[str] = []

    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            raise SbomFinalizeError("release artifact manifest contains a non-object entry")
        entry = dict(raw_entry)
        artifact = _artifact_package(entry)
        purl = str(entry["purl"])
        required_purls.append(purl)
        existing = by_purl.get(purl)
        if existing is not None:
            _ensure_artifact_fields(existing, entry)
            package_id = str(existing["SPDXID"])
        else:
            packages.append(artifact)
            by_purl[purl] = artifact
            package_id = str(artifact["SPDXID"])
        relationship = {
            "spdxElementId": document_id,
            "relatedSpdxElement": package_id,
            "relationshipType": "DESCRIBES",
        }
        if relationship not in relationships:
            relationships.append(relationship)

    missing = [purl for purl in required_purls if purl not in by_purl]
    if missing:
        raise SbomFinalizeError("final SPDX is missing release artifacts: " + ", ".join(missing))

    packages.sort(
        key=lambda package: (
            str(package.get("name", "")),
            str(package.get("versionInfo", "")),
            str(package.get("SPDXID", "")),
        )
    )
    relationships.sort(
        key=lambda relationship: (
            str(relationship.get("spdxElementId", "")),
            str(relationship.get("relationshipType", "")),
            str(relationship.get("relatedSpdxElement", "")),
        )
    )
    syft_document["name"] = "adxl355 verified release artifacts"
    syft_document["comment"] = (
        "Syft dependency inventory augmented with the five verified release artifact "
        "identities and archive SHA-256 checksums."
    )
    return syft_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--syft-sbom", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        syft_document = json.loads(args.syft_sbom.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        final = finalize_release_sbom(syft_document, manifest)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(args.output)
    except (OSError, json.JSONDecodeError, SbomFinalizeError) as error:
        print(f"release SBOM finalization failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "ok",
                "packages": len(final["packages"]),
                "artifacts": len(manifest["archives"]),
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
