"""Attribution → PayoutRouter subscription tests."""

from __future__ import annotations

from decimal import Decimal

from substrate.ad_inventory.event_subscription import (
    AttributionComputedEvent,
    make_subscription,
)
from substrate.ad_inventory.payout import (
    PayoutRouter,
    RevShareKind,
)


def _event(
    page_id: str = "page-1",
    impression_id: str = "imp-1",
    ad_revenue_usd_cents: int = 1_000,
    shares: dict[str, float] | None = None,
    recipients: dict[str, tuple[RevShareKind, str, bool]] | None = None,
) -> AttributionComputedEvent:
    return AttributionComputedEvent(
        page_id=page_id,
        impression_id=impression_id,
        ad_revenue_usd_cents=ad_revenue_usd_cents,
        attribution_shares=shares or {"doc-A": 1.0},
        document_to_recipient=recipients
        or {"doc-A": (RevShareKind.CREATOR, "user-X", False)},
    )


def test_subscription_routes_70_30_split():
    """Per master-spec §13.5: creator gets 70%, platform 30%."""
    router = PayoutRouter()
    sub = make_subscription(router)
    decisions = sub.handle(_event(ad_revenue_usd_cents=1_000))
    # 700¢ → creator, 300¢ → platform
    creator = next(d for d in decisions if d.kind == RevShareKind.CREATOR)
    platform = next(d for d in decisions if d.kind == RevShareKind.PLATFORM)
    assert creator.amount_usd_cents == 700
    assert platform.amount_usd_cents == 300
    assert creator.recipient_ref == "user-X"


def test_subscription_appends_to_audit_log():
    """All decisions land in router.decisions (the audit trail)."""
    router = PayoutRouter()
    sub = make_subscription(router)
    assert router.decisions == []
    sub.handle(_event())
    assert len(router.decisions) == 2  # creator + platform


def test_subscription_invokes_hook_when_provided():
    """on_decisions sink is called with the produced decisions."""
    sink: list = []
    router = PayoutRouter()
    sub = make_subscription(router, on_decisions=lambda ds: sink.extend(ds))
    decisions = sub.handle(_event())
    assert sink == decisions


def test_subscription_respects_per_document_daily_cap():
    """§9.7 anti-gaming cap is enforced through the subscription.

    Cap = $1.00 = 100¢. Single 1 000¢ impression yields 700¢ creator
    share, which the cap clamps to 100¢ on first hit. Second impression
    has zero headroom — no creator decision is created (only platform).
    """
    router = PayoutRouter(per_document_daily_cap_usd=Decimal("1.00"))
    sub = make_subscription(router)

    # First impression: creator share = 700¢, capped to the 100¢ daily limit.
    first = sub.handle(_event(ad_revenue_usd_cents=1_000))
    creator_first = next(d for d in first if d.kind == RevShareKind.CREATOR)
    assert creator_first.amount_usd_cents == 100
    assert creator_first.capped_to_daily_limit is True

    # Second impression: cap already exhausted; no creator decision emitted.
    second = sub.handle(_event(impression_id="imp-2", ad_revenue_usd_cents=1_000))
    creator_second = [d for d in second if d.kind == RevShareKind.CREATOR]
    assert creator_second == []
    # Platform is uncapped — it still routes its 30%.
    platform_second = next(d for d in second if d.kind == RevShareKind.PLATFORM)
    assert platform_second.amount_usd_cents == 300


def test_subscription_splits_revenue_by_attribution_shares():
    """Multi-document attribution splits the creator pool by share."""
    router = PayoutRouter()
    sub = make_subscription(router)
    decisions = sub.handle(_event(
        ad_revenue_usd_cents=1_000,
        shares={"doc-A": 0.6, "doc-B": 0.4},
        recipients={
            "doc-A": (RevShareKind.CREATOR, "user-A", False),
            "doc-B": (RevShareKind.CREATOR, "user-B", False),
        },
    ))
    creator_decisions = {
        d.recipient_ref: d.amount_usd_cents
        for d in decisions if d.kind == RevShareKind.CREATOR
    }
    # Creator pool = 700¢; user-A gets 60% = 420¢; user-B 40% = 280¢.
    assert creator_decisions == {"user-A": 420, "user-B": 280}
