"""Account-scoped, reference-only workspace resume checkpoint."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from substrate.event_log.events import (
    IdempotencyConflict,
    _append_jsonl_authorized_unlocked,
    _authorized_event_lock,
    _read_opened_event_rows,
    _validate_authorized_rows,
    prepare_typed_event,
    require_event_persistence,
)
from substrate.investigation_streams import (
    InvestigationStreamUnbound,
    composite_stream_is_allocated,
    initialize_composite_stream,
    open_investigation_stream,
    resolve_investigation_stream,
)
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas.events import (
    ActionType,
    Event,
    WorkspaceResumeCheckpointSetPayload,
    WorkspaceResumeEntry,
)

CONTROL_STREAM_ID = "antiek:account-workspace-resume:v1"


class WorkspaceRevisionConflict(ValueError):
    pass


@dataclass(frozen=True)
class WorkspaceCheckpoint:
    revision: int
    entries: tuple[WorkspaceResumeEntry, ...]
    event_id: str | None = None


def account_workspace_authority(account_id: str) -> InvestigationAuthority:
    """The caller supplies only validated claims; no HTTP field can select this."""
    return InvestigationAuthority(account_id, CONTROL_STREAM_ID)


def _checkpoint_events(rows: list[dict[str, object]]) -> list[Event]:
    result: list[Event] = []
    for row in rows:
        if row.get("action_type") != ActionType.WORKSPACE_RESUME_CHECKPOINT_SET.value:
            continue
        event = Event.model_validate(row)
        if not isinstance(event.payload, WorkspaceResumeCheckpointSetPayload):
            raise ValueError("workspace checkpoint payload is malformed")
        result.append(event)
    return result


def _latest(events: list[Event]) -> WorkspaceCheckpoint:
    if not events:
        return WorkspaceCheckpoint(0, ())
    event = events[-1]
    payload = event.payload
    if not isinstance(payload, WorkspaceResumeCheckpointSetPayload):
        raise ValueError("workspace checkpoint payload is malformed")
    expected = 1
    for candidate in events:
        candidate_payload = candidate.payload
        if not isinstance(candidate_payload, WorkspaceResumeCheckpointSetPayload):
            raise ValueError("workspace checkpoint payload is malformed")
        if candidate_payload.revision != expected:
            raise ValueError("workspace checkpoint revisions are malformed")
        expected += 1
    return WorkspaceCheckpoint(payload.revision, payload.entries, event.event_id)


def read_workspace_checkpoint(authority: InvestigationAuthority) -> WorkspaceCheckpoint:
    require_event_persistence()
    if not composite_stream_is_allocated(authority):
        return WorkspaceCheckpoint(0, ())
    try:
        resolve_investigation_stream(authority)
    except InvestigationStreamUnbound:
        return WorkspaceCheckpoint(0, ())
    with (
        open_investigation_stream(authority, writable=False) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        return _latest(_checkpoint_events(rows))


def append_workspace_checkpoint(
    authority: InvestigationAuthority,
    *,
    base_revision: int,
    entries: tuple[WorkspaceResumeEntry, ...],
    mutation_key: str,
) -> WorkspaceCheckpoint:
    require_event_persistence()
    initialize_composite_stream(authority)
    canonical = {
        "schema_version": 1,
        "base_revision": base_revision,
        "entries": [entry.model_dump(mode="json", exclude_none=True) for entry in entries],
        "mutation_key": mutation_key,
    }
    request_sha256 = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    mutation_key_sha256 = hashlib.sha256(mutation_key.encode()).hexdigest()
    with (
        open_investigation_stream(authority, writable=True) as stream,
        _authorized_event_lock(stream),
    ):
        rows = _validate_authorized_rows(
            authority, _read_opened_event_rows(stream, reject_malformed=True)
        )
        events = _checkpoint_events(rows)
        for event in events:
            payload = event.payload
            if not isinstance(payload, WorkspaceResumeCheckpointSetPayload):
                raise ValueError("workspace checkpoint payload is malformed")
            if payload.mutation_key_sha256 != mutation_key_sha256:
                continue
            if payload.request_sha256 != request_sha256:
                raise IdempotencyConflict("mutation key was used for another request")
            return WorkspaceCheckpoint(payload.revision, payload.entries, event.event_id)
        current = _latest(events)
        if base_revision != current.revision:
            raise WorkspaceRevisionConflict("workspace checkpoint revision is stale")
        payload = WorkspaceResumeCheckpointSetPayload(
            revision=current.revision + 1,
            base_revision=base_revision,
            entries=entries,
            mutation_key_sha256=mutation_key_sha256,
            request_sha256=request_sha256,
        )
        event = prepare_typed_event(authority.investigation_id, payload)
        _append_jsonl_authorized_unlocked(stream, event.model_dump(mode="json"))
        return WorkspaceCheckpoint(payload.revision, entries, event.event_id)
