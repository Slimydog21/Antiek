"""Parameter → Constraint conversion.

Sprint 7 day 2. The seam between the Parameter Extractor's LLM output
and the Sprint 4 day 3-4 constraint-loop machinery.

The constraint loop reads ``ConstraintSpec`` records from the typed
trajectory and reconstructs ``middleware.constraint_check.Constraint``
dataclasses on the read side. This module is the **producer** —
called by the bridge handler at emit time so the Delivered payload
carries both the raw parameters and the derived constraints in one
event.

Conversion rules (mirror the upstream constraint-loop semantics):

- ``metric_value.value_type == "scalar"`` with numeric value AND a
  unit → ``numeric_range`` constraint with ``config = {field: <anchor>,
  min: <value>, max: <value>}``. A single-value parameter narrows to
  an equality-as-range; the synthesizer's reported metric must equal
  it. (Future: a configurable tolerance band.)
- ``metric_value.value_type == "range"`` → ``numeric_range`` with
  ``config = {field, min, max}`` from the [lo, hi] pair.
- ``metric_value.value_type == "categorical"`` → ``must_include_term``
  constraints, one per allowed string. The synthesizer's claim text
  must contain the term.
- ``metric_value.value_type == "null"`` (qualitative) →
  ``must_attribute`` constraint. Every claim citing this parameter
  must have ≥1 attribution region. (Qualitative parameters can't be
  range-checked; the discipline is "say WHERE this matters in the
  evidence.")

A parameter that produces zero constraints (e.g. a scalar with no
unit AND no value) is **dropped silently** — the parameter still
shows up in the Delivered payload's ``parameters`` list for
trajectory visibility, but it doesn't gate the constraint loop.
"""

from __future__ import annotations

from typing import Iterable, List

try:
    from ...schemas import ConstraintSpec
except ImportError:  # pragma: no cover — direct-script fallback
    import os
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.schemas import ConstraintSpec  # type: ignore[no-redef]

from .parser import ParsedParameter


def _scalar_to_numeric_range(p: ParsedParameter) -> ConstraintSpec | None:
    """Single numeric value → degenerate range (min=max=value).
    Requires a unit — a unitless scalar is too ambiguous to gate
    on. Returns None when the unit is missing."""
    if p.metric_value.unit is None:
        return None
    value = p.metric_value.value
    return ConstraintSpec(
        constraint_id=f"param:{p.semantic_anchor}",
        strictness=p.constraint_strictness,  # type: ignore[arg-type]
        kind="numeric_range",
        description=(
            f"{p.semantic_anchor} must equal {value} "
            f"{p.metric_value.unit}"
        ),
        config={
            "field": p.semantic_anchor,
            "min": float(value),
            "max": float(value),
        },
    )


def _range_to_numeric_range(p: ParsedParameter) -> ConstraintSpec:
    """``[lo, hi]`` → ``numeric_range`` with both bounds."""
    lo, hi = p.metric_value.value
    unit_str = f" {p.metric_value.unit}" if p.metric_value.unit else ""
    return ConstraintSpec(
        constraint_id=f"param:{p.semantic_anchor}",
        strictness=p.constraint_strictness,  # type: ignore[arg-type]
        kind="numeric_range",
        description=(
            f"{p.semantic_anchor} must lie in [{lo}, {hi}]{unit_str}"
        ),
        config={
            "field": p.semantic_anchor,
            "min": float(lo),
            "max": float(hi),
        },
    )


def _categorical_to_must_include_terms(p: ParsedParameter) -> List[ConstraintSpec]:
    """Categorical → one ``must_include_term`` per allowed string.
    Single-string value becomes a one-element list; list-of-strings
    each gets its own constraint id (suffixed with the term)."""
    value = p.metric_value.value
    terms: list[str] = [value] if isinstance(value, str) else list(value)
    out: List[ConstraintSpec] = []
    for term in terms:
        # constraint_id includes the term so the loop can show which
        # specific category violation happened. Term is the value, not
        # the anchor name.
        suffix = term.lower().replace(" ", "_")[:48]
        out.append(ConstraintSpec(
            constraint_id=f"param:{p.semantic_anchor}:{suffix}",
            strictness=p.constraint_strictness,  # type: ignore[arg-type]
            kind="must_include_term",
            description=(
                f"{p.semantic_anchor} must mention {term!r} in the synthesis"
            ),
            config={"term": term, "case_sensitive": "false"},
        ))
    return out


def _qualitative_to_must_attribute(p: ParsedParameter) -> ConstraintSpec:
    """Qualitative parameter → ``must_attribute``. The substantive
    check: any claim that names this parameter must carry an
    attribution region (anti-vacuous-qualitative-claim discipline)."""
    descriptor = p.qualitative_descriptor or "(no descriptor)"
    return ConstraintSpec(
        constraint_id=f"param:{p.semantic_anchor}",
        strictness=p.constraint_strictness,  # type: ignore[arg-type]
        kind="must_attribute",
        description=(
            f"Qualitative parameter {p.semantic_anchor!r} "
            f"({descriptor}) must be cited with attribution by any "
            "thesis claim that mentions it"
        ),
        config={},
    )


def parameters_to_constraints(
    parameters: Iterable[ParsedParameter],
) -> List[ConstraintSpec]:
    """Convert a list of parsed parameters into the ``ConstraintSpec``
    records the Day 3 constraint loop consumes. Pure function — no
    LLM call, no I/O. Silently drops parameters that cannot produce a
    constraint (e.g. unitless scalars)."""
    out: List[ConstraintSpec] = []
    for p in parameters:
        vt = p.metric_value.value_type
        if vt == "scalar":
            spec = _scalar_to_numeric_range(p)
            if spec is not None:
                out.append(spec)
        elif vt == "range":
            out.append(_range_to_numeric_range(p))
        elif vt == "categorical":
            out.extend(_categorical_to_must_include_terms(p))
        elif vt == "null":
            out.append(_qualitative_to_must_attribute(p))
        # Else: unknown value_type already rejected by the parser; we
        # don't reach here.
    return out
