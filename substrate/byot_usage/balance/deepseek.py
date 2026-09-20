"""DeepSeek balance adapter — native balance endpoint.

Endpoint: ``GET https://api.deepseek.com/user/balance``
Auth: ``Authorization: Bearer <key>``

Response shape (2026-08 documented)::

    {
      "is_available": true,
      "balance_infos": [
        {
          "currency": "CNY",
          "total_balance": "100.00",
          "granted_balance": "80.00",
          "topped_up_balance": "20.00"
        }
      ]
    }

Only the first ``balance_infos`` entry is read.  The adapter returns
``unavailable`` on any shape drift.
"""

from __future__ import annotations

from typing import Any

from runtime.byok.secret_str import SecretStr

from .base import BalanceSnapshot

_CATALOG_ID = "deepseek"
_BALANCE_PATH = "/user/balance"

# Source: https://api-docs.deepseek.com/quick_start/pricing
# Polled every 60 s per spec §5.F.


def fetch_deepseek_balance(
    key: SecretStr,
    *,
    base_url: str,
    http: Any,
) -> BalanceSnapshot:
    """Fetch DeepSeek native balance.

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
        infos = data["balance_infos"]
        if not isinstance(infos, list) or len(infos) == 0:
            return BalanceSnapshot(
                catalog_id=_CATALOG_ID,
                kind="unavailable",
                note="balance_infos is empty or not a list",
            )
        info = infos[0]
        total = float(info["total_balance"])
        granted = float(info["granted_balance"])
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return BalanceSnapshot(
            catalog_id=_CATALOG_ID,
            kind="unavailable",
            note=f"schema drift: {type(exc).__name__}: {exc}",
        )

    return BalanceSnapshot(
        catalog_id=_CATALOG_ID,
        kind="balance_native",
        balance_usd=total,
        granted_usd=granted,
    )
