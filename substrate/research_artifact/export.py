"""Write ResearchArtifact HTML and emit artifact.generated."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from services.html_projection.island import embed_island
from substrate.event_log import emit_typed
from substrate.schemas.events import ArtifactGeneratedPayload

from .build_body import build_body
from .paths import artifact_source_path_for, research_artifacts_dir
from .render import render_html
from .schema import ResearchArtifactBody
from .store import ResearchArtifactStore


@dataclass(frozen=True)
class ExportResult:
    artifact_id: str
    investigation_id: str
    path: Path
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
    owner_user_id: str = "__operator__",
) -> ExportResult:
    body = build_body(investigation_id, db_path=db_path, events_dir=events_dir)
    artifact_id = investigation_id
    # The legacy ResearchArtifact remains the human/editable source channel.
    # Add the projection engine's canonical, inert island so the same stored
    # artifact can be deterministically re-rendered without scraping HTML.
    projection_model = _projection_model(body)
    html_text = render_html(body).replace(
        "</body>", f"{embed_island(projection_model)}\n</body>", 1
    )
    out_dir = research_artifacts_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = html_text.encode("utf-8")
    path = artifact_source_path_for(artifact_id, hashlib.sha256(raw).hexdigest())
    if db_path is not None:
        ResearchArtifactStore(db_path).save_source(
            artifact_id, investigation_id, owner_user_id, path, raw
        )
    else:
        from .paths import atomic_write_nofollow

        atomic_write_nofollow(path, raw)
    content_hash = body.content_hash()
    event_id: str | None = None
    if emit_event:
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
        artifact_id=artifact_id,
        investigation_id=investigation_id,
        path=path,
        content_hash=content_hash,
        size_bytes=len(raw),
        event_id=event_id,
    )


def _projection_model(body: ResearchArtifactBody) -> dict[str, object]:
    """Lossless-enough presentation model plus explicit source provenance."""
    content: list[dict[str, object]] = []

    def heading(text: str, level: int = 2) -> None:
        content.append(
            {
                "type": "heading",
                "attrs": {"level": level},
                "content": [{"type": "text", "text": text}],
            }
        )

    def paragraph(text: str) -> None:
        content.append({"type": "paragraph", "content": [{"type": "text", "text": text}]})

    heading("Findings")
    for insight in body.insights:
        paragraph(insight.text)
    heading("Open gaps")
    for question in body.open_questions:
        paragraph(question.text)
    heading("Synthesis excerpt")
    paragraph(body.synthesis_excerpt or "Synthesis not available.")
    if body.agent_notes:
        heading("Agent notes")
        for note in body.agent_notes:
            paragraph(note)
    return {
        "title": body.problem_question,
        "content": content,
        "research_artifact": body.model_dump(mode="json"),
    }


def build_html_only(
    investigation_id: str,
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
) -> tuple[ResearchArtifactBody, str]:
    body = build_body(investigation_id, db_path=db_path, events_dir=events_dir)
    return body, render_html(body)
