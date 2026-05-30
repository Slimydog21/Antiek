"""Book reading-session → rights-holder escrow accrual (SPR-09).

Connects SPR-05's reader impressions to the existing economics engine:
the book's `ip_holder_id` (SPR-01), the `distribute_session_ad_revenue`
rev-share split (`substrate/ad_inventory/payout.py`), and the
`ip_holders` escrow sink. Nothing here is a new ledger or a new payout
path — it is the Read-workflow wiring over machinery that already exists.

The two load-bearing invariants:

1. **Accrual is not disbursement.** This module ACCRUES into escrow. It
   has no Stripe call, no disbursement path. Whether escrow ever pays out
   is `ip_holders` status == 'claimed' (the §9.10 gate, gated on G2 lawyer
   review + G3 publisher opt-in) — read here via `is_disbursement_unlocked`,
   never bypassed. There is deliberately no function in this module that
   can move money out.

2. **Zero buyers shows $0, not invented money.** With no ad revenue, the
   session accrues nothing to escrow (the dollar balance is honestly $0);
   the attention-share — how many slots earned focused dwell — is tracked
   as a fairness ledger, separate from dollars. The "revolutionize
   economics" intent lives in the machinery + the share, not in fabricated
   balances (rigor #1).

Unknown rights holder: a book with `ip_holder_id IS NULL` accrues to a
flagged unattributed bucket (`UNATTRIBUTED_RIGHTS_BUCKET`), never to a
wrong holder, and never disburses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from substrate import ip_holders
from substrate.ad_inventory.payout import (
    PayoutRouter,
    RevShareKind,
    distribute_session_ad_revenue,
)
from substrate.ad_inventory.reader_impressions import (
    ReaderImpression,
    dedup_impressions,
    total_revenue_cents,
)
from substrate.constants import UNATTRIBUTED_RIGHTS_BUCKET
from substrate.event_log import emit_typed
from substrate.schemas.events import RevShareDecidedPayload

# Matches the sibling acquisition modules' convention (explicit dotted name,
# e.g. acquisition/arxiv/store.py). Used to make a failure in the additive
# author-attribution hook AUDITABLE — a silent swallow there would drop
# per-author accrual that feeds researcher payouts with no trace (§9
# traceability / defensibility), so the drop is logged while the escrow path
# stays defensively isolated.
logger = logging.getLogger("substrate.marketplace_metrics.book_escrow")


@dataclass(frozen=True)
class AccrualResult:
    """Outcome of accruing one reading session for one book.

    ``ip_holder_id`` is the resolved rights holder, or
    ``UNATTRIBUTED_RIGHTS_BUCKET`` when the book has none.
    ``accrued_to_escrow_cents`` is what actually landed in escrow (0 for
    zero-buyer sessions and for the unattributed bucket).
    ``attention_impressions`` is the fairness-ledger count — slots that
    earned focused dwell — tracked even when revenue is $0."""

    document_id: str
    ip_holder_id: str
    revenue_cents: int
    accrued_to_escrow_cents: int
    attention_impressions: int
    unattributed: bool
    reason: str


def _resolve_ip_holder(con: Any, document_id: str) -> Optional[str]:
    row = con.execute(
        "SELECT ip_holder_id FROM documents WHERE document_id = ?", [document_id]
    ).fetchone()
    if row is None:
        return None
    return row[0]


def _accrue_payouts_ledger(
    con: Any,
    *,
    document_id: str,
    revenue_cents: int,
    session_id: str,
    impression_ids: list[str],
) -> None:
    """Thin, additive hook into the SPR-06 internal author-attribution ledger.

    The ad-event id is the SAME stable per-session-per-document key the existing
    rev-share split uses (``session:{session_id}:{document_id}``). That key is
    per-session-CONSTANT, but the reader posts impressions INCREMENTALLY (one
    page-flush at a time), so a constant key alone would mis-dedup two disjoint
    page-flush batches that earned EQUAL revenue and DROP the second. To conserve
    against that incremental-posting model we ALSO pass this batch's underlying
    impression-id set (``impression_ids`` — derived from the same deduped
    ``book_imps`` the escrow path sums), making the ledger's dedup unit the
    impression set: disjoint batches (different slots/pages → different
    impression ids) are DISTINCT events that both accrue, while a true retry of
    the SAME impressions stays a no-op on both sides.

    The ledger applies the T1 gate (re-derived from the immutable license_uri),
    the arXiv check, and the zero-revenue check itself, so this is safe to call
    for every book session — non-arXiv / T2 / T3 / zero-revenue emit nothing.
    It writes NO escrow. Defensive: a failure in the additive attribution layer
    must NEVER break the existing escrow accrual, so it is isolated — but the
    drop is LOGGED (never silently swallowed), because this ledger feeds
    researcher payouts and a systematic attribution failure must be auditable."""
    try:
        from substrate.payouts.ledger import accrue_paper_read

        accrue_paper_read(
            con,
            document_id=document_id,
            revenue_cents=revenue_cents,
            ad_event_id=f"session:{session_id}:{document_id}",
            impression_ids=impression_ids,
        )
    except Exception:
        # Internal accounting only — never let it disturb the escrow path, but
        # make the drop VISIBLE so a systematic attribution-layer failure is
        # auditable (it feeds researcher payouts — §9 traceability).
        logger.exception(
            "payouts-ledger accrual failed for document_id=%s session_id=%s; "
            "escrow path unaffected",
            document_id,
            session_id,
        )


def accrue_reading_session(
    con: Any,
    *,
    document_id: str,
    impressions: list[ReaderImpression],
    session_id: str,
    router: Optional[PayoutRouter] = None,
) -> AccrualResult:
    """Accrue a book reading session's ad revenue into the book's rights-
    holder escrow. ``con`` must be a write-locked connection (escrow write
    is single-writer; reconciliation reads the same connection).

    Deterministic + dedup-safe: impressions are deduped by
    ``impression_id`` before summing, so re-emitted impressions can't
    inflate the accrual (reconciliation invariant, SPR-09 M4).
    """
    deduped = dedup_impressions(impressions)
    # Only this book's impressions count toward this book's accrual.
    book_imps = [i for i in deduped if i.document_id == document_id]
    revenue_cents = total_revenue_cents(book_imps)
    attention = sum(1 for i in book_imps if i.counted_attention)

    # SPR-06 (arxiv-ingest) — additive internal author-attribution hook.
    # For a T1 arXiv paper, ALSO accrue this session's ad revenue to the
    # INTERNAL (arxiv_id, author_position) payouts ledger (an additive
    # accounting layer over the SAME revenue — both HOLD, neither disburses, so
    # no double-count of disbursable money). The ledger re-derives the T1 tier
    # itself and emits nothing for non-arXiv / T2 / T3 / zero-revenue, so this
    # is safe to call unconditionally. It writes NO escrow. Wrapped so an
    # attribution-layer failure can never break the existing escrow accrual.
    #
    # Pass this batch's deduped impression-id set so the ledger's idempotency
    # unit is the underlying impression set — the SAME dedup principle the escrow
    # path uses (each impression counted once). The reader flushes impressions
    # INCREMENTALLY under a constant session ad_event_id, so two disjoint
    # page-flush batches that earn equal revenue must be DISTINCT ledger events
    # (both accrue), while a true retry of the same impressions stays a no-op.
    _accrue_payouts_ledger(
        con, document_id=document_id, revenue_cents=revenue_cents,
        session_id=session_id,
        impression_ids=sorted(i.impression_id for i in book_imps),
    )

    holder_id = _resolve_ip_holder(con, document_id)
    unattributed = holder_id is None
    bucket = holder_id if holder_id is not None else UNATTRIBUTED_RIGHTS_BUCKET

    # Zero-buyer OR unattributed → no escrow write. Track the share; show $0.
    if revenue_cents <= 0:
        return AccrualResult(
            document_id=document_id, ip_holder_id=bucket, revenue_cents=0,
            accrued_to_escrow_cents=0, attention_impressions=attention,
            unattributed=unattributed,
            reason="zero_buyer_attention_share_only" if not unattributed
            else "zero_buyer_unattributed",
        )
    if unattributed:
        # Real revenue but unknown holder: it stays in the flagged bucket,
        # un-accrued to any escrow account, until the rights holder is
        # resolved. Never accrue to a wrong holder.
        return AccrualResult(
            document_id=document_id, ip_holder_id=UNATTRIBUTED_RIGHTS_BUCKET,
            revenue_cents=revenue_cents, accrued_to_escrow_cents=0,
            attention_impressions=attention, unattributed=True,
            reason="unattributed_revenue_held",
        )

    # Reuse the existing rev-share split. The book's rights holder is a
    # PUBLISHER recipient with escrow; the platform takes its cut per the
    # existing policy. We attribute the whole session to this one book.
    router = router or PayoutRouter()
    decisions = distribute_session_ad_revenue(
        router,
        impression_id=f"session:{session_id}:{document_id}",
        ad_revenue_usd_cents=revenue_cents,
        attribution_shares={document_id: 1.0},
        document_to_recipient={
            document_id: (RevShareKind.PUBLISHER, holder_id, True)
        },
    )

    accrued = 0
    for d in decisions:
        if d.kind is RevShareKind.PUBLISHER and d.recipient_ref == holder_id:
            if d.amount_usd_cents > 0:
                # Accrue into the EXISTING escrow. accrue_escrow takes USD;
                # convert cents → Decimal dollars.
                ip_holders.accrue_escrow(
                    con, holder_id, Decimal(d.amount_usd_cents) / Decimal(100)
                )
                accrued += d.amount_usd_cents
        # Audit every decision (publisher + platform) for §13.7.
        emit_typed(
            f"read-session-{session_id}",
            RevShareDecidedPayload(
                decision_id=d.decision_id,
                impression_id=d.impression_id,
                kind=d.kind.value,
                recipient_ref=d.recipient_ref,
                amount_usd_cents=d.amount_usd_cents,
                document_id_ref=d.document_id,
                requires_escrow=d.requires_escrow,
                capped_to_daily_limit=d.capped_to_daily_limit,
            ),
            document_id=document_id,
            role="read/books",
            policy_id="read/books/escrow_accrual",
        )

    return AccrualResult(
        document_id=document_id, ip_holder_id=holder_id,
        revenue_cents=revenue_cents, accrued_to_escrow_cents=accrued,
        attention_impressions=attention, unattributed=False,
        reason="accrued_to_publisher_escrow",
    )


def is_disbursement_unlocked(con: Any, ip_holder_id: str) -> bool:
    """Whether the rights holder's escrow may pay out. Reads the EXISTING
    §9.10 gate: payouts unlock only at ``status='claimed'`` (which itself
    gates on G2 lawyer review + G3 publisher opt-in). This module exposes
    the gate read-only; it never flips it and never disburses. The
    unattributed bucket is never a real ip_holder and never unlocks."""
    if ip_holder_id == UNATTRIBUTED_RIGHTS_BUCKET:
        return False
    holder = ip_holders.get(con, ip_holder_id)
    return holder is not None and holder.status == "claimed"
