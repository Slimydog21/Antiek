"""Kimi / Moonshot balance adapter — native balance endpoint.

Endpoint: ``GET {base_url}/users/me/balance``
(base_url is ``https://api.moonshot.ai/v1`` from the preset catalog)
Auth: ``Authorization: Bearer <key>``

Response shape (current official international API)::

    {
      "code": 0,
      "status": true,
      "scode": "0x0",
      "data": {
        "available_balance": 50.00001,
        "voucher_balance": 10.00,
        "cash_balance": 40.00001
      }
    }

Amounts are USD on the documented ``api.moonshot.ai`` host. A key for the
separate kimi.com platform is not valid there. The adapter returns
``unavailable`` on a host mismatch or shape drift.
"""

from __future__ import annotations

import math
from typing import Any

from runtime.byok.secret_str import SecretStr

from .base import BalanceSnapshot

_CATALOG_ID = "kimi"
_BALANCE_PATH = "/users/me/balance"
_DOCUMENTED_BASE_URL = "https://api.moonshot.ai/v1"

# Source: https://platform.kimi.ai/docs/api/balance
# Polled every 60 s per spec §5.F.


def _usd_number(raw: object) -> float:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool) or not math.isfinite(raw):
        raise ValueError("invalid USD balance")
    return float(raw)


def fetch_kimi_balance(
    key: SecretStr,
    *,
    base_url: str,
    http: Any,
) -> BalanceSnapshot:
    """Fetch Kimi/Moonshot native balance.

    Degrades to ``unavailable`` on HTTP error or schema mismatch.
    """
    if base_url.rstrip("/") != _DOCUMENTED_BASE_URL:
        return BalanceSnapshot(
            catalog_id=_CATALOG_ID,
            kind="unavailable",
            note="Kimi balance is supported only on the documented international API host.",
        )
    url = f"{_DOCUMENTED_BASE_URL}{_BALANCE_PATH}"
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
            note=f"HTTP/parse error: {type(exc).__name__}",
        )

    try:
        if type(data["code"]) is not int or data["code"] != 0:
            raise ValueError("balance request failed")
        if data["status"] is not True or data["scode"] != "0x0":
            raise ValueError("balance request failed")
        info = data["data"]
        available = _usd_number(info["available_balance"])
        _usd_number(info["voucher_balance"])
        _usd_number(info["cash_balance"])
    except (KeyError, TypeError, ValueError) as exc:
        return BalanceSnapshot(
            catalog_id=_CATALOG_ID,
            kind="unavailable",
            note=f"schema drift: {type(exc).__name__}",
        )

    return BalanceSnapshot(
        catalog_id=_CATALOG_ID,
        kind="balance_native",
        balance_usd=available,
        native_available=available > 0,
    )
