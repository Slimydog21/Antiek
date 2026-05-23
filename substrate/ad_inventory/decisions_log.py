"""Payout decisions audit log (Sprint 23-24 phase 2 / §13.7 audit).

Persists every ``RevShareDecision`` the PayoutRouter emits to the
``payout_decisions`` table (V6 schema chunk). Without this, decisions
computed by ``distribute_session_ad_revenue`` live only in the
in-memory router and die when the request returns — the audit trail
is broken.

The persisted row carries an additional ``gate_result`` field that
records WHY the decision was admitted (or NOT admitted) so the
operator can audit §9.5 KYC enforcement + §9.7 anti-gaming
enforcement directly from the log.

Joined against ``payout_transfers`` (V4) at audit time to show the
full chain: impression → decision (this table) → transfer attempt
(V4 table) → Stripe transfer id.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Optional

from .payout import RevShareDecision, RevShareKind


class DecisionGate(str, enum.Enum):
    """Why the substrate let (or didn't let) a decision through.

    Persisted as the ``gate_result`` column on ``payout_decisions``;
    CHECK-constrained at the SQL layer so the vocabulary stays in
    sync."""

    # Substrate cleared the recipient for settlement at this amount.
    # Below §9.5 floor → no KYC check needed.
    # At/above §9.5 floor → KYC was COMPLETED.
    # AntiGaming verdict was PASS.
    ADMITTED = "admitted"

    # Amount was below §9.5 $10 floor; rolls over without leaving
    # escrow (no KYC check needed, no transfer initiated).
    ROLLED_OVER = "rolled_over"

    # Above §9.5 floor BUT KYC not COMPLETED. Decision recorded
    # for audit but no transfer should be initiated.
    GATED_KYC = "gated_kyc"

    # AntiGaming returned BLOCK. Decision recorded with zero
    # transfer; the impression was flagged as fraudulent before
    # money could route.
    GATED_FRAUD = "gated_fraud"


@dataclass(frozen=True)
class PersistedDecisionRow:
    """One row from the persisted log. Returned by ``load_for_impression``
    and ``load_for_recipient`` queries."""

    decision_id: str
    impression_id: str
    kind: str
    recipient_ref: str
    amount_usd_cents: int
    document_id: Optional[str]
    requires_escrow: bool
    capped_to_daily_limit: bool
    gate_result: str
    decided_at: str


def ensure_table(con: Any) -> None:
    """Defensive table create. Canonical schema in
    ``substrate/graph/schema.py`` V6 chunk."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS payout_decisions (
                decision_id               TEXT PRIMARY KEY,
                impression_id             TEXT NOT NULL,
                kind                      TEXT NOT NULL CHECK (kind IN (
                    'creator', 'publisher', 'platform'
                )),
                recipient_ref             TEXT NOT NULL,
                amount_usd_cents          INTEGER NOT NULL CHECK (amount_usd_cents >= 0),
                document_id               TEXT,
                requires_escrow           BOOLEAN NOT NULL DEFAULT FALSE,
                capped_to_daily_limit     BOOLEAN NOT NULL DEFAULT FALSE,
                gate_result               TEXT NOT NULL DEFAULT 'admitted'
                    CHECK (gate_result IN (
                        'admitted', 'rolled_over', 'gated_kyc', 'gated_fraud'
                    )),
                decided_at                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception:
        pass


def persist_decision(
    con: Any,
    decision: RevShareDecision,
    *,
    gate: DecisionGate = DecisionGate.ADMITTED,
) -> str:
    """Insert one decision row. Idempotent on ``decision_id`` —
    re-saving the same decision_id is a no-op + returns the existing
    decision_id (matching the existing ``transfer_initiator._record``
    posture)."""
    ensure_table(con)
    existing = con.execute(
        "SELECT decision_id FROM payout_decisions WHERE decision_id = ?",
        [decision.decision_id],
    ).fetchone()
    if existing is not None:
        return decision.decision_id
    con.execute(
        """
        INSERT INTO payout_decisions (
            decision_id, impression_id, kind, recipient_ref,
            amount_usd_cents, document_id, requires_escrow,
            capped_to_daily_limit, gate_result
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            decision.decision_id, decision.impression_id,
            decision.kind.value, decision.recipient_ref,
            decision.amount_usd_cents, decision.document_id,
            decision.requires_escrow, decision.capped_to_daily_limit,
            gate.value,
        ],
    )
    return decision.decision_id


def persist_decisions(
    con: Any,
    decisions: list[RevShareDecision],
    *,
    gate_by_decision: Optional[dict[str, DecisionGate]] = None,
) -> int:
    """Bulk persist. Returns the count of newly-inserted rows
    (existing rows count as 0 — idempotent semantics).

    ``gate_by_decision`` maps decision_id → DecisionGate; defaults
    to ADMITTED for every decision the caller doesn't specify. The
    PayoutRouter caller is responsible for marking gated_kyc /
    gated_fraud explicitly."""
    inserted = 0
    gate_map = gate_by_decision or {}
    for d in decisions:
        gate = gate_map.get(d.decision_id, DecisionGate.ADMITTED)
        before = con.execute(
            "SELECT count(*) FROM payout_decisions WHERE decision_id = ?",
            [d.decision_id],
        ).fetchone()[0]
        persist_decision(con, d, gate=gate)
        after = con.execute(
            "SELECT count(*) FROM payout_decisions WHERE decision_id = ?",
            [d.decision_id],
        ).fetchone()[0]
        inserted += int(after) - int(before)
    return inserted


def load_for_impression(
    con: Any, impression_id: str,
) -> list[PersistedDecisionRow]:
    """Audit query: every decision emitted for one impression."""
    ensure_table(con)
    rows = con.execute(
        """
        SELECT decision_id, impression_id, kind, recipient_ref,
               amount_usd_cents, document_id, requires_escrow,
               capped_to_daily_limit, gate_result,
               strftime(decided_at, '%Y-%m-%dT%H:%M:%S')
        FROM payout_decisions
        WHERE impression_id = ?
        ORDER BY decided_at, decision_id
        """,
        [impression_id],
    ).fetchall()
    return [_row_to_decision(r) for r in rows]


def load_for_recipient(
    con: Any, recipient_ref: str, *, limit: int = 200,
) -> list[PersistedDecisionRow]:
    """Audit query: most-recent decisions for one recipient."""
    ensure_table(con)
    rows = con.execute(
        """
        SELECT decision_id, impression_id, kind, recipient_ref,
               amount_usd_cents, document_id, requires_escrow,
               capped_to_daily_limit, gate_result,
               strftime(decided_at, '%Y-%m-%dT%H:%M:%S')
        FROM payout_decisions
        WHERE recipient_ref = ?
        ORDER BY decided_at DESC, decision_id
        LIMIT ?
        """,
        [recipient_ref, limit],
    ).fetchall()
    return [_row_to_decision(r) for r in rows]


def _row_to_decision(r: tuple) -> PersistedDecisionRow:
    return PersistedDecisionRow(
        decision_id=r[0],
        impression_id=r[1],
        kind=r[2],
        recipient_ref=r[3],
        amount_usd_cents=int(r[4]),
        document_id=r[5],
        requires_escrow=bool(r[6]),
        capped_to_daily_limit=bool(r[7]),
        gate_result=r[8],
        decided_at=r[9] or "",
    )


__all__ = [
    "DecisionGate",
    "PersistedDecisionRow",
    "ensure_table",
    "load_for_impression",
    "load_for_recipient",
    "persist_decision",
    "persist_decisions",
]
