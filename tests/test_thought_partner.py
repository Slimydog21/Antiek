"""Thought-partner role tests (Sprint 18, master-spec §4.5)."""

from __future__ import annotations

import json

from roles.thought_partner import (
    VALID_SHAPES,
    compose_thought_partner_prompt,
    parse_thought_partner_response,
)


def test_valid_shapes_match_spec():
    assert frozenset({"challenge", "synthesis", "extension"}) == VALID_SHAPES


def test_compose_prompt_includes_selected_notes():
    prompt = compose_thought_partner_prompt(
        user_prompt="What's the falsification condition for these claims?",
        selected_notes=[
            {"note_id": "n-1", "note_text": "Error rates below 10⁻³ at 100Q."},
            {"note_id": "n-2", "note_text": "Decoherence times suggest physical-limit headroom."},
        ],
    )
    assert "NOTE n-1" in prompt
    assert "NOTE n-2" in prompt
    assert "falsification condition" in prompt
    # Style guide is optional; omitting it should not break output.
    assert "SECTOR STYLE GUIDE" not in prompt


def test_compose_prompt_includes_style_guide_when_provided():
    prompt = compose_thought_partner_prompt(
        user_prompt="Synthesize",
        selected_notes=[{"note_id": "n-1", "note_text": "Test"}],
        sector_style_guide="Use 'sidelobe' not 'side-lobe'; cite by year.",
    )
    assert "SECTOR STYLE GUIDE" in prompt
    assert "sidelobe" in prompt


# ── Parser tests ─────────────────────────────────────────────────────


def test_parse_challenge_shape():
    response = json.dumps({
        "shape": "challenge",
        "challenges": [
            {
                "condition": "If gate error exceeds 10⁻² at 200Q the threshold thesis fails",
                "note_ids": ["n-1", "n-3"],
            },
        ],
        "synthesis_text": "",
        "extensions": [],
    })
    parsed = parse_thought_partner_response(response)
    assert parsed.shape == "challenge"
    assert len(parsed.challenges) == 1
    assert parsed.challenges[0].condition.startswith("If gate error")
    assert parsed.challenges[0].note_ids == ["n-1", "n-3"]
    assert parsed.synthesis is None
    assert parsed.extensions == []


def test_parse_synthesis_shape():
    response = json.dumps({
        "shape": "synthesis",
        "challenges": [],
        "synthesis_text": "The notes converge on a single thesis: error rates have crossed the threshold but the margin is thin and group-dependent.",
        "extensions": [],
    })
    parsed = parse_thought_partner_response(response)
    assert parsed.shape == "synthesis"
    assert parsed.synthesis is not None
    assert "threshold" in parsed.synthesis.text


def test_parse_extension_shape():
    response = json.dumps({
        "shape": "extension",
        "challenges": [],
        "synthesis_text": "",
        "extensions": [
            {
                "sub_question": "How does QuEra's gate-set decomposition compare to Vuletic's when normalized for circuit depth?",
                "tag": "cross_domain",
                "rationale": "The cross-group benchmark would resolve the gap.",
            },
        ],
    })
    parsed = parse_thought_partner_response(response)
    assert parsed.shape == "extension"
    assert len(parsed.extensions) == 1
    assert parsed.extensions[0].tag == "cross_domain"


def test_parse_unknown_shape_coerces_to_synthesis():
    response = json.dumps({
        "shape": "garbage_value",
        "synthesis_text": "Some text",
        "challenges": [],
        "extensions": [],
    })
    parsed = parse_thought_partner_response(response)
    assert parsed.shape == "synthesis"


def test_parse_malformed_json_falls_back_to_raw_synthesis():
    raw = "This is not JSON but it is a valid musing about the problem."
    parsed = parse_thought_partner_response(raw)
    assert parsed.shape == "synthesis"
    assert parsed.synthesis is not None
    assert raw in parsed.synthesis.text


def test_parse_drops_empty_challenge_conditions():
    response = json.dumps({
        "shape": "challenge",
        "challenges": [
            {"condition": "", "note_ids": ["n-1"]},
            {"condition": "valid one", "note_ids": ["n-2"]},
        ],
    })
    parsed = parse_thought_partner_response(response)
    assert len(parsed.challenges) == 1
    assert parsed.challenges[0].condition == "valid one"


def test_parse_drops_empty_extension_sub_questions():
    response = json.dumps({
        "shape": "extension",
        "extensions": [
            {"sub_question": "", "tag": "x"},
            {"sub_question": "valid one"},
        ],
    })
    parsed = parse_thought_partner_response(response)
    assert len(parsed.extensions) == 1
    assert parsed.extensions[0].sub_question == "valid one"
