"""Decomposer JSON response parser + DecompositionResult dataclass.

Receives the raw LLM text, applies the shared JSON-tolerant decoder
from ``roles/_json_decode.py``, validates the closed taxonomy +
count constraints (4-8 sub-questions, 8-20 keywords, ≤3 synonyms),
and returns a typed ``DecompositionResult``.

Validation failures raise ``DecomposerValidationError`` — the bridge
catches and emits a fallback ``DECOMPOSE_QUESTION_DELIVERED`` with an
empty decomposition, mirroring the grounder bridge's "ambiguous"
escape hatch.

The closed-set membership checks live here AND on the Pydantic
``SubQuestion`` / ``Keyword`` models. The duplication is intentional:
the parser fails loudly on bad input before the bridge tries to emit,
and the Pydantic validator catches drift at the substrate boundary.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

try:
    from ...constants import (
        KEYWORDS_MAX,
        KEYWORDS_MIN,
        SUB_QUESTIONS_MAX,
        SUB_QUESTIONS_MIN,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import (  # type: ignore[no-redef]
        KEYWORDS_MAX,
        KEYWORDS_MIN,
        SUB_QUESTIONS_MAX,
        SUB_QUESTIONS_MIN,
    )

try:
    from .._json_decode import extract_json_object as _extract_json_object
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from roles._json_decode import (
        extract_json_object as _extract_json_object,  # type: ignore[no-redef]
    )


# Closed taxonomies — must equal the schema's SubQuestionCategory /
# EvidenceTypeRequired Literals. Drift caught by tests.

DECOMPOSER_CATEGORIES: frozenset[str] = frozenset({
    "market_sizing",
    "defensibility",
    "unit_economics",
    "team_and_execution",
    "regulatory_exposure",
    "competitive_dynamics",
    "customer_concentration",
    "technology_risk",
    "capital_intensity",
    "exit_pathways",
})

DECOMPOSER_EVIDENCE_TYPES: frozenset[str] = frozenset({
    "quantitative", "qualitative", "mixed",
})

MAX_SYNONYMS_PER_KEYWORD = 3


class DecomposerValidationError(ValueError):
    """Raised on any structural / count / taxonomy failure. The bridge
    catches this to emit a fallback Delivered event and surface the
    failure on the trajectory."""


@dataclass(frozen=True)
class ParsedSubQuestion:
    sub_question: str
    category: str
    rationale: str
    evidence_type_required: str


@dataclass(frozen=True)
class ParsedKeyword:
    term: str
    synonyms: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DecompositionResult:
    """Parsed + validated decomposer output. The bridge maps this
    directly to ``SubQuestion`` / ``Keyword`` Pydantic models for the
    ``DecomposeQuestionDelivered`` payload."""

    investigation_id: str
    decomposition: tuple[ParsedSubQuestion, ...]
    keywords: tuple[ParsedKeyword, ...]
    raw: dict


def _require_str(obj: Any, field_name: str, ctx: str) -> str:
    if not isinstance(obj, str) or not obj.strip():
        raise DecomposerValidationError(
            f"{ctx}: field {field_name!r} must be a non-empty string "
            f"(got {type(obj).__name__})"
        )
    return obj


def _parse_sub_question(obj: Any, idx: int) -> ParsedSubQuestion:
    ctx = f"decomposition[{idx}]"
    if not isinstance(obj, dict):
        raise DecomposerValidationError(f"{ctx}: expected an object")
    sq = _require_str(obj.get("sub_question"), "sub_question", ctx)
    cat = _require_str(obj.get("category"), "category", ctx)
    rat = _require_str(obj.get("rationale"), "rationale", ctx)
    ev = _require_str(
        obj.get("evidence_type_required"), "evidence_type_required", ctx
    )
    if cat not in DECOMPOSER_CATEGORIES:
        raise DecomposerValidationError(
            f"{ctx}: category {cat!r} not in closed taxonomy "
            f"({sorted(DECOMPOSER_CATEGORIES)})"
        )
    if ev not in DECOMPOSER_EVIDENCE_TYPES:
        raise DecomposerValidationError(
            f"{ctx}: evidence_type_required {ev!r} not in "
            f"{sorted(DECOMPOSER_EVIDENCE_TYPES)}"
        )
    return ParsedSubQuestion(
        sub_question=sq,
        category=cat,
        rationale=rat,
        evidence_type_required=ev,
    )


def _parse_keyword(obj: Any, idx: int) -> ParsedKeyword:
    ctx = f"keywords[{idx}]"
    if not isinstance(obj, dict):
        raise DecomposerValidationError(f"{ctx}: expected an object")
    term = _require_str(obj.get("term"), "term", ctx)
    syns_raw = obj.get("synonyms") or []
    if not isinstance(syns_raw, list):
        raise DecomposerValidationError(f"{ctx}: synonyms must be a list")
    if len(syns_raw) > MAX_SYNONYMS_PER_KEYWORD:
        raise DecomposerValidationError(
            f"{ctx}: synonyms length {len(syns_raw)} exceeds cap "
            f"{MAX_SYNONYMS_PER_KEYWORD}"
        )
    syns: list[str] = []
    for j, s in enumerate(syns_raw):
        if not isinstance(s, str) or not s.strip():
            raise DecomposerValidationError(
                f"{ctx}.synonyms[{j}]: must be a non-empty string"
            )
        syns.append(s)
    return ParsedKeyword(term=term, synonyms=tuple(syns))


def parse_decomposer_response(
    text: str,
    *,
    expected_investigation_id: str | None = None,
) -> DecompositionResult:
    """Parse + validate a Decomposer's raw text response.

    ``expected_investigation_id`` is an optional cross-check: when the
    bridge knows which investigation it dispatched for, a model that
    echoes back a different id (hallucinated session) is rejected.
    """
    obj = _extract_json_object(text)
    if not isinstance(obj, dict):
        raise DecomposerValidationError(
            "response did not contain a parseable JSON object"
        )

    # Top-level keys
    iid = _require_str(obj.get("investigation_id"), "investigation_id", "top")
    if expected_investigation_id and iid != expected_investigation_id:
        raise DecomposerValidationError(
            f"investigation_id mismatch: model returned {iid!r}, "
            f"expected {expected_investigation_id!r}"
        )

    decomp_raw = obj.get("decomposition")
    if not isinstance(decomp_raw, list):
        raise DecomposerValidationError("top: decomposition must be a list")
    n_sq = len(decomp_raw)
    if not (SUB_QUESTIONS_MIN <= n_sq <= SUB_QUESTIONS_MAX):
        raise DecomposerValidationError(
            f"top: decomposition count {n_sq} outside "
            f"[{SUB_QUESTIONS_MIN}, {SUB_QUESTIONS_MAX}]"
        )
    decomposition = tuple(_parse_sub_question(s, i) for i, s in enumerate(decomp_raw))

    kw_raw = obj.get("keywords")
    if not isinstance(kw_raw, list):
        raise DecomposerValidationError("top: keywords must be a list")
    n_kw = len(kw_raw)
    if not (KEYWORDS_MIN <= n_kw <= KEYWORDS_MAX):
        raise DecomposerValidationError(
            f"top: keywords count {n_kw} outside "
            f"[{KEYWORDS_MIN}, {KEYWORDS_MAX}]"
        )
    keywords = tuple(_parse_keyword(k, i) for i, k in enumerate(kw_raw))

    return DecompositionResult(
        investigation_id=iid,
        decomposition=decomposition,
        keywords=keywords,
        raw=obj,
    )
