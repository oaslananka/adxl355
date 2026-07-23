from __future__ import annotations

import unittest

from scripts.finalize_release_sbom import SbomFinalizeError, finalize_release_sbom


class FinalizeReleaseSbomTests(unittest.TestCase):
    @staticmethod
    def syft_document() -> dict[str, object]:
        return {
            "spdxVersion": "SPDX-2.3",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "raw syft result",
            "packages": [
                {
                    "name": "adxl355",
                    "SPDXID": "SPDXRef-Package-Python",
                    "versionInfo": "0.1.0a2",
                    "externalRefs": [
                        {
                            "referenceCategory": "PACKAGE-MANAGER",
                            "referenceType": "purl",
                            "referenceLocator": "pkg:pypi/adxl355@0.1.0a2",
                        }
                    ],
                },
                {
                    "name": "embedded-hal",
                    "SPDXID": "SPDXRef-Package-EmbeddedHal",
                    "versionInfo": "1.0.0",
                    "externalRefs": [
                        {
                            "referenceCategory": "PACKAGE-MANAGER",
                            "referenceType": "purl",
                            "referenceLocator": "pkg:cargo/embedded-hal@1.0.0",
                        }
                    ],
                },
            ],
            "relationships": [],
        }

    @staticmethod
    def manifest() -> dict[str, object]:
        identities = (
            ("python-wheel", "python/adxl355.whl", "adxl355", "0.1.0a2", "pkg:pypi/adxl355@0.1.0a2"),
            (
                "rust-crate",
                "rust/adxl355-driver.crate",
                "adxl355-driver",
                "0.1.0-alpha.2",
                "pkg:cargo/adxl355-driver@0.1.0-alpha.2",
            ),
            (
                "node-tarball",
                "node/adxl355.tgz",
                "@oaslananka/adxl355",
                "0.1.0-alpha.2",
                "pkg:npm/%40oaslananka/adxl355@0.1.0-alpha.2",
            ),
            (
                "go-module",
                "go/adxl355-go.tar.gz",
                "github.com/oaslananka/adxl355/go",
                "0.1.0-alpha.2",
                "pkg:golang/github.com/oaslananka/adxl355/go@0.1.0-alpha.2",
            ),
            (
                "native",
                "native/adxl355-c-cpp.tar.gz",
                "adxl355-c-cpp",
                "0.1.0-alpha.2",
                "pkg:generic/adxl355-c-cpp@0.1.0-alpha.2",
            ),
        )
        return {
            "schema_version": 1,
            "archives": [
                {
                    "kind": kind,
                    "archive": archive,
                    "name": name,
                    "version": version,
                    "purl": purl,
                    "sha256": f"{index:064x}",
                    "files": 1,
                }
                for index, (kind, archive, name, version, purl) in enumerate(
                    identities, start=1
                )
            ],
        }

    def test_adds_all_release_artifacts_without_duplicating_syft_packages(self) -> None:
        final = finalize_release_sbom(self.syft_document(), self.manifest())
        packages = final["packages"]
        purls = {
            reference["referenceLocator"]
            for package in packages
            for reference in package.get("externalRefs", [])
            if reference.get("referenceType") == "purl"
        }
        self.assertEqual(len(packages), 6)
        self.assertIn("pkg:pypi/adxl355@0.1.0a2", purls)
        self.assertIn("pkg:cargo/adxl355-driver@0.1.0-alpha.2", purls)
        self.assertIn("pkg:npm/%40oaslananka/adxl355@0.1.0-alpha.2", purls)
        self.assertIn(
            "pkg:golang/github.com/oaslananka/adxl355/go@0.1.0-alpha.2", purls
        )
        self.assertIn("pkg:generic/adxl355-c-cpp@0.1.0-alpha.2", purls)

        python_packages = [package for package in packages if package.get("name") == "adxl355"]
        self.assertEqual(len(python_packages), 1)
        self.assertEqual(python_packages[0]["checksums"][0]["algorithm"], "SHA256")
        self.assertEqual(final["name"], "adxl355 verified release artifacts")
        self.assertGreaterEqual(len(final["relationships"]), 5)

    def test_rejects_incomplete_release_manifest(self) -> None:
        manifest = self.manifest()
        manifest["archives"] = manifest["archives"][:-1]
        document = self.syft_document()
        with self.assertRaisesRegex(SbomFinalizeError, "exactly five"):
            finalize_release_sbom(document, manifest)

    def test_rejects_invalid_artifact_checksum(self) -> None:
        manifest = self.manifest()
        manifest["archives"][0]["sha256"] = "not-a-checksum"
        document = self.syft_document()
        with self.assertRaisesRegex(SbomFinalizeError, "invalid SHA-256"):
            finalize_release_sbom(document, manifest)

    def test_rejects_non_spdx_23_input(self) -> None:
        document = self.syft_document()
        document["spdxVersion"] = "SPDX-2.2"
        manifest = self.manifest()
        with self.assertRaisesRegex(SbomFinalizeError, "SPDX-2.3"):
            finalize_release_sbom(document, manifest)


if __name__ == "__main__":
    unittest.main()
