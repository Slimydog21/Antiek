"""Constraint dataclasses + Violation dataclass.

Constraints are produced by the parameter_extractor role (currently
embedded in Researchmaxx's orchestrate.py monolith; Sprint 5 extracts
it). They flow into the constraint-check middleware which evaluates
them against the Synthesizer's claims and emits typed events.

Sprint 4 day 3-4: ships the pure dataclasses + the v1 kind catalogue.
The constraint-loop machinery (iterate, re-synthesize, terminate) is
deferred until parameter_extractor extraction in Sprint 5 surfaces
real constraint sources to feed it.

Lineage note: the Researchmaxx ``constraint_check.py`` (real
implementation, ~2,000 LOC) was corrupted upstream and only an
emergency no-op stub remains. We build fresh from the Researchmaxx
spec §B + the operator's surfaced vocabulary in
``substrate.constants.CONSTRAINT_STRICTNESS`` / ``CONSTRAINT_MAX_ITERATIONS``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Closed sets — must agree with the schemas-side Literal types.
# Validated by named test in tests/test_middleware_constraint_check.py.

CONSTRAINT_STRICTNESS_VALUES: frozenset[str] = frozenset({
    "hard", "soft", "target",
})

CONSTRAINT_KINDS: frozenset[str] = frozenset({
    "numeric_range",
    "must_include_term",
    "must_attribute",
})


@dataclass(frozen=True)
class Constraint:
    """One constraint emitted by the parameter_extractor.

    ``config`` is kind-specific:

    | kind              | config shape                                      |
    |-------------------|---------------------------------------------------|
    | numeric_range     | {"field": "<name>", "min": float, "max": float}   |
    | must_include_term | {"term": "<substring>", "case_sensitive": bool}   |
    | must_attribute    | {} (claim must have ≥1 attribution_region_id)     |

    Validation lives at construction time: kind + strictness checked
    against the closed sets above. Bad inputs raise ValueError loudly
    rather than slipping through to a SQL-layer failure later."""

    constraint_id: str
    strictness: str       # Literal["hard", "soft", "target"]
    kind: str             # one of CONSTRAINT_KINDS
    description: str
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.strictness not in CONSTRAINT_STRICTNESS_VALUES:
            raise ValueError(
                f"strictness must be one of {sorted(CONSTRAINT_STRICTNESS_VALUES)}, "
                f"got {self.strictness!r}"
            )
        if self.kind not in CONSTRAINT_KINDS:
            raise ValueError(
                f"kind must be one of {sorted(CONSTRAINT_KINDS)}, "
                f"got {self.kind!r}"
            )


@dataclass(frozen=True)
class Violation:
    """One constraint violation produced by ``evaluate_constraints``.
    Carries the constraint_id back to the emit helper so the
    ``ConstraintViolationFoundPayload`` event has all the attribution
    fields it needs."""

    constraint_id: str
    constraint_kind: str  # mirrors the Constraint.kind
    strictness: str
    reason: str
    target_claim_id: str | None = None
