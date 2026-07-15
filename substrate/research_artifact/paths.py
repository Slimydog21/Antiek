"""Filesystem layout for research artifact HTML (gitignored operator store)."""

from __future__ import annotations

import os
import re
from pathlib import Path


def research_artifacts_dir() -> Path:
    raw = os.environ.get("ANTIEK_RESEARCH_ARTIFACTS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".antiek" / "research-artifacts"


def snapshot_dir() -> Path:
    return research_artifacts_dir() / "snapshots"


def artifact_path_for(investigation_id: str) -> Path:
    safe = investigation_id.replace("/", "_")
    return research_artifacts_dir() / f"{safe}.html"


def compose_path_for(*investigation_ids: str) -> Path:
    joined = "-".join(i.replace("/", "_") for i in investigation_ids[:8])
    if len(investigation_ids) > 8:
        joined += f"-and{len(investigation_ids) - 8}-more"
    return research_artifacts_dir() / f"compose-{joined}.html"


def composition_path_for(composition_id: str) -> Path:
    if not re.fullmatch(r"cmp-[0-9a-f]{64}", composition_id):
        raise ValueError("invalid composition ID")
    return research_artifacts_dir() / "compositions" / f"{composition_id}.html"


def composition_member_path_for(composition_id: str, investigation_id: str) -> Path:
    if not re.fullmatch(r"cmp-[0-9a-f]{64}", composition_id):
        raise ValueError("invalid composition ID")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", investigation_id):
        raise ValueError("invalid investigation ID")
    return research_artifacts_dir() / "compositions" / composition_id / f"{investigation_id}.html"
