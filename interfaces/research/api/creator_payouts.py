"""Creator payouts API (Sprint 23-24 phase 4).

GET /creator-payouts/{recipient_ref} — accrued + paid + rollover
history for one recipient (creator or publisher). Backs the
``CreatorPayouts`` UI surface.

Substrate-side: aggregates ``payout_transfers`` rows by status and
joins against the KYC + rollover state machines so the UI can
render "you have $X accrued; $Y paid out; KYC status: COMPLETED".
"""

from __future__ import annotations

from typing import Optional

import duckdb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


# ── Pydantic shapes ────────────────────────────────────────────────


class TransferSummaryResponse(BaseModel):
    transfer_attempt_id: str
    decision_id: str
    stripe_transfer_id: Optional[str]
    amount_usd_cents: int
    status: str  # 'transferred' | 'skipped_escrow' | 'skipped_platform' | 'failed' | 'pending'
    note: str
    initiated_at: str


class CreatorPayoutsResponse(BaseModel):
    recipient_ref: str
    kyc_state: Optional[str]
    rollover_balance_cents: int
    total_paid_cents: int
    total_skipped_escrow_cents: int
    total_failed_cents: int
    transfer_count: int
    transfers: list[TransferSummaryResponse]


def _refuse(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _load_kyc_state(con, recipient_ref: str) -> Optional[str]:
    """Read the latest kyc_status row for the recipient."""
    try:
        row = con.execute(
            "SELECT state FROM kyc_status WHERE recipient_ref = ? "
            "ORDER BY row_inserted_at DESC LIMIT 1",
            [recipient_ref],
        ).fetchone()
    except duckdb.Error:
        return None
    return row[0] if row else None


def _load_transfers(con, recipient_ref: str) -> list[tuple]:
    """Load every transfer attempt routed to the recipient. Filters
    by ``recipient_account_id`` matching the recipient_ref (the
    substrate uses the user_id / ip_holder_id as the Stripe Connect
    account_id; integration layer is responsible for the mapping)."""
    try:
        rows = con.execute(
            "SELECT transfer_attempt_id, decision_id, stripe_transfer_id, "
            "amount_usd_cents, status, note, "
            "strftime(initiated_at, '%Y-%m-%dT%H:%M:%S') "
            "FROM payout_transfers WHERE recipient_account_id = ? "
            "ORDER BY initiated_at DESC",
            [recipient_ref],
        ).fetchall()
    except duckdb.Error:
        return []
    return rows


def register_creator_payouts_routes(app: FastAPI) -> None:
    """Mount the creator-payouts endpoint."""

    @app.get(
        "/creator-payouts/{recipient_ref}",
        response_model=CreatorPayoutsResponse,
        tags=["payouts"],
    )
    async def get_creator_payouts(
        recipient_ref: str,
    ) -> CreatorPayoutsResponse:
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            kyc_state = _load_kyc_state(con, recipient_ref)
            rows = _load_transfers(con, recipient_ref)
        finally:
            con.close()

        total_paid = 0
        total_skipped_escrow = 0
        total_failed = 0
        transfers: list[TransferSummaryResponse] = []
        for r in rows:
            (
                attempt_id, decision_id, stripe_transfer_id,
                amount_usd_cents, status, note, initiated_at,
            ) = r
            amount = int(amount_usd_cents)
            if status == "transferred":
                total_paid += amount
            elif status == "skipped_escrow":
                total_skipped_escrow += amount
            elif status == "failed":
                total_failed += amount
            transfers.append(TransferSummaryResponse(
                transfer_attempt_id=attempt_id,
                decision_id=decision_id,
                stripe_transfer_id=stripe_transfer_id,
                amount_usd_cents=amount,
                status=status,
                note=note or "",
                initiated_at=initiated_at or "",
            ))

        # Rollover balance — substrate's rollover_ledger is in-memory
        # by design (the persistent layer is per-recipient ledger
        # rows in a future schema chunk). Returns 0 here; the operator
        # CLI exposes the real balance.
        rollover_balance_cents = 0

        return CreatorPayoutsResponse(
            recipient_ref=recipient_ref,
            kyc_state=kyc_state,
            rollover_balance_cents=rollover_balance_cents,
            total_paid_cents=total_paid,
            total_skipped_escrow_cents=total_skipped_escrow,
            total_failed_cents=total_failed,
            transfer_count=len(transfers),
            transfers=transfers,
        )


__all__ = [
    "CreatorPayoutsResponse",
    "TransferSummaryResponse",
    "register_creator_payouts_routes",
]
