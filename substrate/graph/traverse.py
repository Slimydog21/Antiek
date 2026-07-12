"""Graph traversal — recursive-CTE algorithms over edges.

Ported from Researchmaxx ``traverse.py`` (558 LOC source → ~310 LOC
here after removing the CLI, the ``as_of`` temporal filter
(graph_at_time not migrated), and a few diagnostic prints).

Four algorithms (spec §5.1–§5.4):

| Algorithm           | Use case                                          |
|---------------------|---------------------------------------------------|
| shortest_path       | Single shortest path source → target              |
| top_n_paths         | Top-N simple paths by depth + confidence         |
| dfs_with_depth      | All paths within depth limit (deepest preferred)  |
| bfs_semantic_stop   | Two-phase BFS through a named waypoint            |

Plus shared utilities: ``resolve_node`` (ID or fuzzy label), degree
normalization helpers, and the ``traverse`` dispatcher that picks the
right algorithm by name.

What's deferred:

- ``as_of`` temporal filter — depends on ``graph_at_time`` which
  hasn't migrated. The signature reserves the parameter slot for a
  future turn but doesn't apply it.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Any, Literal

try:
    from ...constants import (
        TRAVERSAL_DFS_DEPTH,
        TRAVERSAL_MAX_DEPTH,
        TRAVERSAL_TOP_N_PATHS,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import (  # type: ignore[no-redef]
        TRAVERSAL_DFS_DEPTH,
        TRAVERSAL_MAX_DEPTH,
        TRAVERSAL_TOP_N_PATHS,
    )


TraversalAlgorithm = Literal["shortest_path", "top_n", "dfs", "bfs_semantic_stop"]
TraversalScope = Literal["depth", "cross_domain", "constraint", "all"]


# ---------------------------------------------------------------------------
# Resolution + scope helpers
# ---------------------------------------------------------------------------


def _owner_filter(alias: str, owner_user_id: str | None) -> tuple[str, list[str]]:
    if owner_user_id is None:
        return f"{alias}.owner_user_id IS NULL", []
    return f"({alias}.owner_user_id IS NULL OR {alias}.owner_user_id = ?)", [owner_user_id]


def _nodes_visible(con: Any, node_ids: tuple[str, ...], owner_user_id: str | None) -> bool:
    owner_sql, owner_params = _owner_filter("n", owner_user_id)
    placeholders = ",".join("?" for _ in node_ids)
    count = con.execute(
        f"SELECT count(*) FROM nodes n WHERE node_id IN ({placeholders}) AND {owner_sql}",
        [*node_ids, *owner_params],
    ).fetchone()[0]
    return bool(count == len(set(node_ids)))


def resolve_node(
    con: Any, label: str, scope: str | None = None, owner_user_id: str | None = None
) -> str:
    """Resolve a node by ID exact match → canonical_label exact match →
    fuzzy ILIKE. Raises ValueError if nothing matches.

    Production callers should pass already-resolved node_ids when they
    have them; the fuzzy path is for the wrestling UI's "show me the
    PsiQuantum node" affordance."""
    owner_sql, owner_params = _owner_filter("n", owner_user_id)
    row = con.execute(
        f"SELECT node_id FROM nodes n WHERE node_id = ? AND {owner_sql}",
        [label, *owner_params],
    ).fetchone()
    if row:
        return row[0]

    row = con.execute(
        f"SELECT node_id FROM nodes n WHERE canonical_label = ? AND {owner_sql}",
        [label, *owner_params],
    ).fetchone()
    if row:
        return row[0]

    query = f"SELECT node_id, canonical_label FROM nodes n WHERE canonical_label ILIKE ? AND {owner_sql}"
    params: list[Any] = [f"%{label}%", *owner_params]
    if scope and scope != "all":
        query += " AND graph_scope = ?"
        params.append(scope)
    query += " LIMIT 1"

    row = con.execute(query, params).fetchone()
    if row:
        return row[0]
    raise ValueError(f"node not found: {label!r}")


def _scope_filter(scope: str) -> str:
    """SQL fragment for the ``e.graph_scope`` filter. Returns ``"1=1"``
    when scope is ``"all"`` so the recursive CTE doesn't filter at all."""
    if scope == "all":
        return "1=1"
    return f"e.graph_scope = '{scope}'"


# ---------------------------------------------------------------------------
# Degree normalization (used by ``normalize_degree=True`` callers)
# ---------------------------------------------------------------------------


def degree_normalization_weight(con: Any, node_id: str, default_degree: int = 1) -> float:
    """1 / log(max(degree, 2)) — used to discount hub-nodes when
    scoring analogical paths. Spec §5.5."""
    row = con.execute(
        "SELECT COALESCE(degree_cached, ?) FROM nodes WHERE node_id = ?",
        [int(default_degree), node_id],
    ).fetchone()
    if row is None:
        return 1.0
    d = max(int(row[0]), 2)  # avoid log(1) = 0
    return 1.0 / math.log(d)


