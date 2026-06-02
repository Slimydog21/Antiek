"""DRW SPR-05 M2 — persist the plan tree as graph question nodes.

Each plan node becomes a SPR-01 ``question`` node (via the single-writer
promotion path); the tree structure is stored as ``decomposes_into`` edges
(parent → child) so the tree is reloadable. The root node's metadata carries
the approval state + seed provenance so a separate process (SPR-06's launch)
can read "is this plan launchable?" from the graph alone.

Duplicate sub-questions dedup via SPR-01's content hash (the same text → the
same node), so a circular/duplicate plan collapses to a DAG rather than
looping; reload uses a visited set so that case terminates.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

try:
    from ...graph.insight_question import graph_db_path, promote_question
    from ...graph.ops import insert_edge
    from ...runtime.db_lock import connect_read, connect_write
    from .tree_contract import ApprovalState, PlanNode, PlanTree
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from roles.cascade_planner.tree_contract import (  # type: ignore[no-redef]
        ApprovalState,
        PlanNode,
        PlanTree,
    )
    from runtime.db_lock import connect_read, connect_write  # type: ignore[no-redef]
    from substrate.graph.insight_question import (  # type: ignore[no-redef]
        graph_db_path,
        promote_question,
    )
    from substrate.graph.ops import insert_edge  # type: ignore[no-redef]


# The tree-structure relation (free-form on edges.relation; not part of the
# insight/question promotion vocabulary, so created via insert_edge directly).
# SPR-07 reads this relation to find decomposition structure.
TREE_RELATION = "decomposes_into"


def persist_tree(
    tree: PlanTree,
    *,
    investigation_id: str,
    embedding_provider: Any = None,
    db_path: str | None = None,
    con: Any = None,
) -> str:
    """Persist ``tree`` to the graph; returns the root question node id.
    Stamps approval + seed onto the root node metadata so the gate is
    readable from the graph."""
    owned = con is None
    c = con if con is not None else connect_write(db_path or graph_db_path(), purpose="persist_plan")
    try:
        if owned:
            c.execute("BEGIN")
        try:
            root_meta = {
                "plan_root": True, "seed_kind": tree.seed_kind,
                "seed_provenance": tree.seed_provenance,
                "approval": tree.approval.to_dict(),
            }
            root_id = _persist_node(c, tree.root, investigation_id, embedding_provider, root_meta)
            # promote_question is idempotent (on_conflict='ignore'), so on a
            # RE-persist it does not rewrite an existing root's metadata. The
            # approval state must be authoritative on every persist (an edited
            # plan re-opens the gate), so write the root metadata explicitly.
            _write_node_metadata(c, root_id, tree.root, root_meta)
            tree.root_investigation_id = investigation_id
            _persist_children(c, tree.root, investigation_id, embedding_provider)
            if owned:
                c.execute("COMMIT")
        except Exception:
            if owned:
                c.execute("ROLLBACK")
            raise
        return root_id
    finally:
        if owned:
            c.close()


def _node_metadata(node: PlanNode, extra_meta=None) -> dict:
    meta = {"focus_boundary": node.focus_boundary, "rationale": node.rationale,
            "budget_usd": node.budget_usd, "max_depth": node.max_depth,
            "plan_local_id": node.local_id}
    if extra_meta:
        meta.update(extra_meta)
    return meta


def _write_node_metadata(c, node_id: str, node: PlanNode, extra_meta=None) -> None:
    """Authoritatively (re)write a node's metadata — used for the root so the
    approval state reflects the current tree on every persist."""
    c.execute("UPDATE nodes SET metadata = ? WHERE node_id = ?",
              [json.dumps(_node_metadata(node, extra_meta), default=str), node_id])


def _persist_node(c, node: PlanNode, investigation_id, provider, extra_meta=None) -> str:
    meta = {"focus_boundary": node.focus_boundary, "rationale": node.rationale,
            "budget_usd": node.budget_usd, "max_depth": node.max_depth,
            "plan_local_id": node.local_id}
    if extra_meta:
        meta.update(extra_meta)
    nid = promote_question(
        text=node.question, investigation_id=investigation_id,
        metadata=meta, embedding_provider=provider, con=c,
    )
    node.graph_node_id = nid
    return nid


def _persist_children(c, parent: PlanNode, investigation_id, provider) -> None:
    for child in parent.children:
        _persist_node(c, child, investigation_id, provider)
        insert_edge(
            c, source_node_id=parent.graph_node_id, target_node_id=child.graph_node_id,
            relation=TREE_RELATION, source_tier=3, extraction_confidence=1.0,
            graph_scope="depth", investigation_id=investigation_id, on_conflict="ignore",
        )
        _persist_children(c, child, investigation_id, provider)


def load_tree(root_node_id: str, *, db_path: str | None = None, con: Any = None) -> PlanTree | None:
    """Reconstruct a PlanTree from the graph by walking ``decomposes_into``
    edges from the root. Terminates on cycles via a visited set."""
    owned = con is None
    c = con if con is not None else connect_read(db_path or graph_db_path())
    try:
        root_row = c.execute(
            "SELECT canonical_label, metadata FROM nodes WHERE node_id = ?", [root_node_id]
        ).fetchone()
        if root_row is None:
            return None
        visited: set[str] = set()
        root = _load_node(c, root_node_id, root_row[0], root_row[1], visited)
        meta = _json(root_row[1])
        approval = ApprovalState.from_dict(meta.get("approval", {}))
        return PlanTree(root=root, seed_kind=meta.get("seed_kind", "problem"),
                        seed_provenance=meta.get("seed_provenance", {}),
                        approval=approval)
    finally:
        if owned:
            c.close()


def _load_node(c, node_id, label, metadata_json, visited: set) -> PlanNode:
    meta = _json(metadata_json)
    node = PlanNode(
        question=label, rationale=meta.get("rationale", ""),
        focus_boundary=meta.get("focus_boundary", ""),
        budget_usd=meta.get("budget_usd"), max_depth=meta.get("max_depth"),
        local_id=meta.get("plan_local_id") or ("pn-" + node_id[:10]),
        graph_node_id=node_id,
    )
    if node_id in visited:
        return node
    visited.add(node_id)
    children = c.execute(
        "SELECT n.node_id, n.canonical_label, n.metadata FROM edges e "
        "JOIN nodes n ON e.target_node_id = n.node_id "
        "WHERE e.source_node_id = ? AND e.relation = ? ORDER BY n.node_id",
        [node_id, TREE_RELATION],
    ).fetchall()
    for cid, clabel, cmeta in children:
        node.children.append(_load_node(c, cid, clabel, cmeta, visited))
    return node


def _json(s) -> dict:
    if not s:
        return {}
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return {}
