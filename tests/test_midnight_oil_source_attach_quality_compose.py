"""Pure tests for midnight oil source attach quality compose."""

from __future__ import annotations

from substrate.midnight_oil_source_attach_quality_compose import (
    compose_midnight_oil_source_attach_quality,
    format_midnight_oil_source_attach_quality_summary,
)

SOURCES = [
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
        "title": "Deep research essay",
        "html_fragment": "<article>essay…</article>",
    },
]


def test_mo_sources_ready():
    c = compose_midnight_oil_source_attach_quality(
        operator_id="op-1",
        work_minutes=120,
        goals=[
            {"goal_id": "g1", "title": "Survey arxiv scaling laws"},
            {"goal_id": "g2", "title": "Synthesize substack claims"},
        ],
        usd_per_hour=15,
        approved_ceiling_usd=40,
        operator_ack=True,
        unattended_ack=True,
        spend_consent=True,
        session_id="sess-1",
        parent_asset_id="asset-1",
        requested_families=["arxiv", "substack"],
        sources=SOURCES,
        quality_overall=0.88,
        quality_floor=0.7,
        would_exceed=False,
    )
    assert c.mo_unattended.unattended_package_ready is True
    assert c.source_quality.pack_ready is True
    assert c.pack_ready is True
    assert c.live_execution_authorized is False
    assert c.remote_fetched is False
    assert c.pdf_view_authorized is False
    assert c.live_dispatched is False
    assert c.store_mutated is False
    assert (
        c.authority == "midnight_oil_source_attach_quality_compose_advisory"
    )
    assert "live_execution_authorized=false" in format_midnight_oil_source_attach_quality_summary(
        c
    )
    assert c.to_dict()["remote_fetched"] is False


def test_blocks_without_unattended_ack():
    c = compose_midnight_oil_source_attach_quality(
        operator_id="op-1",
        work_minutes=60,
        goals=[{"goal_id": "g1", "title": "T"}],
        usd_per_hour=10,
        approved_ceiling_usd=20,
        operator_ack=True,
        unattended_ack=False,
        spend_consent=True,
        session_id="s",
        parent_asset_id="a",
        requested_families=["arxiv"],
        sources=[SOURCES[0]],
        quality_overall=0.9,
        would_exceed=False,
    )
    assert c.mo_unattended.unattended_package_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False


def test_low_quality_blocks():
    c = compose_midnight_oil_source_attach_quality(
        operator_id="op-1",
        work_minutes=120,
        goals=[{"goal_id": "g1", "title": "Survey"}],
        usd_per_hour=15,
        approved_ceiling_usd=40,
        operator_ack=True,
        unattended_ack=True,
        spend_consent=True,
        session_id="s",
        parent_asset_id="a",
        requested_families=["arxiv"],
        sources=[SOURCES[0]],
        quality_overall=0.2,
        quality_floor=0.7,
        would_exceed=False,
    )
    assert c.source_quality.pack_ready is False
    assert c.pack_ready is False
    assert c.remote_fetched is False


def test_would_exceed_blocks():
    c = compose_midnight_oil_source_attach_quality(
        operator_id="op-1",
        work_minutes=60,
        goals=[{"goal_id": "g1", "title": "T"}],
        usd_per_hour=10,
        approved_ceiling_usd=20,
        operator_ack=True,
        unattended_ack=True,
        spend_consent=True,
        session_id="s",
        parent_asset_id="a",
        requested_families=["arxiv"],
        sources=[SOURCES[0]],
        quality_overall=0.9,
        would_exceed=True,
    )
    assert c.source_quality.pack_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
