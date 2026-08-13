"""Ad-inventory items persistence (Sprint 23-24 phase 1).

Persistent ``ad_inventory_items`` table backing the in-memory
``LeadGenAdInventory`` registry. Without persistence the
``/ad-inventory/select`` endpoint's matcher has nothing to match
against — the registry dies on each request.

Schema chunk in ``substrate/graph/schema.py`` V6. The table mirrors
``AdInventoryItem`` + ``InventoryTargeting`` (the second-generation
targeting from intent_targeting.py).

Operator workflow:
  1. ``python -m substrate.ad_inventory.inventory ...`` (CLI deferred)
     OR direct CRUD through this module persists items.
  2. ``GET /ad-inventory/select`` loads the active subset + invokes
     the matcher.
  3. Items can be deactivated by setting ``active=False`` rather
     than deleting (audit trail).

Per master-spec §9.4 + §9.6: inventory is operator-curated in this
phase. Programmatic auction (§9.4 Option A) is deferred to S30+
and would replace this with a bid-store; explicitly out of scope.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .ad_bidding import AdInventoryItem
from .intent_targeting import InventoryTargeting, TargetedInventoryItem


@dataclass(frozen=True)
class PersistedInventoryItem:
    """An inventory item joined to its targeting + advertiser_id +
    active flag. Returned by ``load_active_inventory`` and rendered
    into ``TargetedInventoryItem`` shape for the matcher."""

    inventory_id: str
    advertiser_id: str
    advertiser_display_name: str
    target_topics: tuple[str, ...]
    target_sectors: tuple[str, ...]
    target_sub_sectors: tuple[str, ...]
    target_audience_intents: tuple[str, ...]
    cpm_usd_cents: int
    creative_url: str
    landing_url: str
    active: bool
    created_at: str

    @property
    def cpm_usd(self) -> Decimal:
        return Decimal(self.cpm_usd_cents) / Decimal(100)

    def to_ad_inventory_item(self) -> AdInventoryItem:
        """Convert to the ``ad_bidding.AdInventoryItem`` shape."""
        return AdInventoryItem(
            inventory_id=self.inventory_id,
            advertiser_display_name=self.advertiser_display_name,
            target_topics=self.target_topics,
            cpm_usd=self.cpm_usd,
            creative_url=self.creative_url,
            landing_url=self.landing_url,
        )

    def to_targeted_inventory_item(self) -> TargetedInventoryItem:
        return TargetedInventoryItem(
            item=self.to_ad_inventory_item(),
            targeting=InventoryTargeting(
                target_sectors=self.target_sectors,
                target_sub_sectors=self.target_sub_sectors,
                target_audience_intents=self.target_audience_intents,
            ),
        )


def ensure_table(con: Any) -> None:
    """Defensive table create. Canonical schema in
    ``substrate/graph/schema.py`` V6 chunk."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS ad_inventory_items (
                inventory_id              TEXT PRIMARY KEY,
                advertiser_id             TEXT NOT NULL,
                advertiser_display_name   TEXT NOT NULL,
                target_topics             TEXT NOT NULL DEFAULT '',
                target_sectors            TEXT NOT NULL DEFAULT '',
                target_sub_sectors        TEXT NOT NULL DEFAULT '',
                target_audience_intents   TEXT NOT NULL DEFAULT '',
                cpm_usd_cents             INTEGER NOT NULL,
                creative_url              TEXT NOT NULL,
                landing_url               TEXT NOT NULL,
                active                    BOOLEAN NOT NULL DEFAULT TRUE,
                created_at                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception:
        pass


def _csv(values: tuple[str, ...]) -> str:
    return ",".join(v for v in values if v)


