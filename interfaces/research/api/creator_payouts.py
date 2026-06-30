"""Creator payouts API (Sprint 23-24 phase 4).

GET /creator-payouts/{recipient_ref} — accrued + paid + rollover
history for one recipient (creator or publisher). Backs the
``CreatorPayouts`` UI surface.

Substrate-side: aggregates ``payout_transfers`` rows by status and
joins against the KYC + rollover state machines so the UI can
render "you have $X accrued; $Y paid out; KYC status: COMPLETED".
"""

from __future__ import annotations

import duckdb
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

# ── Pydantic shapes ────────────────────────────────────────────────


class TransferSummaryResponse(BaseModel):
    transfer_attempt_id: str
    decision_id: str
    stripe_transfer_id: str | None
    amount_usd_cents: int
    status: str  # 'transferred' | 'skipped_escrow' | 'skipped_platform' | 'failed' | 'pending'
    note: str
    initiated_at: str


class CreatorPayoutsResponse(BaseModel):
    recipient_ref: str
    kyc_state: str | None
    rollover_balance_cents: int
    total_paid_cents: int
    total_skipped_escrow_cents: int
    total_failed_cents: int
    transfer_count: int
    transfers: list[TransferSummaryResponse]


class RolloverHistoryEntryResponse(BaseModel):
    at: str
    kind: str
    cents: int


class MePayoutTransferResponse(BaseModel):
    transfer_attempt_id: str
    stripe_transfer_id: str | None
    amount_usd_cents: int
    status: str
    initiated_at: str
    note: str | None


class MePayoutsResponse(BaseModel):
    user_id: str
    current_balance_cents: int
    minimum_payout_cents: int
    rollover_state: str
    rollover_started_month: int | None
    accrual_history: list[RolloverHistoryEntryResponse]
    transfers: list[MePayoutTransferResponse]
    total_paid_cents: int


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


def _load_kyc_state(con, recipient_ref: str) -> str | None:
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


def _load_rollover_row(con, recipient_ref: str) -> tuple[int, str, int | None, str]:
    """Return the recipient's current persisted rollover state.

    Missing row means the recipient has no active below-threshold balance.
    """
    from substrate.rev_share.rollover_persistence import ensure_table

    ensure_table(con)
    row = con.execute(
        """
        SELECT balance_cents, state, accrual_started_month,
               strftime(last_event_at, '%Y-%m-%dT%H:%M:%S')
        FROM rollover_ledger
        WHERE recipient_ref = ?
        """,
        [recipient_ref],
    ).fetchone()
    if row is None:
        return (0, "accruing", None, "")
    balance, state, started, last_event_at = row
    return (
        int(balance),
        str(state),
        int(started) if started is not None else None,
        str(last_event_at or ""),
    )


def _build_me_payouts_response(con, recipient_ref: str) -> MePayoutsResponse:
    from substrate.rev_share import MINIMUM_PAYOUT_USD_CENTS

    rows = _load_transfers(con, recipient_ref)
    rollover_balance, rollover_state, rollover_started_month, last_event_at = (
        _load_rollover_row(con, recipient_ref)
    )

    total_paid = 0
    transfers: list[MePayoutTransferResponse] = []
    for r in rows:
        (
            attempt_id, _decision_id, stripe_transfer_id,
            amount_usd_cents, status, note, initiated_at,
        ) = r
        amount = int(amount_usd_cents)
        if status == "transferred":
            total_paid += amount
        transfers.append(
            MePayoutTransferResponse(
                transfer_attempt_id=attempt_id,
                stripe_transfer_id=stripe_transfer_id,
                amount_usd_cents=amount,
                status=status,
                initiated_at=initiated_at or "",
                note=note or None,
            )
        )

    history = []
    if rollover_balance > 0:
        history.append(
            RolloverHistoryEntryResponse(
                at=last_event_at,
                kind=rollover_state,
                cents=rollover_balance,
            )
        )

    return MePayoutsResponse(
        user_id=recipient_ref,
        current_balance_cents=rollover_balance,
        minimum_payout_cents=MINIMUM_PAYOUT_USD_CENTS,
        rollover_state=rollover_state,
        rollover_started_month=rollover_started_month,
        accrual_history=history,
        transfers=transfers,
        total_paid_cents=total_paid,
    )


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

        # Rollover balance — backed by the V6 rollover_ledger table.
        # Empty / unknown recipient → 0; existing balance → live value.
        from substrate.rev_share.rollover_persistence import (
            load_balance_cents,
        )

        con2 = duckdb.connect(db, read_only=True)
        try:
            rollover_balance_cents = load_balance_cents(
                con2, recipient_ref,
            )
        finally:
            con2.close()

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

    @app.get(
        "/me/payouts",
        response_model=MePayoutsResponse,
        tags=["payouts"],
    )
    async def get_my_payouts(request: Request) -> MePayoutsResponse:
        recipient_ref = getattr(request.state, "user_id", None)
        if not recipient_ref:
            raise _refuse(
                401,
                "operator_auth_required",
                "Authentication required to read your payout ledger.",
            )
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            return _build_me_payouts_response(con, str(recipient_ref))
        finally:
            con.close()


__all__ = [
    "CreatorPayoutsResponse",
    "MePayoutsResponse",
    "TransferSummaryResponse",
    "register_creator_payouts_routes",
]
