"""Pure tests for twin search over HTML-native recursive twin marketplace pack."""

from __future__ import annotations

from substrate.twin_search_html_native_recursive_twin_marketplace_compose import (
    compose_twin_search_html_native_recursive_twin_marketplace,
    format_twin_search_html_native_recursive_twin_marketplace_summary,
)
from tests.test_html_native_recursive_twin_marketplace_free_compose import (
    HTML_VIEW,
    TWIN_PACK,
)

SEARCH_TWIN_RECORDS = [
    {
        "twin_id": "twin-book-1",
        "parent_asset_id": "book-1",
        "insights": [
            "scaling laws hold under noise in compute-optimal regimes"
        ],
        "questions": [
            "Where does scaling break under distribution shift?"
        ],
        "source_label": "book-1-twin",
    },
    {
        "twin_id": "twin-arxiv-1",
        "parent_asset_id": "cite-parent-c1",
        "insights": ["Scaling Laws under Noise"],
        "questions": ["How does arxiv residual inform Antiek DR?"],
        "source_label": "arxiv",
    },
]

HTML_PACK = {
    "html_view": HTML_VIEW,
    "twin_pack": TWIN_PACK,
}


def test_twin_search_html_native_ready():
    c = compose_twin_search_html_native_recursive_twin_marketplace(
        search_query="scaling noise",
        twin_records=SEARCH_TWIN_RECORDS,
        html_pack=HTML_PACK,
        operator_ack=True,
    )
    assert c.hit_count >= 1
    assert c.search.remote_index_queried is False
    assert c.html_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.remote_index_queried is False
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.inventory_mutated is False
    assert c.secrets_stored is False
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "twin_search_html_native_recursive_twin_marketplace_compose_advisory"
    )
    assert "remote_index_queried=false" in (
        format_twin_search_html_native_recursive_twin_marketplace_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_twin_search_html_native_recursive_twin_marketplace(
        search_query="scaling noise",
        twin_records=SEARCH_TWIN_RECORDS,
        html_pack=HTML_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.remote_index_queried is False
    assert c.pdf_view_authorized is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"


def test_zero_hits_blocks():
    c = compose_twin_search_html_native_recursive_twin_marketplace(
        search_query="zzzznonexistenttoken",
        twin_records=SEARCH_TWIN_RECORDS,
        html_pack=HTML_PACK,
        operator_ack=True,
    )
    assert c.hit_count == 0
    assert c.pack_ready is False
    assert c.remote_index_queried is False
    assert c.pdf_view_authorized is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_twin_search_html_native_recursive_twin_marketplace(
        search_query="scaling noise",
        twin_records=SEARCH_TWIN_RECORDS,
        html_pack={
            "html_view": {**HTML_VIEW, "session_id": "sess-other"},
            "twin_pack": TWIN_PACK,
        },
        operator_ack=True,
    )
    assert c.html_pack.session_aligned is False
    assert c.html_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.remote_index_queried is False
    assert c.pdf_view_authorized is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
