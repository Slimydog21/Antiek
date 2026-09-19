"""Filesystem layout for research artifact HTML (gitignored operator store)."""

from __future__ import annotations

import os
from pathlib import Path


def research_artifacts_dir() -> Path:
    raw = os.environ.get("ANTIEK_RESEARCH_ARTIFACTS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".antiek" / "research-artifacts"


def snapshot_dir() -> Path:
    return research_artifacts_dir() / "snapshots"
