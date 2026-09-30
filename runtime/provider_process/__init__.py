"""Delegation to official provider CLI processes (SPR-02, local official harness).

Antiek does not reimplement provider authentication for these paths.  An official
CLI process owns login and provider traffic, and this package is the seam that
spawns it under a private, caller-owned configuration directory.

The discipline, from SPR-02: give each process a private home, never symlink or
copy auth files, keep credential custody with the official process, and report
typed capability state rather than a boolean.
"""

from __future__ import annotations

__all__ = ["claude_cli"]
