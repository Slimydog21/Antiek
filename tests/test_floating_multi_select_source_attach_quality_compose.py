"""Pure tests for floating multi-select + source attach quality compose."""

from __future__ import annotations

from substrate.floating_multi_select_source_attach_quality_compose import (
    compose_floating_multi_select_source_attach_quality,
    format_floating_multi_select_source_attach_quality_summary,
)

MEMBERS = [
    {
        "instance_id": "inst-a",
        "parent_asset_id": "asset-1",
        "status": "open",
        "highlight": "scaling laws claim",
        "prior_prompt": "What evidence supports the claim?",
        "context": ["card-a"],
    },
    {
        "instance_id": "inst-b",
        "parent_asset_id": "asset-1",
        "status": "completed",
        "highlight": "counter-evidence",
        "findings": ["finding-b1"],
    },
    {
        "instance_id": "inst-c",
        "parent_asset_id": "asset-1",
        "status": "proposed",
        "highlight": "third angle",
    },
]
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


def test_multi_select_sources_ready():
    c = compose_floating_multi_select_source_attach_quality(
        session_id="sess-1",
        parent_asset_id="asset-1",
        members=MEMBERS,
        selected_instance_ids=["inst-a", "inst-b"],
        pack_mode="cohesive_prompt",
        cohesive_prompt="Synthesize A and B with arxiv/substack",
        operator_ack=True,
        requested_families=["arxiv", "substack"],
        sources=SOURCES,
        quality_overall=0.88,
        quality_floor=0.7,
        would_exceed=False,
    )
    assert c.multi_select.pack_ready is True
    assert c.source_quality.pack_ready is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.remote_fetched is False
    assert c.pdf_view_authorized is False
    assert c.analysis_written is False
    assert c.merge_executed is False
    assert (
        c.authority
        == "floating_multi_select_source_attach_quality_compose_advisory"
    )
    assert "remote_fetched=false" in format_floating_multi_select_source_attach_quality_summary(
        c
    )
    assert c.to_dict()["live_dispatched"] is False


def test_budget_blocks():
    c = compose_floating_multi_select_source_attach_quality(
        session_id="sess-2",
        parent_asset_id="asset-1",
        members=MEMBERS,
        selected_instance_ids=["inst-a", "inst-b"],
        pack_mode="cohesive_prompt",
        cohesive_prompt="Go",
        operator_ack=True,
        requested_families=["arxiv"],
        sources=[SOURCES[0]],
        quality_overall=0.9,
        would_exceed=True,
    )
    assert c.source_quality.pack_ready is False
    assert c.pack_ready is False
    assert c.live_dispatched is False


def test_operator_ack_false():
    c = compose_floating_multi_select_source_attach_quality(
        session_id="sess-3",
        parent_asset_id="asset-1",
        members=MEMBERS,
        selected_instance_ids=["inst-a", "inst-b"],
        pack_mode="cohesive_prompt",
        cohesive_prompt="Synthesize",
        operator_ack=False,
        requested_families=["arxiv", "substack"],
        sources=SOURCES,
        quality_overall=0.9,
        would_exceed=False,
    )
    assert c.pack_ready is False
    assert c.remote_fetched is False


def test_low_quality_blocks():
    c = compose_floating_multi_select_source_attach_quality(
        session_id="sess-4",
        parent_asset_id="asset-1",
        members=MEMBERS,
        selected_instance_ids=["inst-a", "inst-b", "inst-c"],
        pack_mode="collective_pack",
        cohesive_prompt="Pack",
        operator_ack=True,
        requested_families=["arxiv"],
        sources=[SOURCES[0]],
        quality_overall=0.2,
        quality_floor=0.7,
        would_exceed=False,
    )
    assert c.source_quality.pack_ready is False
    assert c.pack_ready is False
    assert c.pdf_view_authorized is False
