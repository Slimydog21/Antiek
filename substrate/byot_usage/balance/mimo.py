"""Xiaomi MiMo balance adapter — native balance endpoint.

Endpoint: ``GET {base_url}/user/balance``
(base_url is ``https://api.mimo.xiaomi.com/v1`` from the preset catalog)
Auth: ``Authorization: Bearer <key>``

Declared response shape::

    {
      "data": {
        "total_balance": "18.00",
        "granted_balance": "3.00"
      }
    }

HONESTY NOTE (2026-09-22): the MiMo platform docs reachable from
``platform.xiaomimimo.com`` (redirecting to ``mimo.mi.com``) publish no
balance/billing endpoint. The path and shape above are the OpenAI-compatible
convention this adapter DECLARES and the stubbed-transport test pins; they
are not a vendor-documented contract. On any HTTP error or shape drift the
adapter returns ``unavailable`` with an honest note rather than inventing a
number, and the chip renders that as "—", never as credit.
"""

from __future__ import annotations

from typing import Any

from runtime.byok.secret_str import SecretStr

from .base import BalanceSnapshot

_CATALOG_ID = "mimo"
_BALANCE_PATH = "/user/balance"

# Source: https://platform.xiaomimimo.com/docs/pricing (pricing only; no
# balance endpoint published — see module docstring). Polled every 60 s per
# spec §5.F.


def fetch_mimo_balance(
    key: SecretStr,
    *,
    base_url: str,
    http: Any,
) -> BalanceSnapshot:
    """Fetch Xiaomi MiMo native balance.

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
        total = float(info["total_balance"])
        granted = float(info["granted_balance"])
    except (KeyError, TypeError, ValueError) as exc:
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
