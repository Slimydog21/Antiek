"""Private data-only installation, refusal, reuse and rollback contracts."""

from __future__ import annotations

import dataclasses
import gzip
import hashlib
import io
import json
import os
import platform
import stat
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.deploy import install_prime_agent as installer

ROOT = Path(__file__).resolve().parents[1]


class PrimeReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.release = self.base / ("a" * 40)
        self.release.mkdir()
        self.public = self.base / "current"
        # These are bytes, never executable fixtures or a fake CLI response.
        self.bodies = {
            "prime-agent": b"data-only executable fixture\n",
            "package.json": b'{"version":"0.9.8"}\n',
            "runtime/module.py": b"vendor data, never imported\n",
        }
        self.items: list[tuple[tarfile.TarInfo, bytes]] = []
        members = []
        for name in ("prime-agent", "package.json", "runtime", "runtime/module.py"):
            info = tarfile.TarInfo(name)
            directory = name == "runtime"
            body = b"" if directory else self.bodies[name]
            info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
            info.mode = 0o755 if directory or name == "prime-agent" else 0o644
            info.size = len(body)
            self.items.append((info, body))
            members.append(
                installer.MemberPin(
                    name,
                    "directory" if directory else "regular",
                    len(body),
                    info.mode,
                    None if directory else hashlib.sha256(body).hexdigest(),
                )
            )
        self.archive, expanded = self.write_archive(self.items)
        compressed = self.archive.read_bytes()
        self.pin = installer.ArtifactPin(
            "0.9.8",
            "https://public.invalid/unused",
            len(compressed),
            hashlib.sha256(compressed).hexdigest(),
            expanded,
            "1" * 64,
            tuple(members),
        )

    def tearDown(self) -> None:
        for parent, _dirs, _files in os.walk(self.base):
            os.chmod(parent, 0o700)
        self.temporary.cleanup()

    def write_archive(self, items: list[tuple[tarfile.TarInfo, bytes]]) -> tuple[Path, int]:
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            for info, body in items:
                tar.addfile(info, io.BytesIO(body))
        raw = data.getvalue()
        path = self.base / "archive.tar.gz"
        path.write_bytes(gzip.compress(raw, mtime=0))
        return path, len(raw)

    def pin_current_archive(self) -> installer.ArtifactPin:
        body = self.archive.read_bytes()
        return dataclasses.replace(
            self.pin,
            archive_bytes=len(body),
            archive_sha256=hashlib.sha256(body).hexdigest(),
        )

    def install(self, pin: installer.ArtifactPin | None = None) -> None:
        installer.install_release(pin or self.pin, self.release, self.archive, self.public)

    def freeze(self) -> None:
        receipt = self.release / ".release-receipt"
        receipt.write_text(installer.receipt_text(self.pin, self.release.name))
        receipt.chmod(0o444)
        self.release.chmod(0o555)

    def assert_unpublished(self) -> None:
        self.assertFalse((self.release / ".release-receipt").exists())
        self.assertFalse((self.release / installer.BUNDLE).exists())
        self.assertFalse((self.release / installer.ENVIRONMENT).exists())
        self.assertEqual(list(self.release.iterdir()), [])

    def test_complete_readonly_bundle_and_repeat_verification(self) -> None:
        self.install()
        self.install()  # Valid prepared repeat is read-only and deterministic.
        for name, body in self.bodies.items():
            leaf = self.release / installer.BUNDLE / name
            self.assertEqual(leaf.read_bytes(), body)
            self.assertEqual(
                stat.S_IMODE(leaf.stat().st_mode), 0o555 if name == "prime-agent" else 0o444
            )
        self.freeze()
        before = {p: installer._identity(p.stat()) for p in self.release.rglob("*")}
        installer.verify_release(self.pin, self.release, self.public)
        installer.verify_release(self.pin, self.release, self.public)
        self.assertEqual(before, {p: installer._identity(p.stat()) for p in before})

    def test_bad_archive_digest_leaves_no_published_artifact(self) -> None:
        with self.assertRaises(installer.InstallRefused):
            self.install(dataclasses.replace(self.pin, archive_sha256="0" * 64))
        self.assert_unpublished()

    def test_wrong_archive_size_is_refused_before_extract(self) -> None:
        with self.assertRaises(installer.InstallRefused):
            self.install(dataclasses.replace(self.pin, archive_bytes=self.pin.archive_bytes - 1))
        self.assert_unpublished()

    def test_expansion_beyond_pin_refuses_without_publish(self) -> None:
        with self.assertRaises(installer.InstallRefused):
            self.install(
                dataclasses.replace(self.pin, expanded_tar_bytes=self.pin.expanded_tar_bytes - 1)
            )
        self.assert_unpublished()

    def test_member_body_mismatch_refuses_without_publish(self) -> None:
        items = list(self.items)
        info, body = items[-1]
        items[-1] = (info, b"x" * len(body))
        self.write_archive(items)
        with self.assertRaises(installer.InstallRefused):
            self.install(self.pin_current_archive())
        self.assert_unpublished()

    def test_traversal_absolute_and_alias_paths_cannot_escape(self) -> None:
        for name in (
            "../escape",
            "/escape",
            "runtime/../escape",
            "runtime//extra",
            "./prime-agent",
        ):
            with self.subTest(name=name):
                extra = tarfile.TarInfo(name)
                extra.mode = 0o644
                extra.size = 1
                self.write_archive(self.items + [(extra, b"x")])
                with self.assertRaises(installer.InstallRefused):
                    self.install(self.pin_current_archive())
                self.assert_unpublished()
                self.assertFalse((self.base / "escape").exists())

    def test_duplicate_or_missing_member_refused(self) -> None:
        for items in (self.items + [self.items[0]], self.items[:-1]):
            self.write_archive(items)
            with self.assertRaises(installer.InstallRefused):
                self.install(self.pin_current_archive())
            self.assert_unpublished()

    def test_links_specials_and_privileged_modes_refused(self) -> None:
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE):
            with self.subTest(kind=kind):
                info = tarfile.TarInfo("prime-agent")
                info.type = kind
                info.linkname = "package.json"
                info.mode = 0o755
                self.write_archive([(info, b"")] + self.items[1:])
                with self.assertRaises(installer.InstallRefused):
                    self.install(self.pin_current_archive())
                self.assert_unpublished()
        info = tarfile.TarInfo("prime-agent")
        info.mode = 0o4755
        info.size = len(self.bodies["prime-agent"])
        self.write_archive([(info, self.bodies["prime-agent"])] + self.items[1:])
        with self.assertRaises(installer.InstallRefused):
            self.install(self.pin_current_archive())
        self.assert_unpublished()

    def test_full_bundle_hash_rechecked_on_receipt_reuse(self) -> None:
        self.install()
        self.freeze()
        leaf = self.release / installer.BUNDLE / "runtime/module.py"
        leaf.chmod(0o644)
        leaf.write_bytes(b"x" * len(self.bodies["runtime/module.py"]))
        leaf.chmod(0o444)
        with self.assertRaises(installer.InstallRefused):
            installer.verify_release(self.pin, self.release, self.public)

    def test_extra_member_on_reuse_refused(self) -> None:
        self.install()
        self.freeze()
        root = self.release / installer.BUNDLE
        root.chmod(0o755)
        (root / "unexpected").write_bytes(b"unreviewed data")
        root.chmod(0o555)
        with self.assertRaises(installer.InstallRefused):
            installer.verify_release(self.pin, self.release, self.public)

    def test_directory_symlink_substitution_refused(self) -> None:
        self.install()
        self.freeze()
        root = self.release / installer.BUNDLE
        root.chmod(0o755)
        (root / "runtime").chmod(0o755)
        (root / "runtime").rename(self.base / "outside")
        (self.base / "outside").chmod(0o555)
        (root / "runtime").symlink_to(self.base / "outside", target_is_directory=True)
        root.chmod(0o555)
        with self.assertRaises(OSError):
            installer.verify_release(self.pin, self.release, self.public)

    def test_legacy_receipt_and_interrupted_freeze_refused(self) -> None:
        self.install()
        receipt = self.release / ".release-receipt"
        receipt.write_text("source_sha=" + self.release.name + "\n")
        receipt.chmod(0o444)
        self.release.chmod(0o555)
        with self.assertRaises(installer.InstallRefused):
            installer.verify_release(self.pin, self.release, self.public)
        self.release.chmod(0o755)
        with self.assertRaises(installer.InstallRefused):
            installer.verify_release(self.pin, self.release, self.public)

    def test_failure_between_bundle_and_environment_never_completes(self) -> None:
        rename = os.rename

        def fail_environment(source: Path, destination: Path) -> None:
            if destination.name == installer.ENVIRONMENT:
                raise OSError("controlled data publication failure")
            rename(source, destination)

        with (
            mock.patch.object(os, "rename", side_effect=fail_environment),
            self.assertRaises(OSError),
        ):
            self.install()
        self.assertTrue((self.release / installer.BUNDLE).exists())
        self.assertFalse((self.release / ".release-receipt").exists())
        with self.assertRaises(FileNotFoundError):
            self.install()  # Partial state is never silently repaired.
        self.assertFalse(
            any(p.name.startswith(".prime-agent-stage-") for p in self.release.iterdir())
        )

    def test_cleanup_failure_preserves_original_refusal(self) -> None:
        pin = dataclasses.replace(self.pin, expanded_tar_bytes=self.pin.expanded_tar_bytes - 1)
        with (
            mock.patch("shutil.rmtree", side_effect=OSError("controlled cleanup failure")),
            self.assertRaises(installer.InstallRefused) as caught,
        ):
            self.install(pin)
        self.assertIn("expanded archive exceeds", str(caught.exception))
        self.assertEqual(caught.exception.__notes__, ["stage cleanup also failed: OSError"])
        self.assertFalse((self.release / ".release-receipt").exists())
        self.assertFalse((self.release / installer.BUNDLE).exists())

    def test_public_pointer_selects_binary_and_environment_together(self) -> None:
        self.install()
        self.freeze()
        self.public.symlink_to(self.release, target_is_directory=True)
        env = (self.public / installer.ENVIRONMENT).read_text()
        binary = Path(env.strip().split("=", 1)[1])
        self.assertEqual(binary.read_bytes(), self.bodies["prime-agent"])
        old = self.base / ("b" * 40)
        old.mkdir()
        self.public.unlink()
        self.public.symlink_to(old, target_is_directory=True)
        self.assertFalse((self.public / installer.ENVIRONMENT).exists())
        template = (ROOT / "infrastructure/ansible/templates/antiek.service.j2").read_text()
        existing = "EnvironmentFile={{ antiek_secrets_file }}"
        include = "EnvironmentFile=-{{ antiek_install_dir }}/.prime-agent.env"
        self.assertGreater(template.index(include), template.index(existing))
        self.assertNotIn("ANTIEK_PRIME_AGENT_RLM_ENABLED", template)

    def test_platform_refusals_precede_data_installation(self) -> None:
        for system, machine in (("Darwin", "arm64"), ("Linux", "aarch64")):
            with (
                mock.patch.object(platform, "system", return_value=system),
                mock.patch.object(platform, "machine", return_value=machine),
                self.assertRaises(installer.InstallRefused),
            ):
                installer.require_supported_platform()
        with (
            mock.patch.object(platform, "system", return_value="Linux"),
            mock.patch.object(platform, "machine", return_value="x86_64"),
            mock.patch.object(os, "confstr", return_value=None),
            self.assertRaises(installer.InstallRefused),
        ):
            installer.require_supported_platform()

    def test_committed_pin_covers_whole_inspected_bundle(self) -> None:
        pin = installer.load_pin()
        self.assertEqual(len(pin.members), 302)
        self.assertEqual(sum(m.kind == "regular" for m in pin.members), 244)
        self.assertEqual(sum(m.size for m in pin.members), 171839549)
        self.assertEqual(
            pin.archive_sha256, "425f3e57ed8b86c8e1078b6e80bf9c678be262d377e23f4d82c036c1d6734442"
        )

    def test_manifest_bool_size_and_implicit_parent_refused(self) -> None:
        source = ROOT / "tools/deploy/prime_agent_release.json"
        data = json.loads(source.read_text())
        for change in ("bool", "parent"):
            malformed = json.loads(source.read_text())
            if change == "bool":
                malformed["members"][0]["bytes"] = True
            else:
                malformed["members"].append(
                    {
                        "path": "unlisted/leaf",
                        "kind": "regular",
                        "bytes": 0,
                        "archive_mode": 0o644,
                        "sha256": "0" * 64,
                    }
                )
            path = self.base / "bad.json"
            path.write_text(json.dumps(malformed))
            with self.assertRaises(installer.InstallRefused):
                installer.load_pin(path)
        self.assertEqual(data["version"], "0.9.8")


if __name__ == "__main__":
    unittest.main()
