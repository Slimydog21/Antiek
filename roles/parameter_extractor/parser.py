"""Parameter Extractor JSON response parser.

Sprint 7 day 2. Closed vocabularies + the upstream's three load-bearing
discipline rules:

1. ``value_type`` is the literal string ``"null"`` for qualitative
   parameters — the parser normalizes JSON ``null`` to the literal
   string at parse time (mirrors the upstream
   ``_normalize_parsed("parameter_extractor", ...)`` logic).
2. ``unit`` MUST be either a non-empty string OR absent/null — the
   empty string sentinel is REJECTED (upstream prompt rule
   "Prohibited patterns" #2).
3. ``value`` MUST agree with ``value_type``:
   - ``scalar`` → numeric
   - ``range`` → [lo, hi] numeric pair
   - ``categorical`` → string or list of strings
   - ``null`` → absent / JSON null (qualitative parameter)
   Setting ``value_type=null`` while ``value`` is numeric is the
   "over-correction trap" the upstream warns about — REJECTED here.

Validation failures raise ``ParameterValidationError``. The Sprint 7
bridge handler catches and emits a fallback Delivered event.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

try:
    from .._json_decode import extract_json_object as _extract_json_object
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from roles._json_decode import (
        extract_json_object as _extract_json_object,
    )

try:
    from substrate.provenance.validate_refs import validate_refs
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.provenance.validate_refs import validate_refs


# Closed vocabularies — must equal the schema-side Literal sets.
# Drift caught by tests.
METRIC_VALUE_TYPES: frozenset[str] = frozenset({
    "scalar", "range", "categorical", "null",
})

EVIDENCE_STATUS_VALUES: frozenset[str] = frozenset({
    "observed", "imputed",
})

CONSTRAINT_STRICTNESS_VALUES: frozenset[str] = frozenset({
    "hard", "soft", "target",
})


class ParameterValidationError(ValueError):
    """Raised on any structural / vocabulary / shape mismatch. The
    bridge catches this to emit a fallback Delivered event."""


@dataclass(frozen=True)
class ParsedMetricValue:
    value_type: str  # one of METRIC_VALUE_TYPES
    value: Any = None
    unit: str | None = None


@dataclass(frozen=True)
class ParsedParameter:
    semantic_anchor: str
    metric_value: ParsedMetricValue
    evidence_status: str               # one of EVIDENCE_STATUS_VALUES
    source_chunk_ids: tuple[str, ...]
    constraint_strictness: str         # one of CONSTRAINT_STRICTNESS_VALUES
    qualitative_descriptor: str | None = None


@dataclass(frozen=True)
class ParameterExtractResult:
    """Top-level parsed shape. ``parameters`` is the canonicalized list
    after the parser normalized the JSON-null-vs-literal-string
    ambiguity and dropped the empty-string unit cases."""

    parameters: tuple[ParsedParameter, ...]
    raw: dict[str, Any]


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def _require_str(obj: Any, field_name: str, ctx: str, *, allow_empty: bool = False) -> str:
    if not isinstance(obj, str):
        raise ParameterValidationError(
            f"{ctx}: {field_name!r} must be a string (got {type(obj).__name__})"
        )
    if not allow_empty and not obj.strip():
        raise ParameterValidationError(
            f"{ctx}: {field_name!r} must be a non-empty string"
        )
    return obj


def _require_str_list(obj: Any, field_name: str, ctx: str) -> list[str]:
    if obj is None:
        return []
    if not isinstance(obj, list):
        raise ParameterValidationError(
            f"{ctx}: {field_name!r} must be a list (got {type(obj).__name__})"
        )
    out: list[str] = []
    for i, item in enumerate(obj):
        if not isinstance(item, str) or not item.strip():
            raise ParameterValidationError(
                f"{ctx}.{field_name}[{i}]: must be a non-empty string"
            )
        out.append(item)
    return out


def _is_numeric(v: Any) -> bool:
    """``bool`` is a subclass of ``int`` in Python — exclude it
    explicitly so True/False can't slip through as 1/0."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _normalize_metric_value(raw: Any, ctx: str) -> ParsedMetricValue:
    """Apply the upstream normalization rules + validate the
    cross-field consistency.

    Normalization:
    - ``value_type`` of JSON ``None`` → literal string ``"null"``.
    - ``unit`` of JSON ``None`` → dropped (None on the dataclass).

    Validation:
    - ``value_type`` must be in ``METRIC_VALUE_TYPES``.
    - ``unit`` empty string REJECTED (upstream prompt rule).
    - ``value`` agrees with ``value_type`` (the "over-correction
      trap" — qualitative ``null`` type cannot carry a numeric
      ``value``).
    """
    if not isinstance(raw, dict):
        raise ParameterValidationError(
            f"{ctx}.metric_value: must be an object (got "
            f"{type(raw).__name__})"
        )

    vt_raw = raw.get("value_type")
    # Normalize: JSON null → literal "null"
    if vt_raw is None:
        value_type = "null"
    elif isinstance(vt_raw, str):
        value_type = vt_raw
    else:
        raise ParameterValidationError(
            f"{ctx}.metric_value.value_type: must be a string or null "
            f"(got {type(vt_raw).__name__})"
        )

    if value_type not in METRIC_VALUE_TYPES:
        raise ParameterValidationError(
            f"{ctx}.metric_value.value_type: {value_type!r} not in "
            f"{sorted(METRIC_VALUE_TYPES)}"
        )

    # Unit handling — empty string REJECTED, JSON null dropped
    unit_raw = raw.get("unit", None)
    if unit_raw is not None and not isinstance(unit_raw, str):
        raise ParameterValidationError(
            f"{ctx}.metric_value.unit: must be a string or null/absent "
            f"(got {type(unit_raw).__name__})"
        )
    if isinstance(unit_raw, str) and unit_raw == "":
        raise ParameterValidationError(
            f"{ctx}.metric_value.unit: empty string is forbidden — use "
            "null (or omit) when there is genuinely no unit"
        )
    unit: str | None = unit_raw if isinstance(unit_raw, str) else None

    # Value handling — type must agree with value_type
    value = raw.get("value")
    if value_type == "scalar":
        if not _is_numeric(value):
            raise ParameterValidationError(
                f"{ctx}.metric_value.value: scalar value_type requires a "
                f"number (got {type(value).__name__})"
            )
    elif value_type == "range":
        if not (isinstance(value, list) and len(value) == 2
                and _is_numeric(value[0]) and _is_numeric(value[1])):
            raise ParameterValidationError(
                f"{ctx}.metric_value.value: range value_type requires "
                f"[lo, hi] numeric pair (got {value!r})"
            )
        if value[0] > value[1]:
            raise ParameterValidationError(
                f"{ctx}.metric_value.value: range [{value[0]}, {value[1]}] "
                "has lo > hi"
            )
    elif value_type == "categorical":
        if not (
            isinstance(value, str)
            or (isinstance(value, list)
                and all(isinstance(v, str) for v in value))
        ):
            raise ParameterValidationError(
                f"{ctx}.metric_value.value: categorical value_type requires "
                f"a string or list of strings (got {type(value).__name__})"
            )
    elif value_type == "null":
        # Qualitative parameter — value must be absent or JSON null.
        # A numeric value contradicts the qualitative marker (upstream
        # "over-correction trap").
        if value is not None:
            raise ParameterValidationError(
                f"{ctx}.metric_value.value: value_type=null requires "
                f"value to be null or absent (got {value!r}) — this is the "
                "over-correction trap the prompt warns about"
            )
        value = None

    return ParsedMetricValue(value_type=value_type, value=value, unit=unit)


