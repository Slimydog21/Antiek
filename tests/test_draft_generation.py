"""Tests for draft generation's deterministic substrate (specs/write/ SPR-06).

These cover the parts that protect the moat regardless of which model runs
— and use an INJECTED fake dispatch, so no live LLM is needed:

M2/M6 no-blocks section → GAP, never fabricated prose.
M4 cited claims — every claim cites an attached block; uncited paragraphs
   flagged 'unsupported'; citations to non-attached blocks flagged
   'fabricated'.
M5 voice_style gate WINS — sub-threshold prose returns gate_failed even if
   it cites perfectly.
M1 context-building — OutlineBlocks → CreativeWriterContext with the right
   citation ids.

The live generation path (the actual prose a model returns) needs API
credentials + creative_writer wired into the dispatch config; it is marked
PARTIAL in the handoff, not faked green here.
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
