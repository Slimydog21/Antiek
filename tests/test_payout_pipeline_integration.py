"""End-to-end payout pipeline integration test.

Drives a synthetic ad impression through:
  AttributionComputedEvent
    → AttributionToPayoutSubscription
    → RevShareDecisions
    → broadcasting hook emits rev_share.decided events
    → transfer initiator drives them through MockStripeProvider
    → payout_transfers table rows land

Confirms every link in the chain produces the expected audit
artifacts. This is the master-spec §13.7 'audit-from-the-event-log'
substrate-level guarantee.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from substrate.ad_inventory.event_emit import (
    make_broadcasting_payout_hook,
)
from substrate.ad_inventory.event_subscription import (
    AttributionComputedEvent,
    make_subscription,
)
from substrate.ad_inventory.payout import PayoutRouter, RevShareKind
from substrate.ad_inventory.transfer_initiator import (
    STATUS_SKIPPED_PLATFORM,
    STATUS_TRANSFERRED,
    initiate_transfer,
    load_transfers_for_recipient,
)
from substrate.schemas.events import ActionType, Event
from tools.stripe_connect.providers import MockStripeProvider


@pytest.fixture()
def isolated_db():
    tmpdir = tempfile.mkdtemp(prefix="antiek-payout-pipeline-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _strip_action_type(evt: Event) -> str:
    at = evt.action_type
    return at.value if hasattr(at, "value") else at


def test_full_payout_pipeline_end_to_end(isolated_db):
    """One AttributionComputedEvent → full audit trail.

    Pipeline shape:
      attribution event → subscription → 2 decisions (creator +
      platform) → 2 typed events → 2 transfer initiations → 1
      Stripe transfer (platform residual skipped) + 2
      payout_transfers rows in the audit log.
    """
    from runtime.db_lock import connect_write

    captured_events: list[Event] = []
    router = PayoutRouter()
    hook = make_broadcasting_payout_hook(
        investigation_id="inv-1",
        broadcast=captured_events.append,
    )
    subscription = make_subscription(router, on_decisions=hook)

    # 1. Synthetic attribution computed event.
    attribution_event = AttributionComputedEvent(
        page_id="page-1",
        impression_id="imp-1",
        ad_revenue_usd_cents=1_000,  # $10.00
        attribution_shares={"doc-A": 1.0},
        document_to_recipient={
            "doc-A": (RevShareKind.CREATOR, "user-X", False),
        },
    )

    # 2. Subscription produces decisions.
    decisions = subscription.handle(attribution_event)

    # 70% creator + 30% platform = 2 decisions.
    assert len(decisions) == 2
    creator_decision = next(d for d in decisions if d.kind == RevShareKind.CREATOR)
    platform_decision = next(d for d in decisions if d.kind == RevShareKind.PLATFORM)
    assert creator_decision.amount_usd_cents == 700
    assert platform_decision.amount_usd_cents == 300

    # 3. Hook emitted one typed event per decision.
    assert len(captured_events) == 2
    event_action_types = {_strip_action_type(e) for e in captured_events}
    assert event_action_types == {ActionType.REV_SHARE_DECIDED.value}

    # 4. Drive each decision through the Stripe Connect initiator.
    stripe_provider = MockStripeProvider()
    transfer_outcomes = []
    with connect_write(isolated_db, purpose="test:e2e_payout") as con:
        for d in decisions:
            account_id = (
                "acct_user_X" if d.kind == RevShareKind.CREATOR else None
            )
            outcome = initiate_transfer(
                con=con,
                provider=stripe_provider,
                decision=d,
                account_id_for_recipient=account_id,
            )
            transfer_outcomes.append(outcome)

    # 5. Verify the transfer outcomes.
    creator_outcome = next(
        o for o in transfer_outcomes
        if o.recipient_account_id == "acct_user_X"
    )
    platform_outcome = next(
        o for o in transfer_outcomes
        if o.recipient_account_id is None
    )
    assert creator_outcome.status == STATUS_TRANSFERRED
    assert creator_outcome.stripe_transfer_id is not None
    assert platform_outcome.status == STATUS_SKIPPED_PLATFORM
    assert platform_outcome.stripe_transfer_id is None

    # 6. Stripe saw exactly one transfer (creator); platform residual
    # didn't fire.
    assert len(stripe_provider.transfers) == 1
    only_transfer = next(iter(stripe_provider.transfers.values()))
    assert only_transfer["account_id"] == "acct_user_X"
    assert only_transfer["amount_usd_cents"] == 700

    # 7. Audit query — load by recipient — finds the creator row.
    from runtime.db_lock import connect_read
    with connect_read(isolated_db) as con:
        creator_rows = load_transfers_for_recipient(con, "acct_user_X")
    assert len(creator_rows) == 1
    assert creator_rows[0].status == STATUS_TRANSFERRED
    assert creator_rows[0].decision_id == creator_decision.decision_id


def test_full_payout_pipeline_multi_creator_split(isolated_db):
    """Multi-document attribution splits the creator pool by share;
    every decision lands as its own audit row."""
    from runtime.db_lock import connect_write

    captured: list[Event] = []
    router = PayoutRouter()
    hook = make_broadcasting_payout_hook(
        investigation_id="inv-1",
        broadcast=captured.append,
    )
    sub = make_subscription(router, on_decisions=hook)

    attribution_event = AttributionComputedEvent(
        page_id="page-1",
        impression_id="imp-2",
        ad_revenue_usd_cents=1_000,
        attribution_shares={"doc-A": 0.6, "doc-B": 0.4},
        document_to_recipient={
            "doc-A": (RevShareKind.CREATOR, "user-A", False),
            "doc-B": (RevShareKind.CREATOR, "user-B", False),
        },
    )
    decisions = sub.handle(attribution_event)
    # 2 creators + 1 platform.
    assert len(decisions) == 3
    creators = [d for d in decisions if d.kind == RevShareKind.CREATOR]
    assert len(creators) == 2
    amounts = sorted(d.amount_usd_cents for d in creators)
    # creator_pool=700; 60/40 split → 420 + 280.
    assert amounts == [280, 420]

    # 3 typed events emitted.
    assert len(captured) == 3

    # Drive through the initiator with per-user account map.
    stripe_provider = MockStripeProvider()
    user_to_account = {"user-A": "acct_A", "user-B": "acct_B"}
    with connect_write(isolated_db, purpose="test:e2e_multi") as con:
        for d in decisions:
            if d.kind == RevShareKind.PLATFORM:
                acct = None
            else:
                acct = user_to_account[d.recipient_ref]
            initiate_transfer(
                con=con,
                provider=stripe_provider,
                decision=d,
                account_id_for_recipient=acct,
            )

    # Two Stripe transfers, one per creator; platform doesn't fire.
    assert len(stripe_provider.transfers) == 2
    transferred_amounts = sorted(
        t["amount_usd_cents"] for t in stripe_provider.transfers.values()
    )
    assert transferred_amounts == [280, 420]
