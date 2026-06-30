"""Knowledge-graph projection: outbound edges -> a gate-clean dep_graph widget."""

from __future__ import annotations

from services.html_projection.context import RenderContext
from services.html_projection.gate import assert_script_free
from services.html_projection.graph_projection import graph_widget_node
from services.html_projection.renderer import render


def _doc(nodes, edges):
    return {"content": nodes, "title": "t", "edges": edges}


EDGES = [
    {"kind": "supports", "to_document_id": "doc-A"},
    {"kind": "refutes", "to_document_id": "doc-B"},
    {"kind": "cites", "to_document_id": "doc-A"},  # duplicate target
]


def test_no_edges_returns_none():
    assert graph_widget_node([]) is None
    assert graph_widget_node([{"kind": "x"}]) is None  # no to_document_id


def test_builds_dep_graph_node_with_self_root_and_deduped_targets():
    node = graph_widget_node(EDGES, self_label="My synthesis")
    assert node["type"] == "antiek_widget"
    data = node["attrs"]["data"]
    assert node["attrs"]["kind"] == "dep_graph"
    ids = [n["id"] for n in data["nodes"]]
    assert ids[0] == "__self__"  # root first
    assert ids.count("doc-A") == 1 and "doc-B" in ids  # deduped targets
    assert len(data["edges"]) == 3  # an edge per ref (incl the duplicate)
    assert data["nodes"][0]["label"] == "My synthesis"


def test_graph_widget_renders_gate_clean_in_a_document():
    node = graph_widget_node(EDGES)
    html = render(_doc([node], []), RenderContext())
    assert "doc-A" in html and "doc-B" in html
    assert "Knowledge graph" in html
    assert_script_free(html)