def _de_csv(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(v for v in raw.split(",") if v)


def upsert_inventory(
    con: Any,
    *,
    advertiser_id: str,
    advertiser_display_name: str,
    creative_url: str,
    landing_url: str,
    cpm_usd_cents: int,
    target_topics: tuple[str, ...] = (),
    target_sectors: tuple[str, ...] = (),
    target_sub_sectors: tuple[str, ...] = (),
    target_audience_intents: tuple[str, ...] = (),
    active: bool = True,
    inventory_id: str | None = None,
) -> str:
    """Insert (or upsert via inventory_id) one inventory item.
    Returns the inventory_id. Per-advertiser inventory MUST carry
    a known advertiser_id — the substrate doesn't enforce a foreign
    key (advertisers can be removed before their inventory is) but
    join-time validation in the matcher will skip orphans."""
    ensure_table(con)
    iid = inventory_id or f"inv-{uuid.uuid4().hex[:12]}"
    if cpm_usd_cents < 0:
        raise ValueError("cpm_usd_cents must be non-negative")
    existing = con.execute(
        "SELECT inventory_id FROM ad_inventory_items "
        "WHERE inventory_id = ?",
        [iid],
    ).fetchone()
    if existing is None:
        con.execute(
            """
            INSERT INTO ad_inventory_items (
                inventory_id, advertiser_id, advertiser_display_name,
                target_topics, target_sectors, target_sub_sectors,
                target_audience_intents, cpm_usd_cents,
                creative_url, landing_url, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                iid, advertiser_id, advertiser_display_name,
                _csv(target_topics), _csv(target_sectors),
                _csv(target_sub_sectors), _csv(target_audience_intents),
                cpm_usd_cents, creative_url, landing_url, active,
            ],
        )
    else:
        con.execute(
            """
            UPDATE ad_inventory_items SET
                advertiser_id = ?,
                advertiser_display_name = ?,
                target_topics = ?,
                target_sectors = ?,
                target_sub_sectors = ?,
                target_audience_intents = ?,
                cpm_usd_cents = ?,
                creative_url = ?,
                landing_url = ?,
                active = ?
            WHERE inventory_id = ?
            """,
            [
                advertiser_id, advertiser_display_name,
                _csv(target_topics), _csv(target_sectors),
                _csv(target_sub_sectors), _csv(target_audience_intents),
                cpm_usd_cents, creative_url, landing_url, active,
                iid,
            ],
        )
    return iid


def deactivate_inventory(con: Any, *, inventory_id: str) -> None:
    """Soft-delete: flip active=False. Audit trail preserved via the
    row's created_at + the operator's typed activity log."""
    ensure_table(con)
    con.execute(
        "UPDATE ad_inventory_items SET active = FALSE "
        "WHERE inventory_id = ?",
        [inventory_id],
    )


def load_active_inventory(con: Any) -> list[PersistedInventoryItem]:
    """Load every active inventory item. Ordered by created_at so
    ties in the matcher resolve deterministically (older inventory
    wins on tie). The matcher's score × CPM tiebreak handles the
    common case; this ordering only matters when both score and
    CPM are identical."""
    ensure_table(con)
    rows = con.execute(
        """
        SELECT inventory_id, advertiser_id, advertiser_display_name,
               target_topics, target_sectors, target_sub_sectors,
               target_audience_intents, cpm_usd_cents,
               creative_url, landing_url, active,
               strftime(created_at, '%Y-%m-%dT%H:%M:%S')
        FROM ad_inventory_items
        WHERE active = TRUE
        ORDER BY created_at, inventory_id
        """
    ).fetchall()
    return [
        PersistedInventoryItem(
            inventory_id=r[0],
            advertiser_id=r[1],
            advertiser_display_name=r[2],
            target_topics=_de_csv(r[3]),
            target_sectors=_de_csv(r[4]),
            target_sub_sectors=_de_csv(r[5]),
            target_audience_intents=_de_csv(r[6]),
            cpm_usd_cents=int(r[7]),
            creative_url=r[8],
            landing_url=r[9],
            active=bool(r[10]),
            created_at=r[11] or "",
        )
        for r in rows
    ]


def load_serving_for_matcher(
    con: Any,
) -> tuple[list[TargetedInventoryItem], list[AdInventoryItem]]:
    """Render persistent inventory into the shape the matcher
    expects.

    Returns (targeted, flat_fallback):
      - targeted: items with ≥1 second-generation targeting dimension.
      - flat_fallback: items with only flat target_topics (no
        sector/sub_sector/intent set).

    The matcher prefers targeted; falls back to flat. This split
    mirrors ``select_targeted_ad``'s contract."""
    # An inventory row's own ``active`` bit is necessary but not sufficient:
    # the advertiser registry is append-only, and only the advertiser's latest
    # ACTIVE record may serve.  Orphans and suspended/churned advertisers fail
    # closed here.
    from .advertiser_onboarding import load_registry

    registry = load_registry(con)
    serving_advertiser_ids = {
        record.advertiser_id for record in registry.all_serving()
    }
    items = [
        item
        for item in load_active_inventory(con)
        if item.advertiser_id in serving_advertiser_ids
    ]
    targeted: list[TargetedInventoryItem] = []
    flat: list[AdInventoryItem] = []
    for it in items:
        has_target = bool(
            it.target_sectors
            or it.target_sub_sectors
            or it.target_audience_intents
        )
        if has_target:
            targeted.append(it.to_targeted_inventory_item())
        else:
            flat.append(it.to_ad_inventory_item())
    return (targeted, flat)


__all__ = [
    "PersistedInventoryItem",
    "deactivate_inventory",
    "ensure_table",
    "load_active_inventory",
    "load_serving_for_matcher",
    "upsert_inventory",
]
