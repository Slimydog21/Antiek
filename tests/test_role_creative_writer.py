"""Tests for roles/creative_writer/ (Sprint 13)."""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from roles.creative_writer import (
    CREATIVE_WRITER_SYSTEM_PROMPT,
    AdjacentSection,
    CreativeWriterBlock,
    CreativeWriterContext,
    CreativeWriterValidationError,
    parse_creative_writer_response,
    render_full_prompt,
    render_user_template,
)


def _ctx(blocks=None) -> CreativeWriterContext:
    return CreativeWriterContext(
        deliverable_title="Test Memo",
        deliverable_kind="research_memo",
        section_title="Intro",
        section_index=0,
        section_count=3,
        blocks=blocks or [],
    )


# ─────────────────────────────────────────────────────────────────────
# 1. User-template rendering
# ─────────────────────────────────────────────────────────────────────


def test_render_user_template_includes_deliverable_and_section():
    txt = render_user_template(_ctx())
    assert "Test Memo" in txt
    assert "research_memo" in txt
    assert "Intro" in txt
    # 1-based human display: the first section of three reads "section 1 of 3",
    # agreeing with the "§N" neighbour labels (not the old 0-based "section 0").
    assert "section 1 of 3" in txt


def test_render_user_template_no_blocks_message():
    txt = render_user_template(_ctx())
    assert "No blocks attached" in txt


def test_render_user_template_block_formatting():
    blocks = [
        CreativeWriterBlock(
            block_id="node-1", block_kind="insight",
            label="Insight A", body="Substrate compounds.",
            source_tier=2,
        ),
        CreativeWriterBlock(
            block_id="node-2", block_kind="open_question",
            label="Question B", body="What about Y?",
        ),
    ]
    txt = render_user_template(_ctx(blocks))
    assert "`node-1`" in txt
    assert "`node-2`" in txt
    assert "[insight]" in txt
    assert "[open_question]" in txt
    assert "Tier 2" in txt
    assert "Substrate compounds." in txt


def test_render_full_prompt_returns_system_and_user():
    sys_p, user_p = render_full_prompt(_ctx())
    assert sys_p == CREATIVE_WRITER_SYSTEM_PROMPT
    assert "Test Memo" in user_p


# ─────────────────────────────────────────────────────────────────────
# 2. Voice and style discipline lock-in
# ─────────────────────────────────────────────────────────────────────


def test_system_prompt_forbids_em_dashes():
    assert "em-dash" in CREATIVE_WRITER_SYSTEM_PROMPT.lower()


def test_system_prompt_forbids_hedging_modifiers():
    assert "hedging modifier" in CREATIVE_WRITER_SYSTEM_PROMPT.lower() or \
        "perhaps" in CREATIVE_WRITER_SYSTEM_PROMPT.lower()


def test_system_prompt_requires_block_citations():
    assert "[b: " in CREATIVE_WRITER_SYSTEM_PROMPT or "block_id" in CREATIVE_WRITER_SYSTEM_PROMPT
    assert "traceable" in CREATIVE_WRITER_SYSTEM_PROMPT.lower()


def test_system_prompt_operator_notes_outrank():
    assert "operator" in CREATIVE_WRITER_SYSTEM_PROMPT.lower()
    assert "outrank" in CREATIVE_WRITER_SYSTEM_PROMPT.lower()


# ─────────────────────────────────────────────────────────────────────
# 3. Parser
# ─────────────────────────────────────────────────────────────────────


def test_parser_happy_path():
    raw = (
        '{"prose_text": "The substrate compounds nonlinearly [b: node-1].", '
        '"prose_provenance": {"0": ["node-1"]}, '
        '"uncited_blocks": ["node-2"]}'
    )
    r = parse_creative_writer_response(
        raw, known_block_ids={"node-1", "node-2"},
    )
    assert "compounds nonlinearly" in r.prose_text
    assert r.prose_provenance == {0: ["node-1"]}
    assert r.uncited_blocks == ["node-2"]


