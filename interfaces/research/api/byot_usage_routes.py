"""BYOT per-key usage/balance HTTP endpoints — owner-scoped.

Exposes the usage ledger + balance adapters over HTTP so the dashboard
and model dropdown can show per-key usage and remaining balance.

Three endpoints, all scoped to the session user's ``owner_user_id``:

- ``GET /settings/usage`` — per-key usage snapshot.
- ``POST /settings/usage/{api_key_id}/limit`` — set a key's spend cap.
- ``GET /settings/balance/{api_key_id}`` — live balance from the
  provider adapter (or ``unavailable`` on degrade).

Every endpoint enforces owner-scoping: a user never sees another
user's keys (→ 404 on cross-user id).
"""

from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from interfaces.research.api.settings_models_admin import (
    _load_registry,
    request_owner_user_id,
)
from runtime.byok.secret_str import SecretStr
from runtime.byok.store import load_credential
from substrate.byot_usage.balance.base import BalanceSnapshot
from substrate.byot_usage.balance.deepseek import fetch_deepseek_balance
from substrate.byot_usage.balance.kimi import fetch_kimi_balance
from substrate.byot_usage.balance.spend_history import fetch_spend_history_balance
from substrate.byot_usage.ledger import ByotUsageLedger, KeyUsageRow

__all__ = [
    "byot_usage_router",
    "register_byot_usage_routes",
]

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class KeyUsageEntry(BaseModel):
    """One key's usage state."""

    api_key_id: str
    used_cents: int
    limit_cents: int | None
    remaining_cents: int | None


class UsageSnapshotResponse(BaseModel):
    """``GET /settings/usage`` response."""

    keys: list[KeyUsageEntry]
    count: int


class SetLimitRequest(BaseModel):
    """``POST /settings/usage/{api_key_id}/limit`` body."""

    limit_cents: int | None = Field(
        default=None,
        ge=0,
        description="Spend cap in cents, or null to clear.",
    )


class SetLimitResponse(BaseModel):
    """``POST /settings/usage/{api_key_id}/limit`` response."""

    api_key_id: str
    limit_cents: int | None
    used_cents: int
    remaining_cents: int | None


BalanceKind = Literal[
    "balance_native",
    "spend_history",
    "quota_pct",
    "meter_only",
    "unavailable",
]


class BalanceResponse(BaseModel):
    """``GET /settings/balance/{api_key_id}`` response.

    Mirrors ``BalanceSnapshot`` with the owning ``api_key_id`` attached.
    When the adapter degrades, ``kind`` is ``"unavailable"`` and ``note``
    carries the honest reason.
    """

    api_key_id: str
    catalog_id: str
    kind: BalanceKind
    balance_usd: float | None = None
    granted_usd: float | None = None
    spend_usd: float | None = None
    budget_usd: float | None = None
    utilization: float | None = None
    window_label: str | None = None
    resets_at: int | None = None
    note: str | None = None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

