"""Import append-only agent notes; durable typed events authorize re-export."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from substrate.event_log import emit_typed, trajectory
from substrate.schemas.events import ActionType, ArtifactGeneratedPayload

from . import note_store as notes
from .schema import SCHEMA_VERSION, ResearchArtifactBody

# Four rendered/machine copies can each escape one byte to six characters.
# Reserve additional space for markup and non-note research content.
_MAX_HTML_BYTES = 10 * 1024 * 1024
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
    if len(html_text.encode("utf-8")) > _MAX_HTML_BYTES:
        raise ValueError("artifact HTML exceeds its byte bound")
    m = _JSON_BLOCK_RE.search(html_text)
    if not m:
        raise ValueError("missing #antiek-artifact-v1 JSON block")
    data = json.loads(m.group(1).strip())
    # Body-version migration belongs here, independently of the durable note format.
    return ResearchArtifactBody.model_validate(data)


def parse_body_from_path(path: Path) -> ResearchArtifactBody:
    # Caller-selected HTML can be outside artifact storage. Never use an event's
    # path here; durable note loading only opens storage-derived paths.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_HTML_BYTES:
            raise ValueError("artifact HTML must be a bounded regular file")
        data = bytearray()
        while len(data) <= _MAX_HTML_BYTES:
            chunk = os.read(fd, min(65536, _MAX_HTML_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > _MAX_HTML_BYTES:
            raise ValueError("artifact HTML exceeds its byte bound")
        return parse_body_from_html(data.decode("utf-8"))
    finally:
        os.close(fd)


def _persisted_notes(
    investigation_id: str, *, events_dir: str | None, require_legacy_migrated: bool = True,
) -> dict[str, str]:
    notes.validate_investigation_id(investigation_id)
    accepted: dict[str, str] = {}
    total_bytes = 0
    legacy_hashes: set[str] = set()
    for row in trajectory(investigation_id, events_dir=events_dir):
        if row.get("action_type") != ActionType.ARTIFACT_GENERATED.value:
            continue
        raw = row.get("payload")
        if not isinstance(raw, dict):
            continue
        intent = raw.get("intent")
        if not isinstance(intent, str):
            continue
        if intent.startswith("research_artifact_agent_note_v1:"):
            if require_legacy_migrated:
                legacy = ArtifactGeneratedPayload.model_validate(raw)
                digest = legacy.content_hash
                if (not re.fullmatch(r"[0-9a-f]{64}", digest)
                        or legacy.intent != f"research_artifact_agent_note_v1:{investigation_id}:{digest[:16]}"
                        or row.get("investigation_id") != investigation_id
                        or legacy.artifact_kind != "other"):
                    raise notes.NotePersistenceError("legacy accepted note event is corrupt")
                legacy_hashes.add(digest)
            continue
        if not intent.startswith(notes.NOTE_INTENT_PREFIX):
            continue
        try:
            payload = ArtifactGeneratedPayload.model_validate(raw)
            digest = payload.content_hash
            if (row.get("investigation_id") != investigation_id
                    or payload.intent != notes.note_intent(investigation_id, digest)
                    or payload.artifact_id != notes.note_artifact_id(investigation_id, digest)
                    or row.get("event_id") != notes.note_event_id(investigation_id, digest)
                    or payload.artifact_kind != "other"):
                raise notes.NotePersistenceError("accepted note event identity does not match")
            # artifact_path is descriptive metadata, never read authority.
            text = notes.read_note(investigation_id, digest, payload.size_bytes)
        except (ValueError, OSError) as exc:
            raise notes.NotePersistenceError("accepted note event or object is missing or corrupt") from exc
        if digest not in accepted:
            accepted[digest] = text
            total_bytes += payload.size_bytes
            if len(accepted) > notes.MAX_PERSISTED_NOTES or total_bytes > notes.MAX_PERSISTED_BYTES:
                raise notes.NotePersistenceError("accepted notes exceed their aggregate bound")
    if legacy_hashes.difference(accepted):
        raise notes.NotePersistenceError("legacy accepted notes require explicit reimport before export")
    return accepted


def import_agent_notes(
    html_path: Path,
    *,
    investigation_id: str | None = None,
    events_dir: str | None = None,
    generating_role: str = "note_taker",
) -> ImportNotesResult:
    """Commit notes independently; failed batches retain earlier committed notes.

    Legacy HTML requires explicit import, even if an old v1 note event exists.
    Unreferenced objects left by failed/disabled event writes are not accepted.
    """
    body = parse_body_from_path(html_path)
    iid = investigation_id if investigation_id is not None else body.investigation_id
    notes.validate_investigation_id(iid)
    if body.investigation_id != iid:
        raise ValueError("investigation_id mismatch")
    if body.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version {body.schema_version}")
    if len(body.agent_notes) > notes.MAX_PERSISTED_NOTES + notes.MAX_BATCH_NOTES:
        raise ValueError("too many agent notes in one artifact")
    batch = [note.strip() for note in body.agent_notes if note.strip()]
    sizes = [len(text.encode("utf-8")) for text in batch]
    if (any(size > notes.MAX_NOTE_BYTES for size in sizes)
            or sum(sizes) > notes.MAX_PERSISTED_BYTES + notes.MAX_BATCH_BYTES):
        raise ValueError("agent notes exceed artifact byte bounds")

    imported = 0
    skipped = 0
    event_ids: list[str] = []
    with notes.note_import_lock(iid):
        accepted = _persisted_notes(iid, events_dir=events_dir, require_legacy_migrated=False)
        proposed = {hashlib.sha256(text.encode("utf-8")).hexdigest(): text for text in batch}
        new = {digest: text for digest, text in proposed.items() if digest not in accepted}
        if (len(new) > notes.MAX_BATCH_NOTES
                or sum(len(text.encode("utf-8")) for text in new.values()) > notes.MAX_BATCH_BYTES):
            raise ValueError("new agent notes exceed import bounds")
        combined = {**accepted, **new}
        if (len(combined) > notes.MAX_PERSISTED_NOTES
                or sum(len(text.encode("utf-8")) for text in combined.values()) > notes.MAX_PERSISTED_BYTES):
            raise ValueError("agent notes exceed persisted aggregate bounds")
        for text in batch:
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest in accepted:
                skipped += 1
                continue
            digest, path, size = notes.publish_note(iid, text)
            payload = ArtifactGeneratedPayload(
                artifact_id=notes.note_artifact_id(iid, digest),
                artifact_kind="other",
                intent=notes.note_intent(iid, digest),
                generating_role=generating_role,
                artifact_path=str(path),
                content_hash=digest,
                size_bytes=size,
                source_event_ids=body.source_event_ids or [iid],
            )
            eid = emit_typed(
                iid, payload, role=generating_role, events_dir=events_dir,
                strict_write=True, idempotent=True, event_id=notes.note_event_id(iid, digest),
            )
            if eid is None:
                raise notes.NotePersistenceError("note import requires enabled durable events")
            accepted[digest] = text
            event_ids.append(eid)
            imported += 1
    return ImportNotesResult(iid, imported, skipped, event_ids)


def load_persisted_agent_notes(
    investigation_id: str,
    *,
    events_dir: str | None = None,
    artifact_path: Path | None = None,
) -> list[str]:
    """Load only event-accepted immutable notes; never infer acceptance from HTML."""
    if artifact_path is not None:
        raise ValueError("legacy artifact notes require explicit import_agent_notes")
    return list(_persisted_notes(investigation_id, events_dir=events_dir).values())
