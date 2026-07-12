"""Pure tests for HTML-native view residual over settings marketplace free competition pack."""

from __future__ import annotations

from substrate.html_native_settings_marketplace_free_competition_dr_nd_compose import (
    compose_html_native_settings_marketplace_free_competition_dr_nd,
    format_html_native_settings_marketplace_free_competition_dr_nd_summary,
)
from tests.test_settings_add_model_marketplace_free_competition_dr_nd_compose import (
    MARKET_PACK,
    SETTINGS,
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

SETTINGS_PACK = {
    "settings": SETTINGS,
    "market_pack": MARKET_PACK,
}


def test_html_native_settings_marketplace_ready():
    c = compose_html_native_settings_marketplace_free_competition_dr_nd(
        html_view=HTML_VIEW,
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.html_view.pack_ready is True
    assert c.settings_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "html_native_settings_marketplace_free_competition_dr_nd_compose_advisory"
    )
    assert "pdf_primary=false" in (
        format_html_native_settings_marketplace_free_competition_dr_nd_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_html_native_settings_marketplace_free_competition_dr_nd(
        html_view=HTML_VIEW,
        settings_pack=SETTINGS_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.pdf_primary is False
    assert c.purchase_executed is False
    assert c.secrets_stored is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_html_native_settings_marketplace_free_competition_dr_nd(
        html_view={**HTML_VIEW, "session_id": "sess-other"},
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"


def test_asset_mismatch_blocks():
    c = compose_html_native_settings_marketplace_free_competition_dr_nd(
        html_view={**HTML_VIEW, "asset_id": "book-other"},
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
