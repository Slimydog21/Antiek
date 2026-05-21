"""RevShareDecision → typed event emission tests."""

from __future__ import annotations

from substrate.ad_inventory.event_emit import (
    make_broadcasting_payout_hook,
    revshare_to_event,
    revshare_to_payload,
)
from substrate.ad_inventory.event_subscription import (
    AttributionComputedEvent,
    make_subscription,
)
from substrate.ad_inventory.payout import (
    PayoutRouter,
    RevShareDecision,
    RevShareKind,
)
from substrate.schemas.events import (
    ActionType,
    Event,
    RevShareDecidedPayload,
)


def _decision(**overrides) -> RevShareDecision:
    base = dict(
        decision_id="rs-1",
        impression_id="imp-1",
        kind=RevShareKind.CREATOR,
        recipient_ref="user-X",
        amount_usd_cents=100,
        document_id="doc-A",
        requires_escrow=False,
        capped_to_daily_limit=False,
    )
    base.update(overrides)
    return RevShareDecision(**base)


# ── Payload conversion ─────────────────────────────────────────────


def test_revshare_to_payload_round_trips_fields():
    d = _decision()
    p = revshare_to_payload(d)
    assert isinstance(p, RevShareDecidedPayload)
    assert p.decision_id == d.decision_id
    assert p.impression_id == d.impression_id
    assert p.kind == "creator"
    assert p.recipient_ref == "user-X"
    assert p.amount_usd_cents == 100
    assert p.document_id_ref == "doc-A"
    assert p.requires_escrow is False
    assert p.capped_to_daily_limit is False


def test_revshare_to_payload_platform_kind():
    """Platform decisions have no document_id; the payload field
    drops to None."""
    d = _decision(
        kind=RevShareKind.PLATFORM, recipient_ref="__platform__",
        document_id=None,
    )
    p = revshare_to_payload(d)
    assert p.kind == "platform"
    assert p.document_id_ref is None


# ── Event envelope ─────────────────────────────────────────────────


def test_revshare_to_event_emits_full_envelope():
    d = _decision()
    e = revshare_to_event(d, investigation_id="inv-42")
    assert isinstance(e, Event)
    assert e.action_type == ActionType.REV_SHARE_DECIDED
    assert e.investigation_id == "inv-42"
    assert isinstance(e.payload, RevShareDecidedPayload)
    assert e.payload.recipient_ref == "user-X"


# ── Broadcasting hook integrates with the subscription ──────────────


def test_broadcasting_hook_emits_per_decision():
    """The hook fires once per RevShareDecision when wired to a
    real PayoutRouter via AttributionToPayoutSubscription."""
    captured: list[Event] = []
    router = PayoutRouter()
    hook = make_broadcasting_payout_hook(
        investigation_id="inv-1",
        broadcast=captured.append,
    )
    sub = make_subscription(router, on_decisions=hook)

    event = AttributionComputedEvent(
        page_id="page-1",
        impression_id="imp-1",
        ad_revenue_usd_cents=1_000,
        attribution_shares={"doc-A": 1.0},
        document_to_recipient={
            "doc-A": (RevShareKind.CREATOR, "user-X", False),
        },
    )
    sub.handle(event)

    # Expect 2 events: creator + platform.
    assert len(captured) == 2
    kinds = sorted(e.payload.kind for e in captured)
    assert kinds == ["creator", "platform"]
    # All events share the same investigation_id.
    for e in captured:
        assert e.investigation_id == "inv-1"


def test_hook_no_decisions_no_events():
    """No attribution shares → no events emitted (cap-blocked or
    legacy-doc paths)."""
    captured: list[Event] = []
    router = PayoutRouter()
    hook = make_broadcasting_payout_hook(
        investigation_id="inv-1",
        broadcast=captured.append,
    )
    # An empty list of decisions → hook runs zero broadcast calls.
    hook([])
    assert captured == []
