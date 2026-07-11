"""Pure tests for midnight oil source attach quality twin compose."""

from __future__ import annotations

from substrate.midnight_oil_source_attach_quality_twin_compose import (
    compose_midnight_oil_source_attach_quality_twin,
    format_midnight_oil_source_attach_quality_twin_summary,
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
GOALS = [
    {"goal_id": "g1", "title": "Survey arxiv scaling laws"},
    {"goal_id": "g2", "title": "Synthesize substack claims"},
]


def test_mo_source_twin_ready():
    c = compose_midnight_oil_source_attach_quality_twin(
        operator_id="op-1",
        work_minutes=120,
        goals=GOALS,
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
    assert c.mo_source.pack_ready is True
    assert c.twin_feed.feed_ready is True
    assert c.pack_ready is True
    assert c.twin_feed.finding_count == 4
    assert c.live_execution_authorized is False
    assert c.remote_fetched is False
    assert c.twin_written is False
    assert c.prompts_injected is False
    assert (
        c.authority
        == "midnight_oil_source_attach_quality_twin_compose_advisory"
    )
    assert "twin_written=false" in format_midnight_oil_source_attach_quality_twin_summary(
        c
    )


def test_blocks_without_unattended_ack():
    c = compose_midnight_oil_source_attach_quality_twin(
        operator_id="op-1",
        work_minutes=60,
        goals=[GOALS[0]],
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
    assert c.mo_source.pack_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False


def test_caller_twin_findings():
    c = compose_midnight_oil_source_attach_quality_twin(
        operator_id="op-1",
        work_minutes=120,
        goals=[GOALS[0]],
        usd_per_hour=15,
        approved_ceiling_usd=40,
        operator_ack=True,
        unattended_ack=True,
        spend_consent=True,
        session_id="s",
        parent_asset_id="a",
        requested_families=["arxiv"],
        sources=[SOURCES[0]],
        quality_overall=0.9,
        would_exceed=False,
        twin_findings=[
            {
                "source_id": "custom-1",
                "body": "Unattended recap insight",
                "kind": "insight",
            }
        ],
    )
    assert c.twin_feed.finding_count == 1
    assert c.pack_ready is True
    assert c.twin_written is False


def test_operator_ack_false_blocks():
    c = compose_midnight_oil_source_attach_quality_twin(
        operator_id="op-1",
        work_minutes=120,
        goals=GOALS,
        usd_per_hour=15,
        approved_ceiling_usd=40,
        operator_ack=False,
        unattended_ack=True,
        spend_consent=True,
        session_id="s",
        parent_asset_id="a",
        requested_families=["arxiv", "substack"],
        sources=SOURCES,
        quality_overall=0.9,
        would_exceed=False,
    )
    assert c.pack_ready is False
    assert c.prompts_injected is False