byot_usage_router = APIRouter(prefix="/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Dependency seams (monkeypatch targets for tests)
# ---------------------------------------------------------------------------


def _get_ledger() -> ByotUsageLedger:
    """Return the production ledger instance.  Monkeypatch in tests."""
    return ByotUsageLedger()


def _load_key(cred_ref: str) -> SecretStr:
    """Decrypt a credential from the BYOK store.  Monkeypatch in tests."""
    return load_credential(cred_ref)


def _fetch_balance(
    *,
    catalog_id: str,
    key: SecretStr,
    base_url: str,
    ledger: ByotUsageLedger,
    api_key_id: str,
    owner_user_id: str,
) -> BalanceSnapshot:
    """Dispatch to the right balance adapter by ``catalog_id``.

    Providers with a native balance endpoint get their dedicated adapter;
    everything else falls back to the spend-history adapter (client-side
    meter).  Monkeypatch in tests to avoid live net.
    """
    native_adapters: dict[str, Any] = {
        "deepseek": fetch_deepseek_balance,
        "kimi": fetch_kimi_balance,
    }
    adapter_fn = native_adapters.get(catalog_id)
    if adapter_fn is not None:
        try:
            with httpx.Client(timeout=10.0) as client:
                snapshot: BalanceSnapshot = adapter_fn(
                    key, base_url=base_url, http=client,
                )
                return snapshot
        except Exception as exc:
            return BalanceSnapshot(
                catalog_id=catalog_id,
                kind="unavailable",
                note=f"adapter error: {type(exc).__name__}: {exc}",
            )

    # Fallback: spend-history (client-side meter from the ledger).
    return fetch_spend_history_balance(
        key,
        base_url=base_url,
        http=httpx,  # not used by spend_history
        ledger=ledger,
        api_key_id=api_key_id,
        owner_user_id=owner_user_id,
        catalog_id=catalog_id,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_user_record(api_key_id: str, owner_user_id: str) -> Any:
    """Look up a ``UserModelRecord`` by ``id`` + ``owner_user_id``.

    Returns the record if found and owned by the session user, else ``None``.
    """
    registry = _load_registry()
    record = registry.get(api_key_id)
    if record is None or record.owner_user_id != owner_user_id:
        return None
    return record


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@byot_usage_router.get("/usage", response_model=UsageSnapshotResponse)
def get_usage(request: Request) -> UsageSnapshotResponse:
    """Per-key usage snapshot for the session user's keys."""
    owner_user_id = request_owner_user_id(request)
    ledger = _get_ledger()
    rows: list[KeyUsageRow] = ledger.snapshot(owner_user_id)
    return UsageSnapshotResponse(
        keys=[
            KeyUsageEntry(
                api_key_id=row.api_key_id,
                used_cents=row.used_cents,
                limit_cents=row.limit_cents,
                remaining_cents=row.remaining_cents,
            )
            for row in rows
        ],
        count=len(rows),
    )


@byot_usage_router.post(
    "/usage/{api_key_id}/limit",
    response_model=SetLimitResponse,
)
def set_usage_limit(
    api_key_id: str,
    request: Request,
    payload: SetLimitRequest,
) -> SetLimitResponse:
    """Set (or clear) a key's spend cap.

    Returns 404 if the key does not belong to the session user.
    """
    owner_user_id = request_owner_user_id(request)
    record = _find_user_record(api_key_id, owner_user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown api_key_id")
    ledger = _get_ledger()
    ledger.set_limit(api_key_id, owner_user_id, payload.limit_cents)
    # Read back current state.
    row = ledger.key_usage(api_key_id, owner_user_id)
    if row is None:
        # set_limit creates the row via UPSERT; defensive fallback.
        return SetLimitResponse(
            api_key_id=api_key_id,
            limit_cents=payload.limit_cents,
            used_cents=0,
            remaining_cents=payload.limit_cents,
        )
    return SetLimitResponse(
        api_key_id=row.api_key_id,
        limit_cents=row.limit_cents,
        used_cents=row.used_cents,
        remaining_cents=row.remaining_cents,
    )


@byot_usage_router.get(
    "/balance/{api_key_id}",
    response_model=BalanceResponse,
)
def get_balance(api_key_id: str, request: Request) -> BalanceResponse:
    """Live balance from the provider adapter for one key.

    Dispatches to the adapter matching the key's ``provider_catalog_id``.
    Returns ``kind="unavailable"`` when the adapter degrades (never raises).
    """
    owner_user_id = request_owner_user_id(request)
    record = _find_user_record(api_key_id, owner_user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown api_key_id")

    catalog_id: str = record.provider_catalog_id or "unknown"
    base_url: str = record.base_url or ""
    ledger = _get_ledger()

    # Load the decrypted credential for the adapter call.
    try:
        key = _load_key(record.cred_ref)
    except Exception as exc:
        return BalanceResponse(
            api_key_id=api_key_id,
            catalog_id=catalog_id,
            kind="unavailable",
            note=f"credential load failed: {type(exc).__name__}: {exc}",
        )

    snapshot: BalanceSnapshot = _fetch_balance(
        catalog_id=catalog_id,
        key=key,
        base_url=base_url,
        ledger=ledger,
        api_key_id=api_key_id,
        owner_user_id=owner_user_id,
    )

    return BalanceResponse(
        api_key_id=api_key_id,
        catalog_id=snapshot.catalog_id,
        kind=snapshot.kind,
        balance_usd=snapshot.balance_usd,
        granted_usd=snapshot.granted_usd,
        spend_usd=snapshot.spend_usd,
        budget_usd=snapshot.budget_usd,
        utilization=snapshot.utilization,
        window_label=snapshot.window_label,
        resets_at=snapshot.resets_at,
        note=snapshot.note,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_byot_usage_routes(app: FastAPI) -> None:
    """Mount the BYOT usage/balance routes onto ``app``."""
    app.include_router(byot_usage_router)
