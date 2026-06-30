"""Knowledge-graph projection — visualize an artifact's outbound edges.

A born-Antiek artifact carries its user-asserted edges (this document ->
referenced documents, each with a relation kind). This renders them as a
``dep_graph`` widget node so the portable artifact SHOWS its slice of the
knowledge graph, not just a flat textual appendix — directly serving the
"knowledge graph as product" goal. Edges are structural (document ids + a
relation kind), never third-party passage text, so the visualization is
rights-safe by construction.
"""

from __future__ import annotations

from typing import Optional

_SELF = "__self__"


def graph_widget_node(
    edges: list[dict], *, self_label: str = "This document"
) -> Optional[dict]:
    """Build an ``antiek_widget`` (kind=dep_graph) node visualizing the outbound
    edges (this document -> each referenced document), or ``None`` when there are
    no edges to show (so the caller renders no empty graph). The current document
    is the accent-toned root; each ``to_document_id`` is a target node; each edge
    is a root->target arrow. Targets dedupe in first-seen order (deterministic)."""
    refs = [
        e
        for e in (edges or [])
        if isinstance(e, dict) and e.get("to_document_id")
    ]
    if not refs:
        return None
    nodes: list[dict] = [{"id": _SELF, "label": self_label, "tone": "accent"}]
    seen = {_SELF}
    graph_edges: list[dict] = []
    for edge in refs:
        target = str(edge.get("to_document_id"))
        # Prefer a human title (a citation label — rights-safe) over the raw id.
        label = str(edge.get("to_title") or target)
        if target not in seen:
            nodes.append({"id": target, "label": label})
            seen.add(target)
        graph_edges.append({"from": _SELF, "to": target})
    return {
        "type": "antiek_widget",
        "attrs": {
            "kind": "dep_graph",
            "data": {
                "title": "Knowledge graph",
                "nodes": nodes,
                "edges": graph_edges,
            },
        },
    }


__all__ = ["graph_widget_node"]
