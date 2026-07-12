"""Pure tests for source attach over Antiek-bench weekly learn twin presentation."""

from __future__ import annotations

from substrate.source_attach_antiek_bench_weekly_learn_twin_presentation_compose import (
    compose_source_attach_antiek_bench_weekly_learn_twin_presentation,
    format_source_attach_antiek_bench_weekly_learn_twin_presentation_summary,
)
from tests.test_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose import (
    TWIN_PRESENTATION_PACK,
    WEEKLY_LEARN,
)

SOURCES = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "requested_families": ["arxiv", "substack"],
    "sources": [
        {
            "source_id": "arx-1",
            "family": "arxiv",
            "title": "Scaling Laws for Neural Language Models",
            "external_id": "arxiv:2001.08361",
            "html_fragment": "<article>abstract…</article>",
        },
        {
            "source_id": "sub-1",
            "family": "substack",
            "title": "The Batch essay",
            "external_id": "substack:thebatch",
            "url": "https://example.substack.com/p/x",
            "html_fragment": "<article>essay…</article>",
        },
    ],
    "quality_overall": 0.85,
    "quality_floor": 0.7,
    "would_exceed": False,
}

WEEKLY_PACK = {
    "weekly_learn": WEEKLY_LEARN,
    "twin_presentation_pack": TWIN_PRESENTATION_PACK,
}


def test_source_attach_weekly_learn_twin_presentation_ready():
    c = compose_source_attach_antiek_bench_weekly_learn_twin_presentation(
        sources=SOURCES,
        weekly_pack=WEEKLY_PACK,
        operator_ack=True,
    )
    assert c.sources.pack_ready is True
    assert c.weekly_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.remote_fetched is False
    assert c.live_dispatch_authorized is False
    assert c.backlog_mutated is False
    assert c.store_mutated is False
    assert c.suite_rewritten is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.pdf_primary is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "source_attach_antiek_bench_weekly_learn_twin_presentation_compose_advisory"
    )
    assert "remote_fetched=false" in (
        format_source_attach_antiek_bench_weekly_learn_twin_presentation_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_source_attach_antiek_bench_weekly_learn_twin_presentation(
        sources=SOURCES,
        weekly_pack=WEEKLY_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_source_attach_antiek_bench_weekly_learn_twin_presentation(
        sources={**SOURCES, "session_id": "sess-other"},
        weekly_pack=WEEKLY_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks_sources():
    c = compose_source_attach_antiek_bench_weekly_learn_twin_presentation(
        sources={**SOURCES, "would_exceed": True},
        weekly_pack=WEEKLY_PACK,
        operator_ack=True,
    )
    assert c.sources.pack_ready is False
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.production_router_verdict == "REJECT"
