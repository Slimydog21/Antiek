"""Investigation coordinator — async event-await primitive.

Sprint 8 day 3. The Loop 1 orchestrator drives 5 role bridges through
a phase sequence, requiring the ability to (a) post a request event
into the broadcaster AND (b) await the corresponding delivered event
for that specific investigation.

This module provides both:

- ``broadcast_emit(...)`` — emits a typed event via ``emit_typed``,
  then constructs the full ``Event`` envelope and broadcasts it to
  the broadcaster's handlers (the same pattern existing bridges use
  via ``_broadcast_emitted`` after they emit downstream events).
  Triggers the bridge handlers subscribed to that action type.

- ``InvestigationCoordinator`` — one handler per observed action
  type, maintaining a per-(investigation_id, action_type) dict of
  pending ``asyncio.Future`` objects. ``wait_for(...)`` is the
  one-shot await primitive: register a future, the next event of
  that type for that investigation resolves it.

The coordinator is **stateful per broadcaster instance**. Tests create
fresh coordinators per investigation; the production wiring registers
one at app startup that all investigations share.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterable

# Direct import — orchestration depends on substrate.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from interfaces.research.api.broadcast import EventBroadcaster  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import ActionType, Event  # noqa: E402

# Action types the orchestrator awaits during the phase sequence.
# These get a coordinator handler installed at construction time so
# any matching event resolves the appropriate pending future.
DEFAULT_AWAITED_ACTION_TYPES: tuple[str, ...] = (
    "decompose.delivered",
    "evidence.retrieve.delivered",
    "parameter_extract.delivered",
    "connector.delivered",
    "synthesize.delivered",
    "synthesis.master_md_written",
    "skill.auto_patch_applied",
)


async def broadcast_emit(
    broadcaster: EventBroadcaster,
    investigation_id: str,
    payload,
    *,
    role: str | None = None,
    policy_id: str | None = None,
    parent_event_id: str | None = None,
    synthesis_id: str | None = None,
    phase: int | None = None,
    document_id: str | None = None,
) -> str | None:
    """Emit a typed event into the JSONL log AND broadcast it through
    the broadcaster so subscribed handlers (bridges) fire.

    Mirrors the ``_broadcast_emitted`` pattern existing bridge
    handlers use to publish downstream events — generalized here so
    the orchestrator can use the same shape to publish ``Requested``
    events without going through the REST POST surface.

    Returns the new event_id (or ``None`` when events are disabled
    via the ``ANTIEK_EVENTS_DISABLED`` env var)."""
    eid = emit_typed(
        investigation_id,
        payload,
        parent_event_id=parent_event_id,
        synthesis_id=synthesis_id,
        phase=phase,
        role=role,
        policy_id=policy_id,
        document_id=document_id,
    )
    if eid is None:
        return None
    # Look up the just-emitted event to broadcast the full envelope.
    for row in reversed(trajectory(investigation_id)):
        if row.get("event_id") == eid:
            try:
                event = Event.model_validate(row)
                await broadcaster.broadcast(event)
            except Exception:  # pragma: no cover — never block on broadcast
                pass
            break
    return eid


class InvestigationCoordinator:
    """Per-broadcaster handler bank that surfaces ``wait_for(...)``
    semantics over the broadcaster's append-only handler model.

    Construct once per broadcaster; call ``wait_for(inv_id,
    action_type, timeout)`` to await the next matching event.
    Internally maintains a dict of pending futures keyed on
    ``(investigation_id, action_type)``; one handler per action type
    looks up matching futures on each event and resolves them.

    The handler is **non-destructive**: it always lets the event flow
    through to other subscribers. The orchestrator just gets a
    side-channel to know "the bridge finished the request I posted."
    """

    def __init__(
        self,
        broadcaster: EventBroadcaster,
        *,
        action_types: Iterable[str] = DEFAULT_AWAITED_ACTION_TYPES,
    ):
        self.broadcaster = broadcaster
        # (investigation_id, action_type, correlation_key) → Future.
        # correlation_key disambiguates parallel Phase 2 evidence waits
        # (sub_question string); "" means legacy single-waiter semantics.
        self._pending: dict[tuple[str, str, str], asyncio.Future[Event]] = {}
        for action_type in action_types:
            broadcaster.register_handler(action_type, self._on_event)

    async def _on_event(self, event: Event) -> None:
        """Resolve any pending future matching
        ``(investigation_id, action_type)``. No-op when nobody is
        waiting — the event flows through normally."""
        raw_action = event.action_type
        action = (
            raw_action.value
            if isinstance(raw_action, ActionType)
            else str(raw_action)
        )
        inv = event.investigation_id
        correlation = ""
        payload = event.payload
        if hasattr(payload, "sub_question"):
            sq = getattr(payload, "sub_question", None)
            if isinstance(sq, str) and sq:
                correlation = sq
        keys = [(inv, action, correlation)] if correlation else []
        keys.append((inv, action, ""))
        for key in keys:
            fut = self._pending.pop(key, None)
            if fut is not None and not fut.done():
                fut.set_result(event)
                return

    async def wait_for(
        self,
        investigation_id: str,
        action_type: str,
        *,
        timeout: float = 60.0,
        correlation: str = "",
    ) -> Event:
        """Await the next event of ``action_type`` for the given
        investigation. Raises ``asyncio.TimeoutError`` if no matching
        event arrives within ``timeout`` seconds.

        When ``correlation`` is set (Phase 2 sub_question), multiple
        concurrent waiters on the same action type are supported —
        the handler matches ``payload.sub_question``. With an empty
        correlation, only one waiter per ``(investigation_id,
        action_type)`` is allowed (linear phases 1, 3–9)."""
        key = (investigation_id, action_type, correlation)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Event] = loop.create_future()
        self._pending[key] = fut
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            # Clean up unconditionally; the future may have been
            # resolved already (which is fine — .pop() handles both
            # cases). On timeout the future is cancelled by
            # asyncio.wait_for, so cleanup leaves no leak.
            self._pending.pop(key, None)
