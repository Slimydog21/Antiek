"""Apply decoder limits before exec, without a threaded parent's preexec hook."""

from __future__ import annotations

import hashlib
import os
import resource
import stat
import sys


def _limited_exec(executable: str, expected_sha256: str, local_darwin: bool) -> None:
    if sys.platform != "linux" and not (sys.platform == "darwin" and local_darwin):
        raise RuntimeError("required_limits_unavailable")
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (536_870_912, 536_870_912))
        if resource.getrlimit(resource.RLIMIT_AS) != (536_870_912, 536_870_912):
            raise RuntimeError("required_limits_unavailable")
    fd = os.open(executable, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not before.st_mode & 0o111:
            raise RuntimeError("decoder_identity_invalid")
        digest = hashlib.sha256()
        while block := os.read(fd, 65_536):
            digest.update(block)
        after = os.fstat(fd)
        if digest.hexdigest() != expected_sha256 or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise RuntimeError("decoder_identity_invalid")
        argv = [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-xerror",
            "-max_alloc",
            "16777216",
            "-filter_threads",
            "1",
            "-filter_complex_threads",
            "1",
            "-threads",
            "1",
            "-err_detect",
            "explode",
            "-protocol_whitelist",
            "pipe",
            "-format_whitelist",
            "wav,matroska,webm,mp3,mov,ogg,flac",
            "-i",
            "pipe:0",
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-threads",
            "1",
            "-f",
            "s16le",
            "pipe:1",
        ]
        env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
        if sys.platform == "linux":
            # Linux executes the verified inode, including trusted script tools
            # used by isolated controls. The descriptor must survive a shebang.
            os.set_inheritable(fd, True)
            os.execve(fd, argv, env)
        current = os.stat(executable, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError("decoder_identity_invalid")
        # Darwin's explicit local-testing exception does not establish Linux
        # memory enforcement or the Linux descriptor-exec identity guarantee.
        os.execve(executable, argv, env)
    finally:
        os.close(fd)


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[3] not in {"linux", "local-darwin"}:
        return 78
    try:
        _limited_exec(sys.argv[1], sys.argv[2], sys.argv[3] == "local-darwin")
    except Exception:
        os.write(2, b"audio_decoder_setup_failed\n")
        return 78
    return 78


if __name__ == "__main__":
    raise SystemExit(main())
