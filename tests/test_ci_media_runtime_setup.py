"""Synthetic dispatch controls; these do not prove runner media availability."""

import stat
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.ci import ensure_media_runtime as runtime

EXPECTED_APT_COMMANDS = (
    ("sudo", "apt-get", "update"),
    ("sudo", "apt-get", "install", "--yes", "ffmpeg"),
)
_REAL_SUBPROCESS_RUN = subprocess.run


class MediaRuntimeSetupTests(unittest.TestCase):
    def setUp(self):
        self.commands = []
        self.phase = 0
        self.stat_checks = []
        self.bad_binary = None
        self.fault = None
        self.final_fault = False
        self.apt_failure = None
        self.stat_patch = patch.object(Path, "stat", autospec=True, side_effect=self.binary_stat)
        self.access_patch = patch.object(runtime.os, "access", self.binary_access)
        self.run_patch = patch.object(runtime.subprocess, "run", self.run_command)
        for patched in (self.stat_patch, self.access_patch, self.run_patch):
            patched.start()
            self.addCleanup(patched.stop)

    def faulty(self, binary):
        return binary.name == self.bad_binary and (self.phase == 0 or self.final_fault)

    def binary_stat(self, binary):
        self.stat_checks.append(binary.name)
        if self.faulty(binary) and self.fault == "missing":
            raise FileNotFoundError(str(binary))
        mode = stat.S_IFDIR if self.faulty(binary) and self.fault == "directory" else stat.S_IFREG
        return SimpleNamespace(st_mode=mode | 0o755)

    def binary_access(self, binary, mode):
        self.assertEqual(mode, runtime.os.X_OK)
        return not (self.faulty(binary) and self.fault == "nonexecutable")

    def run_command(self, argv, **kwargs):
        self.commands.append(argv)
        self.assertTrue(kwargs["check"])
        if argv[0] == "sudo":
            self.assertEqual(kwargs, {"check": True})
            if argv == self.apt_failure:
                raise subprocess.CalledProcessError(100, argv)
            if argv == list(EXPECTED_APT_COMMANDS[1]):
                self.phase = 1
            return SimpleNamespace(returncode=0)
        binary = Path(argv[0])
        self.assertIn(binary, runtime.BINARIES)
        self.assertEqual(argv, [str(binary), "-version"])
        self.assertEqual(kwargs, {"check": True, "capture_output": True, "text": True})
        if self.faulty(binary):
            if self.fault == "version_exit":
                raise subprocess.CalledProcessError(1, argv)
            if self.fault == "exec_error":
                raise OSError("synthetic execution refusal")
            if self.fault == "invalid_version":
                return SimpleNamespace(stdout="unrelated tool version 7\n")
            if self.fault == "empty_version":
                return SimpleNamespace(stdout="")
            if self.fault == "blank_version":
                return SimpleNamespace(stdout=f"{binary.name} version \n")
        return SimpleNamespace(stdout=f"{binary.name} version 7.1-test\nconfiguration: synthetic\n")

    def test_both_valid_skip_all_apt_commands(self):
        runtime.ensure_media_runtime()
        self.assertEqual(self.commands, [[str(b), "-version"] for b in runtime.BINARIES])

    def test_either_binary_refusal_requires_exact_fallback_and_reverification(self):
        for binary in runtime.BINARIES:
            for fault in (
                "missing",
                "directory",
                "nonexecutable",
                "version_exit",
                "exec_error",
                "invalid_version",
                "empty_version",
                "blank_version",
            ):
                with self.subTest(binary=binary.name, fault=fault):
                    self.commands = []
                    self.phase = 0
                    self.bad_binary = binary.name
                    self.fault = fault
                    runtime.ensure_media_runtime()
                    apt_index = self.commands.index(list(EXPECTED_APT_COMMANDS[0]))
                    self.assertEqual(
                        self.commands[apt_index : apt_index + 2],
                        [list(c) for c in EXPECTED_APT_COMMANDS],
                    )
                    self.assertEqual(
                        self.commands[apt_index + 2 :],
                        [[str(b), "-version"] for b in runtime.BINARIES],
                    )
                    other = (
                        runtime.BINARIES[1]
                        if binary == runtime.BINARIES[0]
                        else runtime.BINARIES[0]
                    )
                    self.assertIn([str(other), "-version"], self.commands[:apt_index])

    def test_apt_update_failure_stops_before_install_and_final_probes(self):
        self.bad_binary, self.fault = "ffmpeg", "missing"
        self.apt_failure = list(EXPECTED_APT_COMMANDS[0])
        with self.assertRaises(subprocess.CalledProcessError):
            runtime.ensure_media_runtime()
        self.assertEqual(self.commands, [["/usr/bin/ffprobe", "-version"], self.apt_failure])

    def test_apt_install_failure_stops_before_final_probes(self):
        self.bad_binary, self.fault = "ffprobe", "missing"
        self.apt_failure = list(EXPECTED_APT_COMMANDS[1])
        with self.assertRaises(subprocess.CalledProcessError):
            runtime.ensure_media_runtime()
        self.assertEqual(
            self.commands,
            [["/usr/bin/ffmpeg", "-version"], *[list(c) for c in EXPECTED_APT_COMMANDS]],
        )

    def test_either_final_binary_refusal_fails_closed(self):
        for binary in runtime.BINARIES:
            for fault in (
                "missing",
                "directory",
                "nonexecutable",
                "version_exit",
                "exec_error",
                "invalid_version",
                "empty_version",
                "blank_version",
            ):
                with self.subTest(binary=binary.name, fault=fault):
                    self.commands = []
                    self.phase = 0
                    self.bad_binary, self.fault = binary.name, fault
                    self.final_fault = True
                    with self.assertRaises(RuntimeError):
                        runtime.ensure_media_runtime()
                    self.assertEqual(
                        [c for c in self.commands if c[0] == "sudo"],
                        [list(c) for c in EXPECTED_APT_COMMANDS],
                    )
                    other = (
                        runtime.BINARIES[1]
                        if binary == runtime.BINARIES[0]
                        else runtime.BINARIES[0]
                    )
                    self.assertEqual(self.stat_checks[-2:], ["ffmpeg", "ffprobe"])
                    install_index = self.commands.index(list(EXPECTED_APT_COMMANDS[1]))
                    self.assertIn([str(other), "-version"], self.commands[install_index + 1 :])

    def test_old_workflow_unconditionally_invokes_apt_even_with_valid_binaries(self):
        old_commands = [
            ["sudo", "apt-get", "update"],
            ["sudo", "apt-get", "install", "--yes", "ffmpeg"],
        ]
        for command in old_commands:
            runtime.subprocess.run(command, check=True)
        self.assertEqual(self.commands, old_commands)
        self.commands = []
        runtime.ensure_media_runtime()
        self.assertFalse(any(c[0] == "sudo" for c in self.commands))

    def _run_decode_command(self, argv, **kwargs):
        if argv[0] != "sudo":
            binary = Path(argv[0])
            if self.faulty(binary) and self.fault == "decode_error":
                self.assertEqual(argv, [str(binary), "-version"])
                self.assertEqual(kwargs, {"check": True, "capture_output": True, "text": True})
                self.commands.append(argv)
                # Exercise the actual decoder with two bytes from a bounded
                # Python child. Media commands and apt remain synthetic.
                return _REAL_SUBPROCESS_RUN(
                    [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\n')"],
                    **kwargs,
                    timeout=5,
                    env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "PYTHONUTF8": "1"},
                )
        return self.run_command(argv, **kwargs)

    def test_each_initial_decode_error_uses_exact_fallback_and_rechecks_both(self):
        with patch.object(runtime.subprocess, "run", self._run_decode_command):
            for binary in runtime.BINARIES:
                with self.subTest(binary=binary.name):
                    self.commands = []
                    self.stat_checks = []
                    self.phase = 0
                    self.bad_binary = binary.name
                    self.fault = "decode_error"
                    self.final_fault = False
                    runtime.ensure_media_runtime()
                    apt_index = self.commands.index(list(EXPECTED_APT_COMMANDS[0]))
                    self.assertEqual(
                        self.commands[apt_index : apt_index + 2],
                        [list(c) for c in EXPECTED_APT_COMMANDS],
                    )
                    self.assertEqual(
                        self.commands[apt_index + 2 :],
                        [[str(b), "-version"] for b in runtime.BINARIES],
                    )
                    other = (
                        runtime.BINARIES[1]
                        if binary == runtime.BINARIES[0]
                        else runtime.BINARIES[0]
                    )
                    self.assertIn([str(other), "-version"], self.commands[:apt_index])

    def test_each_final_decode_error_refuses_after_exact_fallback_and_both_checks(self):
        with patch.object(runtime.subprocess, "run", self._run_decode_command):
            for binary in runtime.BINARIES:
                with self.subTest(binary=binary.name):
                    self.commands = []
                    self.stat_checks = []
                    self.phase = 0
                    self.bad_binary = binary.name
                    self.fault = "decode_error"
                    self.final_fault = True
                    with self.assertRaises(RuntimeError):
                        runtime.ensure_media_runtime()
                    self.assertEqual(
                        [c for c in self.commands if c[0] == "sudo"],
                        [list(c) for c in EXPECTED_APT_COMMANDS],
                    )
                    self.assertEqual(self.stat_checks[-2:], ["ffmpeg", "ffprobe"])
                    install_index = self.commands.index(list(EXPECTED_APT_COMMANDS[1]))
                    other = (
                        runtime.BINARIES[1]
                        if binary == runtime.BINARIES[0]
                        else runtime.BINARIES[0]
                    )
                    self.assertIn([str(other), "-version"], self.commands[install_index + 1 :])
