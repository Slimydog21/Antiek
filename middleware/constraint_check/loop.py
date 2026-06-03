"""Constraint loop machinery (Sprint 7 day 3 — closes the gate opened
in Sprint 4 day 3-4 when the evaluator + escalation helpers shipped
but the loop body couldn't be wired until ``parameter_extractor``
landed).

The loop is **role-agnostic**: it takes initial claims, a list of
``ConstraintSpec`` records (the typed shape that
``ParameterExtractDeliveredPayload`` carries), and a callable that
re-invokes the synthesizer. The callable signature is:

    synthesizer_callable(violations, iteration) -> list[Claim]

The orchestrator (or test) provides the callable. The loop itself
never imports the synthesizer bridge.

Per iteration:

1. Convert ``ConstraintSpec`` → ``Constraint`` dataclasses.
2. Evaluate against the current claims (with ``extracted_values``
   pulled from the ``Parameter`` list when available — needed for the
   ``numeric_range`` checker).
3. Emit one ``CONSTRAINT_VIOLATION_FOUND`` event per violation.
4. Count hard violations:
   - Zero hard violations: terminate with ``passed`` (or
     ``single_pass`` when iteration 0 and no constraints ever applied
     a check).
   - Hard violations exist + iteration < max - 1: emit
     ``CONSTRAINT_REVISION_TRIGGERED`` and re-invoke synthesizer.
     Track hard-count delta — if it INCREASED versus the previous
     iteration, terminate with ``regressed`` (revisions making things
     worse is a load-bearing failure mode the spec calls out).
   - Hard violations exist + at max iteration: terminate with
     ``max_iterations_reached``.
5. Emit ``CONSTRAINT_LOOP_RESOLVED`` exactly once on terminate.

The full iteration history is captured in ``ConstraintLoopResult``
for archive embedding via ``build_constraint_check_result``.

Preflight (constraint-set internal contradiction detection) is
deferred — it's a separate analysis pass and the loop body can be
exercised end-to-end without it. ``preflight_failed`` /
``escalated`` statuses are defined on ``ConstraintLoopStatus`` and
remain valid terminal values when a future preflight pass lands.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

try:
    from ...constants import CONSTRAINT_MAX_ITERATIONS
    from ...schemas import Claim, ConstraintSpec, Parameter
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import CONSTRAINT_MAX_ITERATIONS  # type: ignore[no-redef]
    from substrate.schemas import Claim, ConstraintSpec, Parameter  # type: ignore[no-redef]

from .constraints import Constraint, Violation
from .evaluation import evaluate_constraints
from .events import (
    emit_constraint_loop_resolved,
    emit_constraint_revision_triggered,
    emit_constraint_violation_found,
)

SynthesizerCallable = Callable[[list[Violation], int], list[Claim]]


@dataclass
class ConstraintLoopResult:
    """Loop outcome. ``final_claims`` is what downstream archives;
    ``iteration_history`` is the per-iteration violation snapshot that
    embeds into ``constraint_check_result`` metadata for cohort
    analysis."""

    final_status: str               # one of ConstraintLoopStatus
    total_iterations: int
    final_claims: list[Claim]
    final_violations: list[Violation]
    iteration_history: list[dict] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.final_status in ("passed", "single_pass")


# ---------------------------------------------------------------------------
# Spec → Constraint reconstruction
# ---------------------------------------------------------------------------


def spec_to_constraint(spec: ConstraintSpec) -> Constraint:
    """Reconstruct the evaluator-side ``Constraint`` dataclass from a
    typed ``ConstraintSpec`` payload record.

    The reverse of ``roles.parameter_extractor.converter`` — that
    function produced specs at bridge-emit time; this function turns
    them back into dataclasses on the read side. The dataclass
    enforces closed-set membership on ``strictness`` / ``kind`` in
    its ``__post_init__``, so a spec with a corrupt value fails
    loudly here rather than slipping into the evaluator."""
    # Convert dict[str, Any] config keys to floats where the
    # evaluator expects them. numeric_range checker reads "min" /
    # "max" as floats; categorical reads "term" / "case_sensitive" as
    # str/bool. The converter stringifies case_sensitive — turn it
    # back to a bool here so the evaluator's ``or False`` default
    # behaves consistently.
    config: dict[str, Any] = dict(spec.config)
    if spec.kind == "numeric_range":
        for k in ("min", "max"):
            if k in config and not isinstance(config[k], (int, float)):
                try:
                    config[k] = float(config[k])
                except (TypeError, ValueError):
                    # Leave as-is; the evaluator will surface a
                    # descriptive violation rather than crash.
                    pass
    elif spec.kind == "must_include_term":
        cs = config.get("case_sensitive")
        if isinstance(cs, str):
            config["case_sensitive"] = cs.lower() in ("true", "1", "yes")
    return Constraint(
        constraint_id=spec.constraint_id,
        strictness=spec.strictness,
        kind=spec.kind,
        description=spec.description,
        config=config,
    )


def specs_to_constraints(specs: Iterable[ConstraintSpec]) -> list[Constraint]:
    """Bulk reverse converter."""
    return [spec_to_constraint(s) for s in specs]


# ---------------------------------------------------------------------------
# Extracted-values projection
# ---------------------------------------------------------------------------


def parameters_to_extracted_values(
    parameters: Iterable[Parameter],
) -> dict[str, Any]:
    """Project the ``Parameter`` list down to the
    ``{field: value}`` dict the ``numeric_range`` checker reads.

    - ``scalar`` parameters: ``{anchor: value}``
    - ``range`` parameters: drop (no single value to check against —
      the constraint config carries [min, max])
    - ``categorical`` parameters: drop (handled by
      ``must_include_term`` against claim text)
    - ``null`` (qualitative): drop

    The synthesizer is expected to report the same parameter under the
    same anchor name in its own output for the checker to read; for
    Antiek's current pipeline, ``extracted_values`` IS the parameter
    output verbatim (no separate extraction step yet)."""
    out: dict[str, Any] = {}
    for p in parameters:
        if p.metric_value.value_type == "scalar":
            v = p.metric_value.value
            if isinstance(v, (int, float)):
                out[p.semantic_anchor] = v
    return out


# ---------------------------------------------------------------------------
# Loop body
# ---------------------------------------------------------------------------


def _count_hard(violations: Iterable[Violation]) -> int:
    return sum(1 for v in violations if v.strictness == "hard")


def _violations_to_history_dicts(violations: Iterable[Violation]) -> list[dict]:
    """Project violations to the JSON-serializable dict shape the
    archive metadata stores. Used by both the per-iteration history
    and the final-violations list."""
    return [
        {
            "constraint_id": v.constraint_id,
            "kind": v.constraint_kind,
            "strictness": v.strictness,
            "reason": v.reason,
            "target_claim_id": v.target_claim_id,
        }
        for v in violations
    ]


def run_constraint_loop(
    *,
    investigation_id: str,
    initial_claims: list[Claim],
    constraints: list[ConstraintSpec],
    synthesizer_callable: SynthesizerCallable,
    parameters: list[Parameter] | None = None,
    max_iterations: int = CONSTRAINT_MAX_ITERATIONS,
    parent_event_id: str | None = None,
) -> ConstraintLoopResult:
    """Run the iterate → revise → terminate constraint loop.

    Returns ``ConstraintLoopResult`` with the final claims, final
    violations, full per-iteration history, and the terminal
    ``final_status``.

    Terminal statuses:

    - ``single_pass`` — no constraints to evaluate; iteration 0 only.
    - ``passed`` — iterated until hard violations cleared.
    - ``regressed`` — revision made hard violations strictly worse.
    - ``max_iterations_reached`` — exhausted the budget with hard
      violations still present.

    Every per-violation event, the revision trigger, and the resolved
    event are emitted into the trajectory. The caller (orchestrator)
    is responsible for archiving the ``ConstraintLoopResult`` into the
    synthesis row's ``constraint_check_result`` metadata via
    ``build_constraint_check_result``.
    """
    # ── No-op: no constraints to check ──
    if not constraints:
        emit_constraint_loop_resolved(
            investigation_id=investigation_id,
            final_status="single_pass",
            total_iterations=1,
            final_violation_count=0,
            parent_event_id=parent_event_id,
        )
        return ConstraintLoopResult(
            final_status="single_pass",
            total_iterations=1,
            final_claims=list(initial_claims),
            final_violations=[],
            iteration_history=[],
        )

    constraint_dataclasses = specs_to_constraints(constraints)
    extracted_values = (
        parameters_to_extracted_values(parameters) if parameters else {}
    )

    claims: list[Claim] = list(initial_claims)
    iteration_history: list[dict] = []
    last_hard_count: int | None = None
    total_iterations = 0

    # The ``max_iterations`` ceiling counts revision attempts. The
    # initial evaluation is iteration 0; a revision produces iteration
    # 1; etc. The upstream's hard cap is 3 iterations (so up to 2
    # revisions). We mirror that ceiling verbatim.
    for iteration in range(max_iterations):
        total_iterations = iteration + 1
        violations = evaluate_constraints(
            constraint_dataclasses, claims,
            extracted_values=extracted_values,
        )

        # Emit one CONSTRAINT_VIOLATION_FOUND per violation.
        for v in violations:
            emit_constraint_violation_found(
                investigation_id=investigation_id,
                iteration=iteration,
                violation=v,
                parent_event_id=parent_event_id,
            )

        iteration_history.append({
            "iteration": iteration,
            "violations": _violations_to_history_dicts(violations),
            "n_violations": len(violations),
            "n_hard": _count_hard(violations),
        })

        hard_count = _count_hard(violations)

        # Termination: no hard violations.
        if hard_count == 0:
            # ``passed`` after revision, ``single_pass`` if we cleared
            # on iteration 0 with no revision needed. The terminology
            # distinguishes "iterated until clean" from "got it right
            # first time" so a cohort filter can separate the two
            # populations.
            final_status = "passed" if iteration > 0 else "single_pass"
            emit_constraint_loop_resolved(
                investigation_id=investigation_id,
                final_status=final_status,
                total_iterations=total_iterations,
                final_violation_count=len(violations),
                parent_event_id=parent_event_id,
            )
            return ConstraintLoopResult(
                final_status=final_status,
                total_iterations=total_iterations,
                final_claims=claims,
                final_violations=violations,
                iteration_history=iteration_history,
            )

        # Regression check: revision made it strictly worse.
        if last_hard_count is not None and hard_count > last_hard_count:
            emit_constraint_loop_resolved(
                investigation_id=investigation_id,
                final_status="regressed",
                total_iterations=total_iterations,
                final_violation_count=len(violations),
                parent_event_id=parent_event_id,
            )
            return ConstraintLoopResult(
                final_status="regressed",
                total_iterations=total_iterations,
                final_claims=claims,
                final_violations=violations,
                iteration_history=iteration_history,
            )

        # We have hard violations and they didn't get worse. If
        # there's iteration budget left, revise. Else exit
        # max_iterations_reached.
        if iteration < max_iterations - 1:
            triggering_ids = [
                v.constraint_id for v in violations if v.strictness == "hard"
            ]
            emit_constraint_revision_triggered(
                investigation_id=investigation_id,
                iteration=iteration,
                triggering_constraint_ids=triggering_ids,
                parent_event_id=parent_event_id,
            )
            # Re-invoke the synthesizer with the violation context.
            claims = list(synthesizer_callable(violations, iteration))
            last_hard_count = hard_count
            continue

        # Budget exhausted with hard violations still present.
        emit_constraint_loop_resolved(
            investigation_id=investigation_id,
            final_status="max_iterations_reached",
            total_iterations=total_iterations,
            final_violation_count=len(violations),
            parent_event_id=parent_event_id,
        )
        return ConstraintLoopResult(
            final_status="max_iterations_reached",
            total_iterations=total_iterations,
            final_claims=claims,
            final_violations=violations,
            iteration_history=iteration_history,
        )

    # Unreachable — the for loop always returns. Defensive guard for
    # the type checker.
    raise RuntimeError(
        "constraint loop fell out of its bounded for-loop — should not happen",
    )  # pragma: no cover