def _compute_path_degree_score(con: Any, path: dict) -> float:
    """Geometric mean of per-node degree weights."""
    nodes = path.get("path_nodes", [])
    if not nodes:
        return 1.0
    weights = [degree_normalization_weight(con, nid) for nid in nodes]
    product = 1.0
    for w in weights:
        product *= w
    return round(product ** (1.0 / len(weights)), 4)


def _flag_hub_concerns(path: dict, threshold: float = 0.6) -> list[str]:
    score = path.get("degree_normalized_score", 1.0)
    if score < threshold:
        return [
            f"Path dominated by hub nodes (degree_score={score}); analogical "
            "value may be low"
        ]
    return []


def _format_path(row: Any) -> dict:
    """Format a raw recursive-CTE row into the dict shape every algorithm
    returns. ``path_nodes`` + ``path_relations`` are DuckDB list types
    that already round-trip as Python lists."""
    nodes = row[0] if isinstance(row[0], list) else list(row[0])
    relations = row[1] if isinstance(row[1], list) else list(row[1])
    return {
        "path_nodes": nodes,
        "path_relations": relations,
        "depth": int(row[2]),
        "avg_confidence": round(float(row[3]), 3),
    }


def _resolve_labels(
    con: Any, node_ids: list[str], owner_user_id: str | None = None
) -> list[str]:
    if not node_ids:
        return []
    placeholders = ",".join(["?"] * len(node_ids))
    owner_sql, owner_params = _owner_filter("n", owner_user_id)
    rows = con.execute(
        f"SELECT node_id, canonical_label FROM nodes n WHERE node_id IN ({placeholders}) AND {owner_sql}",
        [*node_ids, *owner_params],
    ).fetchall()
    label_map = {r[0]: r[1] for r in rows}
    return [label_map.get(nid, nid) for nid in node_ids]


# ---------------------------------------------------------------------------
# Algorithm 1: Shortest simple path (BFS)
# ---------------------------------------------------------------------------


def shortest_path(
    con: Any,
    source_id: str,
    target_id: str,
    *,
    max_depth: int = TRAVERSAL_MAX_DEPTH,
    scope: str = "cross_domain",
    min_confidence: float = 0.0,
    normalize_degree: bool = False,
    owner_user_id: str | None = None,
) -> list[dict]:
    if not _nodes_visible(con, (source_id, target_id), owner_user_id):
        return []
    scope_filter = _scope_filter(scope)
    visible_sql, visible_params = _owner_filter("nv", owner_user_id)
    row = con.execute(
        f"""
        WITH RECURSIVE paths AS (
            SELECT
                e.source_node_id, e.target_node_id, e.relation,
                1 AS depth,
                [e.source_node_id, e.target_node_id] AS path_nodes,
                [e.relation] AS path_relations,
                e.extraction_confidence AS confidence
            FROM edges e
            WHERE e.source_node_id = ?
              AND {scope_filter}
              AND e.extraction_confidence >= ?
              AND EXISTS (SELECT 1 FROM nodes nv WHERE nv.node_id=e.target_node_id AND {visible_sql})
            UNION ALL
            SELECT
                e.source_node_id, e.target_node_id, e.relation,
                p.depth + 1,
                list_append(p.path_nodes, e.target_node_id),
                list_append(p.path_relations, e.relation),
                (p.confidence + e.extraction_confidence) / 2.0
            FROM edges e
            JOIN paths p ON e.source_node_id = p.target_node_id
            WHERE p.depth < ?
              AND {scope_filter}
              AND e.extraction_confidence >= ?
              AND NOT list_contains(p.path_nodes, e.target_node_id)
              AND e.target_node_id <> p.source_node_id
              AND EXISTS (SELECT 1 FROM nodes nv WHERE nv.node_id=e.target_node_id AND {visible_sql})
        )
        SELECT path_nodes, path_relations, depth, confidence
        FROM paths
        WHERE target_node_id = ?
        ORDER BY depth ASC
        LIMIT 1
        """,
        [source_id, min_confidence, *visible_params, max_depth, min_confidence, *visible_params, target_id],
    ).fetchone()
    if row is None:
        return []
    path = _format_path(row)
    if normalize_degree:
        path["degree_normalized_score"] = _compute_path_degree_score(con, path)
    return [path]


# ---------------------------------------------------------------------------
# Algorithm 2: Top-N shortest simple paths
# ---------------------------------------------------------------------------


