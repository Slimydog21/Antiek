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


_COMPOSE_ID = re.compile(r"^cmp-[0-9a-f]{24}$")


def compose_dir() -> Path:
    return research_artifacts_dir() / "composes"


def compose_draft_path(compose_id: str) -> Path:
    if not _COMPOSE_ID.fullmatch(compose_id):
        raise ValueError("invalid compose id")
    return compose_dir() / compose_id / "index.html"


def compose_manifest_path(compose_id: str) -> Path:
    if not _COMPOSE_ID.fullmatch(compose_id):
        raise ValueError("invalid compose id")
    return compose_dir() / compose_id / "manifest.json"


def compose_member_path(compose_id: str, member_index: int) -> Path:
    if not _COMPOSE_ID.fullmatch(compose_id):
        raise ValueError("invalid compose id")
    if member_index < 0 or member_index >= 32:
        raise ValueError("invalid compose member index")
    return compose_dir() / compose_id / "members" / f"{member_index}.html"
