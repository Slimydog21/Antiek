"""Load investigation question + synthesis excerpt from trajectory (read-only)."""

from __future__ import annotations

from substrate.event_log import trajectory, trajectory_authorized
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas.events import ActionType


def problem_question_from_events(
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> str:
    for row in trajectory(investigation_id, events_dir=events_dir):
        if row.get("action_type") != ActionType.INVESTIGATION_START_REQUESTED.value:
            continue
        payload = row.get("payload") or {}
        if isinstance(payload, dict):
            q = (payload.get("question") or "").strip()
            if q:
                return q
    return ""


def synthesis_from_events(
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> tuple[str | None, bool, list[str], str | None]:
    """Return (excerpt, withheld_flag, source_event_ids).

    withheld_flag is True when we only have a completion event but no body
    should be shown (caller treats like §9.0 guard — excerpt stays None).
    """
    source_ids: list[str] = []
    excerpt: str | None = None
    synthesis_event_id: str | None = None
    for row in trajectory(investigation_id, events_dir=events_dir):
        at = row.get("action_type")
        eid = row.get("event_id")
        if eid:
            source_ids.append(str(eid))
        if at == ActionType.INVESTIGATION_COMPLETED.value:
            payload = row.get("payload") or {}
            if isinstance(payload, dict):
                summary = (payload.get("thesis_summary") or "").strip()
                if summary:
                    excerpt = summary
        if at == ActionType.SYNTHESIZE_DELIVERED.value and eid:
            synthesis_event_id = str(eid)
        if at == ActionType.SYNTHESIS_ARCHIVED.value:
            payload = row.get("payload") or {}
            if isinstance(payload, dict) and not excerpt:
                excerpt = (
                    payload.get("thesis_summary") or payload.get("summary") or ""
                ).strip() or None
    # De-dupe while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for x in source_ids:
        if x not in seen:
            seen.add(x)
            ordered.append(x)
    return excerpt, False, ordered[-20:], synthesis_event_id


def problem_question_from_events_authorized(
    authority: InvestigationAuthority,
) -> str:
    """Project the start question from one exact account-scoped stream."""
    for row in trajectory_authorized(authority):
        if row.get("action_type") != ActionType.INVESTIGATION_START_REQUESTED.value:
            continue
        payload = row.get("payload") or {}
        if isinstance(payload, dict):
            question = (payload.get("question") or "").strip()
            if question:
                return question
    return ""


def synthesis_from_events_authorized(
    authority: InvestigationAuthority,
) -> tuple[str | None, bool, list[str], str | None]:
    """Return synthesis projection from one exact account-scoped stream."""
    source_ids: list[str] = []
    excerpt: str | None = None
    rows = trajectory_authorized(authority)
    for row in rows:
        action_type = row.get("action_type")
        event_id = row.get("event_id")
        if event_id:
            source_ids.append(str(event_id))
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if action_type == ActionType.INVESTIGATION_COMPLETED.value:
            summary = (payload.get("thesis_summary") or "").strip()
            if summary:
                excerpt = summary
        elif action_type == ActionType.SYNTHESIS_ARCHIVED.value and not excerpt:
            excerpt = (
                payload.get("thesis_summary") or payload.get("summary") or ""
            ).strip() or None
    from middleware.archive import authorized_synthesis_id

    terminal_synthesis_id = authorized_synthesis_id(authority, "terminal")
    archive_rows = [
        row
        for row in rows
        if row.get("action_type") == ActionType.SYNTHESIS_ARCHIVED.value
        and row.get("synthesis_id") == terminal_synthesis_id
    ]
    synthesis_event_id: str | None = None
    if len(archive_rows) == 1:
        candidate = archive_rows[0].get("parent_event_id")
        if isinstance(candidate, str) and any(
            row.get("event_id") == candidate
            and row.get("action_type") == ActionType.SYNTHESIZE_DELIVERED.value
            for row in rows
        ):
            synthesis_event_id = candidate
    return excerpt, False, list(dict.fromkeys(source_ids))[-20:], synthesis_event_id
