"""Verify the fixed CI media binaries before using the existing apt fallback."""

import os
import stat
import subprocess
from pathlib import Path

BINARIES = (Path("/usr/bin/ffmpeg"), Path("/usr/bin/ffprobe"))
APT_COMMANDS = (("sudo", "apt-get", "update"), ("sudo", "apt-get", "install", "--yes", "ffmpeg"))


def _binary_available(binary: Path) -> bool:
    try:
        if not stat.S_ISREG(binary.stat().st_mode) or not os.access(binary, os.X_OK):
            return False
        result = subprocess.run(
            [str(binary), "-version"], check=True, capture_output=True, text=True
        )
    except OSError, subprocess.CalledProcessError, UnicodeDecodeError:
        return False
    prefix = f"{binary.name} version "
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    return first_line.startswith(prefix) and bool(first_line[len(prefix) :].strip())


def _both_available() -> bool:
    # Evaluate both probes even when the first binary is unavailable.
    results = [_binary_available(binary) for binary in BINARIES]
    return all(results)


def ensure_media_runtime() -> None:
    if _both_available():
        return
    for command in APT_COMMANDS:
        subprocess.run(list(command), check=True)
    if not _both_available():
        raise RuntimeError("Both fixed CI media binaries must pass executable and version checks")


if __name__ == "__main__":
    ensure_media_runtime()
