"""Rev-share payout router — integrates anti-gaming + rev-share +
Stripe Connect.

Per master-spec §9.0.1 + §9.5 + §13.9 + §9.10 and the Sprint 23-24
"Attribution → rev-share payout pipeline" phase:

  ad impression
   → AntiGamingDetector.run_full_check → FraudVerdict
       PASS  → split_platform_vs_ip → split_mixed_attribution
                → for each line: ACTIVE Stripe account → settle/rollover
       REVIEW → escrow + operator queue, no transfer yet
       BLOCK  → drop + audit log entry

The router is the integration substrate; it does not call Stripe.
Production wires a RealStripeProvider; tests use MockStripeProvider.
Activation gated on Sprint 23-24 anti-gaming red-team report
(docs/sprint23_red_team.md per the Phase 4 ads callout).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable, Optional

from substrate.anti_gaming.verdict import FraudVerdict, FraudVerdictKind
from substrate.rev_share.mixed_attribution import (
    MixedAttributionInput,
    MixedAttributionResult,
    split_mixed_attribution,
)
from substrate.rev_share.rollover import (
    MINIMUM_PAYOUT_USD_CENTS,
    RolloverLedger,
    RolloverState,
    accrue,
    settle_or_rollover,
)
from substrate.rev_share.splits import split_platform_vs_ip

from .accounts import (
    StripeAccountStatus,
    StripeConnectAccount,
    StripeOperationsLog,
)
from .providers import StripeProvider


def _idem_key(impression_id: str, recipient_ref: str) -> str:
    """Deterministic, audit-traceable idempotency key.

    Same impression + same recipient → same key, so re-running the
    pipeline never double-pays even if the pipeline upstream is at-
    least-once."""
    raw = f"{impression_id}|{recipient_ref}".encode("utf-8")
    return f"rsp-{hashlib.sha256(raw).hexdigest()[:24]}"


@dataclass(frozen=True)
class PayoutOutcome:
    """The result of attempting to settle one rev-share line."""

    recipient_ref: str
    kind: str  # "creator" | "publisher"
    amount_cents: int
    status: str  # "transferred" | "rolled_over" | "escrowed" | "blocked" | "kyc_pending"
    provider_ref: Optional[str] = None
    notes: str = ""


@dataclass
class RevSharePayoutRouter:
    """The integration point — owns the rollover ledger + operations log."""

    provider: StripeProvider
    operations_log: StripeOperationsLog = field(default_factory=StripeOperationsLog)
    rollover_ledger: RolloverLedger = field(default_factory=RolloverLedger)
    accounts: dict[str, StripeConnectAccount] = field(default_factory=dict)
    platform_residual_cents: int = 0

    def register_account(self, account: StripeConnectAccount) -> None:
        """Mirror a Stripe Connect account into the router's lookup."""
        self.accounts[account.substrate_ref] = account


