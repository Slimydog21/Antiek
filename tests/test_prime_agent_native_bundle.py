from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.prime_agent import installation as installation_module
from runtime.prime_agent.installation import (
    PrimeAgentInstallation,
    PrimeAgentUnavailable,
    _snapshot_binary,
    _snapshot_bundle,
    revalidate_prime_agent_installation,
    stage_verified_prime_agent,
)


class NativePrimeBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.release = self.root / "release"
        self.release.mkdir()

    def native_release(self) -> Path:
        binary = self.release / "prime-agent"
        binary.write_bytes(b"\xcf\xfa\xed\xfenative-test-artifact")
        binary.chmod(0o700)
        (self.release / "package.json").write_text('{"version":"0.9.8"}\n')
        runtime = self.release / "prime-agent-runtime"
        runtime.mkdir()
        (runtime / "runtime-data.json").write_text('{"data":"original"}\n')
        return binary

    def snapshot(self, binary: Path) -> PrimeAgentInstallation:
        root, entries = _snapshot_bundle(binary)
        return PrimeAgentInstallation(
            binary=binary,
            version=(0, 9, 8),
            identity=_snapshot_binary(binary),
            bundle_root=root,
            bundle=entries,
        )

    def test_native_release_stages_adjacent_package_and_runtime_data(self) -> None:
        binary = self.native_release()
        installation = self.snapshot(binary)
        destination = self.root / "staged"
        entrypoint = stage_verified_prime_agent(installation, destination)
        self.assertEqual(entrypoint.read_bytes(), binary.read_bytes())
        self.assertEqual(
            (destination / "package.json").read_bytes(),
            (self.release / "package.json").read_bytes(),
        )
        self.assertEqual(
            (destination / "prime-agent-runtime/runtime-data.json").read_bytes(),
            (self.release / "prime-agent-runtime/runtime-data.json").read_bytes(),
        )
        revalidate_prime_agent_installation(installation)

    def test_changed_package_is_refused_before_execution(self) -> None:
        installation = self.snapshot(self.native_release())
        (self.release / "package.json").write_text('{"version":"different"}\n')
        with self.assertRaises(PrimeAgentUnavailable):
            revalidate_prime_agent_installation(installation)

    def test_changed_runtime_data_is_refused_before_execution(self) -> None:
        installation = self.snapshot(self.native_release())
        (self.release / "prime-agent-runtime/runtime-data.json").write_text("replaced")
        with self.assertRaises(PrimeAgentUnavailable):
            revalidate_prime_agent_installation(installation)

    def test_added_native_release_file_invalidates_snapshot(self) -> None:
        installation = self.snapshot(self.native_release())
        (self.release / "unexpected.json").write_text("added")
        with self.assertRaises(PrimeAgentUnavailable):
            revalidate_prime_agent_installation(installation)

    def test_native_bundle_retains_existing_path_order_for_cache_digest(self) -> None:
        binary = self.native_release()
        (self.release / "prime-agent-runtime.json").write_text("sibling")
        installation = self.snapshot(binary)
        self.assertEqual(
            [entry.relative_path for entry in installation.bundle],
            [
                "package.json",
                "prime-agent",
                "prime-agent-runtime/runtime-data.json",
                "prime-agent-runtime.json",
            ],
        )

    def test_native_release_file_symlink_is_refused(self) -> None:
        binary = self.native_release()
        (self.release / "alias.json").symlink_to("package.json")
        with self.assertRaises(PrimeAgentUnavailable):
            self.snapshot(binary)

    def test_native_release_directory_symlink_is_refused(self) -> None:
        binary = self.native_release()
        (self.release / "alias-runtime").symlink_to("prime-agent-runtime", target_is_directory=True)
        with self.assertRaises(PrimeAgentUnavailable):
            self.snapshot(binary)

    def test_native_release_entry_budget_is_enforced(self) -> None:
        binary = self.native_release()
        with (
            patch.object(installation_module, "_MAX_BUNDLE_FILES", 2),
            self.assertRaises(PrimeAgentUnavailable),
        ):
            self.snapshot(binary)

    def test_native_release_byte_budget_is_enforced(self) -> None:
        binary = self.native_release()
        with (
            patch.object(installation_module, "_MAX_BUNDLE_BYTES", 5),
            self.assertRaises(PrimeAgentUnavailable),
        ):
            self.snapshot(binary)

    def test_replaced_directory_cannot_supply_outside_bytes(self) -> None:
        binary = self.native_release()
        runtime = self.release / "prime-agent-runtime"
        original_inode = runtime.stat().st_ino
        outside = self.root / "outside"
        outside.mkdir()
        outside_data = outside / "runtime-data.json"
        outside_data.write_text("outside release")
        outside_inode = outside_data.stat().st_ino
        original_scandir, original_read = os.scandir, os.read
        outside_reads = []
        replaced = False

        def replace_directory(path):
            nonlocal replaced
            inode = os.fstat(path).st_ino if isinstance(path, int) else Path(path).stat().st_ino
            if inode == original_inode and not replaced:
                replaced = True
                runtime.rename(self.root / "retired-runtime")
                runtime.symlink_to(outside, target_is_directory=True)
            return original_scandir(path)

        def record_read(fd, count):
            if os.fstat(fd).st_ino == outside_inode:
                outside_reads.append(count)
            return original_read(fd, count)

        with (
            patch.object(installation_module.os, "scandir", replace_directory),
            patch.object(installation_module.os, "read", record_read),
            self.assertRaises(PrimeAgentUnavailable),
        ):
            self.snapshot(binary)
        self.assertTrue(replaced)
        self.assertEqual(outside_reads, [])

    def test_file_growth_before_open_is_refused_before_body_read(self) -> None:
        binary = self.native_release()
        data = self.release / "prime-agent-runtime/runtime-data.json"
        inode = data.stat().st_ino
        original_open, original_read = os.open, os.read
        reads = []
        grown = False

        def grow_before_open(path, flags, *args, **kwargs):
            nonlocal grown
            if Path(path).name == data.name and not grown:
                grown = True
                data.write_bytes(b"x" * 4096)
            return original_open(path, flags, *args, **kwargs)

        def record_read(fd, count):
            if os.fstat(fd).st_ino == inode:
                reads.append(count)
            return original_read(fd, count)

        with (
            patch.object(installation_module, "_MAX_BUNDLE_BYTES", 1024),
            patch.object(installation_module.os, "open", grow_before_open),
            patch.object(installation_module.os, "read", record_read),
            self.assertRaises(PrimeAgentUnavailable),
        ):
            self.snapshot(binary)
        self.assertTrue(grown)
        self.assertEqual(reads, [])

    def test_file_growth_during_hash_never_reads_past_reservation(self) -> None:
        binary = self.native_release()
        data = self.release / "prime-agent-runtime/runtime-data.json"
        inode, reserved = data.stat().st_ino, data.stat().st_size
        original_read = os.read
        received = 0
        grown = False

        def grow_during_read(fd, count):
            nonlocal received, grown
            if os.fstat(fd).st_ino == inode:
                if not grown:
                    grown = True
                    with data.open("ab") as stream:
                        stream.write(b"x" * 4096)
                chunk = original_read(fd, count)
                received += len(chunk)
                return chunk
            return original_read(fd, count)

        with (
            patch.object(installation_module.os, "read", grow_during_read),
            self.assertRaises(PrimeAgentUnavailable),
        ):
            self.snapshot(binary)
        self.assertTrue(grown)
        self.assertLessEqual(received, reserved)

    def test_replaced_file_is_refused_before_its_body_is_read(self) -> None:
        binary = self.native_release()
        data = self.release / "prime-agent-runtime/runtime-data.json"
        replacement = self.root / "replacement.json"
        replacement.write_text("different inode")
        inode = replacement.stat().st_ino
        original_open, original_read = os.open, os.read
        reads = []
        replaced = False

        def replace_before_open(path, flags, *args, **kwargs):
            nonlocal replaced
            if Path(path).name == data.name and not replaced:
                replaced = True
                replacement.replace(data)
            return original_open(path, flags, *args, **kwargs)

        def record_read(fd, count):
            if os.fstat(fd).st_ino == inode:
                reads.append(count)
            return original_read(fd, count)

        with (
            patch.object(installation_module.os, "open", replace_before_open),
            patch.object(installation_module.os, "read", record_read),
            self.assertRaises(PrimeAgentUnavailable),
        ):
            self.snapshot(binary)
        self.assertTrue(replaced)
        self.assertEqual(reads, [])

    def test_truncation_during_hash_is_refused(self) -> None:
        binary = self.native_release()
        data = self.release / "prime-agent-runtime/runtime-data.json"
        inode = data.stat().st_ino
        original_read = os.read
        truncated = False

        def truncate_during_read(fd, count):
            nonlocal truncated
            if os.fstat(fd).st_ino == inode and not truncated:
                truncated = True
                data.write_bytes(b"")
            return original_read(fd, count)

        with (
            patch.object(installation_module.os, "read", truncate_during_read),
            self.assertRaises(PrimeAgentUnavailable),
        ):
            self.snapshot(binary)
        self.assertTrue(truncated)

    def test_replaced_directory_is_refused_when_staging(self) -> None:
        installation = self.snapshot(self.native_release())
        runtime = self.release / "prime-agent-runtime"
        outside = self.root / "outside"
        runtime.rename(outside)
        runtime.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(PrimeAgentUnavailable):
            stage_verified_prime_agent(installation, self.root / "staged")

    def test_new_directory_identity_invalidates_verified_release(self) -> None:
        installation = self.snapshot(self.native_release())
        runtime = self.release / "prime-agent-runtime"
        runtime.rename(self.root / "retired-runtime")
        runtime.mkdir()
        (self.root / "retired-runtime/runtime-data.json").rename(runtime / "runtime-data.json")
        with self.assertRaises(PrimeAgentUnavailable):
            revalidate_prime_agent_installation(installation)

    def test_growth_during_stage_is_refused_without_reading_new_tail(self) -> None:
        installation = self.snapshot(self.native_release())
        data = self.release / "prime-agent-runtime/runtime-data.json"
        inode, reserved = data.stat().st_ino, data.stat().st_size
        original_read = os.read
        received = 0
        grown = False

        def grow_during_read(fd, count):
            nonlocal received, grown
            if os.fstat(fd).st_ino == inode:
                if not grown:
                    grown = True
                    with data.open("ab") as stream:
                        stream.write(b"x" * 4096)
                chunk = original_read(fd, count)
                received += len(chunk)
                return chunk
            return original_read(fd, count)

        with (
            patch.object(installation_module.os, "read", grow_during_read),
            self.assertRaises(PrimeAgentUnavailable),
        ):
            stage_verified_prime_agent(installation, self.root / "staged")
        self.assertTrue(grown)
        self.assertLessEqual(received, reserved)

    def test_elf_and_windows_releases_preserve_adjacent_package_data(self) -> None:
        binary = self.native_release()
        for header in (b"\x7fELF", b"MZ\x00\x00"):
            with self.subTest(header=header):
                binary.write_bytes(header + b"native-test-artifact")
                installation = self.snapshot(binary)
                destination = self.root / header.hex()
                stage_verified_prime_agent(installation, destination)
                self.assertEqual(
                    (destination / "package.json").read_bytes(),
                    (self.release / "package.json").read_bytes(),
                )

    def test_native_executable_without_package_metadata_remains_standalone(self) -> None:
        binary = self.native_release()
        (self.release / "package.json").unlink()
        installation = self.snapshot(binary)
        destination = self.root / "staged"
        stage_verified_prime_agent(installation, destination)
        self.assertEqual(list(destination.iterdir()), [destination / "prime-agent"])

    def test_javascript_bundle_keeps_relative_imports_and_package_metadata(self) -> None:
        bundle = self.release / "dist/bundle"
        bundle.mkdir(parents=True)
        binary = bundle / "cli.js"
        binary.write_text("#!/usr/bin/env node\nimport './chunk.js';\n")
        binary.chmod(0o700)
        (bundle / "chunk.js").write_text("export const value = 1;\n")
        (self.release / "package.json").write_text('{"type":"module"}\n')
        installation = self.snapshot(binary)
        destination = self.root / "staged"
        entrypoint = stage_verified_prime_agent(installation, destination)
        self.assertEqual(entrypoint.relative_to(destination), Path("dist/bundle/cli.js"))
        self.assertEqual(
            (entrypoint.parent / "chunk.js").read_bytes(), (bundle / "chunk.js").read_bytes()
        )
        self.assertEqual(
            (destination / "package.json").read_bytes(),
            (self.release / "package.json").read_bytes(),
        )

    def test_standalone_script_does_not_adopt_unrelated_package_directory(self) -> None:
        binary = self.release / "prime-agent"
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o700)
        (self.release / "package.json").write_text("{}\n")
        installation = self.snapshot(binary)
        destination = self.root / "staged"
        stage_verified_prime_agent(installation, destination)
        self.assertEqual(list(destination.iterdir()), [destination / "prime-agent"])


if __name__ == "__main__":
    unittest.main()
