"""Pure tests for HTML-native competition write twin search compose."""

from __future__ import annotations

from substrate.html_native_competition_write_twin_search_compose import (
    HtmlNativeCompetitionWriteTwinSearchComposeError,
    compose_html_native_competition_write_twin_search,
    format_html_native_competition_write_twin_search_summary,
)

COMPETITION = {
    "draft_id": "draft-1",
    "parent_asset_id": "asset-1",
    "competitor_decisions": [
        {
            "competitor": "Perplexity",
            "area": "citation_grounding",
            "decision_summary": "Inline citations with source cards",
            "antiek_status": "parity",
        },
        {
            "competitor": "OpenAI DR",
            "area": "multi_agent_orchestration",
            "decision_summary": "Planner + browser agents",
            "antiek_status": "behind",
            "residual": "strengthen collective floating cohesive pack",
        },
    ],
    "requested_families": ["arxiv", "substack"],
    "citations": [
        {
            "citation_id": "c1",
            "family": "arxiv",
            "title": "Scaling Laws under Noise",
            "external_id": "arxiv:2301.00001",
        },
        {
            "citation_id": "c2",
            "family": "substack",
            "title": "Research notes on evals",
            "url": "https://example.substack.com/p/evals",
        },
    ],
    "quality_overall": 0.8,
    "quality_floor": 0.5,
    "would_exceed": False,
    "search_query": "scaling orchestration citations",
}


def test_html_competition_ready():
    c = compose_html_native_competition_write_twin_search(
        session_id="sess-1",
        asset_id="asset-1",
        html_projection_sha="sha-html-1",
        view_requested=True,
        twin_bound=True,
        twin_substrate_ready=True,
        claimed_format="html",
        operator_ack=True,
        competition=COMPETITION,
    )
    assert c.html_view.pack_ready is True
    assert c.competition_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.remote_index_queried is False
    assert c.draft_written is False
    assert c.twin_written is False
    assert c.store_mutated is False
    assert (
        c.authority
        == "html_native_competition_write_twin_search_compose_advisory"
    )
    assert "pdf_view_authorized=false" in (
        format_html_native_competition_write_twin_search_summary(c)
    )


def test_pdf_claimed_blocks_or_denies():
    try:
        c = compose_html_native_competition_write_twin_search(
            session_id="sess-2",
            asset_id="asset-1",
            html_projection_sha="sha-html-1",
            view_requested=True,
            twin_bound=True,
            twin_substrate_ready=True,
            claimed_format="pdf",
            operator_ack=True,
            competition=COMPETITION,
        )
        assert c.html_view.pack_ready is False
        assert c.pack_ready is False
        assert c.pdf_view_authorized is False
        assert c.pdf_primary is False
    except HtmlNativeCompetitionWriteTwinSearchComposeError:
        # Hard-deny path also valid for PDF primary claims.
        pass


def test_budget_blocks():
    c = compose_html_native_competition_write_twin_search(
        session_id="sess-3",
        asset_id="asset-1",
        html_projection_sha="sha-html-1",
        view_requested=True,
        twin_bound=True,
        twin_substrate_ready=True,
        claimed_format="html",
        operator_ack=True,
        competition={**COMPETITION, "would_exceed": True},
    )
    assert c.competition_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.remote_fetched is False


def test_operator_ack_false():
    c = compose_html_native_competition_write_twin_search(
        session_id="sess-4",
        asset_id="asset-1",
        html_projection_sha="sha-html-1",
        view_requested=True,
        twin_bound=True,
        claimed_format="html",
        operator_ack=False,
        competition=COMPETITION,
    )
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.twin_written is False
