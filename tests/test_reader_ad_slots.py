"""Read SPR-05 — ad-border slots, zero-buyer house state, impression /
attention semantics, and the targeting allowlist.

The mechanical gates the spec names: zero-buyer → house (not blank),
attention not counted while idle, impressions don't double-count on
re-render, and targeting never touches gated book text.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from substrate.ad_inventory.ad_bidding import AdInventoryItem, LeadGenAdInventory
from substrate.ad_inventory.reader_impressions import (
    dedup_impressions,
    record_impression,
    total_revenue_cents,
)
from substrate.ad_inventory.reader_slots import (
    HousePromo,
    ReaderAdSlot,
    fill_slot,
    slots_for_page_window,
)
from substrate.ad_inventory.targeting import (
    TargetingSignalRefused,
    assert_no_forbidden_signals,
    page_topics_from_signals,
    targeting_signals_for,
)
from substrate.constants import READER_ATTENTION_DWELL_MS

# ── M1: slots anchored to locators ──────────────────────────────────


def test_slots_anchored_to_page_window_locator():
    slots = slots_for_page_window("doc-book-1", 7)
    assert [s.position for s in slots] == ["top", "bottom"]
    # slot_id is deterministic from (doc, page, position) — not a DOM offset.
    assert slots[0].slot_id == "slot:doc-book-1:p7:top"
    # Same locator → same id (the dedup foundation).
    assert slots_for_page_window("doc-book-1", 7)[0].slot_id == slots[0].slot_id


def test_unknown_slot_position_rejected():
    with pytest.raises(ValueError, match="unknown slot position"):
        slots_for_page_window("d", 0, positions=("middle",))


# ── M1/M3: fill — paid when available, house when not ───────────────


def _inventory() -> LeadGenAdInventory:
    inv = LeadGenAdInventory()
    inv.add(AdInventoryItem(
        inventory_id="ad-1", advertiser_display_name="QuantumCo",
        target_topics=("quantum",), cpm_usd=Decimal("5.0"),
        creative_url="https://x/ad", landing_url="https://x/land",
    ))
    return inv


def test_fill_returns_ad_when_topic_matches():
    slot = ReaderAdSlot("doc-1", 0, "top")
    fill = fill_slot(slot, _inventory(), page_topics=["quantum"], cpm_to_cents=200)
    assert fill.kind == "ad"
    assert fill.ad.inventory_id == "ad-1"
    assert fill.revenue_usd_cents == 200


def test_zero_buyer_falls_back_to_house_not_blank():
    """The keystone SPR-05 behavior: no matching ad → a HOUSE fill that
    promotes a servable book, never a blank/broken slot. House books $0."""
    slot = ReaderAdSlot("doc-current", 3, "bottom")
    house = [
        HousePromo("doc-current", "Self", "Me"),       # must be skipped
        HousePromo("doc-other", "Other Book", "Author"),
    ]
    fill = fill_slot(slot, LeadGenAdInventory(), page_topics=["history"],
                     house_candidates=house)
    assert fill.kind == "house"
    assert fill.revenue_usd_cents == 0
    assert fill.house is not None
    assert fill.house.promoted_document_id == "doc-other"  # never promote self


def test_house_with_no_candidates_is_still_house_not_broken():
    slot = ReaderAdSlot("doc-1", 0, "top")
    fill = fill_slot(slot, LeadGenAdInventory(), page_topics=[])
    assert fill.kind == "house"
    assert fill.house is None  # frontend renders a neutral house card


# ── M4: impression + attention semantics ────────────────────────────


def test_attention_counted_only_above_dwell_threshold():
    slot = ReaderAdSlot("doc-1", 0, "top")
    fill = fill_slot(slot, _inventory(), page_topics=["quantum"], cpm_to_cents=100)
    below = record_impression(session_id="s1", fill=fill,
                              focused_dwell_ms=READER_ATTENTION_DWELL_MS - 1)
    at = record_impression(session_id="s1", fill=fill,
                           focused_dwell_ms=READER_ATTENTION_DWELL_MS)
    assert below.counted_attention is False
    assert at.counted_attention is True


def test_attention_not_counted_while_idle():
    """The 'attention not while idle' gate: a backgrounded tab forces
    attention to 0 and zeroes the recorded dwell regardless of how long
    the slot was nominally visible."""
    slot = ReaderAdSlot("doc-1", 0, "top")
    fill = fill_slot(slot, _inventory(), page_topics=["quantum"], cpm_to_cents=100)
    idle = record_impression(session_id="s1", fill=fill,
                             focused_dwell_ms=10_000, tab_focused=False)
    assert idle.counted_attention is False
    assert idle.focused_dwell_ms == 0


def test_impressions_do_not_double_count_on_rerender():
    """Re-rendering the same slot in the same session is the SAME
    impression (deterministic id), so revenue doesn't inflate."""
    slot = ReaderAdSlot("doc-1", 0, "top")
    fill = fill_slot(slot, _inventory(), page_topics=["quantum"], cpm_to_cents=300)
    imps = [
        record_impression(session_id="s1", fill=fill, focused_dwell_ms=500),
        record_impression(session_id="s1", fill=fill, focused_dwell_ms=2000),  # re-render
    ]
    deduped = dedup_impressions(imps)
    assert len(deduped) == 1
    assert deduped[0].focused_dwell_ms == 2000  # keeps the max dwell
    assert total_revenue_cents(imps) == 300  # counted once, not 600


def test_zero_buyer_session_revenue_is_zero():
    slot = ReaderAdSlot("doc-1", 0, "top")
    house = fill_slot(slot, LeadGenAdInventory(), page_topics=[])
    imp = record_impression(session_id="s1", fill=house,
                            focused_dwell_ms=READER_ATTENTION_DWELL_MS)
    assert imp.fill_kind == "house"
    assert imp.revenue_usd_cents == 0
    assert imp.counted_attention is True  # attention-share tracked even at $0
    assert total_revenue_cents([imp]) == 0


# ── M5: targeting allowlist + no gated text ─────────────────────────


def test_targeting_uses_only_allowlisted_metadata():
    meta = {
        "document_type": "book", "topic": "history", "author": "X",
        "servability": "public_domain",
        "raw_text": "THE ENTIRE COPYRIGHTED BODY OF THE BOOK",  # must be dropped
        "note": "reader's private note",                        # must be dropped
    }
    signals = targeting_signals_for(meta)
    assert set(signals) == {"document_type", "topic", "author", "servability"}
    assert "raw_text" not in signals and "note" not in signals
    assert page_topics_from_signals(signals) == ["history"]


def test_gated_book_targeting_never_uses_body():
    """A gated book yields the same metadata-only signals — its body never
    feeds targeting, even though snippet view would be fair use."""
    gated = {"document_type": "book", "topic": "law", "raw_text": "gated body"}
    signals = targeting_signals_for(gated)
    assert "raw_text" not in signals
    assert page_topics_from_signals(signals) == ["law"]


def test_forbidden_signal_guard_raises():
    with pytest.raises(TargetingSignalRefused, match="forbidden"):
        assert_no_forbidden_signals({"topic": "ok", "raw_text": "leak"})
