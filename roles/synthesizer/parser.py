"""Synthesizer JSON response parser.

Sprint 7 day 5. The most discipline-heavy of the four orchestrate.py
role parsers because the synthesizer's output is what the constraint
loop gates on AND what middleware/archive writes to the syntheses
table.

Closed vocabularies + structural rules:

- ``implicit_recommendation`` ∈ {proceed, pass, conditional,
  insufficient_evidence}
- ``confidence`` ∈ {high, moderate, low, unknown} (NOT "medium")
- ``severity_if_manifested`` ∈ {critical, high, moderate, low}
- ``effective_source_tier`` ∈ [1, 5] OR None (0 REJECTED — the
  upstream prompt's explicit prohibition)
- ``conviction_level`` ∈ [0.0, 1.0]

Tier-hedging discipline (prompt rule 5):

- Tier 5 components must be excluded — the parser rejects them
  loudly because the role's prompt mandates exclusion.
- ``None`` tier components must carry ``confidence="unknown"``
  AND ``hedging_required=True`` (the "treat as Tier 5" rule).
- Tier 4 components must carry ``confidence="low"`` or ``"unknown"``.
- Tier 3 components must carry ``hedging_required=True``.

``reasoning_paths_used[*].support_summary`` ≥ 20 characters
(the prompt's explicit floor).

Provenance discipline: every ``thesis_component`` must cite at least
one ``supporting_chunk_ids`` OR ``supporting_path_indices`` — the
prompt's "provenance is structural" rule. Exception:
``implicit_recommendation == "insufficient_evidence"`` allows empty
provenance (the role honestly admits it can't ground a thesis).

``supporting_path_indices`` referenced in components must be present
in ``reasoning_paths_used`` (cite-back symmetry) when paths are
cited.
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


CONFIDENCE_LEVELS: frozenset[str] = frozenset({
    "high", "moderate", "low", "unknown",
})

IMPLICIT_RECOMMENDATIONS: frozenset[str] = frozenset({
    "proceed", "pass", "conditional", "insufficient_evidence",
})

EXECUTION_RISK_SEVERITIES: frozenset[str] = frozenset({
    "critical", "high", "moderate", "low",
})

# The upstream prompt's explicit minimum for support_summary length.
SUPPORT_SUMMARY_MIN_LENGTH = 20

# Tier-hedging policy structural rules. Drift between these and
# substrate.constants.TIER_HEDGING_POLICY is caught by tests.
TIER_THAT_REQUIRES_HEDGING_FLAG = 3   # Tier 3+ → hedging_required=True
TIER_THAT_LIMITS_CONFIDENCE_LOW = 4   # Tier 4+ → confidence ≤ low
TIER_THAT_EXCLUDES = 5                # Tier 5 → exclude entirely


class SynthesizerValidationError(ValueError):
    """Raised on any structural / vocabulary / discipline failure."""


@dataclass(frozen=True)
class ParsedThesisComponent:
    claim: str
    confidence: str
    supporting_chunk_ids: tuple[str, ...]
    supporting_path_indices: tuple[int, ...]
    confidence_basis: Optional[str] = None
    effective_source_tier: Optional[int] = None
    hedging_required: bool = False


@dataclass(frozen=True)
class ParsedFalsificationCondition:
    condition: str
    specific_observable: str
    timeframe: Optional[str] = None


@dataclass(frozen=True)
class ParsedExecutionRisk:
    risk: str
    severity_if_manifested: str
    leading_indicator: Optional[str] = None


@dataclass(frozen=True)
class ParsedViolationJustification:
    constraint: str
    justification: str


@dataclass(frozen=True)
class ParsedConstraintCompliance:
    hard_constraints_satisfied: bool
    soft_constraints_violated: tuple[str, ...] = field(default_factory=tuple)
    violations_justified: tuple[ParsedViolationJustification, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ParsedReasoningPath:
    path_node_ids: tuple[str, ...]
    path_edge_ids: tuple[str, ...]
    support_summary: str


@dataclass(frozen=True)
class ThesisResult:
    thesis_summary: str
    implicit_recommendation: str
    thesis_components: tuple[ParsedThesisComponent, ...]
    falsification_conditions: tuple[ParsedFalsificationCondition, ...]
    execution_risks: tuple[ParsedExecutionRisk, ...]
    constraint_compliance: ParsedConstraintCompliance
    reasoning_paths_used: tuple[ParsedReasoningPath, ...]
    conviction_level: Optional[float] = None
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Field validators
# ---------------------------------------------------------------------------


def _require_str(obj: Any, field_name: str, ctx: str, *, allow_empty: bool = False) -> str:
    if not isinstance(obj, str):
        raise SynthesizerValidationError(
            f"{ctx}: {field_name!r} must be a string (got {type(obj).__name__})"
        )
    if not allow_empty and not obj.strip():
        raise SynthesizerValidationError(
            f"{ctx}: {field_name!r} must be a non-empty string"
        )
    return obj


def _opt_str(obj: Any, field_name: str, ctx: str) -> Optional[str]:
    if obj is None:
        return None
    if not isinstance(obj, str):
        raise SynthesizerValidationError(
            f"{ctx}: {field_name!r} must be a string or null"
        )
    return obj if obj else None


def _require_str_list(obj: Any, field_name: str, ctx: str) -> List[str]:
    if obj is None:
        return []
    if not isinstance(obj, list):
        raise SynthesizerValidationError(
            f"{ctx}: {field_name!r} must be a list"
        )
    out: List[str] = []
    for i, v in enumerate(obj):
        if not isinstance(v, str) or not v.strip():
            raise SynthesizerValidationError(
                f"{ctx}.{field_name}[{i}]: must be a non-empty string"
            )
        out.append(v)
    return out


def _require_int_list(obj: Any, field_name: str, ctx: str) -> List[int]:
    if obj is None:
        return []
    if not isinstance(obj, list):
        raise SynthesizerValidationError(
            f"{ctx}: {field_name!r} must be a list"
        )
    out: List[int] = []
    for i, v in enumerate(obj):
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise SynthesizerValidationError(
                f"{ctx}.{field_name}[{i}]: must be a non-negative integer"
            )
        out.append(v)
    return out


def _parse_effective_source_tier(obj: Any, ctx: str) -> Optional[int]:
    if obj is None:
        return None
    if isinstance(obj, bool):
        raise SynthesizerValidationError(
            f"{ctx}: effective_source_tier must be int [1,5] or null, got bool"
        )
    if not isinstance(obj, int):
        raise SynthesizerValidationError(
            f"{ctx}: effective_source_tier must be int [1,5] or null, "
            f"got {type(obj).__name__}"
        )
    if obj < 1 or obj > 5:
        raise SynthesizerValidationError(
            f"{ctx}: effective_source_tier={obj} outside [1, 5] "
            "(use null when no qualifying source exists; 0 is forbidden)"
        )
    return obj


def _parse_thesis_component(
    obj: Any, idx: int, *, allow_unprovenanced: bool,
) -> ParsedThesisComponent:
    ctx = f"thesis_components[{idx}]"
    if not isinstance(obj, dict):
        raise SynthesizerValidationError(f"{ctx}: expected an object")
    claim = _require_str(obj.get("claim"), "claim", ctx)
    confidence = _require_str(obj.get("confidence"), "confidence", ctx)
    if confidence not in CONFIDENCE_LEVELS:
        raise SynthesizerValidationError(
            f"{ctx}: confidence {confidence!r} not in {sorted(CONFIDENCE_LEVELS)} "
            "(NOT 'medium' — the upstream enum is high/moderate/low/unknown)"
        )
    chunks = tuple(_require_str_list(
        obj.get("supporting_chunk_ids"), "supporting_chunk_ids", ctx,
    ))
    paths = tuple(_require_int_list(
        obj.get("supporting_path_indices"), "supporting_path_indices", ctx,
    ))
    if not chunks and not paths and not allow_unprovenanced:
        raise SynthesizerValidationError(
            f"{ctx}: must cite at least one supporting_chunk_ids OR "
            "supporting_path_indices (provenance-is-structural rule). "
            "Empty provenance is only allowed when "
            "implicit_recommendation='insufficient_evidence'."
        )

    tier = _parse_effective_source_tier(obj.get("effective_source_tier"), ctx)
    hedging = bool(obj.get("hedging_required", False))

    # Tier-hedging discipline checks.
    if tier == TIER_THAT_EXCLUDES:
        raise SynthesizerValidationError(
            f"{ctx}: effective_source_tier=5 components must be EXCLUDED "
            "from the thesis (prompt rule 5; Tier 5 = unsupported)"
        )
    if tier is None:
        # null-tier components must be treated as Tier 5: hedge
        # maximally AND set confidence to unknown.
        if not hedging:
            raise SynthesizerValidationError(
                f"{ctx}: effective_source_tier=null requires "
                "hedging_required=True (null-tier components hedge maximally)"
            )
        if confidence != "unknown":
            raise SynthesizerValidationError(
                f"{ctx}: effective_source_tier=null requires "
                "confidence='unknown' (null-tier means tier-aggregation "
                "is undefined, so confidence cannot be assessed)"
            )
    elif tier >= TIER_THAT_LIMITS_CONFIDENCE_LOW:
        # Tier 4: hedge AND confidence ≤ low.
        if confidence not in ("low", "unknown"):
            raise SynthesizerValidationError(
                f"{ctx}: effective_source_tier={tier} requires confidence "
                "in ('low', 'unknown') — prompt rule 5 caps Tier 4 at low"
            )
        if not hedging:
            raise SynthesizerValidationError(
                f"{ctx}: effective_source_tier={tier} requires "
                "hedging_required=True"
            )
    elif tier >= TIER_THAT_REQUIRES_HEDGING_FLAG:
        # Tier 3: hedge.
        if not hedging:
            raise SynthesizerValidationError(
                f"{ctx}: effective_source_tier={tier} requires "
                "hedging_required=True"
            )

    return ParsedThesisComponent(
        claim=claim,
        confidence=confidence,
        supporting_chunk_ids=chunks,
        supporting_path_indices=paths,
        confidence_basis=_opt_str(obj.get("confidence_basis"), "confidence_basis", ctx),
        effective_source_tier=tier,
        hedging_required=hedging,
    )


def _parse_falsification(obj: Any, idx: int) -> ParsedFalsificationCondition:
    ctx = f"falsification_conditions[{idx}]"
    if not isinstance(obj, dict):
        raise SynthesizerValidationError(f"{ctx}: expected an object")
    return ParsedFalsificationCondition(
        condition=_require_str(obj.get("condition"), "condition", ctx),
        specific_observable=_require_str(
            obj.get("specific_observable"), "specific_observable", ctx,
        ),
        timeframe=_opt_str(obj.get("timeframe"), "timeframe", ctx),
    )


def _parse_execution_risk(obj: Any, idx: int) -> ParsedExecutionRisk:
    ctx = f"execution_risks[{idx}]"
    if not isinstance(obj, dict):
        raise SynthesizerValidationError(f"{ctx}: expected an object")
    sev = _require_str(
        obj.get("severity_if_manifested"), "severity_if_manifested", ctx,
    )
    if sev not in EXECUTION_RISK_SEVERITIES:
        raise SynthesizerValidationError(
            f"{ctx}: severity_if_manifested {sev!r} not in "
            f"{sorted(EXECUTION_RISK_SEVERITIES)}"
        )
    return ParsedExecutionRisk(
        risk=_require_str(obj.get("risk"), "risk", ctx),
        severity_if_manifested=sev,
        leading_indicator=_opt_str(
            obj.get("leading_indicator"), "leading_indicator", ctx,
        ),
    )


def _parse_violation_justification(
    obj: Any, idx: int,
) -> ParsedViolationJustification:
    ctx = f"constraint_compliance.violations_justified[{idx}]"
    if not isinstance(obj, dict):
        raise SynthesizerValidationError(f"{ctx}: expected an object")
    return ParsedViolationJustification(
        constraint=_require_str(obj.get("constraint"), "constraint", ctx),
        justification=_require_str(
            obj.get("justification"), "justification", ctx,
        ),
    )


def _parse_constraint_compliance(obj: Any) -> ParsedConstraintCompliance:
    ctx = "constraint_compliance"
    if not isinstance(obj, dict):
        raise SynthesizerValidationError(f"{ctx}: must be an object")
    hard_ok = obj.get("hard_constraints_satisfied")
    if not isinstance(hard_ok, bool):
        raise SynthesizerValidationError(
            f"{ctx}.hard_constraints_satisfied: must be boolean"
        )
    soft_violated = tuple(_require_str_list(
        obj.get("soft_constraints_violated"), "soft_constraints_violated", ctx,
    ))
    justifications_raw = obj.get("violations_justified") or []
    if not isinstance(justifications_raw, list):
        raise SynthesizerValidationError(
            f"{ctx}.violations_justified: must be a list"
        )
    justifications = tuple(
        _parse_violation_justification(j, i)
        for i, j in enumerate(justifications_raw)
    )
    return ParsedConstraintCompliance(
        hard_constraints_satisfied=hard_ok,
        soft_constraints_violated=soft_violated,
        violations_justified=justifications,
    )


def _parse_reasoning_path(obj: Any, idx: int) -> ParsedReasoningPath:
    ctx = f"reasoning_paths_used[{idx}]"
    if not isinstance(obj, dict):
        raise SynthesizerValidationError(f"{ctx}: expected an object")
    nodes = tuple(_require_str_list(
        obj.get("path_node_ids"), "path_node_ids", ctx,
    ))
    if not nodes:
        raise SynthesizerValidationError(
            f"{ctx}: path_node_ids cannot be empty"
        )
    edges = tuple(_require_str_list(
        obj.get("path_edge_ids"), "path_edge_ids", ctx,
    ))
    summary = _require_str(
        obj.get("support_summary"), "support_summary", ctx,
    )
    if len(summary) < SUPPORT_SUMMARY_MIN_LENGTH:
        raise SynthesizerValidationError(
            f"{ctx}: support_summary must be ≥{SUPPORT_SUMMARY_MIN_LENGTH} "
            f"characters (got {len(summary)}). Generic summaries like "
            "'supports the thesis' are explicitly rejected by the prompt."
        )
    return ParsedReasoningPath(
        path_node_ids=nodes,
        path_edge_ids=edges,
        support_summary=summary,
    )


def parse_synthesizer_response(text: str) -> ThesisResult:
    """Parse + validate a Synthesizer raw response."""
    obj = _extract_json_object(text)
    if not isinstance(obj, dict):
        raise SynthesizerValidationError(
            "response did not contain a parseable JSON object"
        )

    thesis_summary = _require_str(
        obj.get("thesis_summary"), "thesis_summary", "top",
        allow_empty=True,  # may be minimal under insufficient_evidence
    )

    recommendation = _require_str(
        obj.get("implicit_recommendation"), "implicit_recommendation", "top",
    )
    if recommendation not in IMPLICIT_RECOMMENDATIONS:
        raise SynthesizerValidationError(
            f"top: implicit_recommendation {recommendation!r} not in "
            f"{sorted(IMPLICIT_RECOMMENDATIONS)}"
        )

    allow_unprovenanced = recommendation == "insufficient_evidence"

    components_raw = obj.get("thesis_components")
    if not isinstance(components_raw, list):
        raise SynthesizerValidationError("top: thesis_components must be a list")
    components = tuple(
        _parse_thesis_component(c, i, allow_unprovenanced=allow_unprovenanced)
        for i, c in enumerate(components_raw)
    )

    falsifications_raw = obj.get("falsification_conditions")
    if not isinstance(falsifications_raw, list):
        raise SynthesizerValidationError(
            "top: falsification_conditions must be a list"
        )
    falsifications = tuple(
        _parse_falsification(f, i) for i, f in enumerate(falsifications_raw)
    )

    risks_raw = obj.get("execution_risks")
    if not isinstance(risks_raw, list):
        raise SynthesizerValidationError("top: execution_risks must be a list")
    risks = tuple(
        _parse_execution_risk(r, i) for i, r in enumerate(risks_raw)
    )

    compliance = _parse_constraint_compliance(obj.get("constraint_compliance"))

    reasoning_raw = obj.get("reasoning_paths_used")
    if not isinstance(reasoning_raw, list):
        raise SynthesizerValidationError(
            "top: reasoning_paths_used must be a list (empty list is "
            "valid; ``insufficient_evidence`` typically emits [])"
        )
    reasoning = tuple(
        _parse_reasoning_path(r, i) for i, r in enumerate(reasoning_raw)
    )

    conviction_raw = obj.get("conviction_level")
    conviction: Optional[float] = None
    if conviction_raw is not None:
        if isinstance(conviction_raw, bool) or not isinstance(conviction_raw, (int, float)):
            raise SynthesizerValidationError(
                "top: conviction_level must be a number or null"
            )
        conviction = float(conviction_raw)
        if not 0.0 <= conviction <= 1.0:
            raise SynthesizerValidationError(
                f"top: conviction_level={conviction} outside [0.0, 1.0]"
            )

    return ThesisResult(
        thesis_summary=thesis_summary,
        implicit_recommendation=recommendation,
        thesis_components=components,
        falsification_conditions=falsifications,
        execution_risks=risks,
        constraint_compliance=compliance,
        reasoning_paths_used=reasoning,
        conviction_level=conviction,
        raw=obj,
    )
