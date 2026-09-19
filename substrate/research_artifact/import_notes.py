"""Import append-only agent notes from ResearchArtifact HTML (SPR-AHT-03 v0)."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from substrate.event_log import append_event_once, trajectory
from substrate.schemas.events import ActionType, ArtifactGeneratedPayload

from .authority import ArtifactAuthority
from .outbox import complete_event, mark_event_pending, stage_event
from .schema import SCHEMA_VERSION, ResearchArtifactBody
from .storage import FilesystemArtifactStore

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
    return ResearchArtifactBody.model_validate(data)


def parse_body_from_path(path: Path) -> ResearchArtifactBody:
    return parse_body_from_html(path.read_text(encoding="utf-8"))


def _note_intent(note_text: str, investigation_id: str) -> str:
    digest = hashlib.sha256(note_text.strip().encode("utf-8")).hexdigest()[:16]
    return f"research_artifact_agent_note_v1:{investigation_id}:{digest}"


def _existing_note_intents(
    stream_id: str, investigation_id: str, *, events_dir: str | None
) -> set[str]:
    seen: set[str] = set()
    for row in trajectory(stream_id, events_dir=events_dir):
        if row.get("action_type") != ActionType.ARTIFACT_GENERATED.value:
            continue
        payload = row.get("payload") or {}
        intent = payload.get("intent") or ""
        if intent.startswith(f"research_artifact_agent_note_v1:{investigation_id}:"):
            seen.add(intent)
    return seen


def import_agent_notes_html(
    html_text: str,
    *,
    authority: ArtifactAuthority,
    artifact_path: Path | None = None,
    events_dir: str | None = None,
    generating_role: str = "note_taker",
    before_emit: Callable[[], None] | None = None,
) -> ImportNotesResult:
    """Emit artifact.generated per new agent note. Does not mutate graph insights."""
    body = parse_body_from_html(html_text)
    iid = authority.investigation_id
    if body.investigation_id != iid:
        raise ValueError(f"investigation_id mismatch: file={body.investigation_id} arg={iid}")
    if body.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version {body.schema_version}")

    stream_id = authority.event_stream_id
    existing = _existing_note_intents(stream_id, iid, events_dir=events_dir)
    imported = 0
    skipped = 0
    event_ids: list[str] = []
    candidates: list[tuple[str, str, ArtifactGeneratedPayload]] = []

    for note in body.agent_notes:
        text = (note or "").strip()
        if not text:
            continue
        intent = _note_intent(text, iid)
        if intent in existing:
            skipped += 1
            continue
        # The intent is the logical operation identity. Deriving the event key
        # from it makes concurrent requests and crash retries converge on the
        # same append-once envelope instead of minting duplicate events.
        artifact_id = f"ran-{hashlib.sha256(intent.encode()).hexdigest()[:24]}"
        payload = ArtifactGeneratedPayload(
            artifact_id=artifact_id,
            artifact_kind="other",
            intent=intent,
            generating_role=generating_role,
            artifact_path=str(artifact_path or authority.artifact_path()),
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            size_bytes=len(text.encode("utf-8")),
            source_event_ids=body.source_event_ids or [iid],
        )
        candidates.append((intent, artifact_id, payload))
        existing.add(intent)
        imported += 1

    staged = [
        (
            payload,
            stage_event(
                authority,
                event_key=artifact_id,
                payload=payload.model_dump(mode="json"),
                role=generating_role,
            ),
        )
        for _intent, artifact_id, payload in candidates
    ]
    if before_emit is not None:
        try:
            before_emit()
        except Exception:
            for _payload, _pending in staged:
                mark_event_pending(authority)
            raise

    for index, (_payload, pending) in enumerate(staged):
        try:
            eid = append_event_once(pending.event, events_dir=events_dir)
        except Exception:
            for _payload, _pending in staged[index:]:
                mark_event_pending(authority)
            raise
        if eid is not None:
            event_ids.append(eid)
            complete_event(authority, pending)
        else:
            mark_event_pending(authority)

    return ImportNotesResult(
        investigation_id=iid,
        notes_imported=imported,
        notes_skipped_duplicate=skipped,
        event_ids=event_ids,
    )


def import_agent_notes(
    html_path: Path,
    *,
    authority: ArtifactAuthority,
    events_dir: str | None = None,
    generating_role: str = "note_taker",
) -> ImportNotesResult:
    """Trusted local adapter; HTTP callers must pass store-validated HTML directly."""
    canonical = authority.artifact_path().resolve()
    if html_path.resolve() != canonical:
        raise ValueError("artifact path does not match authority")
    return import_agent_notes_html(
        FilesystemArtifactStore().read(authority),
        authority=authority,
        artifact_path=canonical,
        events_dir=events_dir,
        generating_role=generating_role,
    )


def load_persisted_agent_notes(
    investigation_id: str,
    *,
    authority: ArtifactAuthority,
) -> list[str]:
    """Carry forward agent_notes from on-disk artifact when re-exporting."""
    if authority.investigation_id != investigation_id:
        raise ValueError("artifact authority investigation mismatch")
    artifact_path = authority.artifact_path()
    sidecar_path = authority.sidecar_path()
    artifact_exists = artifact_path.exists() or artifact_path.is_symlink()
    sidecar_exists = sidecar_path.exists() or sidecar_path.is_symlink()
    if not artifact_exists and not sidecar_exists:
        return []
    try:
        html_text = FilesystemArtifactStore().read(authority)
        body = parse_body_from_html(html_text)
    # fmt: off -- project supports Python 3.11+; py314 exception syntax is invalid there.
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        # fmt: on
        return []
    if body.investigation_id != investigation_id:
        return []
    return list(body.agent_notes)
