"""Deno preflight -- detect deno binary + version before run_script first call."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

DENO_MIN_VERSION: tuple[int, int, int] = (1, 40, 0)


@dataclass(frozen=True)
class DenoPreflight:
    available: bool
    version: tuple[int, int, int] | None
    error: str | None = None

    @property
    def usable(self) -> bool:
        return self.available and self.error is None


_VERSION_RE = re.compile(r"^deno\s+(\d+)\.(\d+)\.(\d+)")


def preflight() -> DenoPreflight:
    binary = shutil.which("deno")
    if binary is None:
        return DenoPreflight(
            available=False,
            version=None,
            error=(
                "deno not found on PATH; install via "
                "`curl -fsSL https://deno.land/install.sh | sh` "
                "(macOS: `brew install deno`)"
            ),
        )
    try:
        out = subprocess.check_output(
            [binary, "--version"], text=True, timeout=5, stderr=subprocess.STDOUT
        )
    except subprocess.TimeoutExpired:
        return DenoPreflight(available=True, version=None, error="deno --version timed out after 5s")
    except subprocess.SubprocessError as exc:
        return DenoPreflight(available=True, version=None, error=f"deno --version failed: {exc!r}")

    first_line = out.splitlines()[0] if out else ""
    m = _VERSION_RE.match(first_line)
    if not m:
        return DenoPreflight(
            available=True,
            version=None,
            error=f"could not parse deno version from {first_line!r}",
        )
    v = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if v < DENO_MIN_VERSION:
        return DenoPreflight(
            available=True,
            version=v,
            error=(
                f"deno {v[0]}.{v[1]}.{v[2]} < required "
                f"{DENO_MIN_VERSION[0]}.{DENO_MIN_VERSION[1]}.{DENO_MIN_VERSION[2]}; "
                f"upgrade via `deno upgrade`"
            ),
        )
    return DenoPreflight(available=True, version=v, error=None)
