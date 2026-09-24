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

Every ``balance_infos`` entry retains its reported currency and decimal
precision. The adapter returns ``unavailable`` on any shape drift.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from runtime.byok.secret_str import SecretStr

from .base import BalanceSnapshot, NativeBalance

_CATALOG_ID = "deepseek"
_BALANCE_PATH = "/user/balance"
_CURRENCIES = frozenset({"CNY", "USD"})
_AMOUNT_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")

# Source: https://api-docs.deepseek.com/api/get-user-balance/
# Polled every 60 s per spec §5.F.


def _decimal_amount(raw: object) -> str:
    if not isinstance(raw, str) or len(raw) > 64 or not _AMOUNT_PATTERN.fullmatch(raw):
        raise ValueError("invalid decimal amount")
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal amount") from exc
    if not amount.is_finite():
        raise ValueError("non-finite decimal amount")
    return format(amount, "f")


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
            note=f"HTTP/parse error: {type(exc).__name__}",
        )

    try:
        if not isinstance(data["is_available"], bool):
            raise ValueError("invalid availability flag")
        infos = data["balance_infos"]
        if not isinstance(infos, list) or not 1 <= len(infos) <= 8:
            raise ValueError("balance_infos is empty, oversized or not a list")
        balances: list[NativeBalance] = []
        currencies: set[str] = set()
        for info in infos:
            currency = info["currency"]
            if not isinstance(currency, str) or currency not in _CURRENCIES:
                raise ValueError("unrecognised balance currency")
            if currency in currencies:
                raise ValueError("duplicate balance currency")
            currencies.add(currency)
            balances.append(
                NativeBalance(
                    currency=currency,
                    total=_decimal_amount(info["total_balance"]),
                    granted=_decimal_amount(info["granted_balance"]),
                    topped_up=_decimal_amount(info["topped_up_balance"]),
                )
            )
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return BalanceSnapshot(
            catalog_id=_CATALOG_ID,
            kind="unavailable",
            note=f"schema drift: {type(exc).__name__}",
        )

    return BalanceSnapshot(
        catalog_id=_CATALOG_ID,
        kind="balance_native",
        native_balances=tuple(balances),
    )
