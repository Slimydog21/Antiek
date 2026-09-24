"""MiMo native-balance capability.

The public MiMo docs show account balance in the console, but publish no
balance API path or response schema. Billing may be RMB or USD by region, so
an unlabelled amount cannot be presented as dollar credit. Do not send a
credential to a guessed endpoint.

Sources: https://mimo.mi.com/docs/en-US/price/pay-as-you-go
         https://mimo.mi.com/docs/en-US/quick-start/faq/payment
"""

from __future__ import annotations

from runtime.byok.secret_str import SecretStr

from .base import BalanceSnapshot


def fetch_mimo_balance(
    key: SecretStr,
    *,
    base_url: str,
    http: object,
) -> BalanceSnapshot:
    """Report the missing provider balance contract without making a request."""
    del key, base_url, http
    return BalanceSnapshot(
        catalog_id="mimo",
        kind="unavailable",
        note="Provider has not documented a native balance API.",
    )
