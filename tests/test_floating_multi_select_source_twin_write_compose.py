"""Pure tests for multi-select source twin write compose."""

from __future__ import annotations

from substrate.floating_multi_select_source_twin_write_compose import (
    compose_floating_multi_select_source_twin_write,
    format_floating_multi_select_source_twin_write_summary,
)

MEMBERS = [
    {
        "instance_id": "inst-a",
        "parent_asset_id": "asset-1",
        "status": "completed",
        "highlight": "scaling laws claim",
        "findings": ["finding-a1"],
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


def test_multi_twin_write_ready():
    c = compose_floating_multi_select_source_twin_write(
        session_id="sess-1",
        draft_id="draft-1",
        parent_asset_id="asset-1",
        members=MEMBERS,
        selected_instance_ids=["inst-a", "inst-b"],
        pack_mode="cohesive_prompt",
        cohesive_prompt="Synthesize with sources into write",
        operator_ack=True,
        requested_families=["arxiv"],
        sources=SOURCES,
        quality_overall=0.9,
        would_exceed=False,
    )
    assert c.multi_twin.pack_ready is True
    assert c.write_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.twin_written is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.merge_executed is False
    assert c.remote_fetched is False
    assert (
        c.authority
        == "floating_multi_select_source_twin_write_compose_advisory"
    )
    assert "draft_written=false" in format_floating_multi_select_source_twin_write_summary(
        c
    )


def test_budget_blocks():
    c = compose_floating_multi_select_source_twin_write(
        session_id="sess-2",
        draft_id="draft-2",
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
    assert c.multi_twin.pack_ready is False
    assert c.pack_ready is False
    assert c.draft_written is False


def test_operator_ack_false():
    c = compose_floating_multi_select_source_twin_write(
        session_id="sess-3",
        draft_id="draft-3",
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
    assert c.analysis_written is False


def test_caller_twin_slices():
    c = compose_floating_multi_select_source_twin_write(
        session_id="sess-4",
        draft_id="draft-4",
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
        twin_slices=[
            {
                "parent_asset_id": "asset-1",
                "insights": ["Caller insight A", "Caller insight B"],
                "questions": ["Q1?"],
            }
        ],
        chase_slots=[
            {
                "slot_id": "s1",
                "question_id": "q1",
                "parent_asset_id": "asset-1",
                "status": "completed",
                "findings": ["f1"],
            },
            {
                "slot_id": "s2",
                "question_id": "q2",
                "parent_asset_id": "asset-1",
                "status": "completed",
                "findings": ["f2"],
            },
        ],
        analysis_kind="full_analysis",
    )
    assert c.write_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.merge_executed is False
