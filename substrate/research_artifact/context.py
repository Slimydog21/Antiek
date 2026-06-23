"""Load investigation question + synthesis excerpt from trajectory (read-only)."""

from __future__ import annotations

from substrate.event_log import trajectory
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
) -> tuple[str | None, bool, list[str]]:
    """Return (excerpt, withheld_flag, source_event_ids).

    withheld_flag is True when we only have a completion event but no body
    should be shown (caller treats like §9.0 guard — excerpt stays None).
    """
    source_ids: list[str] = []
    excerpt: str | None = None
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
        if at == ActionType.SYNTHESIS_ARCHIVED.value:
            payload = row.get("payload") or {}
            if isinstance(payload, dict) and not excerpt:
                excerpt = (payload.get("thesis_summary") or payload.get("summary") or "").strip() or None
    # De-dupe while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for x in source_ids:
        if x not in seen:
            seen.add(x)
            ordered.append(x)
    return excerpt, False, ordered[-20:]