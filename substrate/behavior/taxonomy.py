"""Closed event taxonomy for the Tier-1 behavior store (SPR-01).

This is the closed set of event types Wave 2 surfaces (SPR-04 onward)
may emit into the behavior store. Adding a type later requires a
schema migration AND a bump of ``BEHAVIOR_TAXONOMY_VERSION``; the
emit API refuses ad-hoc strings.

Why a closed set?
-----------------
The behavior store is RL-shaped (state, action, outcome, reward
proxy). Each row will become a training datum; an ad-hoc event-type
vocabulary blows up the state space and makes the reward-proxy
backfill workers undefined on unknown types. The cost of the
discipline is one migration per added type; the cost of NOT being
disciplined is policy-level garbage data.

Schema discipline
-----------------
Every type in ``BehaviorEventType`` MUST have a matching JSON Schema
in ``substrate/behavior/schemas/<event_type_value>.json`` describing
the allowed ``state`` and ``action`` field shapes. ``api.py`` loads
those schemas and validates payloads at emit time.

Schemas referenced (one file per type, value = filename stem):
- highlight_created
- highlight_removed
- voice_note_recorded
- voice_note_played
- ai_prompt_sent
- ai_response_accepted
- ai_response_rejected
- cite_jump
- cross_doc_link_surfaced
- cross_doc_link_clicked
- cross_doc_link_dismissed
- reading_mode_toggled
- document_opened
- document_closed
- notebook_block_demoted
- notebook_block_edited

Lineage
-------
The 16 types are exactly the closed set enumerated in
``specs/wrestle-evolution/sprint-01-behavior-store.html`` M1. No
deviations; rationale for any future addition lives in the handoff
of the sprint that adds it.
"""

from __future__ import annotations

import json
import os
from enum import Enum
from functools import lru_cache
from typing import Any, Final


BEHAVIOR_TAXONOMY_VERSION: Final[int] = 1
"""Bump when the taxonomy expands or a schema file changes shape.
Stamped into ``consent_version`` defaults and into per-row metadata
so downstream replays know which vocabulary applied."""


class BehaviorEventType(str, Enum):
    """Closed vocabulary for Tier-1 behavior events.

    Values are the stored strings (Parquet- and JSON-safe). Names are
    SCREAMING_SNAKE for Python import ergonomics. Do NOT repurpose a
    value; deprecate by adding a new value and leaving the old one in
    the enum for historical row decoding.
    """

    # ── Highlights (SPR-04 reading surface) ──
    HIGHLIGHT_CREATED = "highlight_created"
    HIGHLIGHT_REMOVED = "highlight_removed"

    # ── Voice notes (SPR-02 / SPR-05) ──
    VOICE_NOTE_RECORDED = "voice_note_recorded"
    VOICE_NOTE_PLAYED = "voice_note_played"

    # ── Inline AI conversation (SPR-06) ──
    AI_PROMPT_SENT = "ai_prompt_sent"
    AI_RESPONSE_ACCEPTED = "ai_response_accepted"
    AI_RESPONSE_REJECTED = "ai_response_rejected"

    # ── Citation jumps + cross-doc links (SPR-07) ──
    CITE_JUMP = "cite_jump"
    CROSS_DOC_LINK_SURFACED = "cross_doc_link_surfaced"
    CROSS_DOC_LINK_CLICKED = "cross_doc_link_clicked"
    CROSS_DOC_LINK_DISMISSED = "cross_doc_link_dismissed"

    # ── Reading-mode + document lifecycle (SPR-04 / SPR-08) ──
    READING_MODE_TOGGLED = "reading_mode_toggled"
    DOCUMENT_OPENED = "document_opened"
    DOCUMENT_CLOSED = "document_closed"

    # ── Notebook block lifecycle (SPR-08) ──
    NOTEBOOK_BLOCK_DEMOTED = "notebook_block_demoted"
    NOTEBOOK_BLOCK_EDITED = "notebook_block_edited"


# Public alias used by callers that need to declare "any taxonomy
# member" without importing the Enum class.
ALL_BEHAVIOR_EVENT_TYPES: Final[tuple[str, ...]] = tuple(
    t.value for t in BehaviorEventType
)


_SCHEMA_DIR: Final[str] = os.path.join(os.path.dirname(__file__), "schemas")


class InvalidEventType(ValueError):
    """Raised by the emit API when ``event_type`` is not in the closed
    taxonomy. Caller bug, not telemetry noise — re-raised, never
    swallowed."""


class SchemaValidationError(ValueError):
    """Raised when an event's ``state`` or ``action`` payload does not
    match the JSON Schema for its type."""


