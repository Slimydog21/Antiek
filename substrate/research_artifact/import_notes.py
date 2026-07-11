"""Import append-only agent notes from ResearchArtifact HTML (SPR-AHT-03 v0)."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from substrate.event_log import emit_typed, trajectory
from substrate.schemas.events import ActionType, ArtifactGeneratedPayload

from .schema import SCHEMA_VERSION, ResearchArtifactBody

_JSON_BLOCK_RE = re.compile(
    r'<script\s+type="application/json"\s+id="antiek-artifact-v1"\s*>([\s\S]*?)</script>',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ImportNotesResult:
    investigation_id: str
    notes_imported: int
    notes_skipped_duplicate: int
    event_ids: list[str]


def parse_body_from_html(html_text: str) -> ResearchArtifactBody:
    m = _JSON_BLOCK_RE.search(html_text)
    if not m:
        raise ValueError("missing #antiek-artifact-v1 JSON block")
    data = json.loads(m.group(1).strip())
    if type(data) is not dict:
        raise ValueError("#antiek-artifact-v1 must contain a JSON object")
    if data.get("schema_version") == 1:
        data = {**data, "schema_version": SCHEMA_VERSION, "claims": []}
    return ResearchArtifactBody.model_validate(data)


def parse_body_from_path(path: Path) -> ResearchArtifactBody:
    return parse_body_from_html(path.read_text(encoding="utf-8"))


def _note_intent(note_text: str, investigation_id: str) -> str:
    digest = hashlib.sha256(note_text.strip().encode("utf-8")).hexdigest()[:16]
    return f"research_artifact_agent_note_v1:{investigation_id}:{digest}"


def _existing_note_intents(investigation_id: str, *, events_dir: str | None) -> set[str]:
    seen: set[str] = set()
    for row in trajectory(investigation_id, events_dir=events_dir):
        if row.get("action_type") != ActionType.ARTIFACT_GENERATED.value:
            continue
        payload = row.get("payload") or {}
        intent = payload.get("intent") or ""
        if intent.startswith(f"research_artifact_agent_note_v1:{investigation_id}:"):
            seen.add(intent)
    return seen


def import_agent_notes(
    html_path: Path,
    *,
    investigation_id: str | None = None,
    events_dir: str | None = None,
    generating_role: str = "note_taker",
) -> ImportNotesResult:
    """Emit artifact.generated per new agent note. Does not mutate graph insights."""
    body = parse_body_from_path(html_path)
    iid = investigation_id or body.investigation_id
    if body.investigation_id != iid:
        raise ValueError(
            f"investigation_id mismatch: file={body.investigation_id} arg={iid}"
        )
    if body.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version {body.schema_version}")

    existing = _existing_note_intents(iid, events_dir=events_dir)
    imported = 0
    skipped = 0
    event_ids: list[str] = []

    for note in body.agent_notes:
        text = (note or "").strip()
        if not text:
            continue
        intent = _note_intent(text, iid)
        if intent in existing:
            skipped += 1
            continue
        artifact_id = f"ran-{uuid.uuid4().hex[:12]}"
        payload = ArtifactGeneratedPayload(
            artifact_id=artifact_id,
            artifact_kind="other",
            intent=intent,
            generating_role=generating_role,
            artifact_path=str(html_path),
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            size_bytes=len(text.encode("utf-8")),
            source_event_ids=body.source_event_ids or [iid],
        )
        # ``emit_typed`` returns None when events are disabled — guard so
        # ``event_ids`` stays ``list[str]`` (same convention as
        # substrate/books/voice_note.py).
        eid = emit_typed(iid, payload, role=generating_role, events_dir=events_dir)
        if eid is not None:
            event_ids.append(eid)
        existing.add(intent)
        imported += 1

    return ImportNotesResult(
        investigation_id=iid,
        notes_imported=imported,
        notes_skipped_duplicate=skipped,
        event_ids=event_ids,
    )


def load_persisted_agent_notes(
    investigation_id: str,
    *,
    artifact_path: Path | None = None,
) -> list[str]:
    """Carry forward agent_notes from on-disk artifact when re-exporting."""
    from .paths import artifact_path_for

    path = artifact_path or artifact_path_for(investigation_id)
    if not path.is_file():
        return []
    try:
        body = parse_body_from_path(path)
    except (ValueError, json.JSONDecodeError):
        return []
    if body.investigation_id != investigation_id:
        return []
    return list(body.agent_notes)
