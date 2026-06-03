"""Pure-function constraint evaluation.

Takes a list of Constraints + the Synthesizer's typed Claims (and
optionally an extracted-values dict from the Parameter Extractor) and
returns a list of Violations.

Three checker kinds shipped for v1:

- ``numeric_range`` — operates on an ``extracted_values`` dict supplied
  by the parameter_extractor. Checks ``min ≤ value ≤ max``.
- ``must_include_term`` — searches across all claim texts for a
  required substring. Case-sensitive by default; opt-in for case-
  insensitive.
- ``must_attribute`` — each claim must have ≥1 attribution_region_id.
  Claims without attribution become violations.

The function is **pure** — no I/O, no dispatch, no DB. Easy to unit
test, easy to call from the constraint-loop machinery (Sprint 5).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from substrate.schemas import Claim

from .constraints import Constraint, Violation


def evaluate_constraints(
    constraints: Iterable[Constraint],
    claims: Iterable[Claim],
    *,
    extracted_values: Mapping[str, Any] | None = None,
) -> list[Violation]:
    """Evaluate every constraint against the claims (and the optional
    extracted_values dict). Returns the full list of violations — the
    caller decides which to act on based on strictness.

    Order: constraints are evaluated in the order supplied. Violations
    are appended in the order they're discovered so a downstream
    cohort analysis sees a stable ordering."""
    claims_list = list(claims)
    extracted = extracted_values or {}
    violations: list[Violation] = []

    for c in constraints:
        if c.kind == "numeric_range":
            v = _check_numeric_range(c, extracted)
            if v is not None:
                violations.append(v)

        elif c.kind == "must_include_term":
            v = _check_must_include_term(c, claims_list)
            if v is not None:
                violations.append(v)

        elif c.kind == "must_attribute":
            violations.extend(_check_must_attribute(c, claims_list))

        # else: unknown kind — silently skip. The Constraint dataclass
        # validates kind at construction so this branch is unreachable
        # in practice; leaving the catch-all to make future kind
        # additions backwards-compatible.

    return violations


# ---------------------------------------------------------------------------
# Per-kind checkers — each returns one or more Violations or None
# ---------------------------------------------------------------------------


def _check_numeric_range(
    c: Constraint,
    extracted_values: Mapping[str, Any],
) -> Violation | None:
    """``config`` shape: ``{"field": str, "min": float, "max": float}``.
    Pulls the extracted value by name; if missing, that's a violation
    (the parameter_extractor was supposed to surface it)."""
    field = c.config.get("field")
    if not field:
        return Violation(
            constraint_id=c.constraint_id,
            constraint_kind=c.kind,
            strictness=c.strictness,
            reason="numeric_range constraint config missing 'field' key",
        )
    if field not in extracted_values:
        return Violation(
            constraint_id=c.constraint_id,
            constraint_kind=c.kind,
            strictness=c.strictness,
            reason=f"extracted_values has no '{field}' — parameter_extractor "
                   "did not surface this constraint's field",
        )
    raw = extracted_values[field]
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return Violation(
            constraint_id=c.constraint_id,
            constraint_kind=c.kind,
            strictness=c.strictness,
            reason=f"'{field}' is {raw!r}, not numeric",
        )
    lo = c.config.get("min")
    hi = c.config.get("max")
    if lo is not None and value < float(lo):
        return Violation(
            constraint_id=c.constraint_id,
            constraint_kind=c.kind,
            strictness=c.strictness,
            reason=f"{field}={value} < min={lo}",
        )
    if hi is not None and value > float(hi):
        return Violation(
            constraint_id=c.constraint_id,
            constraint_kind=c.kind,
            strictness=c.strictness,
            reason=f"{field}={value} > max={hi}",
        )
    return None


def _check_must_include_term(
    c: Constraint,
    claims: list[Claim],
) -> Violation | None:
    """``config`` shape: ``{"term": str, "case_sensitive": bool}``.
    Searches claim texts for the term. Returns a violation if NO
    claim contains it (the constraint says the synthesis must include
    discussion of this term)."""
    term = c.config.get("term")
    if not term:
        return Violation(
            constraint_id=c.constraint_id,
            constraint_kind=c.kind,
            strictness=c.strictness,
            reason="must_include_term constraint config missing 'term' key",
        )
    case_sensitive = bool(c.config.get("case_sensitive", False))
    needle = term if case_sensitive else term.lower()
    for claim in claims:
        haystack = claim.text if case_sensitive else claim.text.lower()
        if needle in haystack:
            return None  # at least one claim mentions it; satisfied
    return Violation(
        constraint_id=c.constraint_id,
        constraint_kind=c.kind,
        strictness=c.strictness,
        reason=f"no claim mentions required term {term!r}",
    )


def _check_must_attribute(
    c: Constraint,
    claims: list[Claim],
) -> list[Violation]:
    """``config`` is empty (no fields). Returns one Violation per
    claim that has no ``attribution_region_ids``. The constraint
    says every claim in the synthesis must be source-attributed."""
    out: list[Violation] = []
    for claim in claims:
        if not claim.attribution_region_ids:
            out.append(Violation(
                constraint_id=c.constraint_id,
                constraint_kind=c.kind,
                strictness=c.strictness,
                target_claim_id=claim.claim_id,
                reason=f"claim {claim.claim_id!r} has no attribution_region_ids",
            ))
    return out
