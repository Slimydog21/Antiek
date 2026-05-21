"""The single public emit API for the Tier-1 behavior store.

SPR-01 M6. Wave 2 surfaces (SPR-04 onward) call ``emit_behavior_event``
only; everything else in ``substrate/behavior/`` is internal.

Contract
--------
- Synchronous: returns an opaque ``event_id`` immediately.
- Async write: the row lands in DuckDB ~50–500 ms later via the
  ``BehaviorQueue`` worker. This keeps UI threads unblocked.
- Validation: raises ``InvalidEventType`` if ``event_type`` is not
  in the closed taxonomy enum. Raises ``SchemaValidationError`` if
  ``state`` or ``action`` doesn't match the JSON schema for that
  type. These are SUBSTRATE BUGS, not telemetry noise — re-raised
  so Wave 2 surfaces fail loudly during development.
- Consent: returns the same opaque event id regardless. If consent
  is absent for the user, NO row is written — the queue simply
  isn't fed.

API stability
-------------
The signature below MUST stay stable across Wave 2 surfaces. New
optional kwargs are allowed; renaming positional args is not. The
TypeScript client at ``apps/reading/src/lib/behaviorEvents.ts``
mirrors this surface 1:1.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from typing import Any, Optional

try:
    from .consent import active_consent_version
    from .queue import BehaviorRow, get_default_queue
    from .taxonomy import (
        BehaviorEventType,
        InvalidEventType,
        SchemaValidationError,
        coerce,
        validate_payload_shape,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.behavior.consent import active_consent_version  # type: ignore[no-redef]
    from substrate.behavior.queue import BehaviorRow, get_default_queue  # type: ignore[no-redef]
    from substrate.behavior.taxonomy import (  # type: ignore[no-redef]
        BehaviorEventType,
        InvalidEventType,
        SchemaValidationError,
        coerce,
        validate_payload_shape,
    )


# Operator default for single-user mode (matches the
# ``owner_user_id`` default in graph/schema.py).
DEFAULT_USER_ID = "__operator__"


def _new_event_id() -> str:
    """Opaque event id. ``evt-<12 hex>-<ms epoch>`` matches the
    event_log convention (see event_log/events.py::_new_event_id)
    for grep ergonomics across the two stores."""
    return f"evt-{uuid.uuid4().hex[:12]}-{int(time.time() * 1000)}"


def emit_behavior_event(
    event_type: "str | BehaviorEventType",
    state: dict[str, Any],
    action: dict[str, Any],
    outcome: Optional[dict[str, Any]] = None,
    *,
    user_id: str = DEFAULT_USER_ID,
    session_id: Optional[str] = None,
    document_id: Optional[str] = None,
    queue: Optional[Any] = None,
) -> str:
    """Emit one behavior event.

    Validates against the closed taxonomy + JSON schema for the
    type, checks consent, and enqueues a row for asynchronous
    insertion into ``behavior_events``. Returns the opaque event id
    synchronously.

    Args:
        event_type: A ``BehaviorEventType`` enum or its string value.
            Raises ``InvalidEventType`` if unknown.
        state: The state-feature dict for the RL row. Validated
            against the JSON schema's ``state`` block.
        action: The action dict. Validated against the schema's
            ``action`` block.
        outcome: Optional outcome dict (often populated later by a
            backfill worker; the emit API stores whatever the caller
            passes verbatim).
        user_id: Who the event belongs to. Defaults to the single-
            operator constant.
        session_id: Opaque session key. Generated on first emit if
            absent — but callers that want session-coherent reward
            shaping (cross-document-link follow-up) should pass a
            stable id.
        document_id: Optional FK into ``documents``. Required by
            most event types via the JSON schema's ``state.required``,
            but the column itself is nullable for session-scoped
            events.
        queue: Optional ``BehaviorQueue`` override. Tests pass their
            own queue tied to a tmp DB; production uses the default.

    Returns:
        The opaque event id. Always; the id is returned even when
        consent is absent so callers don't need to branch on it.
    """
    # 1. Validate the type. Raises InvalidEventType; the caller fix
    #    is "use a member of BehaviorEventType".
    coerced = coerce(event_type)

    # 2. Validate the payload shape. Raises SchemaValidationError;
    #    the caller fix is "update your call site to match the
    #    schemas/<value>.json file".
    validate_payload_shape(coerced, state, action)

    # 3. Mint the event id BEFORE the consent check. The caller
    #    holds this id either way; it doesn't tell them whether
    #    consent was active (privacy posture: don't leak consent
    #    state through return-value side channels).
    event_id = _new_event_id()

    # 4. Consent gate. ``active_consent_version`` returns None if no
    #    active consent row — that's our signal to no-op.
    consent_version = active_consent_version(user_id=user_id)
    if consent_version is None:
        return event_id

    # 5. Generate a session id if the caller didn't provide one.
    if session_id is None:
        session_id = f"sess-{uuid.uuid4().hex[:12]}"

    # 6. Submit to the queue. Non-blocking; drops on overflow with
    #    a stderr breadcrumb.
    q = queue or get_default_queue()
    q.submit(
        BehaviorRow(
            event_id=event_id,
            user_id=user_id,
            session_id=session_id,
            event_type=coerced.value,
            document_id=document_id,
            state=state,
            action=action,
            outcome=outcome,
            consent_version=consent_version,
        )
    )
    return event_id


__all__ = [
    "DEFAULT_USER_ID",
    "InvalidEventType",
    "SchemaValidationError",
    "emit_behavior_event",
]