def route_impression_revenue(
    router: RevSharePayoutRouter,
    *,
    impression_id: str,
    ad_revenue_cents: int,
    attribution_shares: dict[str, float],
    document_to_recipient: dict[str, tuple[str, str]],
    verdict: FraudVerdict,
    current_month_index: int,
) -> tuple[list[PayoutOutcome], MixedAttributionResult]:
    """Distribute one impression's revenue end-to-end.

    Returns (per-line outcomes, the mixed-attribution result).

    Discipline:
    - BLOCK verdict drops the impression entirely; nothing routed, audit
      log records a blocked entry.
    - REVIEW verdict accrues to the rollover ledger but never settles
      this round, regardless of threshold — operator queue handles
      manual release.
    - PASS verdict splits 30/70, runs mixed_attribution, then for each
      line checks the account's StripeAccountStatus; ACTIVE accounts
      get accrued and (if threshold crossed) settled; PENDING accounts
      accrue but cannot settle (KYC required).
    """
    if ad_revenue_cents <= 0:
        return ([], MixedAttributionResult(impression_id=impression_id, lines=(), unallocated_cents=0))

    if verdict.kind == FraudVerdictKind.BLOCK:
        router.operations_log.append_intent(
            op_type="payout_blocked",
            amount_usd_cents=ad_revenue_cents,
            substrate_ref=impression_id,
            idempotency_key=_idem_key(impression_id, "__blocked__"),
            metadata={"verdict_id": verdict.verdict_id, "signals": [s.name for s in verdict.signals]},
        )
        return ([PayoutOutcome(
            recipient_ref="__blocked__",
            kind="block",
            amount_cents=ad_revenue_cents,
            status="blocked",
            notes=f"verdict={verdict.kind.value} signals={[s.name for s in verdict.signals]}",
        )], MixedAttributionResult(impression_id=impression_id, lines=(), unallocated_cents=0))

    platform_cents, ip_pool_cents = split_platform_vs_ip(ad_revenue_cents)
    router.platform_residual_cents += platform_cents

    result = split_mixed_attribution(MixedAttributionInput(
        impression_id=impression_id,
        ip_holder_pool_cents=ip_pool_cents,
        attribution_shares=attribution_shares,
        document_to_recipient=document_to_recipient,
    ))
    # Unallocated rounding residual goes to the platform residual.
    router.platform_residual_cents += result.unallocated_cents

    outcomes: list[PayoutOutcome] = []
    for line in result.lines:
        account = router.accounts.get(line.recipient_ref)
        if verdict.kind == FraudVerdictKind.REVIEW:
            router.operations_log.append_intent(
                op_type="payout_review",
                amount_usd_cents=line.amount_cents,
                substrate_ref=line.recipient_ref,
                idempotency_key=_idem_key(impression_id, line.recipient_ref),
                metadata={"verdict_id": verdict.verdict_id, "kind": line.kind},
            )
            outcomes.append(PayoutOutcome(
                recipient_ref=line.recipient_ref,
                kind=line.kind,
                amount_cents=line.amount_cents,
                status="escrowed",
                notes=f"verdict=REVIEW awaiting operator decision",
            ))
            continue

        # PASS — accrue, then evaluate threshold + KYC.
        accrue(
            router.rollover_ledger,
            recipient_ref=line.recipient_ref,
            cents=line.amount_cents,
            current_month_index=current_month_index,
        )

        if account is None or account.status != StripeAccountStatus.ACTIVE:
            outcomes.append(PayoutOutcome(
                recipient_ref=line.recipient_ref,
                kind=line.kind,
                amount_cents=line.amount_cents,
                status="kyc_pending",
                notes="account not ACTIVE; accrued in rollover ledger",
            ))
            continue

        state, settled_cents = settle_or_rollover(
            router.rollover_ledger,
            recipient_ref=line.recipient_ref,
            current_month_index=current_month_index,
        )
        if state == RolloverState.SETTLED and settled_cents > 0:
            idem = _idem_key(impression_id, line.recipient_ref)
            entry = router.operations_log.append_intent(
                op_type=f"{line.kind}_payout",
                amount_usd_cents=settled_cents,
                substrate_ref=line.recipient_ref,
                idempotency_key=idem,
                metadata={"impression_id": impression_id, "verdict_id": verdict.verdict_id},
            )
            provider_ref = router.provider.transfer_to_connect(
                account_id=account.connect_account_id,
                amount_usd_cents=settled_cents,
                idempotency_key=idem,
                metadata={"impression_id": impression_id, "kind": line.kind},
            )
            router.operations_log.mark_complete(
                idempotency_key=idem,
                provider_ref=provider_ref,
            )
            outcomes.append(PayoutOutcome(
                recipient_ref=line.recipient_ref,
                kind=line.kind,
                amount_cents=settled_cents,
                status="transferred",
                provider_ref=provider_ref,
            ))
        else:
            outcomes.append(PayoutOutcome(
                recipient_ref=line.recipient_ref,
                kind=line.kind,
                amount_cents=line.amount_cents,
                status="rolled_over",
                notes=f"below {MINIMUM_PAYOUT_USD_CENTS}c threshold; rolled in ledger",
            ))

    return (outcomes, result)


# ---------------------------------------------------------------------------
# 1099 export (Sprint 30+ long-tail thread — tax-tooling integration)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaxYearRow:
    recipient_ref: str
    kind: str
    total_paid_cents: int
    transfer_refs: tuple[str, ...]


def export_tax_year(
    router: RevSharePayoutRouter,
    *,
    year: int,
) -> list[TaxYearRow]:
    """Produce a per-recipient roll-up of completed transfers for a
    tax year. Caller passes year as YYYY; entries with created_at
    starting `f"{year}-"` are aggregated. Format suitable for
    accountant-review per the Sprint 30+ tax_export.py deliverable."""
    prefix = f"{year}-"
    per: dict[tuple[str, str], list[dict]] = {}
    for entry in router.operations_log.log_entries:
        if entry["status"] != "completed":
            continue
        if not entry["completed_at"] or not entry["completed_at"].startswith(prefix):
            continue
        kind = entry["op_type"].replace("_payout", "")
        key = (entry["substrate_ref"], kind)
        per.setdefault(key, []).append(entry)
    rows: list[TaxYearRow] = []
    for (ref, kind), entries in sorted(per.items()):
        rows.append(TaxYearRow(
            recipient_ref=ref,
            kind=kind,
            total_paid_cents=sum(e["amount_usd_cents"] for e in entries),
            transfer_refs=tuple(e["provider_ref"] for e in entries if e["provider_ref"]),
        ))
    return rows
