"""Tests for roles/evidence_retriever/ (Sprint 6 day 4-5 extraction —
prompt + parser only; bridge handler lands Sprint 7).

Coverage:

A. Prompt:
   1. ``render_user_template`` substitutes all six placeholders.
   2. ``render_full_prompt`` includes system + user.
   3. Empty chunks/subgraph fall back to ``(no chunks)`` /
      ``(no subgraph)`` placeholders so the template never carries
      a stranded ``{{...}}`` token.
   4. ``extra_user_prefix`` threads through the user portion.

B. Parser — happy path:
   5. Well-formed response parses into ``EvidenceResult`` with
      correct nested shapes.
   6. ``insufficient_evidence=True`` accepts empty
      ``supporting_claims``.

C. Parser — validation failures:
   7. Garbage text → ``EvidenceValidationError``.
   8. Missing ``sub_question`` rejected.
   9. ``sub_question`` mismatch when ``expected_sub_question`` set.
   10. Top-level keys missing / wrong types rejected
       (``answer``, ``supporting_claims``, ``evidentiary_gaps``,
       ``insufficient_evidence``).
   11. ``insufficient_evidence=False`` with empty
       ``supporting_claims`` rejected (cite-every-claim rule).
   12. Bad ``evidence_type`` rejected.
   13. Bad ``confidence`` rejected.
   14. ``source_tier_min=0`` REJECTED (upstream's null-vs-zero rule).
   15. ``source_tier_min=6`` rejected.
   16. ``source_tier_min=None`` accepted (the spec sentinel).
   17. Empty ``chunk_ids`` rejected for non-``gap`` claims.
   18. Empty ``chunk_ids`` ACCEPTED for ``gap`` claims.
   19. Non-string ``chunk_ids`` rejected.
   20. ``source_tier_min`` as bool (subclass of int) rejected.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from roles.evidence_retriever import (  # noqa: E402
    EVIDENCE_CONFIDENCE_LEVELS,
    EVIDENCE_RETRIEVER_SYSTEM_PROMPT,
    EVIDENCE_TYPES,
    EvidenceResult,
    EvidenceValidationError,
    parse_evidence_response,
    render_full_prompt,
    render_user_template,
)


# ---------------------------------------------------------------------------
# A. Prompt
# ---------------------------------------------------------------------------


def test_render_user_template_substitutes_all_placeholders():
    s = render_user_template(
        sub_question="Q?",
        category="market_sizing",
        evidence_type_required="quantitative",
        top_k=5,
        chunks_block="[chunk1]",
        subgraph_block="[edge1]",
    )
    assert "Q?" in s
    assert "market_sizing" in s
    assert "quantitative" in s
    assert "k=5" in s
    assert "[chunk1]" in s
    assert "[edge1]" in s
    for unsubstituted in (
        "{{sub_question}}", "{{category}}", "{{evidence_type_required}}",
        "{{top_k}}", "{{chunks_block}}", "{{subgraph_block}}",
    ):
        assert unsubstituted not in s


def test_render_user_template_empty_blocks_fall_back():
    s = render_user_template(
        sub_question="Q",
        category="market_sizing",
        evidence_type_required="quantitative",
        top_k=0,
        chunks_block="",
        subgraph_block="",
    )
    assert "(no chunks)" in s
    assert "(no subgraph)" in s


def test_render_full_prompt_includes_system_and_user():
    p = render_full_prompt(
        sub_question="Q", category="defensibility",
        evidence_type_required="mixed", top_k=3,
        chunks_block="C", subgraph_block="S",
    )
    assert EVIDENCE_RETRIEVER_SYSTEM_PROMPT in p
    assert "Q" in p


def test_render_full_prompt_extra_user_prefix_threads():
    p = render_full_prompt(
        sub_question="Q", category="defensibility",
        evidence_type_required="mixed", top_k=3,
        chunks_block="C", subgraph_block="S",
        extra_user_prefix="REGENERATE",
    )
    user_start = p.index("REGENERATE")
    sys_end = p.index(EVIDENCE_RETRIEVER_SYSTEM_PROMPT) + len(EVIDENCE_RETRIEVER_SYSTEM_PROMPT)
    assert user_start > sys_end


# ---------------------------------------------------------------------------
# B. Parser — happy path
# ---------------------------------------------------------------------------


def _good_response() -> dict:
    return {
        "sub_question": "What is X?",
        "answer": "X is established by two Tier-1 sources.",
        "supporting_claims": [
            {
                "claim": "X is observable as Y",
                "evidence_type": "direct",
                "chunk_ids": ["chunk-1", "chunk-2"],
                "edge_ids": ["edge-1"],
                "source_tier_min": 1,
                "confidence": "high",
                "confidence_basis": "two independent Tier-1 SEC filings",
            },
        ],
        "evidentiary_gaps": [
            {
                "gap_description": "Pre-2020 baseline missing",
                "additional_retrieval_suggested": "Search annual reports 2015-2019",
            },
        ],
        "insufficient_evidence": False,
    }


def test_parse_happy_path():
    out = parse_evidence_response(json.dumps(_good_response()))
    assert isinstance(out, EvidenceResult)
    assert out.sub_question == "What is X?"
    assert out.insufficient_evidence is False
    assert len(out.supporting_claims) == 1
    c = out.supporting_claims[0]
    assert c.evidence_type == "direct"
    assert c.chunk_ids == ("chunk-1", "chunk-2")
    assert c.source_tier_min == 1
    assert len(out.evidentiary_gaps) == 1


def test_parse_insufficient_evidence_with_no_claims():
    payload = {
        "sub_question": "Q",
        "answer": "",
        "supporting_claims": [],
        "evidentiary_gaps": [
            {"gap_description": "everything"},
        ],
        "insufficient_evidence": True,
    }
    out = parse_evidence_response(json.dumps(payload))
    assert out.insufficient_evidence is True
    assert out.supporting_claims == ()


def test_parse_gap_claim_accepts_empty_chunk_ids():
    payload = _good_response()
    payload["supporting_claims"][0]["evidence_type"] = "gap"
    payload["supporting_claims"][0]["chunk_ids"] = []
    out = parse_evidence_response(json.dumps(payload))
    assert out.supporting_claims[0].evidence_type == "gap"
    assert out.supporting_claims[0].chunk_ids == ()


def test_parse_expected_sub_question_match():
    raw = json.dumps(_good_response())
    out = parse_evidence_response(raw, expected_sub_question="What is X?")
    assert out.sub_question == "What is X?"


# ---------------------------------------------------------------------------
# C. Parser — validation failures
# ---------------------------------------------------------------------------


def test_parse_garbage_rejected():
    with pytest.raises(EvidenceValidationError, match="parseable JSON"):
        parse_evidence_response("this isn't JSON")


def test_parse_missing_sub_question_rejected():
    payload = _good_response()
    del payload["sub_question"]
    with pytest.raises(EvidenceValidationError, match="sub_question"):
        parse_evidence_response(json.dumps(payload))


def test_parse_sub_question_mismatch_rejected():
    raw = json.dumps(_good_response())
    with pytest.raises(EvidenceValidationError, match="sub_question mismatch"):
        parse_evidence_response(raw, expected_sub_question="different question")


def test_parse_null_sub_question_falls_back_to_expected():
    """Regression for 2026-05-18 production incident.

    grok-4.3 returned ``"sub_question": null`` in production
    responses, blocking every evidence_retriever parse with
    ``top: field 'sub_question' must be a string (got NoneType)``.
    The orchestrator IS the source of truth for which sub-question
    was dispatched; the model's echo is a soft cross-check. When the
    model nulls the field and the bridge supplied
    ``expected_sub_question``, fall back to the expected value rather
    than failing the parse."""
    payload = _good_response()
    payload["sub_question"] = None
    out = parse_evidence_response(
        json.dumps(payload), expected_sub_question="What is X?",
    )
    assert out.sub_question == "What is X?"


def test_parse_missing_sub_question_falls_back_to_expected():
    """``sub_question`` key entirely absent → same fallback."""
    payload = _good_response()
    del payload["sub_question"]
    out = parse_evidence_response(
        json.dumps(payload), expected_sub_question="What is X?",
    )
    assert out.sub_question == "What is X?"


def test_parse_null_sub_question_without_expected_still_rejected():
    """Without ``expected_sub_question`` the parser has no way to
    recover the field — null still raises. The fallback is strictly
    bridge-driven."""
    payload = _good_response()
    payload["sub_question"] = None
    with pytest.raises(EvidenceValidationError, match="sub_question"):
        parse_evidence_response(json.dumps(payload))


def test_parse_missing_answer_rejected():
    payload = _good_response()
    del payload["answer"]
    with pytest.raises(EvidenceValidationError, match="answer"):
        parse_evidence_response(json.dumps(payload))


def test_parse_supporting_claims_not_a_list_rejected():
    payload = _good_response()
    payload["supporting_claims"] = "not a list"
    with pytest.raises(EvidenceValidationError, match="supporting_claims"):
        parse_evidence_response(json.dumps(payload))


def test_parse_insufficient_false_with_no_claims_rejected():
    payload = _good_response()
    payload["supporting_claims"] = []
    payload["insufficient_evidence"] = False
    with pytest.raises(EvidenceValidationError, match="cite-every-claim"):
        parse_evidence_response(json.dumps(payload))


def test_parse_bad_evidence_type_rejected():
    payload = _good_response()
    payload["supporting_claims"][0]["evidence_type"] = "fabricated"
    with pytest.raises(EvidenceValidationError, match="evidence_type"):
        parse_evidence_response(json.dumps(payload))


def test_parse_bad_confidence_rejected():
    payload = _good_response()
    payload["supporting_claims"][0]["confidence"] = "very-high"
    with pytest.raises(EvidenceValidationError, match="confidence"):
        parse_evidence_response(json.dumps(payload))


def test_parse_source_tier_zero_rejected():
    """The upstream prompt forbids 0; 'null' is the sentinel for
    'below the schema floor'."""
    payload = _good_response()
    payload["supporting_claims"][0]["source_tier_min"] = 0
    with pytest.raises(EvidenceValidationError, match="source_tier_min"):
        parse_evidence_response(json.dumps(payload))


def test_parse_source_tier_six_rejected():
    payload = _good_response()
    payload["supporting_claims"][0]["source_tier_min"] = 6
    with pytest.raises(EvidenceValidationError, match="source_tier_min"):
        parse_evidence_response(json.dumps(payload))


def test_parse_source_tier_null_accepted():
    payload = _good_response()
    payload["supporting_claims"][0]["source_tier_min"] = None
    out = parse_evidence_response(json.dumps(payload))
    assert out.supporting_claims[0].source_tier_min is None


def test_parse_source_tier_bool_rejected():
    """Python's bool inherits from int; without explicit exclusion the
    schema accepts True / False as 1 / 0. Defend against that."""
    payload = _good_response()
    payload["supporting_claims"][0]["source_tier_min"] = True
    with pytest.raises(EvidenceValidationError, match="bool"):
        parse_evidence_response(json.dumps(payload))


def test_parse_non_string_chunk_id_rejected():
    payload = _good_response()
    payload["supporting_claims"][0]["chunk_ids"] = ["valid", 42]
    with pytest.raises(EvidenceValidationError, match="chunk_ids"):
        parse_evidence_response(json.dumps(payload))


def test_parse_non_gap_claim_with_empty_chunks_rejected():
    payload = _good_response()
    payload["supporting_claims"][0]["chunk_ids"] = []
    payload["supporting_claims"][0]["evidence_type"] = "direct"
    with pytest.raises(EvidenceValidationError, match="chunk_ids cannot be empty"):
        parse_evidence_response(json.dumps(payload))


def test_parse_evidentiary_gaps_not_a_list_rejected():
    payload = _good_response()
    payload["evidentiary_gaps"] = {"not": "a list"}
    with pytest.raises(EvidenceValidationError, match="evidentiary_gaps"):
        parse_evidence_response(json.dumps(payload))


def test_parse_insufficient_evidence_wrong_type_rejected():
    payload = _good_response()
    payload["insufficient_evidence"] = "false"  # string, not bool
    with pytest.raises(EvidenceValidationError, match="insufficient_evidence"):
        parse_evidence_response(json.dumps(payload))


# ---------------------------------------------------------------------------
# Closed-set sanity (drift catcher — the bridge will assert these
# equal schema Literals when Sprint 7's payloads land).
# ---------------------------------------------------------------------------


def test_evidence_types_canonical_three():
    assert EVIDENCE_TYPES == frozenset({"direct", "inferred", "gap"})


def test_evidence_confidence_canonical_four():
    assert EVIDENCE_CONFIDENCE_LEVELS == frozenset({
        "high", "moderate", "low", "insufficient",
    })
