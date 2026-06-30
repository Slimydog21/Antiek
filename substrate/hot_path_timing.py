"""ARE-12 hot-path timing recorder.

The decorator records boundary timings without changing the wrapped
function's return value or exception behavior. It is intentionally tiny:
benchmarks own where records are written, production callers can leave the
sink unset and pay only a monotonic clock read plus one branch.
"""

from __future__ import annotations

import functools
import os
import platform
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

SCHEMA_VERSION = 1
_sink: Callable[[dict[str, Any]], None] | None = None
_git_sha: str | None = None


def set_hot_path_timing_sink(sink: Callable[[dict[str, Any]], None] | None) -> None:
    global _sink
    _sink = sink


def current_git_sha() -> str:
    global _git_sha
    if _git_sha is not None:
        return _git_sha
    try:
        root = Path(__file__).resolve().parents[1]
        _git_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        _git_sha = "unknown"
    return _git_sha


def make_timing_record(path_name: str, ts_start: float, ts_end: float) -> dict[str, Any]:
    return {
        "path": path_name,
        "ts_start": ts_start,
        "ts_end": ts_end,
        "duration_ms": round((ts_end - ts_start) * 1000.0, 6),
        "schema_version": SCHEMA_VERSION,
        "git_sha": current_git_sha(),
        "python_version": platform.python_version(),
        "os": platform.system(),
        "platform": platform.platform(),
        "pid": os.getpid(),
    }


def hot_path_timing(path_name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            ts_start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                ts_end = time.perf_counter()
                if _sink is not None:
                    _sink(make_timing_record(path_name, ts_start, ts_end))

        return wrapper

    return decorate


def runtime_fingerprint() -> dict[str, str]:
    return {
        "git_sha": current_git_sha(),
        "python_version": sys.version.split()[0],
        "os": platform.system(),
        "platform": platform.platform(),
    }
