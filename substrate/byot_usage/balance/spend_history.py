"""OpenAI spend-history balance adapter — budget minus ledger spend.

This adapter does NOT make a live HTTP call.  It computes remaining
budget from the per-key usage ledger (``ByotUsageLedger``) and an
optional user-set budget.  It is the fallback for providers that lack
a native balance endpoint (OpenAI, Anthropic non-admin, etc.).

Spec §5.F: "spend-history-only (remaining = budget − spend)".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from runtime.byok.secret_str import SecretStr

from .base import BalanceSnapshot

if TYPE_CHECKING:
    from substrate.byot_usage.ledger import ByotUsageLedger

_CATALOG_ID_OPENAI = "openai"

# Source: spec §5.F — no live endpoint; derived from client-side meter.


def fetch_spend_history_balance(
    key: SecretStr,
    *,
    base_url: str,
    http: object,
    ledger: ByotUsageLedger,
    api_key_id: str,
    owner_user_id: str,
    catalog_id: str = _CATALOG_ID_OPENAI,
) -> BalanceSnapshot:
    """Compute remaining budget from the usage ledger.

    If the key has no ledger row or no limit is set, returns
    ``spend_usd`` with ``budget_usd=None`` (the caller knows the
    budget is unknown).
    """
    row = ledger.key_usage(api_key_id, owner_user_id)
    if row is None:
        return BalanceSnapshot(
            catalog_id=catalog_id,
            kind="spend_history",
            spend_usd=0.0,
            budget_usd=None,
            note="no usage recorded for this key",
        )

    spend = row.used_cents / 100.0
    budget = row.limit_cents / 100.0 if row.limit_cents is not None else None
    return BalanceSnapshot(
        catalog_id=catalog_id,
        kind="spend_history",
        spend_usd=spend,
        budget_usd=budget,
    )
