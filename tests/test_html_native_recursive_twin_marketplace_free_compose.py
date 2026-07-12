"""Pure tests for HTML-native over recursive twin marketplace free pack."""

from __future__ import annotations

from substrate.html_native_recursive_twin_marketplace_free_compose import (
    compose_html_native_recursive_twin_marketplace_free,
    format_html_native_recursive_twin_marketplace_free_summary,
)
from tests.test_recursive_twin_marketplace_free_competition_dr_compose import (
    MARKET_PACK,
    TWIN,
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

TWIN_PACK = {
    "twin": TWIN,
    "market_pack": MARKET_PACK,
}


def test_html_native_recursive_twin_ready():
    c = compose_html_native_recursive_twin_marketplace_free(
        html_view=HTML_VIEW,
        twin_pack=TWIN_PACK,
        operator_ack=True,
    )
    assert c.html_view.pack_ready is True
    assert c.twin_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.live_dispatch_authorized is False
    assert c.inventory_mutated is False
    assert c.secrets_stored is False
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "html_native_recursive_twin_marketplace_free_compose_advisory"
    )
    assert "pdf_view_authorized=false" in (
        format_html_native_recursive_twin_marketplace_free_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_html_native_recursive_twin_marketplace_free(
        html_view=HTML_VIEW,
        twin_pack=TWIN_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_html_native_recursive_twin_marketplace_free(
        html_view={**HTML_VIEW, "session_id": "sess-other"},
        twin_pack=TWIN_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.pdf_view_authorized is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"


def test_claimed_pdf_blocks():
    c = compose_html_native_recursive_twin_marketplace_free(
        html_view={**HTML_VIEW, "claimed_format": "pdf"},
        twin_pack=TWIN_PACK,
        operator_ack=True,
    )
    assert c.html_view.pack_ready is False
    assert c.pack_ready is False
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"
