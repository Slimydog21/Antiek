"""Trusted platform defaults for local FFmpeg execution."""

from __future__ import annotations

import platform
from pathlib import Path


def _default_executable(name: str) -> str:
    candidates = (Path("/opt/homebrew/bin") / name, Path("/usr/bin") / name)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    # Imports must remain usable on hosts without FFmpeg. The execution
    # boundary resolves this absolute path strictly and fails closed.
    root = Path("/opt/homebrew/bin") if platform.system() == "Darwin" else Path("/usr/bin")
    return str(root / name)


DEFAULT_FFMPEG_PATH = _default_executable("ffmpeg")
DEFAULT_FFPROBE_PATH = _default_executable("ffprobe")


__all__ = ["DEFAULT_FFMPEG_PATH", "DEFAULT_FFPROBE_PATH"]