def coerce(event_type: "str | BehaviorEventType") -> BehaviorEventType:
    """Convert a string or enum member to a ``BehaviorEventType``.

    Raises ``InvalidEventType`` on unknown strings — this is the
    boundary check Wave 2 surfaces hit when they call the emit API.
    """
    if isinstance(event_type, BehaviorEventType):
        return event_type
    try:
        return BehaviorEventType(event_type)
    except ValueError as exc:
        raise InvalidEventType(
            f"unknown behavior event type {event_type!r}; "
            f"valid: {list(ALL_BEHAVIOR_EVENT_TYPES)}"
        ) from exc


@lru_cache(maxsize=64)
def load_schema(event_type: "str | BehaviorEventType") -> dict[str, Any]:
    """Load and cache the JSON Schema for a behavior event type.

    Schemas live at ``substrate/behavior/schemas/<value>.json``. The
    file is the source of truth for allowed ``state`` and ``action``
    fields; missing-file is treated as a substrate bug (not a runtime
    miss) and re-raised loudly.
    """
    et = coerce(event_type)
    path = os.path.join(_SCHEMA_DIR, f"{et.value}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"behavior taxonomy: schema file missing for {et.value!r} at {path}. "
            "Every enum member MUST have a matching schemas/<value>.json file."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def all_schema_files() -> list[str]:
    """Diagnostic: list the schema files on disk. Used by the M1
    acceptance test that asserts every enum member has a matching
    file."""
    if not os.path.isdir(_SCHEMA_DIR):
        return []
    return sorted(
        fn[: -len(".json")]
        for fn in os.listdir(_SCHEMA_DIR)
        if fn.endswith(".json")
    )


def validate_payload_shape(
    event_type: "str | BehaviorEventType",
    state: dict[str, Any],
    action: dict[str, Any],
) -> None:
    """Validate ``state`` and ``action`` against the type's JSON
    Schema. Raises ``SchemaValidationError`` on mismatch.

    The validation is intentionally minimal — required-key checks +
    extra-key rejection. We do not pull in a full ``jsonschema``
    dependency for this; the schema dicts carry ``required`` lists
    and ``properties`` keys that we walk by hand. The schemas
    themselves are full-fat Draft-07 documents so a future swap to
    ``jsonschema.validate`` is a single-line change.
    """
    schema = load_schema(event_type)
    _validate_subobject(state, schema.get("state", {}), "state")
    _validate_subobject(action, schema.get("action", {}), "action")


def _validate_subobject(
    payload: dict[str, Any],
    sub_schema: dict[str, Any],
    label: str,
) -> None:
    """Tiny ad-hoc JSON-Schema validator. Supports ``properties``,
    ``required``, and ``additionalProperties: false`` — the only
    constructs the M1 schemas use.
    """
    if not isinstance(payload, dict):
        raise SchemaValidationError(
            f"{label} must be a dict, got {type(payload).__name__}"
        )
    properties = sub_schema.get("properties", {}) or {}
    required = sub_schema.get("required", []) or []
    additional = sub_schema.get("additionalProperties", True)

    for req in required:
        if req not in payload:
            raise SchemaValidationError(
                f"{label}: missing required field {req!r} "
                f"(schema requires {required})"
            )

    if additional is False:
        extra = set(payload.keys()) - set(properties.keys())
        if extra:
            raise SchemaValidationError(
                f"{label}: unexpected field(s) {sorted(extra)!r}; "
                f"allowed: {sorted(properties.keys())}"
            )

    # Light type check on properties present in the payload.
    for key, value in payload.items():
        prop_schema = properties.get(key)
        if not prop_schema:
            continue
        expected = prop_schema.get("type")
        if expected and not _matches_type(value, expected):
            raise SchemaValidationError(
                f"{label}.{key}: expected {expected!r}, got "
                f"{type(value).__name__}"
            )


_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list, tuple),
    "null": (type(None),),
}


def _matches_type(value: Any, expected: "str | list[str]") -> bool:
    if isinstance(expected, list):
        return any(_matches_type(value, e) for e in expected)
    # JSON Schema special-case: ``bool`` is a subclass of ``int`` in
    # Python; reject ``True``/``False`` for ``integer``/``number``.
    if expected in ("integer", "number") and isinstance(value, bool):
        return False
    types = _TYPE_MAP.get(expected, ())
    return isinstance(value, types) if types else True


__all__ = [
    "ALL_BEHAVIOR_EVENT_TYPES",
    "BEHAVIOR_TAXONOMY_VERSION",
    "BehaviorEventType",
    "InvalidEventType",
    "SchemaValidationError",
    "all_schema_files",
    "coerce",
    "load_schema",
    "validate_payload_shape",
]
