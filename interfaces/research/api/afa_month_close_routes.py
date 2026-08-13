"""AFA month-close HTTP surface (escrow-only; read + operator close).

Completes the S6 M4 surface that the CLI-only scope deferred: owner-scoped
endpoints to (1) run a month close, (2) read the published close record +
month root, (3) fetch a per-payee statement with its inclusion proof
(server-side verified before returning). No payout path; accrual ledger
only. The close itself is idempotent (statements_digest gate) and refuses
mutated ledgers, per sprint-06.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from pydantic import BaseModel

from runtime.db_lock import connect_write
from substrate.ad_inventory.monthly_close import (
    CloseError,
    CloseInconsistentError,
    close_month,
    get_root,
    load_close,
    parse_period,
    verify_statement_against_root,
)
from substrate.graph import default_db_path

_afa_router = APIRouter(prefix="/ops/afa/month-close", tags=["afa-month-close"])


def _owner(request: Request) -> str:
    """Owner identity: middleware-populated user_id, else the operator."""
    return str(getattr(request.state, "user_id", None) or "__operator__")


def _load_statement(period: str, payee_id: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Load a persisted statement + proof from the artifact dir.

    Returns (statement, proof, root_hex). Raises HTTPException when the
    close or the artifact is missing.
    """
    db = default_db_path()
    with connect_write(db, purpose="afa/month-close/read") as con:
        root = get_root(con, period)
        rec = load_close(con, period)
    if root is None or rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"month {period} has not been closed",
        )
    import json
    from pathlib import Path

    artifact_dir = Path(rec["artifact_dir"])
    stmt_path = artifact_dir / "statements" / f"{_safe(payee_id)}.json"
    proof_path = artifact_dir / "proofs" / f"{_safe(payee_id)}.json"
    if not stmt_path.is_file() or not proof_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"statement for payee {payee_id!r} not found for {period}",
        )
    statement = json.loads(stmt_path.read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    return statement, proof, root


def _safe(payee_id: str) -> str:
    """Mirror monthly_close._safe_filename: artifact-safe payee id."""
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in payee_id)


class MonthCloseResponse(BaseModel):
    period: str
    month_root_hex: str
    statement_count: int
    total_payee_cents: int
    total_house_cents: int
    total_window_cents: int
    attribution_math_version: str
    month_close_version: str
    merkle_serialization: str
    statements_digest: str
    artifact_dir: str
    closed_at: str


class StatementWithProof(BaseModel):
    period: str
    payee_id: str
    verified: bool
    root_hex: str
    statement: dict[str, Any]
    proof: dict[str, Any]


@_afa_router.get("/{period}", response_model=MonthCloseResponse)
async def get_month_close(period: str, request: Request) -> MonthCloseResponse:
    """Read the published close record for a month (escrow-only, read-only)."""
    _owner(request)  # auth assertion
    try:
        parse_period(period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db = default_db_path()
    with connect_write(db, purpose="afa/month-close/read") as con:
        rec = load_close(con, period)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"month {period} has not been closed")
    return MonthCloseResponse(**rec)


@_afa_router.post("/{period}", response_model=MonthCloseResponse, status_code=201)
async def run_month_close(period: str, request: Request) -> MonthCloseResponse:
    """Run (or idempotently re-run) a month close. Escrow-only accrual."""
    _owner(request)  # auth assertion (escrow-only surface)
    try:
        parse_period(period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db = default_db_path()
    try:
        with connect_write(db, purpose="afa/month-close/close") as con:
            close_month(con, period)
            rec = load_close(con, period)
    except CloseInconsistentError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"ledger mutated since close; refusing silent rewrite: {exc}",
        ) from exc
    except CloseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if rec is None:
        raise HTTPException(status_code=500, detail="close did not persist a record")
    return MonthCloseResponse(**rec)


@_afa_router.get("/{period}/statement/{payee_id}", response_model=StatementWithProof)
async def get_statement(period: str, payee_id: str, request: Request) -> StatementWithProof:
    """Fetch a per-payee statement + inclusion proof, server-verified."""
    _owner(request)  # auth assertion
    try:
        parse_period(period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    statement, proof, root = _load_statement(period, payee_id)
    verified = verify_statement_against_root(statement, proof, root)
    return StatementWithProof(
        period=period,
        payee_id=payee_id,
        verified=verified,
        root_hex=root,
        statement=statement,
        proof=proof,
    )


def register_afa_month_close_routes(app: FastAPI) -> None:
    """Register the escrow-only month-close surface."""
    app.include_router(_afa_router)
