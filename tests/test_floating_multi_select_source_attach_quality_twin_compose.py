"""Pure tests for multi-select source attach quality twin compose."""

from __future__ import annotations

from substrate.floating_multi_select_source_attach_quality_twin_compose import (
    compose_floating_multi_select_source_attach_quality_twin,
    format_floating_multi_select_source_attach_quality_twin_summary,
)

MEMBERS = [
    {
        "instance_id": "inst-a",
        "parent_asset_id": "asset-1",
        "status": "open",
        "highlight": "scaling laws claim",
    },
    {
        "instance_id": "inst-b",
        "parent_asset_id": "asset-1",
        "status": "completed",
        "highlight": "counter-evidence",
        "findings": ["finding-b1"],
    },
]
SOURCES = [
    {
        "source_id": "arx-1",
        "family": "arxiv",
        "title": "Scaling Laws for Neural Language Models",
        "html_fragment": "<article>abstract…</article>",
    }
]


def test_multi_source_twin_ready():
    c = compose_floating_multi_select_source_attach_quality_twin(
        session_id="sess-1",
        parent_asset_id="asset-1",
        members=MEMBERS,
        selected_instance_ids=["inst-a", "inst-b"],
        pack_mode="cohesive_prompt",
        cohesive_prompt="Synthesize with sources",
        operator_ack=True,
        requested_families=["arxiv"],
        sources=SOURCES,
        quality_overall=0.9,
        would_exceed=False,
    )
    assert c.multi_source.pack_ready is True
    assert c.twin_feed.feed_ready is True
    assert c.pack_ready is True
    assert c.twin_feed.finding_count == 4
    assert c.live_dispatched is False
    assert c.twin_written is False
    assert c.remote_fetched is False
    assert "twin_written=false" in format_floating_multi_select_source_attach_quality_twin_summary(
        c
    )


def test_budget_blocks():
    c = compose_floating_multi_select_source_attach_quality_twin(
        session_id="sess-2",
        parent_asset_id="asset-1",
        members=MEMBERS,
        selected_instance_ids=["inst-a", "inst-b"],
        pack_mode="cohesive_prompt",
        cohesive_prompt="Go",
        operator_ack=True,
        requested_families=["arxiv"],
        sources=SOURCES,
        quality_overall=0.9,
        would_exceed=True,
    )
    assert c.multi_source.pack_ready is False
    assert c.pack_ready is False
    assert c.twin_written is False


def test_operator_ack_false():
    c = compose_floating_multi_select_source_attach_quality_twin(
        session_id="sess-3",
        parent_asset_id="asset-1",
        members=MEMBERS,
        selected_instance_ids=["inst-a", "inst-b"],
        pack_mode="cohesive_prompt",
        cohesive_prompt="Synthesize",
        operator_ack=False,
        requested_families=["arxiv"],
        sources=SOURCES,
        quality_overall=0.9,
        would_exceed=False,
    )
    assert c.pack_ready is False
    assert c.prompts_injected is False


def test_caller_twin_findings():
    c = compose_floating_multi_select_source_attach_quality_twin(
        session_id="sess-4",
        parent_asset_id="asset-1",
        members=MEMBERS,
        selected_instance_ids=["inst-a", "inst-b"],
        pack_mode="cohesive_prompt",
        cohesive_prompt="Synthesize",
        operator_ack=True,
        requested_families=["arxiv"],
        sources=SOURCES,
        quality_overall=0.9,
        would_exceed=False,
        twin_findings=[
            {
                "source_id": "c1",
                "body": "Caller collective insight",
                "kind": "insight",
            }
        ],
    )
    assert c.twin_feed.finding_count == 1
    assert c.pack_ready is True
    assert c.twin_written is False
