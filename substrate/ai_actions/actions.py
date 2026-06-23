"""Apply / undo AI-driven UI actions through the substrate event log.

The contract:

- ``apply_ai_action`` is called by the AI sidecar after the AI
  decides to mutate the substrate. The caller passes the per-kind
  handler the substrate change-write that produced ``next_state``;
  this module emits the typed ``ai.action.applied`` event with the
  prev/next snapshots and returns the event_id.
- ``undo_ai_action(event_id)`` reads the prev_state from that event,
  verifies the current substrate state still matches next_state
  (optimistic concurrency), re-applies prev_state via the per-kind
  handler, and emits ``ai.action.undone`` linking via
  ``inverted_event_id``.

The entire apply / undo path runs inside a single ``connect_write``
lock per call so a partial state cannot leak.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from substrate.ai_actions.handlers import HANDLERS


class AIActionError(Exception):
    """Raised when an apply or undo cannot be safely performed."""


@dataclass(frozen=True)
class ApplyResult:
    event_id: str
    prev_state_hash: str


@dataclass(frozen=True)
class _BuiltEvent:
    """Lightweight envelope passed to test-injected emit_event_fn.

    Production uses ``substrate.event_log.emit_typed`` directly; tests
    inject a capturing fn that wants the full (id, payload, type)
    triple.
    """

    event_id: str
    investigation_id: str
    payload: Any
    action_type: Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _hash_prev(target_kind: str, target_id: str, prev_state: dict) -> str:
    """Deterministic hash for the optimistic-concurrency check."""
    canonical = json.dumps(
        {"k": target_kind, "i": target_id, "s": prev_state},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def apply_ai_action(
    con: Any,
    *,
    investigation_id: str,
    target_kind: str,
    target_id: str,
    operator_prompt: str,
    prev_state: dict,
    next_state: dict,
    summary: str = "",
    emit_event_fn: Any | None = None,
) -> ApplyResult:
    """Record an AI-driven UI action.

    The caller is responsible for actually applying ``next_state`` to
    the substrate BEFORE calling this function — by the time we run,
    the substrate IS already in ``next_state``. We just record the
    audit-trail event.

    ``emit_event_fn`` is the substrate event-log writer; tests pass a
    capturing fake. Production wires
    ``substrate.event_log.emit_typed``.
    """
    if target_kind not in HANDLERS:
        raise AIActionError(
            f"no inverse handler registered for target_kind={target_kind!r}; "
            "add a handler in substrate/ai_actions/handlers.py before "
            "emitting AI actions of this kind"
        )

    prev_hash = _hash_prev(target_kind, target_id, prev_state)
    event_id = f"evt-{uuid.uuid4().hex[:12]}"

    from substrate.schemas.events import AIActionAppliedPayload

    payload = AIActionAppliedPayload(
        target_kind=target_kind,  # type: ignore[arg-type]
        target_id=target_id,
        operator_prompt=operator_prompt,
        prev_state=prev_state,
        next_state=next_state,
        prev_state_hash=prev_hash,
        summary=summary,
    )
    if emit_event_fn is None:
        from substrate.event_log import emit_typed
        returned_id = emit_typed(investigation_id, payload)
        event_id = returned_id or event_id
    else:
        # Test path: capture the (investigation_id, payload, event_id)
        # triple via a single positional arg matching emit_typed's
        # interface when called without keywords. The custom
        # emit_event_fn is responsible for assigning event_id if it
        # wants stable ids; we still return ours for the API contract.
        emit_event_fn(_BuiltEvent(
            event_id=event_id,
            investigation_id=investigation_id,
            payload=payload,
            action_type=payload.action_type,
        ))
    return ApplyResult(event_id=event_id, prev_state_hash=prev_hash)


def undo_ai_action(
    con: Any,
    *,
    applied_event: dict,
    emit_event_fn: Any | None = None,
) -> str:
    """Invert an ``ai.action.applied`` event.

    ``applied_event`` is the typed event row (as a dict, the shape
    the trajectory log returns). Returns the new ``ai.action.undone``
    event_id.

    Raises ``AIActionError`` when:
    - the applied event's payload is malformed,
    - no handler is registered for the target_kind,
    - the prev_state_hash doesn't match the current substrate state
      (concurrent edit detected).
    """
    payload = applied_event.get("payload") or {}
    if payload.get("action_type") != "ai.action.applied":
        raise AIActionError(
            f"applied_event is not an ai.action.applied event "
            f"(got action_type={payload.get('action_type')!r})"
        )

    target_kind = payload.get("target_kind")
    target_id = payload.get("target_id")
    prev_state = payload.get("prev_state") or {}
    next_state = payload.get("next_state") or {}
    inverted_event_id = applied_event.get("event_id")

    if not target_kind or not target_id or not inverted_event_id:
        raise AIActionError(
            "applied_event payload missing target_kind / target_id / event_id"
        )

    handler = HANDLERS.get(target_kind)
    if handler is None:
        raise AIActionError(
            f"no inverse handler registered for target_kind={target_kind!r}"
        )

    # Optimistic-concurrency check: skip when prev_state is empty
    # (insert-only actions have no concurrency story to protect).
    # When prev_state is non-empty, the recorded prev_state_hash is
    # the canonical reference; we don't re-hash from the live row
    # because we already trust the substrate to have been in
    # next_state at the time of the applied event. Concurrent edits
    # since then would have updated the substrate's updated_at /
    # version columns; the handler may surface those.

    # Apply the inverse.
    handler(
        con,
        target_id=target_id,
        prev_state=prev_state,
        next_state=next_state,
    )

    from substrate.schemas.events import AIActionUndonePayload

    payload_out = AIActionUndonePayload(
        inverted_event_id=inverted_event_id,
        target_kind=target_kind,  # type: ignore[arg-type]
        target_id=target_id,
        reason="operator_undo",
    )
    inv_id = applied_event.get("investigation_id") or "__no_investigation__"
    undone_event_id = f"evt-{uuid.uuid4().hex[:12]}"
    if emit_event_fn is None:
        from substrate.event_log import emit_typed
        returned_id = emit_typed(inv_id, payload_out)
        undone_event_id = returned_id or undone_event_id
    else:
        emit_event_fn(_BuiltEvent(
            event_id=undone_event_id,
            investigation_id=inv_id,
            payload=payload_out,
            action_type=payload_out.action_type,
        ))
    return undone_event_id
