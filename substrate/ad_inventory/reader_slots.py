"""Reader ad-border slots — page-window ad inventory for the Read
workflow (SPR-05 M1 + M3).

Ad slots live at the *border* of each page window, anchored to the book's
page-window locator (the `page_index` of `book_assets` / SPR-01), never to
DOM offsets — so a slot is stable across re-layouts and the same reading
position always maps to the same slot id. The reading column itself is
sacred: TOP/BOTTOM rails are the v1 default; LEFT/RIGHT are only for wide
viewports (that's a render-layer decision the frontend honors using
`READER_AD_SLOT_POSITIONS_DEFAULT`).

Fill reuses the existing `select_lead_gen_ad` matcher. The load-bearing
honesty point (rigor #1): **zero buyers is the reality, not an edge
case.** `fill_slot` returns a HOUSE fill — a promotion of a genuinely
servable, platform-authored book — whenever no ad matches. The house path
is the default, fully modeled, not a stub behind a "no fill" branch.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from substrate.constants import READER_AD_SLOT_POSITIONS, READER_AD_SLOT_POSITIONS_DEFAULT

from .ad_bidding import AdInventoryItem, LeadGenAdInventory, select_lead_gen_ad


@dataclass(frozen=True)
class ReaderAdSlot:
    """One border ad slot, anchored to a (book, page-window, position)
    locator. ``slot_id`` is deterministic from that locator so the same
    reading position always yields the same slot — the key to dedup-ing
    impressions on re-render (SPR-05 M4)."""

    document_id: str
    page_index: int
    position: str  # one of READER_AD_SLOT_POSITIONS

    @property
    def slot_id(self) -> str:
        return f"slot:{self.document_id}:p{self.page_index}:{self.position}"


@dataclass(frozen=True)
class HousePromo:
    """The zero-buyer house fill: a promotion of a servable book. Carries
    the promoted book's id + display so the frontend renders a real,
    useful card (not blank/filler). Surfaced when no ad matches."""

    promoted_document_id: str
    title: str | None
    author: str | None


@dataclass(frozen=True)
class SlotFill:
    """What fills a slot. ``kind`` is 'ad' (a paid AdInventoryItem) or
    'house' (a HousePromo, the zero-buyer default). Exactly one of
    ``ad`` / ``house`` is set. ``revenue_usd_cents`` is what the advertiser
    pays for this fill — 0 for house fills, which is the honest v1 default
    (no invented revenue)."""

    slot: ReaderAdSlot
    kind: str  # 'ad' | 'house'
    ad: AdInventoryItem | None = None
    house: HousePromo | None = None
    revenue_usd_cents: int = 0


def slots_for_page_window(
    document_id: str,
    page_index: int,
    *,
    positions: Sequence[str] = READER_AD_SLOT_POSITIONS_DEFAULT,
) -> list[ReaderAdSlot]:
    """The border slots for one page window. Defaults to TOP/BOTTOM (the
    positions that never narrow the reading column). The frontend may pass
    LEFT/RIGHT on wide viewports."""
    bad = [p for p in positions if p not in READER_AD_SLOT_POSITIONS]
    if bad:
        raise ValueError(
            f"unknown slot position(s) {bad}; expected {READER_AD_SLOT_POSITIONS}"
        )
    return [ReaderAdSlot(document_id, page_index, p) for p in positions]


def fill_slot(
    slot: ReaderAdSlot,
    inventory: LeadGenAdInventory,
    *,
    page_topics: Sequence[str],
    cpm_to_cents: int = 0,
    house_candidates: Sequence[HousePromo] = (),
) -> SlotFill:
    """Fill one slot. Tries the paid matcher first; on no match, returns a
    HOUSE fill — the v1 default.

    ``page_topics`` are the targeting signals (see
    ``substrate.ad_inventory.targeting`` — always an allowlisted subset,
    never gated book text). ``cpm_to_cents`` is the revenue booked for a
    paid fill (the caller resolves CPM→cents per its bidding policy); house
    fills always book 0. ``house_candidates`` are servable books to
    promote; when empty (or no ad matches and no candidates), the slot
    still returns a house fill with a null promo so the frontend renders a
    neutral house card rather than a broken/blank slot.
    """
    ad = select_lead_gen_ad(inventory, page_topics=list(page_topics))
    if ad is not None:
        return SlotFill(slot=slot, kind="ad", ad=ad, revenue_usd_cents=int(cpm_to_cents))
    # Zero-buyer house state — the default, not an edge case.
    promo = _pick_house_promo(slot, house_candidates)
    return SlotFill(slot=slot, kind="house", house=promo, revenue_usd_cents=0)


def _pick_house_promo(
    slot: ReaderAdSlot, candidates: Sequence[HousePromo]
) -> HousePromo | None:
    """Deterministically pick a house promo for a slot, skipping the book
    currently being read (don't promote the book back to itself). Returns
    None when there's nothing to promote — the frontend renders a neutral
    house card, never a broken slot."""
    pool = [c for c in candidates if c.promoted_document_id != slot.document_id]
    if not pool:
        return None
    # Deterministic per slot so the same position shows a stable promo
    # (no flicker on re-render) without a trained recommender (§16).
    return pool[hash(slot.slot_id) % len(pool)]
