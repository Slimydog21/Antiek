"""Write ResearchArtifact HTML and emit artifact.generated."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from substrate.event_log import emit_typed
from substrate.schemas.events import ArtifactGeneratedPayload

from .build_body import build_body
from .paths import artifact_path_for, research_artifacts_dir
from .render import render_html
from .schema import ResearchArtifactBody
from .twin_notes import write_twin_notes


@dataclass(frozen=True)
class ExportResult:
    investigation_id: str
    path: Path
    twin_notes_path: Path
    content_hash: str
    size_bytes: int
    event_id: str | None


def export_research_artifact(
    investigation_id: str,
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
    emit_event: bool = True,
    generating_role: str = "note_taker",
) -> ExportResult:
    body = build_body(
        investigation_id, db_path=db_path, events_dir=events_dir
    )
    html_text = render_html(body)
    out_dir = research_artifacts_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_path_for(investigation_id)
    path.write_text(html_text, encoding="utf-8")
    twin_notes_path = write_twin_notes(body, artifact_path=path)
    raw = html_text.encode("utf-8")
    content_hash = body.content_hash()
    event_id: str | None = None
    if emit_event:
        artifact_id = f"ra-{uuid.uuid4().hex[:12]}"
        payload = ArtifactGeneratedPayload(
            artifact_id=artifact_id,
            artifact_kind="other",
            intent=f"research_artifact_v1:{investigation_id}",
            generating_role=generating_role,
            artifact_path=str(path),
            content_hash=content_hash,
            size_bytes=len(raw),
            source_event_ids=body.source_event_ids or [investigation_id],
        )
        event_id = emit_typed(
            investigation_id,
            payload,
            role=generating_role,
            events_dir=events_dir,
        )
    return ExportResult(
        investigation_id=investigation_id,
        path=path,
        twin_notes_path=twin_notes_path,
        content_hash=content_hash,
        size_bytes=len(raw),
        event_id=event_id,
    )


def build_html_only(
    investigation_id: str,
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
) -> tuple[ResearchArtifactBody, str]:
    body = build_body(
        investigation_id, db_path=db_path, events_dir=events_dir
    )
    return body, render_html(body)
