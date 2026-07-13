"""Tests for draft generation's deterministic substrate (specs/write/ SPR-06).

These cover the parts that protect the moat regardless of which model runs
— and use an INJECTED fake dispatch, so no live LLM is needed:

M2/M6 no-blocks section → GAP, never fabricated prose.
M4 cited claims — every claim cites an attached block; unsupported,
   fabricated, or provenance-mismatched prose is rejected.
M5 voice_style gate WINS — sub-threshold prose returns gate_failed even if
   it cites perfectly.
M1 context-building — OutlineBlocks → CreativeWriterContext with the right
   citation ids.

The deterministic model boundary is injected here; no provider call is needed
to prove that rejected prose cannot cross into durable state.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from roles.creative_writer.prompt import CreativeWriterContext
from substrate.write.draft_generation import (
    VOICE_STYLE_GATE,
    build_creative_writer_context,
    enforce_voice_gate,
    extract_inline_citations,
    generate_section,
    validate_generated_citations,
)
from substrate.write.outline_block import OutlineBlock


def _oblock(obid, *, node_id=None, content=None, kind="insight", prov="graph_node"):
    return OutlineBlock(
        outline_block_id=obid, section_id="sec-1", block_kind=kind,
        provenance_kind=prov, node_id=node_id, source_block_kind=None,
        source_block_id=None, content=content, block_index=0, cluster_id=None,
    )


def _fake_dispatch(response: str):
    def _fn(system: str, user: str) -> str:
        return response
    return _fn


# ── M1 — context building ──────────────────────────────────────────


def test_build_context_uses_node_id_as_citation_id():
    blocks = [_oblock("oblk-1", node_id="node-abc")]
    ctx = build_creative_writer_context(
        deliverable_title="T", deliverable_kind="research_memo",
        section_title="S", section_index=0, section_count=1, blocks=blocks,
        node_label_resolver=lambda nid: "the resolved label",
    )
    assert ctx.blocks[0].block_id == "node-abc"
    assert ctx.blocks[0].body == "the resolved label"


def test_user_authored_block_cites_outline_block_id():
    blocks = [_oblock("oblk-2", content="my thought", kind="user_authored", prov="user_authored")]
    ctx = build_creative_writer_context(
        deliverable_title="T", deliverable_kind="general_essay",
        section_title="S", section_index=0, section_count=1, blocks=blocks,
    )
    assert ctx.blocks[0].block_id == "oblk-2"
    assert ctx.blocks[0].body == "my thought"


def test_adjacent_sections_reach_the_context_and_the_prompt():
    """WV-SPR-01 (§10.6 coherence): adjacent sections handed to the builder
    must land on the CreativeWriterContext AND be rendered into the prompt the
    model actually sees — prior sections carrying their prose (so the model
    does not repeat them), the real position instead of the 0-of-1 placeholder.
    Without the render, threading them through the context would be inert."""
    from roles.creative_writer.prompt import AdjacentSection, render_full_prompt

    ctx = build_creative_writer_context(
        deliverable_title="Memo", deliverable_kind="research_memo",
        section_title="Consequences", section_index=2, section_count=3,
        blocks=[_oblock("oblk-1", node_id="node-abc")],
        adjacent_sections=[
            AdjacentSection(section_index=0, title="Origins", prose_text="Origins prose."),
            AdjacentSection(section_index=1, title="The turn", prose_text="The turn prose."),
        ],
        node_label_resolver=lambda nid: "resolved",
    )
    assert [a.title for a in ctx.adjacent_sections] == ["Origins", "The turn"]
    assert ctx.section_index == 2 and ctx.section_count == 3

    _system, user = render_full_prompt(ctx)
    assert "Origins prose." in user  # prior prose is visible → avoid repetition
    assert "The turn prose." in user
    # 1-based, human-facing position — the 3rd of 3, agreeing with the "§N"
    # neighbour labels; NOT the old "section 0 of 1" placeholder.
    assert "section 3 of 3" in user


def test_context_without_adjacent_sections_defaults_empty():
    """A single-section deliverable passes no neighbours; the builder must
    default to an empty list (not crash, not fabricate one)."""
    ctx = build_creative_writer_context(
        deliverable_title="T", deliverable_kind="general_essay",
        section_title="Only", section_index=0, section_count=1,
        blocks=[_oblock("oblk-3", node_id="n")],
    )
    assert ctx.adjacent_sections == []


# ── M4 — citation validation (the moat) ────────────────────────────


def test_inline_citation_extraction():
    text = "The thesis holds [b: node-1]. The mechanism is load-bearing [b: node-2]."
    assert extract_inline_citations(text) == ["node-1", "node-2"]


def test_unsupported_paragraph_flagged():
    from roles.creative_writer.parser import CreativeWriterResult
    result = CreativeWriterResult(
        prose_text=(
            "The capital intensity rises with scale and the moat is the data [b: node-1].\n\n"
            "This is a long, substantive, uncited claim that asserts something material "
            "without naming any source block at all."
        ),
        prose_provenance={0: ["node-1"]},
        uncited_blocks=[],
    )
    report = validate_generated_citations(result, attached_block_ids={"node-1"})
    assert 0 in report.supported_paragraphs
    assert 1 in report.unsupported_paragraphs  # flagged, not asserted as fact
    assert not report.all_claims_cited


def test_fabricated_citation_flagged():
    from roles.creative_writer.parser import CreativeWriterResult
    result = CreativeWriterResult(
        prose_text="A claim citing a block that was never attached [b: node-ghost].",
        prose_provenance={},
        uncited_blocks=[],
    )
    report = validate_generated_citations(result, attached_block_ids={"node-real"})
    assert "node-ghost" in report.fabricated_citations
    assert not report.all_claims_cited


def test_all_claims_cited_clean_case():
    from roles.creative_writer.parser import CreativeWriterResult
    result = CreativeWriterResult(
        prose_text="The thesis holds because the mechanism is load-bearing [b: node-1].",
        prose_provenance={0: ["node-1"]},
        uncited_blocks=[],
    )
    report = validate_generated_citations(result, attached_block_ids={"node-1"})
    assert report.all_claims_cited
    assert report.fabricated_citations == []
    assert report.provenance_mismatches == []


def _context_with_nodes(*node_ids: str) -> CreativeWriterContext:
    return build_creative_writer_context(
        deliverable_title="T", deliverable_kind="research_memo",
        section_title="S", section_index=0, section_count=1,
        blocks=[_oblock(f"oblk-{i}", node_id=node_id) for i, node_id in enumerate(node_ids)],
    )


def test_generation_rejects_substantive_uncited_paragraph():
    raw = (
        '{"prose_text": "This substantive paragraph makes a material claim without any '
        'attached evidence or inline citation at all.", '
        '"prose_provenance": {}, "uncited_blocks": ["node-1"]}'
    )
    res = generate_section(
        ctx=_context_with_nodes("node-1"),
        dispatch_fn=_fake_dispatch(raw), section_id="sec-1",
    )
    assert res.status == "citation_failed"
    assert res.citation_report.unsupported_paragraphs == [0]
    assert res.prose_provenance == {}


def test_generation_rejects_fabricated_inline_citation():
    raw = (
        '{"prose_text": "The mechanism is load-bearing and grounded in the evidence '
        '[b: node-ghost].", "prose_provenance": {"0": []}, '
        '"uncited_blocks": ["node-1"]}'
    )
    res = generate_section(
        ctx=_context_with_nodes("node-1"),
        dispatch_fn=_fake_dispatch(raw), section_id="sec-1",
    )
    assert res.status == "citation_failed"
    assert res.citation_report.fabricated_citations == ["node-ghost"]


def test_generation_classifies_fabricated_inline_and_provenance_as_citation_failure():
    raw = (
        '{"prose_text": "The mechanism is load-bearing and grounded in the evidence '
        '[b: node-ghost].", "prose_provenance": {"0": ["node-ghost"]}, '
        '"uncited_blocks": ["node-1"]}'
    )
    res = generate_section(
        ctx=_context_with_nodes("node-1"),
        dispatch_fn=_fake_dispatch(raw), section_id="sec-1",
    )
    assert res.status == "citation_failed"
    assert res.citation_report.fabricated_citations == ["node-ghost"]
    assert res.citation_report.provenance_mismatches == []


@pytest.mark.parametrize(
    "inline,provenance",
    [
        ("", '["node-1"]'),
        (" [b: node-1]", "[]"),
        (" [b: node-1]", '["node-2"]'),
    ],
)
def test_generation_rejects_inline_provenance_disagreement(inline, provenance):
    raw = (
        '{"prose_text": "The mechanism is load-bearing and grounded in attached evidence'
        f'{inline}.", "prose_provenance": {{"0": {provenance}}}, '
        '"uncited_blocks": []}'
    )
    res = generate_section(
        ctx=_context_with_nodes("node-1", "node-2"),
        dispatch_fn=_fake_dispatch(raw), section_id="sec-1",
    )
    assert res.status == "citation_failed"
    assert res.citation_report.provenance_mismatches == [0]


def test_unused_attached_block_and_short_structural_paragraph_remain_legal():
    raw = (
        '{"prose_text": "Implications.\\n\\nThe mechanism is load-bearing and grounded '
        'in the attached evidence [b: node-1].", '
        '"prose_provenance": {"1": ["node-1"]}, '
        '"uncited_blocks": ["node-2"]}'
    )
    res = generate_section(
        ctx=_context_with_nodes("node-1", "node-2"),
        dispatch_fn=_fake_dispatch(raw), section_id="sec-1",
    )
    assert res.status == "generated"
    assert res.citation_report.uncited_blocks == ["node-2"]


def test_generation_rejects_provenance_for_nonexistent_paragraph():
    raw = (
        '{"prose_text": "The mechanism is load-bearing and grounded in the evidence '
        '[b: node-1].", "prose_provenance": {"0": ["node-1"], "9": ["node-1"]}, '
        '"uncited_blocks": []}'
    )
    res = generate_section(
        ctx=_context_with_nodes("node-1"),
        dispatch_fn=_fake_dispatch(raw), section_id="sec-1",
    )
    assert res.status == "citation_failed"
    assert res.citation_report.provenance_mismatches == [9]


# ── M5 — the gate wins ─────────────────────────────────────────────


def test_gate_passes_clean_prose():
    clean = "The thesis holds because the mechanism is load-bearing, not decorative."
    gate = enforce_voice_gate(clean)
    assert gate.passed
    assert gate.score >= VOICE_STYLE_GATE


def test_generation_gate_failed_blocks_slop():
    """Even with perfect citations, slop fails the gate → gate_failed."""
    slop_json = (
        '{"prose_text": "Key takeaways: let me explain [b: node-1]. Moreover, '
        'furthermore, additionally, it could be argued that perhaps possibly — '
        'arguably — in some sense worth noting [b: node-1]. In conclusion, to '
        'summarize, all in all [b: node-1].\\n- one\\n- two\\n- three\\n- four\\n'
        '- five\\n- six\\n- seven", '
        '"prose_provenance": {"0": ["node-1"]}, "uncited_blocks": []}'
    )
    ctx = build_creative_writer_context(
        deliverable_title="T", deliverable_kind="research_memo",
        section_title="S", section_index=0, section_count=1,
        blocks=[_oblock("oblk-1", node_id="node-1")],
    )
    res = generate_section(ctx=ctx, dispatch_fn=_fake_dispatch(slop_json), section_id="sec-1")
    assert res.status == "gate_failed"
    assert "gate wins" in res.detail.lower()


# ── M2/M6 — no-blocks section → gap, no fabrication ────────────────


def test_no_blocks_section_returns_gap():
    ctx = CreativeWriterContext(
        deliverable_title="T", deliverable_kind="research_memo",
        section_title="Empty section", section_index=0, section_count=1, blocks=[],
    )
    # dispatch_fn should NOT be called for an empty section.
    def _boom(system, user):
        raise AssertionError("must not call the model for a no-blocks section")
    res = generate_section(ctx=ctx, dispatch_fn=_boom, section_id="sec-1")
    assert res.status == "gap"
    assert res.prose_text == ""
    assert "not fabricated" in res.detail


def test_happy_path_generation_with_fake_model():
    good_json = (
        '{"prose_text": "The capital intensity rises with scale, and the moat is '
        'the data rather than the model [b: node-1].", '
        '"prose_provenance": {"0": ["node-1"]}, "uncited_blocks": []}'
    )
    ctx = build_creative_writer_context(
        deliverable_title="T", deliverable_kind="research_memo",
        section_title="S", section_index=0, section_count=1,
        blocks=[_oblock("oblk-1", node_id="node-1")],
    )
    res = generate_section(ctx=ctx, dispatch_fn=_fake_dispatch(good_json), section_id="sec-1")
    assert res.status == "generated"
    assert res.citation_report.all_claims_cited
    assert res.gate.passed
