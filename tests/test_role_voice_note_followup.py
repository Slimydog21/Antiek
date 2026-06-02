"""Tests for roles/voice_note_followup/ (Sprint 13)."""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from roles.voice_note_followup import (
    VOICE_NOTE_FOLLOWUP_SYSTEM_PROMPT,
    VoiceNoteFollowupContext,
    VoiceNoteFollowupValidationError,
    parse_voice_note_followup_response,
    render_full_prompt,
    render_user_template,
)

# ─────────────────────────────────────────────────────────────────────
# 1. Template rendering
# ─────────────────────────────────────────────────────────────────────


def test_render_user_template_includes_transcript():
    ctx = VoiceNoteFollowupContext(transcript="I was thinking about X.")
    out = render_user_template(ctx)
    assert "I was thinking about X." in out


def test_render_user_template_empty_inputs_show_placeholder():
    ctx = VoiceNoteFollowupContext(transcript="")
    out = render_user_template(ctx)
    assert "empty transcript" in out
    assert "_None._" in out
    assert "No prior voice notes" in out


def test_render_user_template_lists_insights_with_ids():
    ctx = VoiceNoteFollowupContext(
        transcript="thinking",
        insights=[{"id": "i-1", "text": "A is true"}],
        open_questions=[{"id": "q-1", "text": "Why?"}],
    )
    out = render_user_template(ctx)
    assert "`i-1`" in out
    assert "A is true" in out
    assert "`q-1`" in out
    assert "Why?" in out


def test_render_full_prompt_returns_system_and_user():
    sys_p, user_p = render_full_prompt(VoiceNoteFollowupContext(transcript="x"))
    assert sys_p == VOICE_NOTE_FOLLOWUP_SYSTEM_PROMPT
    assert "## Your output" in user_p


# ─────────────────────────────────────────────────────────────────────
# 2. System prompt discipline
# ─────────────────────────────────────────────────────────────────────


def test_system_prompt_limits_to_three_prompts():
    assert "1-3" in VOICE_NOTE_FOLLOWUP_SYSTEM_PROMPT or "three" in VOICE_NOTE_FOLLOWUP_SYSTEM_PROMPT.lower()


def test_system_prompt_forbids_generic_clarification():
    assert "generic" in VOICE_NOTE_FOLLOWUP_SYSTEM_PROMPT.lower()


# ─────────────────────────────────────────────────────────────────────
# 3. Parser
# ─────────────────────────────────────────────────────────────────────


def test_parser_happy_path_minimal():
    raw = (
        '{"prompts": [{"prompt": "What did you actually mean by X?", '
        '"anchor_block_id": "i-1", "rationale": "untouched thread."}]}'
    )
    r = parse_voice_note_followup_response(raw, known_block_ids={"i-1"})
    assert len(r.prompts) == 1
    assert r.prompts[0].anchor_block_id == "i-1"


def test_parser_anchor_null_allowed():
    raw = (
        '{"prompts": [{"prompt": "A free-standing follow-up?", '
        '"anchor_block_id": null, "rationale": ""}]}'
    )
    r = parse_voice_note_followup_response(raw)
    assert r.prompts[0].anchor_block_id is None


def test_parser_unknown_anchor_rejected_when_set_provided():
    raw = (
        '{"prompts": [{"prompt": "What about Y here?", '
        '"anchor_block_id": "i-X", "rationale": "weird."}]}'
    )
    with pytest.raises(VoiceNoteFollowupValidationError, match="known_block_ids"):
        parse_voice_note_followup_response(raw, known_block_ids={"i-1"})


def test_parser_more_than_three_prompts_rejected():
    raw = '{"prompts": [' + ",".join(
        '{"prompt": "Question number ' + str(i) + ' here", "anchor_block_id": null, "rationale": ""}'
        for i in range(4)
    ) + "]}"
    with pytest.raises(VoiceNoteFollowupValidationError, match="too many"):
        parse_voice_note_followup_response(raw)


def test_parser_short_prompt_rejected():
    raw = '{"prompts": [{"prompt": "Why?", "anchor_block_id": null, "rationale": ""}]}'
    with pytest.raises(VoiceNoteFollowupValidationError, match="chars"):
        parse_voice_note_followup_response(raw)


def test_parser_empty_prompts_rejected():
    raw = '{"prompts": []}'
    with pytest.raises(VoiceNoteFollowupValidationError, match="at least one"):
        parse_voice_note_followup_response(raw)


def test_parser_no_json_rejected():
    with pytest.raises(VoiceNoteFollowupValidationError, match="no JSON"):
        parse_voice_note_followup_response("not json at all")
