"""Bridge ``RevShareDecision`` records → typed
``rev_share.decided`` events.

Per master-spec §9.3 + §13.7 audit: every payout decision lands in
the event log as a typed payload so the trajectory has the full
revenue-routing audit trail. The bridge is decoupled from the
broadcaster so callers can:

  - Plug it as the ``on_decisions`` hook on an
    ``AttributionToPayoutSubscription`` (the production wire-up).
  - Use it standalone to materialize payloads for offline analysis
    without an active event bus.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from substrate.schemas.events import (
    ActionType,
    Event,
    RevShareDecidedPayload,
)

from .payout import RevShareDecision


def revshare_to_payload(decision: RevShareDecision) -> RevShareDecidedPayload:
    """Convert a ``RevShareDecision`` to its typed payload form."""
    return RevShareDecidedPayload(
        decision_id=decision.decision_id,
        impression_id=decision.impression_id,
        kind=decision.kind.value,  # type: ignore[arg-type]
        recipient_ref=decision.recipient_ref,
        amount_usd_cents=decision.amount_usd_cents,
        document_id_ref=decision.document_id,
        requires_escrow=decision.requires_escrow,
        capped_to_daily_limit=decision.capped_to_daily_limit,
    )


def revshare_to_event(
    decision: RevShareDecision,
    *,
    investigation_id: str,
    param_version: str = "substrate-v0",
) -> Event:
    """Materialize a full ``Event`` envelope around a payout decision.

    Used by both the production broadcaster path and the offline
    analysis path. ``investigation_id`` is the synthesis page's
    parent investigation; production wires this from the originating
    attribution event."""
    return Event(
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        investigation_id=investigation_id,
        action_type=ActionType.REV_SHARE_DECIDED,
        payload=revshare_to_payload(decision),
        param_version=param_version,
        emitted_at=datetime.now(timezone.utc),
    )


BroadcastFn = Callable[[Event], "object"]
"""Return type is ``object`` so this works with either sync (returning
None) or async (returning a coroutine) broadcaster signatures —
the caller is responsible for awaiting if needed."""


def make_broadcasting_payout_hook(
    *,
    investigation_id: str,
    broadcast: Callable[[Event], None],
    param_version: str = "substrate-v0",
) -> Callable[[list[RevShareDecision]], None]:
    """Build an ``on_decisions`` hook that emits a typed event per
    decision through the provided ``broadcast`` function.

    ``broadcast`` is intentionally typed as the synchronous shape;
    async broadcasters wrap this hook with a sync→async adapter at
    the call site (the in-process ``EventBroadcaster`` exposes both
    forms).
    """

    def _hook(decisions: list[RevShareDecision]) -> None:
        for d in decisions:
            evt = revshare_to_event(
                d,
                investigation_id=investigation_id,
                param_version=param_version,
            )
            broadcast(evt)

    return _hook
