"""Pure tests for source attach residual over write twin collective fullscreen pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.source_attach_write_twin_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    compose_source_attach_write_twin_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
    format_source_attach_write_twin_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_summary,
)
from tests.test_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    FULLSCREEN_PACK,
    WRITE,
)

SOURCES = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "requested_families": ["arxiv", "substack"],
    "sources": [
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
}

WRITE_PACK = {
    "write": WRITE,
    "fullscreen_pack": FULLSCREEN_PACK,
}


def test_source_attach_write_twin_ready():
    c = compose_source_attach_write_twin_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        sources=SOURCES,
        write_pack=WRITE_PACK,
        operator_ack=True,
    )
    assert c.sources.attach_ready is True
    assert c.attach_ready is True
    assert c.write_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.remote_fetched is False
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.twin_written is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "source_attach_write_twin_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
    )
    assert "remote_fetched=false" in (
        format_source_attach_write_twin_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_source_attach_write_twin_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        sources=SOURCES,
        write_pack=WRITE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.pdf_primary is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_source_attach_write_twin_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        sources={**SOURCES, "session_id": "sess-other"},
        write_pack=WRITE_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"


def test_empty_sources_blocks():
    c = compose_source_attach_write_twin_fs_draft_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        sources={**SOURCES, "sources": []},
        write_pack=WRITE_PACK,
        operator_ack=True,
    )
    assert c.attach_ready is False
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
