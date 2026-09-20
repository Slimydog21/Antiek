"""Owner projections of events shared with internal agent handlers."""
from __future__ import annotations

from typing import Any

from substrate.schemas import ActionType

# Evidence requests are agent inputs, not owner-readable source material.
# Use an allowlist so adding another agent context field cannot expose it.
_OWNER_EVIDENCE_REQUEST_FIELDS = frozenset({
    "action_type", "sub_question", "category", "evidence_type_required",
    "top_k", "owner_semantic_call_id",
})


def owner_event_projection(row: dict[str, Any]) -> dict[str, Any]:
    """Keep event identity and progress while withholding agent source context.

    Does not mutate the durable event or the object delivered to agent handlers.
    Old events receive the same policy as new ones, without relying on metadata
    written by their producer. Derived evidence-delivery events remain visible.
    """
    payload = row.get("payload")
    requested = ActionType.EVIDENCE_RETRIEVE_REQUESTED.value
    if row.get("action_type") != requested and (
        not isinstance(payload, dict) or payload.get("action_type") != requested
    ):
        return row
    if not isinstance(payload, dict):
        payload = {}
    return {
        **row,
        "payload": {
            **{key: value for key, value in payload.items() if key in _OWNER_EVIDENCE_REQUEST_FIELDS},
            "chunks_block": "",
            "subgraph_block": "",
        },
    }
