"""Attribution → Payout event subscription.

Bridges the ``page_attribution_computed`` event stream into the
``PayoutRouter`` so revenue distribution happens deterministically
when an attribution decision lands. Sprint 23-24 substrate plumbing
(master-spec §9.3 + §9.7 + §13.5).

Design constraints per master-spec:
- §9.7 anti-gaming: per-document daily cap is enforced inside
  ``PayoutRouter.distribute_session_ad_revenue``; this subscription
  does not bypass it.
- §13.5: creator rev-share = 70%, platform cut = 30%; reflected in
  ``CREATOR_REV_SHARE``.
- §13.7 audit: every distribution decision is appended to the
  router's ``decisions`` list, which is the audit trail.
- Single-writer invariant: this module emits decisions in-memory
  only. Persistence to the events table is the caller's
  responsibility (via the event broadcaster).

The subscription is event-shaped (not coroutine-shaped) so it can
hook into either the in-process broadcaster OR a future Kafka
adapter without refactoring.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .payout import (
    PayoutRouter,
    RevShareDecision,
    RevShareKind,
    distribute_session_ad_revenue,
)


@dataclass(frozen=True)
class AttributionComputedEvent:
    """The event the subscription consumes.

    Emitted by the synthesis pipeline whenever a page generates an
    ad impression with attribution shares computed. The carrier
    fields below are the minimum the bridge needs; richer telemetry
    (algorithm name, claim_id mapping) rides separately.
    """

    page_id: str
    impression_id: str
    ad_revenue_usd_cents: int
    attribution_shares: dict[str, float]
    document_to_recipient: dict[str, tuple[RevShareKind, str, bool]]


PayoutHook = Callable[[list[RevShareDecision]], None]


@dataclass
class AttributionToPayoutSubscription:
    """In-memory subscription. Production wires this into the event
    broadcaster's ``page_attribution_computed`` channel.

    Args:
      router: the PayoutRouter that owns the daily-cap state +
        decisions log.
      on_decisions: optional sink for the resulting decisions (e.g.
        an event-emitter that publishes ``revenue_distributed`` for
        downstream Stripe Connect transfer initiation).
    """

    router: PayoutRouter
    on_decisions: PayoutHook | None = None

    def handle(self, event: AttributionComputedEvent) -> list[RevShareDecision]:
        """Process one ``AttributionComputedEvent``. Returns the list
        of decisions; also forwards to ``on_decisions`` if set."""
        decisions = distribute_session_ad_revenue(
            self.router,
            impression_id=event.impression_id,
            ad_revenue_usd_cents=event.ad_revenue_usd_cents,
            attribution_shares=event.attribution_shares,
            document_to_recipient=event.document_to_recipient,
        )
        if self.on_decisions is not None:
            self.on_decisions(decisions)
        return decisions


def make_subscription(
    router: PayoutRouter,
    on_decisions: PayoutHook | None = None,
) -> AttributionToPayoutSubscription:
    """Factory. Mirrors the established substrate-side
    ``make_*`` factories that orchestrate.py wires up at boot."""
    return AttributionToPayoutSubscription(
        router=router, on_decisions=on_decisions,
    )
