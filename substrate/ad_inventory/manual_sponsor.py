"""Operator-sold manual sponsor creative (website ads MVP Phase 2).

Doctrine: docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md
§3.2 — static HTML sponsor card, Antiek-served, never network demand.

Creative is projection only. When env is complete this module yields an
``AdInventoryItem`` with ``cpm_usd=0`` so ``POST /api/ad/fills`` can persist
an ``ad_fill_decisions`` row at revenue $0 / price_status=unpriced.
No fake revenue; disbursable gates elsewhere stay closed.
"""

from __future__ import annotations

import os
from decimal import Decimal

from substrate.ad_inventory.ad_bidding import AdInventoryItem, BiddingPolicy

_ENABLE_ENV = "ANTIEK_MANUAL_SPONSOR_ENABLED"
_NAME_ENV = "ANTIEK_MANUAL_SPONSOR_NAME"
_LANDING_ENV = "ANTIEK_MANUAL_SPONSOR_LANDING_URL"
_CREATIVE_ENV = "ANTIEK_MANUAL_SPONSOR_CREATIVE_URL"
_DEFAULT_CREATIVE = "/mark-32.png"
_INVENTORY_ID = "manual_sponsor:operator"


def _env_truthy(name: str) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def manual_sponsor_enabled() -> bool:
    """True when the operator explicitly unlocked the Phase-2 sponsor slot."""
    return _env_truthy(_ENABLE_ENV)


def resolve_manual_sponsor_item(
    *,
    env: dict[str, str] | None = None,
) -> AdInventoryItem | None:
    """Return a $0 CPM inventory item when enabled + name + landing are set.

    Incomplete config → None (caller falls through to house). Creative URL
    defaults to the Antiek mark so dogfood does not require a banner asset.
    """
    source = env if env is not None else os.environ
    enabled_raw = (source.get(_ENABLE_ENV) or "").strip().lower()
    if enabled_raw not in {"1", "true", "yes", "on"}:
        return None
    name = (source.get(_NAME_ENV) or "").strip()
    landing = (source.get(_LANDING_ENV) or "").strip()
    creative = (source.get(_CREATIVE_ENV) or "").strip() or _DEFAULT_CREATIVE
    if not name or not landing:
        return None
    return AdInventoryItem(
        inventory_id=_INVENTORY_ID,
        advertiser_display_name=name,
        # Match research-lens page_topics=["research"] in ad_fills.
        target_topics=("research",),
        cpm_usd=Decimal("0"),
        creative_url=creative,
        landing_url=landing,
    )


def bidding_policy_wire() -> str:
    return BiddingPolicy.MANUAL_SPONSOR.value
