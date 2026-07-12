"""Plan-tree HTML renderer — contract tests.

Pins the visible-plan-tree renderer (competitive gap). Pure: takes a PlanTree,
returns escaped self-contained HTML. No I/O.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402

from roles.cascade_planner.render_html import render_plan_tree_html  # noqa: E402
from roles.cascade_planner.tree_contract import (  # noqa: E402
    ApprovalState,
    PlanNode,
    PlanTree,
)


def _tree(
    *,
    root_question: str = "How does retrieval-augmented generation reduce hallucination?",
    children: list[PlanNode] | None = None,
    approval_state: str = "draft",
    seed_kind: str = "problem",
    root_investigation_id: str | None = None,
) -> PlanTree:
    root = PlanNode(question=root_question, children=children or [])
    return PlanTree(
        root=root,
        seed_kind=seed_kind,
        approval=ApprovalState(state=approval_state),
        root_investigation_id=root_investigation_id,
    )


# --- structure: root question as title, tree present ---


def test_root_question_is_title() -> None:
    html_out = render_plan_tree_html(_tree())

    assert "<h1>" in html_out
    assert "How does retrieval-augmented generation reduce hallucination?" in html_out


def test_subquestions_render_as_collapsible_details() -> None:
    children = [
        PlanNode(question="What is the grounding mechanism?", rationale="core mechanism"),
        PlanNode(question="Does it survive distribution shift?"),
    ]
    html_out = render_plan_tree_html(_tree(children=children))

    assert "What is the grounding mechanism?" in html_out
    assert "Does it survive distribution shift?" in html_out
    assert html_out.count("<details") >= 3  # root + 2 children


def test_root_details_open_by_default() -> None:
    html_out = render_plan_tree_html(_tree())

    # Root <details> is open so the operator sees the decomposition immediately.
    assert "<details open>" in html_out


def test_deep_nodes_start_collapsed() -> None:
    deep = PlanNode(
        question="root",
        children=[PlanNode(question="child", children=[PlanNode(question="grandchild")])],
    )
    tree = PlanTree(root=deep)
    html_out = render_plan_tree_html(tree)

    # Only ONE <details open> (the root); grandchildren are collapsed.
    assert html_out.count("<details open>") == 1


# --- approval banner ---


def test_draft_banner_not_launchable() -> None:
    html_out = render_plan_tree_html(_tree(approval_state="draft"))

    assert "DRAFT" in html_out
    assert "not launchable" in html_out


def test_approved_banner_launchable() -> None:
    html_out = render_plan_tree_html(_tree(approval_state="approved"))

    assert "APPROVED" in html_out
    assert "launchable" in html_out


# --- escaping (untrusted LLM questions/rationales) ---


def test_malicious_question_escaped() -> None:
    malicious = "<script>alert(1)</script>"
    html_out = render_plan_tree_html(_tree(root_question=malicious))

    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out


def test_malicious_rationale_escaped() -> None:
    malicious = '<img src=x onerror="steal()">'
    child = PlanNode(question="safe q", rationale=malicious)
    html_out = render_plan_tree_html(_tree(children=[child]))

    assert 'onerror="steal()"' not in html_out
    assert "&lt;img" in html_out


def test_malicious_focus_boundary_escaped() -> None:
    child = PlanNode(question="q", focus_boundary="<b>bold</b> boundary")
    html_out = render_plan_tree_html(_tree(children=[child]))

    assert "<b>bold</b>" not in html_out


# --- node metadata rendered honestly ---


def test_rationale_rendered_when_present() -> None:
    child = PlanNode(question="q", rationale="because evidence")
    html_out = render_plan_tree_html(_tree(children=[child]))

    assert "because evidence" in html_out
    assert "Rationale" in html_out


def test_empty_rationale_honest_placeholder() -> None:
    child = PlanNode(question="q", rationale="")
    html_out = render_plan_tree_html(_tree(children=[child]))

    assert "(none)" in html_out


def test_budget_rendered_when_set() -> None:
    child = PlanNode(question="q", budget_usd=1.50)
    html_out = render_plan_tree_html(_tree(children=[child]))

    assert "$1.50" in html_out


def test_budget_none_honest_dash() -> None:
    child = PlanNode(question="q")
    html_out = render_plan_tree_html(_tree(children=[child]))

    assert "&mdash;" in html_out  # None budget → dash, never invented


def test_leaf_tag_on_leaf_nodes() -> None:
    leaf = PlanNode(question="leaf q")
    html_out = render_plan_tree_html(_tree(children=[leaf]))

    assert "[leaf]" in html_out


def test_non_leaf_no_leaf_tag() -> None:
    branching = PlanNode(question="branch", children=[PlanNode(question="sub")])
    html_out = render_plan_tree_html(_tree(children=[branching]))

    # The branching node summary should not carry [leaf]; only the deepest sub does.
    assert "[leaf]" in html_out  # the sub is a leaf
    assert html_out.count("[leaf]") == 1


# --- provenance footer ---


def test_provenance_footer_seed_and_investigation() -> None:
    html_out = render_plan_tree_html(
        _tree(seed_kind="gap", root_investigation_id="inv-42")
    )

    assert "inv-42" in html_out
    assert "seed_kind gap" in html_out


def test_provenance_none_investigation_honest() -> None:
    html_out = render_plan_tree_html(_tree(root_investigation_id=None))

    assert "root_investigation_id &mdash;" in html_out  # None → dash


# --- counts ---


def test_node_and_leaf_counts() -> None:
    children = [
        PlanNode(question="a", children=[PlanNode(question="a1"), PlanNode(question="a2")]),
        PlanNode(question="b"),  # leaf
    ]
    html_out = render_plan_tree_html(_tree(children=children))

    # 5 nodes total (root + a + a1 + a2 + b); 3 leaves (a1, a2, b)
    assert "5 node(s)" in html_out
    assert "3 leaf question(s)" in html_out


# --- self-contained + valid structure ---


def test_self_contained_html_document() -> None:
    html_out = render_plan_tree_html(_tree())

    assert html_out.startswith("<!doctype html>")
    assert "</html>" in html_out
    assert "<style>" in html_out  # inline CSS, no external dep


def test_none_root_rejected() -> None:
    tree = PlanTree(root=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="root"):
        render_plan_tree_html(tree)


# --- idempotent ---


def test_idempotent_same_tree_same_html() -> None:
    tree = _tree(children=[PlanNode(question="x", rationale="r")])
    one = render_plan_tree_html(tree)
    two = render_plan_tree_html(tree)

    assert one == two
