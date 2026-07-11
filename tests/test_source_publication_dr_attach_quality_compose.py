"""Pure tests for source publication DR attach quality compose."""

from __future__ import annotations

from substrate.source_publication_dr_attach_quality_compose import (
    compose_source_publication_dr_attach_quality,
    format_source_publication_dr_attach_quality_summary,
)


def test_arxiv_substack_ready():
    c = compose_source_publication_dr_attach_quality(
        session_id="sess-1",
        parent_asset_id="asset-1",
        requested_families=["arxiv", "substack"],
        sources=[
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
        quality_overall=0.85,
        quality_floor=0.7,
        would_exceed=False,
        operator_ack=True,
    )
    assert c.attach.attach_ready is True
    assert c.citation_pack.pack_ready is True
    assert c.citation_pack.citation_count == 2
    assert c.quality_gate.gate_ready is True
    assert c.pack_ready is True
    assert c.remote_fetched is False
    assert c.pdf_view_authorized is False
    assert c.store_mutated is False
    assert c.live_dispatch_authorized is False
    assert "pdf_view_authorized=false" in format_source_publication_dr_attach_quality_summary(
        c
    )
    assert c.to_dict()["live_dispatch_authorized"] is False


def test_budget_blocks():
    c = compose_source_publication_dr_attach_quality(
        session_id="sess-2",
        parent_asset_id="a",
        requested_families=["arxiv"],
        sources=[
            {
                "source_id": "arx-1",
                "family": "arxiv",
                "title": "Paper",
                "html_fragment": "<p>x</p>",
            }
        ],
        quality_overall=0.9,
        would_exceed=True,
        operator_ack=True,
    )
    assert c.quality_gate.gate_ready is False
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False


def test_low_quality_blocks():
    c = compose_source_publication_dr_attach_quality(
        session_id="sess-3",
        parent_asset_id="a",
        requested_families=["arxiv"],
        sources=[
            {
                "source_id": "arx-1",
                "family": "arxiv",
                "title": "Paper",
                "html_fragment": "<p>x</p>",
            }
        ],
        quality_overall=0.2,
        quality_floor=0.7,
        would_exceed=False,
        operator_ack=True,
    )
    assert c.pack_ready is False
    assert c.remote_fetched is False


def test_ack_false():
    c = compose_source_publication_dr_attach_quality(
        session_id="sess-4",
        parent_asset_id="a",
        requested_families=["substack"],
        sources=[
            {
                "source_id": "s1",
                "family": "substack",
                "title": "Essay",
                "html_fragment": "<p>y</p>",
            }
        ],
        quality_overall=0.9,
        would_exceed=False,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False


def test_explicit_citations():
    c = compose_source_publication_dr_attach_quality(
        session_id="sess-5",
        parent_asset_id="a",
        requested_families=["arxiv"],
        sources=[
            {
                "source_id": "arx-1",
                "family": "arxiv",
                "title": "Paper A",
                "html_fragment": "<p>a</p>",
            }
        ],
        citations=[
            {
                "citation_id": "custom-1",
                "family": "arxiv",
                "title": "Custom citation title",
                "external_id": "arxiv:9999.99999",
            }
        ],
        quality_overall=0.8,
        would_exceed=False,
        operator_ack=True,
    )
    first = c.citation_pack.citations[0]
    cid = first["citation_id"] if isinstance(first, dict) else first.citation_id
    assert cid == "custom-1"
    assert c.pack_ready is True
