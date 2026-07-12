"""Pure tests for source-attach residual over Antiek-bench rewrite model decision."""

from __future__ import annotations

from substrate.source_attach_antiek_bench_rewrite_model_decision_compose import (
    compose_source_attach_antiek_bench_rewrite_model_decision,
    format_source_attach_antiek_bench_rewrite_model_decision_summary,
)
from tests.test_antiek_bench_rewrite_model_decision_marketplace_compose import (
    MODEL_DECISION_PACK,
    REWRITE_EMPTY,
    REWRITE_READY,
)

SOURCES = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "requested_families": ["arxiv", "substack"],
    "sources": [
        {
            "source_id": "arx-1",
            "family": "arxiv",
            "title": "Scaling Laws under Noise",
            "external_id": "arxiv:2301.00001",
            "html_fragment": "<article>abstract…</article>",
        },
        {
            "source_id": "sub-1",
            "family": "substack",
            "title": "Research notes on evals",
            "external_id": "substack:evals",
            "url": "https://example.substack.com/p/evals",
            "html_fragment": "<article>essay…</article>",
        },
    ],
}

REWRITE_PACK = {
    "rewrite": REWRITE_READY,
    "model_decision_pack": MODEL_DECISION_PACK,
}


def test_source_attach_rewrite_ready():
    c = compose_source_attach_antiek_bench_rewrite_model_decision(
        sources=SOURCES,
        rewrite_pack=REWRITE_PACK,
        operator_ack=True,
    )
    assert c.attach_ready is True
    assert c.sources.source_count == 2
    assert c.sources.html_ready_count == 2
    assert c.rewrite_pack.pack_ready is True
    assert c.rewrite_pack.proposal_count >= 1
    assert c.pack_ready is True
    assert c.remote_fetched is False
    assert c.suite_rewritten is False
    assert c.applied is False
    assert c.pdf_primary is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "source_attach_antiek_bench_rewrite_model_decision_compose_advisory"
    )
    assert "remote_fetched=false" in (
        format_source_attach_antiek_bench_rewrite_model_decision_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_source_attach_antiek_bench_rewrite_model_decision(
        sources=SOURCES,
        rewrite_pack=REWRITE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.suite_rewritten is False
    assert c.applied is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_source_attach_antiek_bench_rewrite_model_decision(
        sources={**SOURCES, "session_id": "sess-other"},
        rewrite_pack=REWRITE_PACK,
        operator_ack=True,
    )
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"


def test_zero_proposals_blocks():
    c = compose_source_attach_antiek_bench_rewrite_model_decision(
        sources=SOURCES,
        rewrite_pack={
            "rewrite": REWRITE_EMPTY,
            "model_decision_pack": MODEL_DECISION_PACK,
        },
        operator_ack=True,
    )
    assert c.rewrite_pack.proposal_count == 0
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.suite_rewritten is False
    assert c.applied is False
    assert c.production_router_verdict == "REJECT"
