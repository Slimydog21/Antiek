"""Tests for the extracted roles/grounder/ + formalized roles/challenger/.

Sprint 4 day 4-5 refactor:

- roles/grounder/ — extracted prompt + parser from
  interfaces/research/api/grounding.py. The bridge now re-exports
  the parser as a back-compat shim; the existing test_grounding.py
  tests remain green (verified).
- roles/challenger/ — formalized the default challenge prompt and
  Challenge dataclass + compose_challenge composer.
- roles/_json_decode.py — shared JSON-tolerant decoder that broke
  the circular import path through wrestling.py.

Coverage here is for the role-module surfaces directly. The bridge
behavior tests (test_grounding.py) continue to exercise the end-to-
end paths through the role modules.
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from roles._json_decode import extract_json_object  # noqa: E402
from roles.challenger import (  # noqa: E402
    AUTONOMOUS_CHALLENGER_ROLE_PROMPT,
    DEFAULT_CHALLENGE_PROMPT,
    Challenge,
    compose_challenge,
)
from roles.grounder import (  # noqa: E402
    GROUNDER_ROLE_PROMPT,
    GROUNDING_FAILURE_REASONS,
    GroundingVerdict,
    parse_grounder_response,
)

# ---------------------------------------------------------------------------
# 1. roles/_json_decode — shared parser primitive
# ---------------------------------------------------------------------------


def test_extract_json_object_plain_json():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_object_code_fence():
    assert extract_json_object('```json\n{"a": 2}\n```') == {"a": 2}


def test_extract_json_object_prose_preamble():
    assert extract_json_object("Sure!\n\n{\"a\": 3}") == {"a": 3}


def test_extract_json_object_returns_none_for_garbage():
    assert extract_json_object("no braces here") is None
    assert extract_json_object("") is None


def test_extract_json_object_picks_first_balanced_object():
    text = '{"a": 1} stray words {"b": 2}'
    # The function tries the outermost {...} first; if that fails it
    # walks inward. Either way, returns a valid decode.
    result = extract_json_object(text)
    assert result in ({"a": 1}, {"b": 2}, {"a": 1, "b": 2})


# ---------------------------------------------------------------------------
# 2. roles/grounder
# ---------------------------------------------------------------------------


def test_grounder_prompt_is_non_empty():
    """Sanity: the role prompt exists and explicitly forbids paraphrase."""
    assert "DIRECT textual support" in GROUNDER_ROLE_PROMPT
    assert "Paraphrase is NOT direct" in GROUNDER_ROLE_PROMPT


def test_grounding_failure_reasons_closed_set():
    """Module's frozenset must equal the schema's Literal arg set —
    drift would let the parser produce a value the payload validator
    would reject."""
    import typing

    from substrate.schemas.events import ClaimGroundingCheckFailedPayload

    payload_field = ClaimGroundingCheckFailedPayload.model_fields["reason"]
    schema_args = set(typing.get_args(payload_field.annotation))
    assert schema_args == GROUNDING_FAILURE_REASONS


def test_parse_grounder_response_passed():
    v = parse_grounder_response(
        '{"grounded": true, "located_chunk_id": "chunk-1", "confidence": 0.8}'
    )
    assert isinstance(v, GroundingVerdict)
    assert v.grounded is True
    assert v.located_chunk_id == "chunk-1"
    assert v.confidence == pytest.approx(0.8)
    assert v.reason is None


def test_parse_grounder_response_rejects_fabricated_chunk_id():
    v = parse_grounder_response(
        '{"grounded": true, "located_chunk_id": "chunk-fake", "confidence": 0.8}',
        canonical_chunk_ids={"chunk-real"},
    )
    assert v.grounded is True
    assert v.located_chunk_id is None
    assert v.confidence == pytest.approx(0.8)


def test_parse_grounder_response_failed_with_each_reason():
    for reason in GROUNDING_FAILURE_REASONS:
        v = parse_grounder_response(
            f'{{"grounded": false, "reason": "{reason}"}}'
        )
        assert v.grounded is False
        assert v.reason == reason


def test_parse_grounder_response_clamps_confidence():
    v_hi = parse_grounder_response(
        '{"grounded": true, "located_chunk_id": "c", "confidence": 1.5}'
    )
    assert v_hi.confidence == 1.0

    v_lo = parse_grounder_response(
        '{"grounded": true, "located_chunk_id": "c", "confidence": -0.2}'
    )
    assert v_lo.confidence == 0.0


def test_parse_grounder_response_defaults_to_ambiguous_on_garbage():
    v = parse_grounder_response("totally not JSON")
    assert v == GroundingVerdict(False, None, 0.0, "ambiguous")


def test_parse_grounder_response_coerces_unknown_reason_to_ambiguous():
    v = parse_grounder_response(
        '{"grounded": false, "reason": "i_made_this_up"}'
    )
    assert v.reason == "ambiguous"


# ---------------------------------------------------------------------------
# 3. roles/challenger
# ---------------------------------------------------------------------------


def test_default_challenge_prompt_is_meaningful():
    assert "source passage" in DEFAULT_CHALLENGE_PROMPT
    assert "well-grounded" in DEFAULT_CHALLENGE_PROMPT


def test_autonomous_challenger_prompt_exists():
    """Reserved for the Sprint 6+ autonomous handler. Just check it
    has the expected structural anchors."""
    assert "challenges" in AUTONOMOUS_CHALLENGER_ROLE_PROMPT
    assert "challenged_claim_id" in AUTONOMOUS_CHALLENGER_ROLE_PROMPT


def test_compose_challenge_with_defaults():
    ch = compose_challenge(claim_text="X causes Y")
    assert isinstance(ch, Challenge)
    assert ch.claim_text == "X causes Y"
    assert ch.challenged_claim_id is None
    assert ch.anchor_region_id is None
    assert ch.user_question == DEFAULT_CHALLENGE_PROMPT


def test_compose_challenge_with_explicit_user_question():
    ch = compose_challenge(
        claim_text="X causes Y",
        claim_id="c-1",
        anchor_region_id="r-99",
        user_question="Where in the source does it say this?",
    )
    assert ch.challenged_claim_id == "c-1"
    assert ch.anchor_region_id == "r-99"
    assert ch.user_question == "Where in the source does it say this?"


def test_compose_challenge_strips_whitespace():
    ch = compose_challenge(claim_text="  padded claim  ")
    assert ch.claim_text == "padded claim"


def test_compose_challenge_rejects_empty_claim():
    with pytest.raises(ValueError, match="claim_text"):
        compose_challenge(claim_text="")
    with pytest.raises(ValueError, match="claim_text"):
        compose_challenge(claim_text="   ")


def test_challenge_dataclass_is_frozen():
    ch = compose_challenge(claim_text="x")
    with pytest.raises(Exception):
        ch.claim_text = "mutated"  # type: ignore[misc]


def test_compose_challenge_fallback_to_default_when_user_question_empty():
    """An explicit empty string for user_question falls back to the
    canonical default. Defensive — UI components might pass "" when
    the user just clicks the button without typing."""
    ch = compose_challenge(claim_text="x", user_question="")
    assert ch.user_question == DEFAULT_CHALLENGE_PROMPT
