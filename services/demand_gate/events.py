"""Demand-gate telemetry event contract (HPRJ SPR-08 M3).

The four measurement events — export-offered, export-taken (which format),
share-link-taken, re-import-detected — plus the two third-party/agent signal
types. These ride the existing typed-event discipline (an ``action_type`` + a
flat payload, the shape the analysis in `analysis.py` and the round-trip
detector already consume); there is no separate ``substrate/behavior/`` package
on this branch, so this module IS the demand-gate slice of the taxonomy.

PRIVACY GATE (the load-bearing part — a measurement sprint that smuggled in an
ungated content-bearing event would be an ironic privacy regression): a
demand-gate event may carry ONLY counts, format choices, ids, and hashes —
NEVER artifact content. `assert_no_content` enforces this mechanically: it
rejects any forbidden content key and any field outside the allowlist. Build
events through the builders here so the gate is unbypassable.
"""

from __future__ import annotations

from typing import Optional

# The four measurement events + the round-trip detector's event + the two
# admissible third-party/agent signals the analysis counts.
EXPORT_OFFERED = "demand_gate.export_offered"
EXPORT_TAKEN = "demand_gate.export_taken"
SHARE_LINK_TAKEN = "demand_gate.share_link_taken"
RE_IMPORT_DETECTED = "demand_gate.roundtrip_detected"  # the detector's event type
THIRD_PARTY_READER = "demand_gate.third_party_reader"
AGENT_UNPROMPTED = "demand_gate.agent_unprompted_adoption"

DEMAND_GATE_EVENT_TYPES = frozenset(
    {
        EXPORT_OFFERED,
        EXPORT_TAKEN,
        SHARE_LINK_TAKEN,
        RE_IMPORT_DETECTED,
        THIRD_PARTY_READER,
        AGENT_UNPROMPTED,
    }
)

# The ONLY fields a demand-gate event may carry. Counts/choices/ids/hashes only.
_ALLOWED_FIELDS = frozenset(
    {
        "action_type",
        "user_id",
        "surface",
        "format",
        "formats",
        "document_id",
        "classification",
        "content_hash",
        "tool",
        "agent",
    }
)

# Content keys that MUST NEVER appear on a demand-gate event (the privacy line).
_FORBIDDEN_CONTENT_FIELDS = frozenset(
    {"text", "body", "content", "content_tiptap", "passage", "statement",
     "html", "quote", "title", "label", "value"}
)


def assert_no_content(event: dict) -> None:
    """Privacy gate: a demand-gate event carries only counts/choices/ids/hashes
    — never artifact content. Rejects any forbidden content key OR any field
    outside the allowlist (an unrecognised field could carry content)."""
    keys = set(event)
    leaked = keys & _FORBIDDEN_CONTENT_FIELDS
    if leaked:
        raise ValueError(
            f"demand-gate event carries content field(s) {sorted(leaked)} — "
            f"measurement events are counts/choices only, never content."
        )
    extra = keys - _ALLOWED_FIELDS
    if extra:
        raise ValueError(
            f"demand-gate event has non-allowlisted field(s) {sorted(extra)}; "
            f"add them to _ALLOWED_FIELDS only if they carry no content."
        )


def build_export_offered(user_id: str, surface: str, formats: tuple[str, ...]) -> dict:
    e = {
        "action_type": EXPORT_OFFERED,
        "user_id": user_id,
        "surface": surface,
        "formats": list(formats),
    }
    assert_no_content(e)
    return e


def build_export_taken(user_id: str, surface: str, format: str) -> dict:
    e = {
        "action_type": EXPORT_TAKEN,
        "user_id": user_id,
        "surface": surface,
        "format": format,
    }
    assert_no_content(e)
    return e


def build_share_link_taken(user_id: str, surface: str) -> dict:
    e = {"action_type": SHARE_LINK_TAKEN, "user_id": user_id, "surface": surface}
    assert_no_content(e)
    return e


def build_re_import_detected(
    document_id: str, classification: str, content_hash: str, user_id: Optional[str] = None
) -> dict:
    e = {
        "action_type": RE_IMPORT_DETECTED,
        "document_id": document_id,
        "classification": classification,
        "content_hash": content_hash,
    }
    if user_id is not None:
        e["user_id"] = user_id
    assert_no_content(e)
    return e


__all__ = [
    "AGENT_UNPROMPTED",
    "DEMAND_GATE_EVENT_TYPES",
    "EXPORT_OFFERED",
    "EXPORT_TAKEN",
    "RE_IMPORT_DETECTED",
    "SHARE_LINK_TAKEN",
    "THIRD_PARTY_READER",
    "assert_no_content",
    "build_export_offered",
    "build_export_taken",
    "build_re_import_detected",
    "build_share_link_taken",
]
