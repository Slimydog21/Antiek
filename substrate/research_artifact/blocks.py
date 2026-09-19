"""Outline blocks for Write surface bridge (SPR-AHT-06)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .authority import ArtifactAuthority
from .build_body import build_body


@dataclass(frozen=True)
class OutlineBlockRef:
    node_id: str
    kind: str
    label: str
    investigation_id: str
    artifact_path: str | None


def list_outline_blocks(
    investigation_id: str,
    *,
    authority: ArtifactAuthority,
    db_path: str | None = None,
    events_dir: str | None = None,
    artifact_path: Path | None = None,
) -> list[OutlineBlockRef]:
    body = build_body(investigation_id, authority=authority, db_path=db_path, events_dir=events_dir)
    if authority.investigation_id != investigation_id:
        raise ValueError("artifact authority investigation mismatch")
    ap = str(artifact_path or authority.artifact_path())
    blocks: list[OutlineBlockRef] = []
    for ins in body.insights:
        blocks.append(
            OutlineBlockRef(
                node_id=ins.node_id,
                kind="insight",
                label=ins.text[:200],
                investigation_id=investigation_id,
                artifact_path=ap,
            )
        )
    for q in body.open_questions:
        blocks.append(
            OutlineBlockRef(
                node_id=q.node_id,
                kind="question",
                label=q.text[:200],
                investigation_id=investigation_id,
                artifact_path=ap,
            )
        )
    return blocks
