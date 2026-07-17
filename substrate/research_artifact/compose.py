"""Compose multiple investigations into one HTML index (view-layer merge)."""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from pathlib import Path

from .export import export_research_artifact
from .paths import compose_path_for


@dataclass(frozen=True)
class ComposeMember:
    investigation_id: str
    content_hash: str
    artifact_path: Path


@dataclass(frozen=True)
class ComposeResult:
    path: Path
    members: list[ComposeMember]
    hash_conflicts: list[tuple[str, str]]
    composition_id: str
    composition_version: int = 1


def composition_identity(members: list[ComposeMember]) -> str:
    """Bind a draft basis to exact ordered artifact versions."""
    payload = {
        "contract": "research-composition-draft-basis-v1",
        "members": [
            {
                "investigation_id": member.investigation_id,
                "content_hash": member.content_hash,
            }
            for member in members
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compose_artifacts(
    investigation_ids: list[str],
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
    write_index: bool = True,
) -> ComposeResult:
    members: list[ComposeMember] = []
    by_hash: dict[str, str] = {}
    conflicts: list[tuple[str, str]] = []
    for iid in investigation_ids:
        res = export_research_artifact(
            iid,
            db_path=db_path,
            events_dir=events_dir,
            emit_event=False,
        )
        m = ComposeMember(
            investigation_id=iid,
            content_hash=res.content_hash,
            artifact_path=res.path,
        )
        members.append(m)
        prev = by_hash.get(res.content_hash)
        if prev and prev != iid:
            conflicts.append((prev, iid))
        else:
            by_hash[res.content_hash] = iid

    out_path = compose_path_for(*investigation_ids)
    if write_index:
        rows = ""
        for m in members:
            rows += (
                f"<li><a href=\"file://{html.escape(str(m.artifact_path))}\">"
                f"{html.escape(m.investigation_id)}</a> "
                f"<code>{html.escape(m.content_hash[:12])}</code></li>"
            )
        conflict_block = ""
        if conflicts:
            conflict_block = (
                "<section><h2>Hash collisions (review)</h2><ul>"
                + "".join(
                    f"<li>{html.escape(a)} vs {html.escape(b)}</li>"
                    for a, b in conflicts
                )
                + "</ul></section>"
            )
        index = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Compose — {len(members)} artifacts</title></head><body>
<h1>Composed research artifacts</h1>
<ul>{rows}</ul>{conflict_block}
</body></html>"""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(index, encoding="utf-8")

    return ComposeResult(
        path=out_path,
        members=members,
        hash_conflicts=conflicts,
        composition_id=composition_identity(members),
    )
