"""Render the editable plan tree to self-contained HTML (visible plan tree).

Closes the competitive gap from
``sprint-briefs/deep-research-quality-competitive-spec.md``: Antiek builds the
research-plan decomposition in the backend (``tree_contract.PlanTree``) but the
operator could not SEE it as a navigable tree before approving/launching. This
module is the pure renderer that turns a ``PlanTree`` into a single
self-contained HTML document the operator reviews and edits — the glass-box
control that is the product's differentiator (``tree_contract`` docstring:
"a tree the user edits and approves before anything launches").

**Native HTML collapse, no JavaScript.** Each sub-question is a
``<details><summary>`` block — collapsible by the browser's own semantics, no
JS dependency, fully controllable by coding agents (the operator's HTML vision,
ask #6). Deeply nested trees stay navigable without a frontend framework.

**Pure** — no I/O, no network. Takes a ``PlanTree`` (the on-main data model),
returns a string. Every interpolated value is ``html.escape``d — the questions
and rationales are LLM-produced (untrusted); the renderer never passes them
through raw. The structural tags are static literals, not interpolated.

**Approval state is prominent** — a banner shows draft/approved + launchable,
so the operator never confuses an un-approved plan for a launched investigation
(the approval gate's whole purpose, per ``ApprovalState.is_launchable``).

**Provenance is real** — the seed kind (problem / gap / note_challenge) and the
root investigation id appear in the footer, so the operator can trace why this
plan exists. Empty optionals are shown honestly (``&mdash;``), never invented.
"""

from __future__ import annotations

import html

from roles.cascade_planner.tree_contract import PlanNode, PlanTree

_PAGE_CSS = """
:root { --stone-900:#1c1917; --stone-600:#57534e; --stone-200:#e7e5e4; --stone-50:#fafaf9;
  --amber-50:#fffbeb; --blue-700:#1d4ed8; --green-700:#15803d; --amber-700:#b45309; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.55; color: var(--stone-900); background: var(--stone-50); margin: 0; padding: 24px; }
main { max-width: 760px; margin: 0 auto; }
h1 { font-family: Charter, Georgia, serif; font-size: 1.7rem; }
.kicker { color: var(--stone-600); font-size: 0.85rem; }
.banner { padding: 12px 16px; border-radius: 6px; margin: 16px 0; font-weight: 600; }
.banner.draft { background: var(--amber-50); border: 1px solid var(--amber-700); color: var(--amber-700); }
.banner.approved { background: #f0fdf4; border: 1px solid var(--green-700); color: var(--green-700); }
details { border: 1px solid var(--stone-200); background: #fff; border-radius: 6px;
  margin: 8px 0; padding: 8px 14px; }
details > summary { cursor: pointer; font-weight: 600; }
details[open] > summary { margin-bottom: 8px; }
.node-body { padding: 6px 0 6px 8px; border-left: 3px solid var(--blue-700); margin: 6px 0; }
.field { margin: 4px 0; }
.field .label { color: var(--stone-600); font-size: 0.8rem; text-transform: uppercase;
  letter-spacing: 0.04em; }
.tag { font-size: 0.75rem; color: var(--stone-600); }
.leaf { font-size: 0.75rem; color: var(--blue-700); font-weight: 600; }
.empty { color: var(--stone-600); font-style: italic; }
footer { margin-top: 32px; font-size: 0.8rem; color: var(--stone-600); }
"""


def _esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def _render_node(node: PlanNode, depth: int) -> str:
    """Render one plan node as a collapsible <details> block (recursive).

    ``depth`` governs whether the root opens by default (depth 0 = open) so the
    operator sees the full decomposition immediately; deeper levels start
    collapsed to keep large trees navigable.
    """
    open_attr = " open" if depth == 0 else ""
    leaf_tag = '<span class="leaf">[leaf]</span>' if node.is_leaf else ""
    parts = [
        f'<details{open_attr}>',
        f'<summary>{_esc(node.question)} {leaf_tag}</summary>',
        '<div class="node-body">',
    ]

    if node.rationale.strip():
        parts.append(
            f'<div class="field"><span class="label">Rationale</span>'
            f"<p>{_esc(node.rationale)}</p></div>"
        )
    else:
        parts.append(
            '<div class="field"><span class="label">Rationale</span>'
            '<p class="empty">(none)</p></div>'
        )

    if node.focus_boundary.strip():
        parts.append(
            f'<div class="field"><span class="label">Focus boundary</span>'
            f"<p>{_esc(node.focus_boundary)}</p></div>"
        )

    # Budget + depth — honest about None (not invented).
    budget_disp = (
        f"${node.budget_usd:.2f}" if node.budget_usd is not None else "&mdash;"
    )
    depth_disp = str(node.max_depth) if node.max_depth is not None else "&mdash;"
    parts.append(
        f'<p class="tag">budget {budget_disp} &middot; max depth {depth_disp}'
        f" &middot; node {_esc(node.local_id)}</p>"
    )

    if node.children:
        parts.append('<div class="children">')
        for child in node.children:
            parts.append(_render_node(child, depth + 1))
        parts.append("</div>")

    parts.append("</div></details>")
    return "".join(parts)


def render_plan_tree_html(tree: PlanTree) -> str:
    """Render a PlanTree to a single self-contained HTML document.

    Pure: no I/O. The root question is the title; sub-questions nest as
    collapsible ``<details>`` blocks; the approval state is a prominent banner;
    provenance (seed kind + root investigation) is in the footer. Every
    interpolated value is escaped.
    """
    if tree.root is None:
        raise ValueError("PlanTree.root must not be None")

    approval = tree.approval
    if approval.state == "approved":
        banner = (
            '<div class="banner approved">APPROVED &mdash; launchable '
            f"(plan_version {_esc(approval.plan_version)})</div>"
        )
    else:
        banner = (
            '<div class="banner draft">DRAFT &mdash; not launchable until approved '
            f"(plan_version {_esc(approval.plan_version)})</div>"
        )

    leaf_count = sum(1 for _ in tree.root.iter_leaves())
    node_count = sum(1 for _ in tree.root.iter_all())

    root_inv = (
        _esc(tree.root_investigation_id)
        if tree.root_investigation_id
        else "&mdash;"
    )

    tree_html = _render_node(tree.root, 0)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Research plan &mdash; {_esc(tree.root.question)}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<main>
<p class="kicker">Research plan tree &middot; editable &middot; glass-box control</p>
{banner}
<h1>{_esc(tree.root.question)}</h1>
<p class="kicker">{node_count} node(s) &middot; {leaf_count} leaf question(s) &middot; seed: {_esc(tree.seed_kind)}</p>
{tree_html}
<footer>seed_kind {_esc(tree.seed_kind)} &middot; root_investigation_id {root_inv}
&middot; plan_version {_esc(approval.plan_version)} &middot; state {_esc(approval.state)}</footer>
</main>
</body>
</html>
"""


__all__ = ["render_plan_tree_html"]
