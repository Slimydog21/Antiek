"""DRW SPR-05 M1 + M4 + M5 — the cascade planner.

Decomposes one problem (or a structural gap, or a note challenge) into a
tree of *focused* sub-questions the user edits and approves before anything
launches. Built on the existing ``roles/decomposer`` parse contract; the
actual decomposition call is injected (``Decomposer``) so the planner's
tree-building + focus logic is testable without a live model.

Focus-driven recursion (M5): each produced sub-question is run through
``focus_check``; an over-broad one is decomposed again (down to
``max_depth``), so an over-broad *problem* yields a deeper, narrower tree
rather than three vague branches. An atomic problem that the decomposer
returns un-split stays a single leaf. The ``MAX_BRANCHES`` cap surfaces
(flags + truncates with a recorded note) rather than silently dropping.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Protocol, Sequence

try:
    from .tree_contract import PlanNode, PlanTree
    from .focus import MAX_BRANCHES, focus_check, is_over_broad
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from roles.cascade_planner.tree_contract import PlanNode, PlanTree  # type: ignore[no-redef]
    from roles.cascade_planner.focus import MAX_BRANCHES, focus_check, is_over_broad  # type: ignore[no-redef]


DEFAULT_MAX_DEPTH = 3


@dataclass(frozen=True)
class SubQuestion:
    """A decomposed sub-question. Mirrors decomposer.ParsedSubQuestion's
    useful fields; the planner is agnostic to where it came from."""

    question: str
    rationale: str = ""
    focus_boundary: str = ""


class Decomposer(Protocol):
    """problem text → list of sub-questions. Production wraps the decomposer
    role (dispatch + parse_decomposer_response); tests inject a fake."""

    def decompose(self, question: str, *, context: str = "") -> List[SubQuestion]: ...


class DispatchDecomposer:
    """Production decomposer: dispatch the decomposer role and parse."""

    def decompose(self, question: str, *, context: str = "") -> List[SubQuestion]:
        import uuid

        from substrate.dispatch import dispatch
        from roles.decomposer import parse_decomposer_response, render_full_prompt

        investigation_id = f"decomp-{uuid.uuid4().hex[:12]}"
        prompt = render_full_prompt(
            investigation_id=investigation_id,
            question=question,
            context=context,
        )
        result = dispatch(prompt, role="decomposer", investigation_id=investigation_id)
        text = getattr(result, "text", None) or str(result)
        parsed = parse_decomposer_response(
            text, expected_investigation_id=investigation_id,
        )
        return [SubQuestion(question=sq.sub_question, rationale=sq.rationale,
                            focus_boundary=sq.category)
                for sq in parsed.decomposition]


@dataclass
class PlanReport:
    tree: PlanTree
    capped_nodes: List[str]          # local_ids where MAX_BRANCHES truncated
    over_broad_leaves: List[str]     # leaves still over-broad at max depth (honest)


def build_plan(
    problem: str,
    *,
    decomposer: Decomposer,
    context: str = "",
    max_depth: int = DEFAULT_MAX_DEPTH,
    seed_kind: str = "problem",
    seed_provenance: Optional[dict] = None,
) -> PlanReport:
    """Decompose ``problem`` into a focus-checked, editable tree."""
    capped: List[str] = []
    over_broad: List[str] = []

    root = PlanNode(question=problem, rationale="root problem")
    _expand(root, decomposer, context, depth=0, max_depth=max_depth,
            capped=capped, over_broad=over_broad)
    tree = PlanTree(root=root, seed_kind=seed_kind,
                    seed_provenance=seed_provenance or {})
    return PlanReport(tree=tree, capped_nodes=capped, over_broad_leaves=over_broad)


def _expand(node: PlanNode, decomposer: Decomposer, context: str, *,
            depth: int, max_depth: int, capped: List[str], over_broad: List[str]) -> None:
    if depth >= max_depth:
        if is_over_broad(node.question) and depth > 0:
            over_broad.append(node.local_id)  # honest: still broad, out of depth
        return
    subs = decomposer.decompose(node.question, context=context)
    # An atomic problem the decomposer does not split (0 or 1 sub) stays a
    # leaf — no forced branches.
    if len(subs) <= 1:
        if depth == 0 and len(subs) == 1:
            # A single sub at the root: keep it as one child (still a focused
            # plan), do not fabricate siblings.
            pass
        else:
            return
    if len(subs) > MAX_BRANCHES:
        capped.append(node.local_id)
        subs = subs[:MAX_BRANCHES]   # surfaced via capped, not silent
    for sq in subs:
        child = PlanNode(question=sq.question, rationale=sq.rationale,
                         focus_boundary=sq.focus_boundary)
        node.children.append(child)
        # Recurse into over-broad children to deepen focus.
        if is_over_broad(child.question):
            _expand(child, decomposer, context, depth=depth + 1,
                    max_depth=max_depth, capped=capped, over_broad=over_broad)


# ---------------------------------------------------------------------------
# M4 — gap- and note-seeded planning (the compounding seam)
# ---------------------------------------------------------------------------


def plan_from_gap(
    gap: Any, *, decomposer: Decomposer, max_depth: int = DEFAULT_MAX_DEPTH,
) -> PlanReport:
    """Seed a plan from a structural gap (SPR-07). ``gap`` is duck-typed:
    we read ``.question``/``.text`` and ``.gap_id``/``.node_id`` if present,
    so this works against the SPR-07 interface before it lands."""
    question = (getattr(gap, "question", None) or getattr(gap, "text", None)
                or str(gap))
    gap_id = getattr(gap, "gap_id", None) or getattr(gap, "node_id", None)
    return build_plan(
        question, decomposer=decomposer, max_depth=max_depth, seed_kind="gap",
        seed_provenance={"gap_id": gap_id, "kind": getattr(gap, "kind", None)},
    )


def plan_from_note_challenge(
    note_node_id: str, challenge_text: str, *, decomposer: Decomposer,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> PlanReport:
    """Seed a plan from a note challenge (SPR-03/SPR-10). Records which note
    + challenge seeded it on the root provenance."""
    return build_plan(
        challenge_text, decomposer=decomposer, max_depth=max_depth,
        seed_kind="note_challenge",
        seed_provenance={"note_node_id": note_node_id, "challenge": challenge_text},
    )
