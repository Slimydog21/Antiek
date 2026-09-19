"""Write ResearchArtifact HTML and emit artifact.generated."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from substrate.event_log import append_event_once
from substrate.schemas.events import ArtifactGeneratedPayload

from .authority import ArtifactAuthority
from .build_body import build_body
from .outbox import complete_event, mark_event_pending, stage_event
from .render import render_html
from .schema import ResearchArtifactBody
from .storage import FilesystemArtifactStore


@dataclass(frozen=True)
class ExportResult:
    investigation_id: str
    path: Path
    content_hash: str
    size_bytes: int
    event_id: str | None


def export_research_artifact(
    investigation_id: str,
    *,
    authority: ArtifactAuthority,
    db_path: str | None = None,
    events_dir: str | None = None,
    emit_event: bool = True,
    generating_role: str = "note_taker",
    source_coverage: object | None = None,
    inherited_reuse: object | None = None,
    terminal_provenance: object | None = None,
) -> ExportResult:
    if authority.investigation_id != investigation_id:
        raise ValueError("artifact authority investigation mismatch")
    body = build_body(investigation_id, authority=authority, db_path=db_path, events_dir=events_dir)
    if inherited_reuse is not None:
        from substrate.source_coverage import ArchivedSourceCoverageEnvelope

        if terminal_provenance is None:
            raise ValueError("artifact inherited reuse requires terminal provenance")
        envelope = ArchivedSourceCoverageEnvelope.model_validate(terminal_provenance)
        expected_inherited = (
            envelope.inherited_reuse.model_dump(mode="json")
            if envelope.inherited_reuse is not None else None
        )
        expected_coverage = (
            envelope.coverage.model_dump(mode="json")
            if envelope.coverage is not None else None
        )
        if inherited_reuse != expected_inherited or source_coverage != expected_coverage:
            raise ValueError("artifact channels conflict with terminal provenance")
    if source_coverage is not None:
        proposed = ResearchArtifactBody.model_validate(
            {**body.model_dump(mode="json"), "source_coverage": source_coverage}
        ).source_coverage
        if body.source_coverage is not None and body.source_coverage != proposed:
            raise ValueError("artifact source coverage conflicts with synthesis archive")
        raw_body = body.model_dump(mode="json")
        raw_body["source_coverage"] = proposed
        body = ResearchArtifactBody.model_validate(raw_body)
    if inherited_reuse is not None:
        proposed = ResearchArtifactBody.model_validate(
            {**body.model_dump(mode="json"), "inherited_reuse": inherited_reuse}
        ).inherited_reuse
        if body.inherited_reuse is not None and body.inherited_reuse != proposed:
            raise ValueError("artifact inherited reuse conflicts with synthesis archive")
        raw_body = body.model_dump(mode="json")
        raw_body["inherited_reuse"] = proposed
        body = ResearchArtifactBody.model_validate(raw_body)
    html_text = render_html(body)
    path = authority.artifact_path()
    raw = html_text.encode("utf-8")
    content_hash = body.content_hash()
    event_id: str | None = None
    if emit_event:
        artifact_id = "ra-" + hashlib.sha256(
            b"antiek.research-artifact.export.v2\x00"
            + authority.event_stream_id.encode("ascii")
            + b"\x00"
            + content_hash.encode("ascii")
        ).hexdigest()[:24]
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
        pending = stage_event(
            authority,
            event_key=artifact_id,
            payload=payload.model_dump(mode="json"),
            role=generating_role,
            expected_storage_hash=hashlib.sha256(raw).hexdigest(),
        )
        store = FilesystemArtifactStore()
        try:
            with store.mutation_lock(authority):
                path = store._write_locked(authority, html_text)
                event_id = append_event_once(pending.event, events_dir=events_dir)
        except Exception:
            mark_event_pending(authority)
            raise
        if event_id is None:
            mark_event_pending(authority)
        else:
            complete_event(authority, pending)
    else:
        path = FilesystemArtifactStore().write(authority, html_text)
    return ExportResult(
        investigation_id=investigation_id,
        path=path,
        content_hash=content_hash,
        size_bytes=len(raw),
        event_id=event_id,
    )


def build_html_only(
    investigation_id: str,
    *,
    authority: ArtifactAuthority,
    db_path: str | None = None,
    events_dir: str | None = None,
) -> tuple[ResearchArtifactBody, str]:
    body = build_body(investigation_id, authority=authority, db_path=db_path, events_dir=events_dir)
    return body, render_html(body)
