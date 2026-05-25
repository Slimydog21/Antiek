"""Cascade planner role — DRW SPR-05.

Decomposes one problem into a tree of focused sub-researches the user edits
and approves before anything launches. The glass-box plan: control, not
autonomy, is the product's differentiator, so this role *stops* at an
approved, editable plan — launching is SPR-06.

Built on ``roles/decomposer`` (reuses its parse contract via an injected
``Decomposer``); persists to SPR-01 question nodes; gates launch behind an
explicit approval. See ``program.md`` for the operator-editable conventions.
"""

from .tree_contract import ApprovalState, PlanNode, PlanTree
from .focus import MAX_BRANCHES, FocusVerdict, focus_check, is_over_broad
from .planner import (
    DEFAULT_MAX_DEPTH,
    Decomposer,
    DispatchDecomposer,
    PlanReport,
    SubQuestion,
    build_plan,
    plan_from_gap,
    plan_from_note_challenge,
)
from .persist import TREE_RELATION, load_tree, persist_tree
from .approval import (
    PlanNotApproved,
    approve_plan,
    assert_launchable,
    is_plan_launchable,
    load_approval,
)

__all__ = [
    "ApprovalState", "PlanNode", "PlanTree",
    "MAX_BRANCHES", "FocusVerdict", "focus_check", "is_over_broad",
    "DEFAULT_MAX_DEPTH", "Decomposer", "DispatchDecomposer", "PlanReport",
    "SubQuestion", "build_plan", "plan_from_gap", "plan_from_note_challenge",
    "TREE_RELATION", "load_tree", "persist_tree",
    "PlanNotApproved", "approve_plan", "assert_launchable",
    "is_plan_launchable", "load_approval",
]
