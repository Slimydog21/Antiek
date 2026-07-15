from __future__ import annotations

import hashlib

import pytest

from substrate.research_artifact.grounded_companion_answer import (
    AnswerClaimInput,
    GroundedAnswerCandidate,
    GroundedAnswerError,
    VerifiedCompanionExecutionReceipt,
    build_grounded_answer,
    candidate_digest,
    public_grounded_answer,
)


def _pack() -> dict[str, object]:
    return {
        "pack_sha256": "a" * 64,
        "citations": [{
            "citation_id": "dchunk_" + "b" * 64,
            "section_anchor": 'engine"><script>alert(1)</script>',
        }],
    }


def _candidate(citations: tuple[str, ...] | None = None) -> GroundedAnswerCandidate:
    return GroundedAnswerCandidate(claims=(
        AnswerClaimInput("Lift < drag & thrust.", citations or ("dchunk_" + "b" * 64,)),
        AnswerClaimInput("A hypothesis requiring more evidence."),
    ))


def _receipt(candidate: GroundedAnswerCandidate, **changes: str) -> VerifiedCompanionExecutionReceipt:
    values = {
        "receipt_id": "rex_" + "c" * 64,
        "receipt_digest": "d" * 64,
        "status": "settled",
        "provider": "qualified-provider",
        "model": "grounded-model",
        "turn_id": "dturn_" + "e" * 32,
        "evidence_pack_sha256": "a" * 64,
        "output_digest": candidate_digest(candidate),
    }
    values.update(changes)
    return VerifiedCompanionExecutionReceipt(**values)


def test_builds_deterministic_escaped_answer_with_explicit_gap() -> None:
    candidate = _candidate()
    first = build_grounded_answer(
        turn_id="dturn_" + "e" * 32, evidence_pack=_pack(), candidate=candidate,
        receipt=_receipt(candidate),
    )
    replay = build_grounded_answer(
        turn_id="dturn_" + "e" * 32, evidence_pack=_pack(), candidate=candidate,
        receipt=_receipt(candidate),
    )
    assert replay == first
    assert first["unsupported_claim_count"] == 1
    assert first["cited_citation_ids"] == ["dchunk_" + "b" * 64]
    assert "<script>" not in first["answer_html"]
    assert "Lift &lt; drag &amp; thrust." in first["answer_html"]
    assert 'data-grounding="supported"' in first["answer_html"]
    assert 'data-grounding="unsupported"' in first["answer_html"]
    assert first["answer_html_sha256"] == hashlib.sha256(
        first["answer_html"].encode()
    ).hexdigest()
    public = public_grounded_answer(first)
    assert "execution_receipt_id" not in public
    assert "output_digest" not in public


@pytest.mark.parametrize("change", [
    {"status": "unknown"}, {"turn_id": "dturn_" + "f" * 32},
    {"evidence_pack_sha256": "f" * 64}, {"output_digest": "f" * 64},
])
def test_refuses_receipt_binding_conflicts(change: dict[str, str]) -> None:
    candidate = _candidate()
    with pytest.raises(GroundedAnswerError, match="receipt"):
        build_grounded_answer(
            turn_id="dturn_" + "e" * 32, evidence_pack=_pack(), candidate=candidate,
            receipt=_receipt(candidate, **change),
        )


def test_refuses_unknown_and_duplicate_citations() -> None:
    unknown = _candidate(("dchunk_" + "f" * 64,))
    with pytest.raises(GroundedAnswerError, match="outside"):
        build_grounded_answer(
            turn_id="dturn_" + "e" * 32, evidence_pack=_pack(), candidate=unknown,
            receipt=_receipt(unknown),
        )
    duplicate = _candidate(("dchunk_" + "b" * 64, "dchunk_" + "b" * 64))
    with pytest.raises(GroundedAnswerError, match="repeats"):
        build_grounded_answer(
            turn_id="dturn_" + "e" * 32, evidence_pack=_pack(), candidate=duplicate,
            receipt=_receipt(duplicate),
        )


def test_refuses_empty_and_oversized_claim_sets() -> None:
    empty = GroundedAnswerCandidate(claims=())
    with pytest.raises(GroundedAnswerError, match="bounded"):
        candidate_digest(empty)
    oversized = GroundedAnswerCandidate(claims=(AnswerClaimInput("x" * 8193),))
    with pytest.raises(GroundedAnswerError, match="text"):
        candidate_digest(oversized)
