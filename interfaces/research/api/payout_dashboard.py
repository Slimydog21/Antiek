"""Operator payout dashboard API.

Read-only rollup for the PayoutDashboard UI. This endpoint observes transfer,
publisher escrow, KYC, and rollover state; it never initiates a transfer or
mutates escrow.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class RevenueLineResponse(BaseModel):
    recipient_kind: Literal["creator", "publisher"]
    recipient_ref: str
    recipient_name: str
    current_month_cents: int
    lifetime_cents: int
    status: str
    kyc_complete: bool


class PayoutDashboardResponse(BaseModel):
    current_month_label: str
    lines: list[RevenueLineResponse]
    platform_residual_month_cents: int
    unallocated_rounding_month_cents: int


class PayoutDashboardSourceError(RuntimeError):
    """Raised when dashboard source tables cannot be read honestly."""


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _month_start() -> datetime:
    now = datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC)


def _normalize_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _latest_kyc_states(con) -> dict[str, str]:
    try:
        rows = con.execute(
            """
            SELECT recipient_ref, state
            FROM (
                SELECT recipient_ref, state,
                       ROW_NUMBER() OVER (
                         PARTITION BY recipient_ref
                         ORDER BY row_inserted_at DESC
                       ) AS rn
                FROM kyc_status
            )
            WHERE rn = 1
            """
        ).fetchall()
    except Exception as exc:
        raise PayoutDashboardSourceError("could not read latest KYC states") from exc
    return {str(ref): str(state) for ref, state in rows}


def _publisher_rows(con) -> dict[str, tuple[str, str]]:
    try:
        rows = con.execute(
            "SELECT ip_holder_id, display_name, status FROM ip_holders"
        ).fetchall()
    except Exception as exc:
        raise PayoutDashboardSourceError("could not read publisher rows") from exc
    return {str(row[0]): (str(row[1]), str(row[2])) for row in rows}


def _rollover_rows(con) -> dict[str, tuple[int, str]]:
    try:
        rows = con.execute(
            "SELECT recipient_ref, balance_cents, state FROM rollover_ledger"
        ).fetchall()
    except Exception as exc:
        raise PayoutDashboardSourceError("could not read rollover ledger") from exc
    return {str(ref): (int(balance), str(state)) for ref, balance, state in rows}


def _transfer_rows(con) -> list[tuple]:
    try:
        return con.execute(
            """
            SELECT recipient_account_id, amount_usd_cents, status, initiated_at
            FROM payout_transfers
            ORDER BY initiated_at DESC
            """
        ).fetchall()
    except Exception as exc:
        raise PayoutDashboardSourceError("could not read payout transfers") from exc


def _line_status(
    *,
    recipient_kind: Literal["creator", "publisher"],
    recipient_ref: str,
    publisher_statuses: dict[str, tuple[str, str]],
    kyc_states: dict[str, str],
    rollover_state: str | None,
) -> tuple[str, bool]:
    if rollover_state == "forfeited":
        return ("forfeited", False)
    if recipient_kind == "publisher":
        status = publisher_statuses.get(recipient_ref, ("", "pre_onboarded"))[1]
        if status == "claimed":
            return ("active", True)
        return ("escrow_only", False)
    kyc_complete = kyc_states.get(recipient_ref) == "completed"
    return ("active" if kyc_complete else "pending_kyc", kyc_complete)


def _build_dashboard(con) -> PayoutDashboardResponse:
    month_start = _month_start()
    publishers = _publisher_rows(con)
    kyc_states = _latest_kyc_states(con)
    rollovers = _rollover_rows(con)

    current_by_ref: defaultdict[str, int] = defaultdict(int)
    lifetime_by_ref: defaultdict[str, int] = defaultdict(int)
    platform_residual_month = 0

    for recipient_ref, amount, status, initiated_at in _transfer_rows(con):
        cents = int(amount)
        dt = _normalize_dt(initiated_at)
        in_current_month = dt is not None and dt >= month_start
        if status == "skipped_platform":
            if in_current_month:
                platform_residual_month += cents
            continue
        if status == "failed" or recipient_ref is None:
            continue
        ref = str(recipient_ref)
        lifetime_by_ref[ref] += cents
        if in_current_month:
            current_by_ref[ref] += cents

    for ref, (balance, state) in rollovers.items():
        if balance <= 0:
            continue
        lifetime_by_ref.setdefault(ref, 0)
        current_by_ref.setdefault(ref, 0)
        if state == "forfeited":
            platform_residual_month += balance
        else:
            lifetime_by_ref[ref] += balance
            current_by_ref[ref] += balance

    lines: list[RevenueLineResponse] = []
    for ref in sorted(lifetime_by_ref):
        kind: Literal["creator", "publisher"] = (
            "publisher" if ref in publishers else "creator"
        )
        name = publishers[ref][0] if kind == "publisher" else ref
        rollover_state = rollovers.get(ref, (0, ""))[1] or None
        status, kyc_complete = _line_status(
            recipient_kind=kind,
            recipient_ref=ref,
            publisher_statuses=publishers,
            kyc_states=kyc_states,
            rollover_state=rollover_state,
        )
        lines.append(
            RevenueLineResponse(
                recipient_kind=kind,
                recipient_ref=ref,
                recipient_name=name,
                current_month_cents=current_by_ref[ref],
                lifetime_cents=lifetime_by_ref[ref],
                status=status,
                kyc_complete=kyc_complete,
            )
        )

    return PayoutDashboardResponse(
        current_month_label=month_start.strftime("%Y-%m"),
        lines=lines,
        platform_residual_month_cents=platform_residual_month,
        unallocated_rounding_month_cents=0,
    )


def register_payout_dashboard_routes(app: FastAPI) -> None:
    @app.get(
        "/operator/payouts/dashboard",
        response_model=PayoutDashboardResponse,
        tags=["payouts"],
    )
    async def get_operator_payout_dashboard() -> PayoutDashboardResponse:
        from runtime.db_lock import connect_read

        try:
            with connect_read(_resolve_db_path()) as con:
                return _build_dashboard(con)
        except Exception as exc:
            message = (
                str(exc)
                if isinstance(exc, PayoutDashboardSourceError)
                else "could not initialize payout dashboard sources"
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "payout_dashboard_source_unavailable",
                        "message": message,
                    }
                },
            ) from exc


__all__ = [
    "PayoutDashboardResponse",
    "PayoutDashboardSourceError",
    "RevenueLineResponse",
    "register_payout_dashboard_routes",
]