def top_n_paths(
    con: Any,
    source_id: str,
    target_id: str,
    *,
    n: int = TRAVERSAL_TOP_N_PATHS,
    max_depth: int = TRAVERSAL_MAX_DEPTH,
    scope: str = "cross_domain",
    min_confidence: float = 0.0,
    normalize_degree: bool = False,
    owner_user_id: str | None = None,
) -> list[dict]:
    if not _nodes_visible(con, (source_id, target_id), owner_user_id):
        return []
    scope_filter = _scope_filter(scope)
    visible_sql, visible_params = _owner_filter("nv", owner_user_id)
    rows = con.execute(
        f"""
        WITH RECURSIVE paths AS (
            SELECT
                e.source_node_id, e.target_node_id, e.relation,
                1 AS depth,
                [e.source_node_id, e.target_node_id] AS path_nodes,
                [e.relation] AS path_relations,
                e.extraction_confidence AS confidence
            FROM edges e
            WHERE e.source_node_id = ?
              AND {scope_filter}
              AND e.extraction_confidence >= ?
              AND EXISTS (SELECT 1 FROM nodes nv WHERE nv.node_id=e.target_node_id AND {visible_sql})
            UNION ALL
            SELECT
                e.source_node_id, e.target_node_id, e.relation,
                p.depth + 1,
                list_append(p.path_nodes, e.target_node_id),
                list_append(p.path_relations, e.relation),
                (p.confidence + e.extraction_confidence) / 2.0
            FROM edges e
            JOIN paths p ON e.source_node_id = p.target_node_id
            WHERE p.depth < ?
              AND {scope_filter}
              AND e.extraction_confidence >= ?
              AND NOT list_contains(p.path_nodes, e.target_node_id)
              AND EXISTS (SELECT 1 FROM nodes nv WHERE nv.node_id=e.target_node_id AND {visible_sql})
        )
        SELECT path_nodes, path_relations, depth, confidence
        FROM paths
        WHERE target_node_id = ?
        ORDER BY depth ASC, confidence DESC
        LIMIT ?
        """,
        [source_id, min_confidence, *visible_params, max_depth, min_confidence, *visible_params, target_id, int(n)],
    ).fetchall()
    paths = [_format_path(r) for r in rows]
    if normalize_degree:
        for p in paths:
            p["degree_normalized_score"] = _compute_path_degree_score(con, p)
    return paths


# ---------------------------------------------------------------------------
# Algorithm 3: DFS with depth limit
# ---------------------------------------------------------------------------


def dfs_with_depth(
    con: Any,
    source_id: str,
    target_id: str,
    *,
    depth_limit: int = TRAVERSAL_DFS_DEPTH,
    scope: str = "cross_domain",
    min_confidence: float = 0.0,
    normalize_degree: bool = False,
    owner_user_id: str | None = None,
) -> list[dict]:
    if not _nodes_visible(con, (source_id, target_id), owner_user_id):
        return []
    scope_filter = _scope_filter(scope)
    visible_sql, visible_params = _owner_filter("nv", owner_user_id)
    rows = con.execute(
        f"""
        WITH RECURSIVE paths AS (
            SELECT
                e.source_node_id, e.target_node_id, e.relation,
                1 AS depth,
                [e.source_node_id, e.target_node_id] AS path_nodes,
                [e.relation] AS path_relations,
                e.extraction_confidence AS confidence
            FROM edges e
            WHERE e.source_node_id = ?
              AND {scope_filter}
              AND e.extraction_confidence >= ?
              AND EXISTS (SELECT 1 FROM nodes nv WHERE nv.node_id=e.target_node_id AND {visible_sql})
            UNION ALL
            SELECT
                e.source_node_id, e.target_node_id, e.relation,
                p.depth + 1,
                list_append(p.path_nodes, e.target_node_id),
                list_append(p.path_relations, e.relation),
                (p.confidence + e.extraction_confidence) / 2.0
            FROM edges e
            JOIN paths p ON e.source_node_id = p.target_node_id
            WHERE p.depth < ?
              AND {scope_filter}
              AND e.extraction_confidence >= ?
              AND NOT list_contains(p.path_nodes, e.target_node_id)
              AND EXISTS (SELECT 1 FROM nodes nv WHERE nv.node_id=e.target_node_id AND {visible_sql})
        )
        SELECT path_nodes, path_relations, depth, confidence
        FROM paths
        WHERE target_node_id = ?
        ORDER BY depth DESC, confidence DESC
        LIMIT 10
        """,
        [source_id, min_confidence, *visible_params, int(depth_limit), min_confidence, *visible_params, target_id],
    ).fetchall()
    paths = [_format_path(r) for r in rows]
    if normalize_degree:
        for p in paths:
            p["degree_normalized_score"] = _compute_path_degree_score(con, p)
    return paths


# ---------------------------------------------------------------------------
# Algorithm 4: BFS with semantic stop (two-phase: source→waypoint→target)
# ---------------------------------------------------------------------------


