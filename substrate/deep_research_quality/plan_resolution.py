"""Plan-resolution coverage — did the investigation resolve its plan's questions?

The cascade planner (on-main ``roles/cascade_planner``) decomposes a root problem
into an editable tree of focused sub-questions (a ``PlanTree``), the operator
approves it, an investigation executes, and findings resolve some sub-questions
via ``resolved_by`` edges (graph-level, read by ``substrate/gap_detection``).
But nothing MEASURES whether the plan was actually carried out — which sub-
questions the evidence resolved, which remain UNADDRESSED, and whether the ROOT
problem is solved. THIS module is that measurement: the recursion-closer of the
plan -> execute -> measure -> re-plan loop.

**Why pure + import-free of the plan layer.** The plan tree (``roles/cascade_planner``)
and the resolution edges (``substrate/gap_detection``, which needs a DB) live in
different layers. This substrate takes a minimal compatible ``PlanQuestion`` shape
(a Protocol mirroring ``PlanNode``'s load-bearing fields) and the SET of resolved
question node-ids as input. The caller reads the ``resolved_by`` edges from the
graph and hands the resolved set here; the pure layer never touches the DB. This
keeps the module independently bar-clean on frozen main (the #1873 compatible-
shape pattern) and testable in isolation.

**The resolution states (hard to vary, mutually exclusive):**
  * ``resolved`` — the question's ``graph_node_id`` IS in the resolved set. The
    evidence resolved it.
  * ``unpersisted`` — the question has NO ``graph_node_id`` yet (it was never
    written to the graph, e.g. a plan node added after launch, or a leaf that the
    planner never persisted). It is neither resolved nor unresolved — it cannot be
    measured. Surfaced distinctly so the operator does not mistake "we forgot to
    persist this" for "the research failed to address this."
  * ``unresolved`` — the question HAS a ``graph_node_id`` but it is NOT in the
    resolved set. The research ran but the evidence did not resolve this question.
    This is the RE-PLAN SIGNAL: the operator can sharpen, re-scope, or launch a
    follow-up investigation.

**The score (hard to vary).** Resolution coverage is the fraction of MEASURABLE
plan questions (those WITH a graph_node_id) that are resolved. Unpersisted
questions are EXCLUDED from the denominator — a plan half-persisted should not
score artificially low (penalizing persistence gaps) nor artificially high
(coercing unpersisted to resolved). The score is the exact ratio
``resolved / (resolved + unresolved)`` in ``[0, 1]``.

**Root resolution is the keystone.** The root problem question is the whole point
of the plan; if it is unresolved, ``root_resolved`` is ``False`` regardless of how
many leaves resolved. A plan that resolves all its leaves but not its root has
done sub-work without delivering the answer — ``root_resolved`` makes that failure
visible. (An unpersisted root is ``root_resolved=None`` — the plan was never
grounded in the graph, so root resolution is unmeasurable.)

**Honest scope.** This is a STRUCTURAL measurement — it counts resolved_by edges,
not semantic quality. A resolved question may have a weak resolution (the edge
exists but the evidence is thin); that is a DIFFERENT axis (the rubric / the
confidence on the resolved_by edge). This module never judges resolution quality;
``notes`` say so. The ``unresolved`` list is the actionable re-plan surface.

**Honesty rules (load-bearing):**
* ``measured=False`` when zero plan questions are measurable (all unpersisted) --
  resolution of an ungrounded plan is unknown, never fabricated.
* ``root_resolved`` is ``None`` when the root is unpersisted, ``True``/``False``
  when it is grounded in the graph.
* Deterministic and pure: same plan + resolved set -> same report. No LLM, no
  network, no clock, no mutation, no DB. ``authority`` is always ``"advisory"``.
* Every question's state is carried through (auditable): the resolved, unresolved,
  and unpersisted lists let the operator see EXACTLY where the plan stands.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import Protocol


class PlanResolutionError(ValueError):
    """A plan-resolution input violates a load-bearing invariant."""


class PlanQuestion(Protocol):
    """A node in the editable plan tree (mirrors PlanNode's load-bearing fields).

    ``graph_node_id`` is ``None`` until the planner persists the question to the
    graph (writes the SPR-01 question node); after that it carries the node id that
    ``resolved_by`` edges reference. ``children`` are the decomposed sub-questions.
    """

    question: str
    local_id: str
    graph_node_id: str | None
    children: list[PlanQuestion]


@dataclass(frozen=True)
class QuestionResolution:
    """One plan question's resolution state. Auditable."""

    local_id: str
    question: str
    graph_node_id: str | None
    state: str  # "resolved" | "unresolved" | "unpersisted"


@dataclass(frozen=True)
class PlanResolutionReport:
    """The plan-resolution verdict for one investigation. Advisory, pure."""

    resolved_count: int
    unresolved_count: int
    unpersisted_count: int
    total_questions: int  # all plan questions (root + descendants)
    measurable_count: int  # resolved + unresolved (has a graph_node_id)
    coverage: float  # resolved / measurable in [0, 1]; 0.0 when not measurable
    measured: bool  # False when no question is measurable (all unpersisted)
    root_resolved: bool | None  # None when root unpersisted; True/False when grounded
    resolved: tuple[QuestionResolution, ...]
    unresolved: tuple[QuestionResolution, ...]  # the re-plan signal (actionable)
    unpersisted: tuple[QuestionResolution, ...]
    notes: tuple[str, ...]
    authority: str = "advisory"


def _iter_questions(root: PlanQuestion) -> typing.Iterator[PlanQuestion]:
    """Yield the root then all descendants, depth-first (stable order)."""
    yield root
    stack = list(reversed(root.children))
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def score_plan_resolution(
    root: PlanQuestion,
    resolved_graph_node_ids: set[str] | frozenset[str],
) -> PlanResolutionReport:
    """Measure how well the investigation's evidence resolved the plan.

    ``root`` is the plan tree root (a ``PlanQuestion`` / ``PlanNode``). The caller
    reads ``resolved_by`` edges from the graph and passes the resolved question
    node-ids as ``resolved_graph_node_ids``. Returns a
    :class:`PlanResolutionReport` with each question's state, the coverage score,
    and the unresolved list (the re-plan surface).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not root.question.strip():
        raise PlanResolutionError(
            "root question must be non-empty; cannot measure resolution of nothing"
        )

    resolved_set = set(resolved_graph_node_ids)
    questions = list(_iter_questions(root))

    resolved: list[QuestionResolution] = []
    unresolved: list[QuestionResolution] = []
    unpersisted: list[QuestionResolution] = []

    for node in questions:
        if not node.local_id.strip():
            raise PlanResolutionError(
                "every plan question must have a non-empty local_id "
                "(provenance is load-bearing)"
            )
        if node.graph_node_id is None:
            state = "unpersisted"
        elif node.graph_node_id in resolved_set:
            state = "resolved"
        else:
            state = "unresolved"
        state_obj = QuestionResolution(
            local_id=node.local_id,
            question=node.question,
            graph_node_id=node.graph_node_id,
            state=state,
        )
        if state == "resolved":
            resolved.append(state_obj)
        elif state == "unresolved":
            unresolved.append(state_obj)
        else:
            unpersisted.append(state_obj)

    measurable = len(resolved) + len(unresolved)
    coverage = (len(resolved) / measurable) if measurable > 0 else 0.0

    if root.graph_node_id is None:
        root_resolved: bool | None = None
    else:
        root_resolved = root.graph_node_id in resolved_set

    notes: list[str] = [
        "coverage is structural: resolved / measurable plan questions (has a "
        "graph_node_id); unpersisted questions are excluded, not penalized",
        "resolution quality (weak vs strong evidence) is a different axis "
        "(the resolved_by confidence); this module counts edges, not quality",
    ]
    if measurable == 0:
        notes.append(
            "no plan question is measurable (all unpersisted); resolution of an "
            "ungrounded plan is unmeasurable"
        )
    else:
        notes.append(
            f"coverage {coverage:.0%} ({len(resolved)} of {measurable} measurable "
            f"questions resolved)"
        )
    if root_resolved is None:
        notes.append("root question is unpersisted — root resolution unmeasurable")
    elif root_resolved:
        notes.append("root problem question IS resolved (keystone met)")
    else:
        notes.append(
            "root problem question is UNRESOLVED — the plan did not deliver its "
            "answer even if leaves resolved (keystone failed)"
        )
    if unresolved:
        notes.append(
            f"RE-PLAN SIGNAL: {len(unresolved)} unresolved question(s): "
            + ", ".join(q.local_id for q in unresolved)
        )

    return PlanResolutionReport(
        resolved_count=len(resolved),
        unresolved_count=len(unresolved),
        unpersisted_count=len(unpersisted),
        total_questions=len(questions),
        measurable_count=measurable,
        coverage=coverage,
        measured=measurable > 0,
        root_resolved=root_resolved,
        resolved=tuple(resolved),
        unresolved=tuple(unresolved),
        unpersisted=tuple(unpersisted),
        notes=tuple(notes),
    )


__all__ = [
    "PlanResolutionError",
    "PlanQuestion",
    "QuestionResolution",
    "PlanResolutionReport",
    "score_plan_resolution",
]
