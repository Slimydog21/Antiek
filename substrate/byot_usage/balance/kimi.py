"""Kimi / Moonshot balance adapter — native balance endpoint.

Endpoint: ``GET {base_url}/users/me/balance``
(base_url is ``https://api.moonshot.ai/v1`` from the preset catalog)
Auth: ``Authorization: Bearer <key>``

Response shape (2026-08 documented)::

    {
      "status": "ok",
      "data": {
        "available_balance": "50.00",
        "voucher_balance": "10.00",
        "cash_balance": "40.00"
      }
    }

The adapter returns ``unavailable`` on any shape drift.
"""

from __future__ import annotations

from typing import Any

from runtime.byok.secret_str import SecretStr

from .base import BalanceSnapshot

_CATALOG_ID = "kimi"
_BALANCE_PATH = "/users/me/balance"

# Source: https://platform.moonshot.ai/docs/pricing/chat
# Polled every 60 s per spec §5.F.


def fetch_kimi_balance(
    key: SecretStr,
    *,
    base_url: str,
    http: Any,
) -> BalanceSnapshot:
    """Fetch Kimi/Moonshot native balance.

    Degrades to ``unavailable`` on HTTP error or schema mismatch.
    """
    url = f"{base_url.rstrip('/')}{_BALANCE_PATH}"
    try:
        response = http.get(
            url,
            headers={"Authorization": f"Bearer {key.reveal()}"},
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return BalanceSnapshot(
            catalog_id=_CATALOG_ID,
            kind="unavailable",
            note=f"HTTP/parse error: {type(exc).__name__}: {exc}",
        )

    try:
        info = data["data"]
        available = float(info["available_balance"])
        cash = float(info["cash_balance"])
    except (KeyError, TypeError, ValueError) as exc:
        return BalanceSnapshot(
            catalog_id=_CATALOG_ID,
            kind="unavailable",
            note=f"schema drift: {type(exc).__name__}: {exc}",
        )

    return BalanceSnapshot(
        catalog_id=_CATALOG_ID,
        kind="balance_native",
        balance_usd=available,
        granted_usd=cash,
    )
