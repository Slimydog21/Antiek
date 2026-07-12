"""Pure tests for HTML-native view over marketplace free settings ND twin pack."""

from __future__ import annotations

from substrate.html_native_marketplace_free_settings_nd_twin_compose import (
    compose_html_native_marketplace_free_settings_nd_twin,
    format_html_native_marketplace_free_settings_nd_twin_summary,
)
from tests.test_marketplace_free_settings_add_model_nd_shadow_twin_compose import (
    MARKET,
    SETTINGS_PACK,
)

HTML_VIEW = {
    "session_id": "sess-1",
    "asset_id": "book-1",
    "html_projection_sha": "sha-html-ready",
    "view_requested": True,
    "twin_bound": True,
    "twin_substrate_ready": True,
    "claimed_format": "html",
}

MARKET_PACK = {
    "market": MARKET,
    "settings_pack": SETTINGS_PACK,
}


def test_html_native_marketplace_free_settings_nd_twin_ready():
    c = compose_html_native_marketplace_free_settings_nd_twin(
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
    assert c.twin_written is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "html_native_marketplace_free_settings_nd_twin_compose_advisory"
    )
    assert "pdf_primary=false" in (
        format_html_native_marketplace_free_settings_nd_twin_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_html_native_marketplace_free_settings_nd_twin(
        html_view=HTML_VIEW,
        market_pack=MARKET_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.pdf_primary is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_html_native_marketplace_free_settings_nd_twin(
        html_view={**HTML_VIEW, "session_id": "sess-other"},
        market_pack=MARKET_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.pdf_primary is False
    assert c.hosted is False


def test_asset_mismatch_blocks_parent_aligned():
    c = compose_html_native_marketplace_free_settings_nd_twin(
        html_view={**HTML_VIEW, "asset_id": "book-other"},
        market_pack=MARKET_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.pdf_view_authorized is False
    assert c.purchase_executed is False
