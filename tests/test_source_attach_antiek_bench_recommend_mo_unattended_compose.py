"""Pure tests for source attach over Antiek-bench recommend MO unattended pack."""

from __future__ import annotations

from substrate.source_attach_antiek_bench_recommend_mo_unattended_compose import (
    compose_source_attach_antiek_bench_recommend_mo_unattended,
    format_source_attach_antiek_bench_recommend_mo_unattended_summary,
)
from tests.test_antiek_bench_recommend_mo_unattended_fullscreen_draft_compose import (
    BENCH,
    MO_PACK,
)

SOURCES = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "requested_families": ["arxiv", "substack"],
    "sources": [
        {
            "source_id": "s1",
            "family": "arxiv",
            "title": "Scaling Laws for Neural Language Models",
            "external_id": "arxiv:2001.08361",
            "html_fragment": "<article>abstract…</article>",
        },
        {
            "source_id": "s2",
            "family": "substack",
            "title": "Evals that matter",
            "external_id": "substack:evals",
            "url": "https://example.substack.com/p/evals",
        },
    ],
}

RECOMMEND_PACK = {
    "bench": BENCH,
    "mo_pack": MO_PACK,
}


def test_source_attach_antiek_bench_recommend_ready():
    c = compose_source_attach_antiek_bench_recommend_mo_unattended(
        sources=SOURCES,
        recommend_pack=RECOMMEND_PACK,
        operator_ack=True,
    )
    assert c.sources.attach_ready is True
    assert c.sources.source_count == 2
    assert c.sources.html_ready_count == 1
    assert c.recommend_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.attach_ready is True
    assert c.remote_fetched is False
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.suite_rewritten is False
    assert c.live_router_authorized is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.remote_index_queried is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "source_attach_antiek_bench_recommend_mo_unattended_compose_advisory"
    )
    assert "remote_fetched=false" in (
        format_source_attach_antiek_bench_recommend_mo_unattended_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_source_attach_antiek_bench_recommend_mo_unattended(
        sources=SOURCES,
        recommend_pack=RECOMMEND_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.live_router_authorized is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_source_attach_antiek_bench_recommend_mo_unattended(
        sources={**SOURCES, "session_id": "sess-other"},
        recommend_pack=RECOMMEND_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_empty_sources_blocks():
    c = compose_source_attach_antiek_bench_recommend_mo_unattended(
        sources={**SOURCES, "sources": []},
        recommend_pack=RECOMMEND_PACK,
        operator_ack=True,
    )
    assert c.sources.attach_ready is False
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.suite_rewritten is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"
