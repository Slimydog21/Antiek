"""Pure tests for HTML-native source attach compose."""

from __future__ import annotations

import pytest

from substrate.html_native_source_attach_compose import (
    HtmlNativeSourceAttachComposeError,
    compose_html_native_source_attach,
    format_html_native_source_attach_summary,
)


def test_attach_arxiv_substack_honesty():
    c = compose_html_native_source_attach(
        session_id="ws-1",
        parent_asset_id="asset-1",
        requested_families=["arxiv", "substack"],
        operator_ack=True,
        sources=[
            {
                "source_id": "s1",
                "family": "arxiv",
                "title": "Scaling laws",
                "external_id": "arxiv:2301.00001",
                "html_fragment": "<article>abstract…</article>",
            },
            {
                "source_id": "s2",
                "family": "substack",
                "title": "Essay on routing",
                "url": "https://example.substack.com/p/routing",
            },
        ],
    )
    assert c.attach_ready is True
    assert c.source_count == 2
    assert c.html_ready_count == 1
    assert c.remote_fetched is False
    assert c.pdf_view_authorized is False
    assert c.store_mutated is False
    d = c.to_dict()
    assert d["remote_fetched"] is False
    assert d["pdf_view_authorized"] is False
    assert d["store_mutated"] is False
    assert "remote_fetched=false" in format_html_native_source_attach_summary(c)


def test_not_ready_without_ack_or_sources():
    no_ack = compose_html_native_source_attach(
        session_id="ws-1",
        parent_asset_id="a",
        requested_families=["arxiv"],
        operator_ack=False,
        sources=[
            {
                "source_id": "s1",
                "family": "arxiv",
                "title": "T",
                "html_fragment": "<p>x</p>",
            }
        ],
    )
    assert no_ack.attach_ready is False
    empty = compose_html_native_source_attach(
        session_id="ws-1",
        parent_asset_id="a",
        requested_families=["arxiv"],
        operator_ack=True,
        sources=[],
    )
    assert empty.attach_ready is False


def test_rejects_family_and_duplicates():
    with pytest.raises(
        HtmlNativeSourceAttachComposeError, match="not in requested_families"
    ):
        compose_html_native_source_attach(
            session_id="ws",
            parent_asset_id="a",
            requested_families=["arxiv"],
            operator_ack=True,
            sources=[
                {"source_id": "s1", "family": "substack", "title": "T"},
            ],
        )
    with pytest.raises(HtmlNativeSourceAttachComposeError, match="duplicate"):
        compose_html_native_source_attach(
            session_id="ws",
            parent_asset_id="a",
            requested_families=["arxiv"],
            operator_ack=True,
            sources=[
                {"source_id": "s1", "family": "arxiv", "title": "A"},
                {"source_id": "s1", "family": "arxiv", "title": "B"},
            ],
        )