def _parse_parameter(
    obj: Any,
    idx: int,
    canonical_chunk_ids: Iterable[str] | None = None,
) -> ParsedParameter:
    ctx = f"parameters[{idx}]"
    if not isinstance(obj, dict):
        raise ParameterValidationError(f"{ctx}: expected an object")

    anchor = _require_str(obj.get("semantic_anchor"), "semantic_anchor", ctx)
    metric_value = _normalize_metric_value(obj.get("metric_value"), ctx)
    evidence_status = _require_str(
        obj.get("evidence_status"), "evidence_status", ctx,
    )
    if evidence_status not in EVIDENCE_STATUS_VALUES:
        raise ParameterValidationError(
            f"{ctx}: evidence_status {evidence_status!r} not in "
            f"{sorted(EVIDENCE_STATUS_VALUES)}"
        )

    raw_source_chunk_ids = _require_str_list(
        obj.get("source_chunk_ids"), "source_chunk_ids", ctx,
    )
    if canonical_chunk_ids is None:
        source_chunk_ids = tuple(raw_source_chunk_ids)
    else:
        source_chunk_ids = validate_refs(raw_source_chunk_ids, canonical_chunk_ids)
    if not source_chunk_ids:
        raise ParameterValidationError(
            f"{ctx}: source_chunk_ids cannot be empty — every parameter "
            "must cite at least one chunk (cite-every-claim discipline)"
        )

    strictness = _require_str(
        obj.get("constraint_strictness"), "constraint_strictness", ctx,
    )
    if strictness not in CONSTRAINT_STRICTNESS_VALUES:
        raise ParameterValidationError(
            f"{ctx}: constraint_strictness {strictness!r} not in "
            f"{sorted(CONSTRAINT_STRICTNESS_VALUES)}"
        )

    qual = obj.get("qualitative_descriptor")
    if qual is not None and not isinstance(qual, str):
        raise ParameterValidationError(
            f"{ctx}: qualitative_descriptor must be string or null"
        )

    # Qualitative parameter discipline: a "null" value_type MUST come
    # with a non-empty qualitative_descriptor — otherwise the
    # parameter carries no information.
    if metric_value.value_type == "null" and (not qual or not qual.strip()):
        raise ParameterValidationError(
            f"{ctx}: value_type=null requires a non-empty "
            "qualitative_descriptor (anti-pattern #4: skipping qualitative "
            "parameters)"
        )

    return ParsedParameter(
        semantic_anchor=anchor,
        metric_value=metric_value,
        evidence_status=evidence_status,
        source_chunk_ids=source_chunk_ids,
        constraint_strictness=strictness,
        qualitative_descriptor=qual if qual else None,
    )


def parse_parameter_extractor_response(
    text: str,
    *,
    canonical_chunk_ids: Iterable[str] | None = None,
) -> ParameterExtractResult:
    """Parse + validate a Parameter Extractor raw response."""
    obj = _extract_json_object(text)
    if not isinstance(obj, dict):
        raise ParameterValidationError(
            "response did not contain a parseable JSON object"
        )

    params_raw = obj.get("parameters")
    if not isinstance(params_raw, list):
        raise ParameterValidationError(
            "top: parameters must be a list"
        )

    parameters = tuple(
        _parse_parameter(p, i, canonical_chunk_ids)
        for i, p in enumerate(params_raw)
    )
    return ParameterExtractResult(parameters=parameters, raw=obj)
