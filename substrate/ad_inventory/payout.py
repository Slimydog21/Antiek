"""Attribution-to-payout routing (master-spec §13.9 + §9.10).

When an ad impression accrues, the substrate:
1. Computes attribution shares (per §9.3 algorithm)
2. For each contributing document, looks up its ip_holder_id
3. If ip_holder is a CREATOR (user-as-IP-holder per §13.9): routes
   70% of ad revenue to creator's Stripe Connect account
4. If ip_holder is a PUBLISHER (master-spec §9.10): accrues escrow
   until claim_status='claimed', then transfers via Stripe Connect

Per master-spec §9.7 anti-gaming: per-document daily payout cap +
click/view fraud detection + audit logs + operator-controlled
publisher verification."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


CREATOR_REV_SHARE = Decimal("0.70")  # per master-spec §13.5 + §13.9
PLATFORM_CUT = Decimal("0.30")  # per master-spec §9.0.1 (80/20 Perplexity benchmark adjusted to 70/30)
DEFAULT_PER_DOCUMENT_DAILY_CAP_USD = Decimal("50.00")  # per §9.7 anti-gaming


class RevShareKind(str, enum.Enum):
    CREATOR = "creator"  # user-as-IP-holder
    PUBLISHER = "publisher"  # pre-onboarded IP holder (§9.10)
    PLATFORM = "platform"  # Antiek's 30% cut


@dataclass(frozen=True)
class RevShareDecision:
    """One revenue-routing decision arising from an ad impression."""

    decision_id: str
    impression_id: str
    kind: RevShareKind
    recipient_ref: str  # user_id, ip_holder_id, or "__platform__"
    amount_usd_cents: int
    document_id: Optional[str]
    requires_escrow: bool  # True if publisher is pre_onboarded / invited
    capped_to_daily_limit: bool  # True if the §9.7 cap reduced the payout
    decided_at: str = field(default_factory=_now_iso)


@dataclass
class PayoutRouter:
    """Routes attribution-derived revenue to recipients.

    ``gates_by_decision_id`` records why each decision was admitted
    (or NOT admitted). Values mirror ``decisions_log.DecisionGate``:
    "admitted" | "rolled_over" | "gated_kyc" | "gated_fraud".

    The router still emits a decision for every recipient (so the
    audit trail is complete), but the gate result tells the
    transfer-initiator whether to actually call Stripe."""

    per_document_daily_cap_usd: Decimal = DEFAULT_PER_DOCUMENT_DAILY_CAP_USD
    document_daily_spent_cents: dict[str, int] = field(default_factory=dict)
    decisions: list[RevShareDecision] = field(default_factory=list)
    gates_by_decision_id: dict[str, str] = field(default_factory=dict)


def distribute_session_ad_revenue(
    router: PayoutRouter,
    *,
    impression_id: str,
    ad_revenue_usd_cents: int,
    attribution_shares: dict[str, float],
    document_to_recipient: dict[str, tuple[RevShareKind, str, bool]],
) -> list[RevShareDecision]:
    """Distribute the ad revenue per attribution shares.

    Args:
        router: the PayoutRouter (tracks daily caps)
        impression_id: links back to the AdImpression
        ad_revenue_usd_cents: total cents the advertiser paid
        attribution_shares: document_id → share in [0, 1]
        document_to_recipient: document_id → (kind, recipient_ref,
            requires_escrow). For creator: (CREATOR, user_id, False).
            For publisher: (PUBLISHER, ip_holder_id,
            requires_escrow=True if pre_onboarded).

    Returns:
        List of RevShareDecision. Platform's 30% is the last entry.
    """
    decisions: list[RevShareDecision] = []
    creator_pool_cents = int(ad_revenue_usd_cents * float(CREATOR_REV_SHARE))
    platform_cents = ad_revenue_usd_cents - creator_pool_cents

    for doc_id, share in attribution_shares.items():
        if doc_id not in document_to_recipient:
            continue  # legacy doc; skip
        kind, recipient_ref, requires_escrow = document_to_recipient[doc_id]
        share_cents = int(creator_pool_cents * share)
        share_cents, capped = enforce_per_document_daily_cap(
            router, doc_id, share_cents,
        )
        if share_cents <= 0:
            continue
        decisions.append(RevShareDecision(
            decision_id=f"rs-{uuid.uuid4().hex[:12]}",
            impression_id=impression_id,
            kind=kind,
            recipient_ref=recipient_ref,
            amount_usd_cents=share_cents,
            document_id=doc_id,
            requires_escrow=requires_escrow,
            capped_to_daily_limit=capped,
        ))

    # Platform cut (always; not capped).
    decisions.append(RevShareDecision(
        decision_id=f"rs-{uuid.uuid4().hex[:12]}",
        impression_id=impression_id,
        kind=RevShareKind.PLATFORM,
        recipient_ref="__platform__",
        amount_usd_cents=platform_cents,
        document_id=None,
        requires_escrow=False,
        capped_to_daily_limit=False,
    ))

    router.decisions.extend(decisions)
    return decisions


def enforce_per_document_daily_cap(
    router: PayoutRouter,
    document_id: str,
    proposed_cents: int,
) -> tuple[int, bool]:
    """Enforce master-spec §9.7 anti-gaming per-document daily cap.

    Returns (capped_cents, was_capped_bool)."""
    cap_cents = int(router.per_document_daily_cap_usd * 100)
    spent = router.document_daily_spent_cents.get(document_id, 0)
    available = max(0, cap_cents - spent)
    if proposed_cents <= available:
        router.document_daily_spent_cents[document_id] = spent + proposed_cents
        return (proposed_cents, False)
    # Cap kicks in.
    router.document_daily_spent_cents[document_id] = cap_cents
    return (available, True)


def distribute_with_gates(
    router: PayoutRouter,
    *,
    impression_id: str,
    ad_revenue_usd_cents: int,
    attribution_shares: dict[str, float],
    document_to_recipient: dict[str, tuple["RevShareKind", str, bool]],
    kyc_registry=None,  # type: Optional[KycRegistry]
    fraud_verdict=None,  # type: Optional[FraudVerdict]
) -> list[RevShareDecision]:
    """Distribute revenue + apply §9.5 KYC settlement gate + §9.7
    anti-gaming gate.

    Same return shape as ``distribute_session_ad_revenue``, but
    populates ``router.gates_by_decision_id`` with the gate result
    per decision. Caller (typically the persistence layer) reads
    the dict to record ``payout_decisions.gate_result``.

    Gates applied:

      - FraudVerdict.BLOCK → every creator/publisher decision tagged
        ``gated_fraud``. Platform cut still emitted (Antiek bears
        the operational cost of the impression regardless).
      - Below §9.5 floor amount → tagged ``rolled_over``.
      - At/above §9.5 floor + KYC not COMPLETED → tagged ``gated_kyc``.
      - Otherwise → ``admitted``.

    Substrate produces the decisions but the gate value tells the
    transfer initiator whether to actually move money. Gated
    decisions are still persisted so the operator can audit which
    impressions were blocked from settlement and why."""
    # Defer imports to avoid hard coupling at module-load time.
    from substrate.billing.kyc import (
        KYC_PAYOUT_FLOOR_USD_CENTS, KycState, can_settle,
    )

    fraud_blocked = False
    if fraud_verdict is not None:
        verdict_kind = getattr(fraud_verdict, "kind", None)
        if verdict_kind is not None and str(verdict_kind).endswith("BLOCK"):
            fraud_blocked = True

    decisions = distribute_session_ad_revenue(
        router,
        impression_id=impression_id,
        ad_revenue_usd_cents=ad_revenue_usd_cents,
        attribution_shares=attribution_shares,
        document_to_recipient=document_to_recipient,
    )

    # We tagged nothing inside distribute_session_ad_revenue, so
    # everything currently reads ADMITTED. Now apply gates by
    # post-processing.
    for d in decisions:
        if d.kind == RevShareKind.PLATFORM:
            router.gates_by_decision_id[d.decision_id] = "admitted"
            continue
        if fraud_blocked:
            router.gates_by_decision_id[d.decision_id] = "gated_fraud"
            continue
        if d.amount_usd_cents <= KYC_PAYOUT_FLOOR_USD_CENTS:
            router.gates_by_decision_id[d.decision_id] = "rolled_over"
            continue
        if kyc_registry is not None:
            if not can_settle(
                kyc_registry,
                recipient_ref=d.recipient_ref,
                amount_usd_cents=d.amount_usd_cents,
            ):
                router.gates_by_decision_id[d.decision_id] = "gated_kyc"
                continue
        router.gates_by_decision_id[d.decision_id] = "admitted"

    return decisions