def bfs_semantic_stop(
    con: Any,
    source_id: str,
    target_id: str,
    waypoint_label: str,
    *,
    max_depth: int = TRAVERSAL_MAX_DEPTH,
    scope: str = "cross_domain",
    min_confidence: float = 0.0,
    normalize_degree: bool = False,
    owner_user_id: str | None = None,
) -> list[dict]:
    """Two-phase BFS through a constraint waypoint. Useful when the
    cross-domain analogy MUST flow through a named intermediate
    concept (e.g. "must touch 'photon coherence' on the way from
    PsiQuantum to error-correction-threshold")."""
    waypoint_id = resolve_node(con, waypoint_label, scope, owner_user_id)
    half = max(1, int(max_depth) // 2)

    phase1 = top_n_paths(
        con, source_id, waypoint_id,
        n=3, max_depth=half, scope=scope,
        min_confidence=min_confidence, normalize_degree=False,
        owner_user_id=owner_user_id,
    )
    if not phase1:
        return []

    all_paths: list[dict] = []
    for p1 in phase1:
        phase2 = top_n_paths(
            con, waypoint_id, target_id,
            n=3, max_depth=half, scope=scope,
            min_confidence=min_confidence, normalize_degree=False,
            owner_user_id=owner_user_id,
        )
        for p2 in phase2:
            full_nodes = p1["path_nodes"] + p2["path_nodes"][1:]
            full_rels = p1["path_relations"] + p2["path_relations"]
            full_depth = p1["depth"] + p2["depth"]
            full_conf = (p1["avg_confidence"] + p2["avg_confidence"]) / 2.0
            path: dict[str, Any] = {
                "path_nodes": full_nodes,
                "path_relations": full_rels,
                "depth": full_depth,
                "avg_confidence": round(float(full_conf), 3),
                "waypoint": waypoint_label,
            }
            if normalize_degree:
                path["degree_normalized_score"] = _compute_path_degree_score(con, path)
            all_paths.append(path)
    return all_paths


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def traverse(
    con: Any,
    *,
    source: str,
    target: str,
    algorithm: TraversalAlgorithm = "top_n",
    n: int = TRAVERSAL_TOP_N_PATHS,
    depth: int = TRAVERSAL_MAX_DEPTH,
    waypoint: str | None = None,
    scope: TraversalScope = "cross_domain",
    min_confidence: float = 0.0,
    normalize_degree: bool = True,
    owner_user_id: str | None = None,
) -> dict:
    """Execute one traversal. Resolves ``source`` and ``target`` (by id
    or fuzzy label) before dispatching. Returns a dict shaped to match
    the Researchmaxx convention so downstream consumers don't need
    adapter code."""
    source_id = resolve_node(con, source, scope, owner_user_id)
    target_id = resolve_node(con, target, scope, owner_user_id)
    source_label = con.execute(
        "SELECT canonical_label FROM nodes WHERE node_id = ?", [source_id]
    ).fetchone()[0]
    target_label = con.execute(
        "SELECT canonical_label FROM nodes WHERE node_id = ?", [target_id]
    ).fetchone()[0]

    if algorithm == "shortest_path":
        paths = shortest_path(
            con, source_id, target_id,
            max_depth=depth, scope=scope,
            min_confidence=min_confidence,
            normalize_degree=normalize_degree,
            owner_user_id=owner_user_id,
        )
    elif algorithm == "top_n":
        paths = top_n_paths(
            con, source_id, target_id,
            n=n, max_depth=depth, scope=scope,
            min_confidence=min_confidence,
            normalize_degree=normalize_degree,
            owner_user_id=owner_user_id,
        )
    elif algorithm == "dfs":
        paths = dfs_with_depth(
            con, source_id, target_id,
            depth_limit=depth, scope=scope,
            min_confidence=min_confidence,
            normalize_degree=normalize_degree,
            owner_user_id=owner_user_id,
        )
    elif algorithm == "bfs_semantic_stop":
        if not waypoint:
            raise ValueError("waypoint required for bfs_semantic_stop")
        paths = bfs_semantic_stop(
            con, source_id, target_id, waypoint,
            max_depth=depth, scope=scope,
            min_confidence=min_confidence,
            normalize_degree=normalize_degree,
            owner_user_id=owner_user_id,
        )
    else:  # pragma: no cover — Literal exhausted
        raise ValueError(f"unknown algorithm: {algorithm!r}")

    for path in paths:
        if "node_labels" not in path:
            path["node_labels"] = _resolve_labels(con, path["path_nodes"], owner_user_id)
        if normalize_degree:
            path["hub_concerns"] = _flag_hub_concerns(path)

    return {
        "source": {"id": source_id, "label": source_label},
        "target": {"id": target_id, "label": target_label},
        "algorithm": algorithm,
        "scope": scope,
        "degree_normalization": normalize_degree,
        "path_count": len(paths),
        "paths": paths,
    }
