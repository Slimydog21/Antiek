"""Evidence Retriever JSON response parser.

Sprint 6 day 4-5. Parses + validates the Evidence Retriever's raw
text response into a typed ``EvidenceResult`` dataclass. Closed
vocabularies enforced at parse time:

- ``evidence_type`` ∈ {direct, inferred, gap}
- ``confidence``    ∈ {high, moderate, low, insufficient}
- ``source_tier_min`` ∈ [1, 5] OR ``None`` (the spec's null
  sentinel for "below the schema floor"; ``0`` is REJECTED — that's
  the original schema bug the upstream prompt warns about).

Validation failures raise ``EvidenceValidationError``. The Sprint 7
bridge handler will catch and emit a fallback delivered event.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, List, Optional

try:
    from .._json_decode import extract_json_object as _extract_json_object
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from roles._json_decode import extract_json_object as _extract_json_object  # type: ignore[no-redef]


# Closed vocabularies — kept here for fail-loud parser-side checks.
# When the Sprint 7 typed payloads land, these MUST equal the schema
# Literal sets (drift detection lives in the test suite).
EVIDENCE_TYPES: frozenset[str] = frozenset({"direct", "inferred", "gap"})
EVIDENCE_CONFIDENCE_LEVELS: frozenset[str] = frozenset({
    "high", "moderate", "low", "insufficient",
})

# Source tier floor + ceiling. The upstream prompt explicitly forbids
# ``0`` and reserves ``None`` for "below the schema floor" — both are
# enforced here.
SOURCE_TIER_MIN_VALUE = 1
SOURCE_TIER_MAX_VALUE = 5


class EvidenceValidationError(ValueError):
    """Raised on any structural / vocabulary / count failure. The
    bridge catches and emits a fallback delivered event."""


@dataclass(frozen=True)
class ParsedClaim:
    claim: str
    evidence_type: str
    chunk_ids: tuple[str, ...]
    confidence: str
    confidence_basis: str
    edge_ids: tuple[str, ...] = field(default_factory=tuple)
    source_tier_min: Optional[int] = None  # None or [1, 5]


@dataclass(frozen=True)
class ParsedGap:
    gap_description: str
    additional_retrieval_suggested: Optional[str] = None


@dataclass(frozen=True)
class EvidenceResult:
    """The parsed Evidence Retriever output. Bridge maps this to
    typed Pydantic payloads when Sprint 7 wires the delivered
    event."""

    sub_question: str
    answer: str
    supporting_claims: tuple[ParsedClaim, ...]
    evidentiary_gaps: tuple[ParsedGap, ...]
    insufficient_evidence: bool
    raw: dict


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def _require_str(obj: Any, field_name: str, ctx: str, *, allow_empty: bool = False) -> str:
    if not isinstance(obj, str):
        raise EvidenceValidationError(
            f"{ctx}: field {field_name!r} must be a string "
            f"(got {type(obj).__name__})"
        )
    if not allow_empty and not obj.strip():
        raise EvidenceValidationError(
            f"{ctx}: field {field_name!r} must be a non-empty string"
        )
    return obj


def _require_str_list(obj: Any, field_name: str, ctx: str) -> List[str]:
    if obj is None:
        return []
    if not isinstance(obj, list):
        raise EvidenceValidationError(
            f"{ctx}: {field_name!r} must be a list (got {type(obj).__name__})"
        )
    out: List[str] = []
    for i, item in enumerate(obj):
        if not isinstance(item, str) or not item.strip():
            raise EvidenceValidationError(
                f"{ctx}.{field_name}[{i}]: must be a non-empty string"
            )
        out.append(item)
    return out


def _parse_source_tier(obj: Any, ctx: str) -> Optional[int]:
    """``None`` is allowed; integers must lie in [1, 5]; ``0`` is
    REJECTED (the upstream schema bug the prompt explicitly warns
    against)."""
    if obj is None:
        return None
    if isinstance(obj, bool):  # bool is a subtype of int — exclude
        raise EvidenceValidationError(
            f"{ctx}: source_tier_min must be int in [1,5] or null, got bool"
        )
    if not isinstance(obj, int):
        raise EvidenceValidationError(
            f"{ctx}: source_tier_min must be int in [1,5] or null, "
            f"got {type(obj).__name__}"
        )
    if obj < SOURCE_TIER_MIN_VALUE or obj > SOURCE_TIER_MAX_VALUE:
        raise EvidenceValidationError(
            f"{ctx}: source_tier_min={obj} outside "
            f"[{SOURCE_TIER_MIN_VALUE}, {SOURCE_TIER_MAX_VALUE}] "
            f"(use null to indicate \"below the schema floor\"; 0 is forbidden)"
        )
    return obj


def _parse_claim(obj: Any, idx: int) -> ParsedClaim:
    ctx = f"supporting_claims[{idx}]"
    if not isinstance(obj, dict):
        raise EvidenceValidationError(f"{ctx}: expected an object")
    claim = _require_str(obj.get("claim"), "claim", ctx)
    evidence_type = _require_str(obj.get("evidence_type"), "evidence_type", ctx)
    if evidence_type not in EVIDENCE_TYPES:
        raise EvidenceValidationError(
            f"{ctx}: evidence_type {evidence_type!r} not in "
            f"{sorted(EVIDENCE_TYPES)}"
        )
    chunk_ids = tuple(_require_str_list(obj.get("chunk_ids"), "chunk_ids", ctx))
    if not chunk_ids and evidence_type != "gap":
        raise EvidenceValidationError(
            f"{ctx}: chunk_ids cannot be empty when evidence_type="
            f"{evidence_type!r} (gap claims may have empty chunk_ids)"
        )
    edge_ids = tuple(_require_str_list(obj.get("edge_ids"), "edge_ids", ctx))
    confidence = _require_str(obj.get("confidence"), "confidence", ctx)
    if confidence not in EVIDENCE_CONFIDENCE_LEVELS:
        raise EvidenceValidationError(
            f"{ctx}: confidence {confidence!r} not in "
            f"{sorted(EVIDENCE_CONFIDENCE_LEVELS)}"
        )
    confidence_basis = _require_str(
        obj.get("confidence_basis"), "confidence_basis", ctx,
        allow_empty=False,
    )
    source_tier_min = _parse_source_tier(obj.get("source_tier_min"), ctx)
    return ParsedClaim(
        claim=claim,
        evidence_type=evidence_type,
        chunk_ids=chunk_ids,
        edge_ids=edge_ids,
        confidence=confidence,
        confidence_basis=confidence_basis,
        source_tier_min=source_tier_min,
    )


def _parse_gap(obj: Any, idx: int) -> ParsedGap:
    ctx = f"evidentiary_gaps[{idx}]"
    if not isinstance(obj, dict):
        raise EvidenceValidationError(f"{ctx}: expected an object")
    gap_description = _require_str(
        obj.get("gap_description"), "gap_description", ctx,
    )
    suggested = obj.get("additional_retrieval_suggested")
    if suggested is not None and not isinstance(suggested, str):
        raise EvidenceValidationError(
            f"{ctx}: additional_retrieval_suggested must be string or null"
        )
    return ParsedGap(
        gap_description=gap_description,
        additional_retrieval_suggested=suggested if suggested else None,
    )


def parse_evidence_response(
    text: str,
    *,
    expected_sub_question: Optional[str] = None,
) -> EvidenceResult:
    """Parse + validate an Evidence Retriever raw response.

    ``expected_sub_question`` is a soft cross-check — when the bridge
    knows which sub-question it dispatched for, a model that echoes
    back a different one is rejected at parse time."""
    obj = _extract_json_object(text)
    if not isinstance(obj, dict):
        raise EvidenceValidationError(
            "response did not contain a parseable JSON object"
        )

    sub_question = _require_str(obj.get("sub_question"), "sub_question", "top")
    if expected_sub_question is not None and sub_question.strip() != expected_sub_question.strip():
        raise EvidenceValidationError(
            f"sub_question mismatch: model returned {sub_question!r}, "
            f"expected {expected_sub_question!r}"
        )

    # ``answer`` may be empty when insufficient_evidence=True — the
    # role's discipline is "say nothing rather than fabricate."
    answer_raw = obj.get("answer")
    if not isinstance(answer_raw, str):
        raise EvidenceValidationError("top: answer must be a string")
    answer = answer_raw

    claims_raw = obj.get("supporting_claims")
    if not isinstance(claims_raw, list):
        raise EvidenceValidationError("top: supporting_claims must be a list")
    claims = tuple(_parse_claim(c, i) for i, c in enumerate(claims_raw))

    gaps_raw = obj.get("evidentiary_gaps")
    if not isinstance(gaps_raw, list):
        raise EvidenceValidationError("top: evidentiary_gaps must be a list")
    gaps = tuple(_parse_gap(g, i) for i, g in enumerate(gaps_raw))

    insufficient = obj.get("insufficient_evidence")
    if not isinstance(insufficient, bool):
        raise EvidenceValidationError(
            "top: insufficient_evidence must be a boolean"
        )

    # Cross-field validation: when insufficient_evidence=False the
    # role must produce at least one supporting claim — otherwise the
    # answer is unsupported. (The prompt rule "cite every claim by
    # chunk_id" is the policy this enforces structurally.)
    if not insufficient and not claims:
        raise EvidenceValidationError(
            "insufficient_evidence=False requires at least one entry in "
            "supporting_claims (cite-every-claim rule). Set "
            "insufficient_evidence=True if no claims can be made."
        )

    return EvidenceResult(
        sub_question=sub_question,
        answer=answer,
        supporting_claims=claims,
        evidentiary_gaps=gaps,
        insufficient_evidence=insufficient,
        raw=obj,
    )
