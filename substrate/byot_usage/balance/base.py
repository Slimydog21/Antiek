"""Balance adapter protocol and snapshot type.

Every adapter degrades to ``kind="unavailable"`` on schema mismatch or
HTTP error — it never raises to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from runtime.byok.secret_str import SecretStr

__all__ = [
    "BalanceAdapter",
    "BalanceSnapshot",
]


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    """Normalised balance state returned by every adapter.

    Only the fields relevant to ``kind`` are populated; the rest are
    ``None``.  The caller switches on ``kind`` to decide which fields
    to display.
    """

    catalog_id: str
    kind: Literal[
        "balance_native",
        "spend_history",
        "quota_pct",
        "meter_only",
        "unavailable",
    ]
    # balance_native: real dollars held at the provider
    balance_usd: float | None = None
    granted_usd: float | None = None
    # spend_history: provider-reported spend + user-set budget → derived remaining
    spend_usd: float | None = None
    budget_usd: float | None = None
    # quota_pct: utilization bars, no dollar amounts
    utilization: float | None = None  # 0..1 normalised
    window_label: str | None = None
    resets_at: int | None = None  # unix timestamp
    note: str | None = None  # honest reason when unavailable


class BalanceAdapter(Protocol):
    """Protocol implemented by each per-provider balance adapter."""

    catalog_id: str

    def fetch(
        self,
        key: SecretStr,
        *,
        base_url: str,
        http: object,
    ) -> BalanceSnapshot:
        """Fetch balance from the provider and return a normalised snapshot.

        Parameters
        ----------
        key:
            The decrypted API key (redacting ``SecretStr``).
        base_url:
            The provider base URL (e.g. ``https://api.deepseek.com``).
        http:
            An ``httpx.Client`` (real) or ``httpx.MockTransport``-backed
            client (tests).  The adapter calls ``http.get(...)``.
        """
        ...
