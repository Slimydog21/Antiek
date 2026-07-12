"""Pure tests for HTML-native over marketplace free MO settings pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose import (
    compose_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack,
    format_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_summary,
)
from tests.test_marketplace_free_mo_settings_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose import (
    MARKET,
    MO_PACK,
)

HTML_VIEW = {
    "session_id": "sess-1",
    "asset_id": "book-1",
    "html_projection_sha": "sha-free-1",
    "view_requested": True,
    "twin_bound": True,
    "twin_substrate_ready": True,
    "claimed_format": "html",
}

MARKET_PACK = {
    "market": MARKET,
    "mo_pack": MO_PACK,
}


def test_html_native_marketplace_free_mo_ready():
    c = compose_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack(
        html_view=HTML_VIEW,
        market_pack=MARKET_PACK,
        operator_ack=True,
    )
    assert c.html_view.pack_ready is True
    assert c.market_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose_advisory"
    )
    assert "pdf_primary=false" in (
        format_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack(
        html_view=HTML_VIEW,
        market_pack=MARKET_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.pdf_primary is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack(
        html_view={**HTML_VIEW, "session_id": "sess-other"},
        market_pack=MARKET_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.pdf_primary is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"


def test_missing_html_sha_blocks():
    c = compose_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack(
        html_view={**HTML_VIEW, "html_projection_sha": None},
        market_pack=MARKET_PACK,
        operator_ack=True,
    )
    assert c.html_view.pack_ready is False
    assert c.pack_ready is False
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"
