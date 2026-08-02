from __future__ import annotations

import io
import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.release_artifacts import (
    ArtifactError,
    _extract_tar,
    inspect_native,
    inspect_node,
    inspect_python,
    inspect_rust,
)


class ReleaseArtifactTests(unittest.TestCase):
    def make_directory(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="adxl355-artifact-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(directory))
        return directory

    @staticmethod
    def add_tar_text(
        handle: tarfile.TarFile, name: str, text: str, *, mode: int = 0o644
    ) -> None:
        payload = text.encode()
        info = tarfile.TarInfo(name)
        info.size = len(payload)
        info.mode = mode
        handle.addfile(info, io.BytesIO(payload))

    def make_python_artifacts(self, *, include_tests: bool = False) -> Path:
        directory = self.make_directory()
        wheel = directory / "adxl355-0.1.0a2-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as handle:
            handle.writestr("adxl355/__init__.py", "")
            handle.writestr(
                "adxl355-0.1.0a2.dist-info/METADATA",
                "Metadata-Version: 2.4\n"
                "Name: adxl355\n"
                "Version: 0.1.0a2\n"
                "Project-URL: Repository, https://github.com/oaslananka/adxl355\n"
                "Project-URL: Documentation, https://github.com/oaslananka/adxl355/tree/main/docs\n",
            )
            if include_tests:
                handle.writestr("tests/test_bad.py", "")
        with tarfile.open(directory / "adxl355-0.1.0a2.tar.gz", "w:gz") as handle:
            self.add_tar_text(handle, "adxl355-0.1.0a2/README.md", "readme")
            self.add_tar_text(handle, "adxl355-0.1.0a2/LICENSE", "license")
            self.add_tar_text(handle, "adxl355-0.1.0a2/src/adxl355/__init__.py", "")
        return directory

    def test_python_artifacts_enforce_metadata_and_runtime_only_files(self) -> None:
        report = inspect_python(self.make_python_artifacts(), "0.1.0a2", smoke=False)
        self.assertEqual(report["package"], "python")

        invalid_artifacts = self.make_python_artifacts(include_tests=True)
        with self.assertRaisesRegex(ArtifactError, "tests or examples"):
            inspect_python(invalid_artifacts, "0.1.0a2", smoke=False)

    def make_rust_artifact(
        self, *, import_name: str = "adxl355", add_link: bool = False
    ) -> Path:
        directory = self.make_directory()
        prefix = "adxl355-driver-0.1.0-alpha.2"
        with tarfile.open(directory / f"{prefix}.crate", "w:gz") as handle:
            self.add_tar_text(
                handle,
                f"{prefix}/Cargo.toml",
                "[package]\n"
                'name = "adxl355-driver"\n'
                'version = "0.1.0-alpha.2"\n'
                f'\n[lib]\nname = "{import_name}"\npath = "src/lib.rs"\n',
            )
            self.add_tar_text(handle, f"{prefix}/README.md", "readme")
            self.add_tar_text(handle, f"{prefix}/LICENSE", "license")
            self.add_tar_text(handle, f"{prefix}/src/lib.rs", "")
            if add_link:
                link = tarfile.TarInfo(f"{prefix}/README-link.md")
                link.type = tarfile.SYMTYPE
                link.linkname = "README.md"
                handle.addfile(link)
        return directory

    def test_rust_artifact_preserves_distribution_and_import_names(self) -> None:
        report = inspect_rust(self.make_rust_artifact(), "0.1.0-alpha.2", smoke=False)
        self.assertEqual(report["package"], "rust")

        invalid_artifact = self.make_rust_artifact(import_name="adxl355_driver")
        with self.assertRaisesRegex(ArtifactError, "import name"):
            inspect_rust(invalid_artifact, "0.1.0-alpha.2", smoke=False)

    def test_rust_artifact_rejects_link_members(self) -> None:
        linked_artifact = self.make_rust_artifact(add_link=True)
        with self.assertRaisesRegex(ArtifactError, "unsupported member type"):
            inspect_rust(linked_artifact, "0.1.0-alpha.2", smoke=False)

    def make_node_artifact(self, *, extra_file: str | None = None) -> Path:
        directory = self.make_directory()
        with tarfile.open(
            directory / "oaslananka-adxl355-0.1.0-alpha.2.tgz", "w:gz"
        ) as handle:
            package = {
                "name": "@oaslananka/adxl355",
                "version": "0.1.0-alpha.2",
                "exports": {
                    ".": {"import": "./dist/index.js"},
                    "./linux/spi": {"import": "./dist/linux/spi.js"},
                    "./linux/i2c": {"import": "./dist/linux/i2c.js"},
                },
            }
            self.add_tar_text(handle, "package/package.json", json.dumps(package))
            self.add_tar_text(handle, "package/README.md", "readme")
            self.add_tar_text(handle, "package/LICENSE", "license")
            self.add_tar_text(handle, "package/dist/index.js", "")
            if extra_file is not None:
                self.add_tar_text(handle, extra_file, "unexpected")
        return directory

    def test_node_artifact_rejects_unreviewed_exports(self) -> None:
        directory = self.make_node_artifact()
        tarball = next(directory.glob("*.tgz"))
        replacement = directory / "replacement.tgz"
        with tarfile.open(tarball, "r:gz") as source, tarfile.open(replacement, "w:gz") as target:
            for member in source.getmembers():
                extracted = source.extractfile(member) if member.isfile() else None
                if member.name == "package/package.json":
                    package = json.loads(extracted.read())
                    package["exports"]["./internal"] = {"import": "./dist/internal.js"}
                    self.add_tar_text(target, member.name, json.dumps(package))
                else:
                    target.addfile(member, extracted)
        tarball.unlink()
        replacement.rename(tarball)
        with self.assertRaisesRegex(ArtifactError, "unsupported entry points"):
            inspect_node(directory, "0.1.0-alpha.2", smoke=False)

    def test_node_artifact_rejects_development_files(self) -> None:
        report = inspect_node(self.make_node_artifact(), "0.1.0-alpha.2", smoke=False)
        self.assertEqual(report["package"], "node")

        invalid_artifact = self.make_node_artifact(extra_file="package/src/device.ts")
        with self.assertRaisesRegex(ArtifactError, "unexpected file"):
            inspect_node(invalid_artifact, "0.1.0-alpha.2", smoke=False)

    def test_tar_extraction_strips_privileged_bits_and_preserves_execution(self) -> None:
        directory = self.make_directory()
        archive = directory / "mode.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            self.add_tar_text(
                handle, "bin/tool", "#!/bin/sh\nexit 0\n", mode=0o6755
            )
        extracted = directory / "extracted"
        extracted.mkdir()

        _extract_tar(archive, extracted)

        mode = (extracted / "bin/tool").stat().st_mode & 0o7777
        self.assertEqual(mode, 0o755)

    def make_native_artifact(self) -> Path:
        directory = self.make_directory()
        archive = directory / "adxl355-c-cpp-0.1.0-alpha.3.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            for name in (
                "include/adxl355/adxl355.h",
                "include/adxl355/adxl355_version.h",
                "include/adxl355-cpp/adxl355.hpp",
                "lib/libadxl355.a",
            ):
                self.add_tar_text(handle, name, "fixture")
            self.add_tar_text(
                handle,
                "bin/adxl355-c-basic-read",
                "#!/bin/sh\nexit 0\n",
                mode=0o4755,
            )
            self.add_tar_text(
                handle,
                "bin/adxl355-cpp-basic-read",
                "#!/bin/sh\nexit 0\n",
                mode=0o755,
            )
            self.add_tar_text(
                handle,
                "BUILD_INFO.txt",
                "version=0.1.0-alpha.3\ncommit=fixture\n",
            )
        return directory

    def test_native_artifact_preserves_safe_executable_intent_for_smoke(self) -> None:
        report = inspect_native(
            self.make_native_artifact(), "0.1.0-alpha.3", smoke=True
        )
        self.assertEqual(report["package"], "c-cpp")

    def test_archive_path_traversal_is_rejected(self) -> None:
        directory = self.make_node_artifact(extra_file="../escape.txt")
        with self.assertRaisesRegex(ArtifactError, "unsafe path"):
            inspect_node(directory, "0.1.0-alpha.2", smoke=False)


if __name__ == "__main__":
    unittest.main()
