"""Outline blocks for Write surface bridge (SPR-AHT-06)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .build_body import build_body
from .paths import artifact_path_for


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
    db_path: str | None = None,
    events_dir: str | None = None,
    artifact_path: Path | None = None,
) -> list[OutlineBlockRef]:
    body = build_body(
        investigation_id, db_path=db_path, events_dir=events_dir
    )
    ap = str(artifact_path or artifact_path_for(investigation_id))
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