def test_parser_handles_markdown_fenced_json():
    raw = (
        "```json\n"
        '{"prose_text": "A claim [b: node-1].", '
        '"prose_provenance": {"0": ["node-1"]}, '
        '"uncited_blocks": []}\n'
        "```"
    )
    r = parse_creative_writer_response(raw, known_block_ids={"node-1"})
    assert "A claim" in r.prose_text


def test_parser_empty_prose_text_rejected():
    raw = '{"prose_text": "", "prose_provenance": {}, "uncited_blocks": []}'
    with pytest.raises(CreativeWriterValidationError, match="prose_text"):
        parse_creative_writer_response(raw, known_block_ids=set())


def test_parser_unknown_block_in_provenance_rejected():
    raw = (
        '{"prose_text": "A claim [b: node-x].", '
        '"prose_provenance": {"0": ["node-x"]}, '
        '"uncited_blocks": []}'
    )
    with pytest.raises(CreativeWriterValidationError, match="unknown block_id"):
        parse_creative_writer_response(raw, known_block_ids={"node-1"})


def test_parser_unknown_block_in_uncited_rejected():
    raw = (
        '{"prose_text": "A claim.", '
        '"prose_provenance": {}, '
        '"uncited_blocks": ["node-x"]}'
    )
    with pytest.raises(CreativeWriterValidationError, match="unknown block_id"):
        parse_creative_writer_response(raw, known_block_ids={"node-1"})


def test_parser_non_int_provenance_key_rejected():
    raw = (
        '{"prose_text": "A claim.", '
        '"prose_provenance": {"intro": ["node-1"]}, '
        '"uncited_blocks": []}'
    )
    with pytest.raises(CreativeWriterValidationError, match="integer"):
        parse_creative_writer_response(raw, known_block_ids={"node-1"})


def test_parser_no_json_rejected():
    raw = "I am the model and I will not produce JSON today."
    with pytest.raises(CreativeWriterValidationError, match="no JSON"):
        parse_creative_writer_response(raw, known_block_ids=set())


# ─────────────────────────────────────────────────────────────────────
# 4. Multi-section coherence (Sprint 14)
# ─────────────────────────────────────────────────────────────────────


def test_render_user_template_no_adjacent_sections_shows_placeholder():
    txt = render_user_template(_ctx())
    assert "No adjacent sections yet" in txt


def test_render_user_template_prior_section_includes_prose():
    ctx = CreativeWriterContext(
        deliverable_title="Memo",
        deliverable_kind="research_memo",
        section_title="Body",
        section_index=1,
        section_count=3,
        adjacent_sections=[
            AdjacentSection(
                section_index=0,
                title="Intro",
                prose_text="The substrate compounds nonlinearly.",
            ),
        ],
    )
    txt = render_user_template(ctx)
    assert "Prior §1" in txt
    assert "Intro" in txt
    assert "compounds nonlinearly" in txt


def test_render_user_template_upcoming_section_shows_title_only():
    ctx = CreativeWriterContext(
        deliverable_title="Memo",
        deliverable_kind="research_memo",
        section_title="Body",
        section_index=1,
        section_count=3,
        adjacent_sections=[
            AdjacentSection(section_index=2, title="Conclusion"),
        ],
    )
    txt = render_user_template(ctx)
    assert "Upcoming §3" in txt
    assert "Conclusion" in txt
    assert "not yet written" in txt


def test_system_prompt_warns_against_repetition():
    # Hard discipline lock-in for multi-section coherence: the user
    # template tells the model to avoid restating prior material.
    ctx = CreativeWriterContext(
        deliverable_title="Memo", deliverable_kind="research_memo",
        section_title="Body", section_index=1, section_count=2,
        adjacent_sections=[
            AdjacentSection(section_index=0, title="Intro", prose_text="x"),
        ],
    )
    txt = render_user_template(ctx)
    assert "Do NOT restate" in txt or "repetition" in txt.lower()
