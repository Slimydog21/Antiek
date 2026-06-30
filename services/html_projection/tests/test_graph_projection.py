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


def test_to_title_is_preferred_as_the_node_label():
    node = graph_widget_node(
        [{"kind": "cites", "to_document_id": "doc-A", "to_title": "On Liberty"}]
    )
    labels = [n["label"] for n in node["attrs"]["data"]["nodes"]]
    assert "On Liberty" in labels and "doc-A" not in labels  # title beats raw id


def test_graph_preserves_rights_tone_on_target_nodes():
    node = graph_widget_node(
        [
            {
                "kind": "cites",
                "to_document_id": "doc-A",
                "to_title": "On Liberty",
                "tone": "success",
            },
            {
                "kind": "cites",
                "to_document_id": "doc-B",
                "to_title": "A PG Essay",
                "tone": "warning",
            },
        ]
    )
    nodes = {n["id"]: n for n in node["attrs"]["data"]["nodes"]}
    assert nodes["doc-A"]["tone"] == "success"
    assert nodes["doc-B"]["tone"] == "warning"


def test_synthesis_artifact_shows_knowledge_graph_rights_safe():
    from services.html_projection.adapters.synthesis import (
        Claim,
        SourceRef,
        SynthesisExport,
        adapt_synthesis,
    )

    # A non-servable source: its title is a citation (SHOWN in the graph), its
    # passage is withheld.
    src = SourceRef(
        document_id="doc-PG",
        document_title="A PG Essay",
        content_class="personal_reading",
        ip_holder_id="pg",
        locator="p.3",
        chunk_text="SECRET PASSAGE",
    )
    dm = adapt_synthesis(
        SynthesisExport(
            synthesis_id="s",
            target_question="Q?",
            recommendation="proceed",
            claims=[Claim("A claim", [src])],
        )
    )
    assert any(e["to_document_id"] == "doc-PG" for e in dm["edges"])  # edge populated
    html = render(dm, RenderContext())
    assert "Knowledge graph" in html and "A PG Essay" in html  # cited title shown
    assert "SECRET PASSAGE" not in html  # passage withheld even though cited
    assert_script_free(html)


def test_synthesis_edges_carry_rights_tone():
    from services.html_projection.adapters.synthesis import (
        Claim,
        SourceRef,
        SynthesisExport,
        adapt_synthesis,
    )

    dm = adapt_synthesis(
        SynthesisExport(
            synthesis_id="s",
            target_question="Q?",
            claims=[
                Claim(
                    "A claim",
                    [
                        SourceRef(
                            document_id="doc-PD",
                            document_title="On Liberty",
                            content_class="public_domain",
                            ip_holder_id=None,
                            chunk_text="PUBLIC TEXT",
                        ),
                        SourceRef(
                            document_id="doc-PR",
                            document_title="A PG Essay",
                            content_class="personal_reading",
                            ip_holder_id="pg",
                            chunk_text="SECRET",
                        ),
                    ],
                )
            ],
        )
    )
    tones = {edge["to_document_id"]: edge["tone"] for edge in dm["edges"]}
    assert tones == {"doc-PD": "success", "doc-PR": "warning"}


def test_deliverable_edges_carry_rights_tone():
    from services.html_projection.adapters.deliverable import (
        DeliverableBlock,
        DeliverableExport,
        DeliverableSection,
        adapt_deliverable,
    )

    dm = adapt_deliverable(
        DeliverableExport(
            title="Memo",
            sections=[
                DeliverableSection(
                    heading="Findings",
                    blocks=[
                        DeliverableBlock(
                            "claim",
                            "PUBLIC TEXT",
                            content_class="public_domain",
                            source_title="On Liberty",
                        ),
                        DeliverableBlock(
                            "claim",
                            "SECRET",
                            content_class="personal_reading",
                            ip_holder_id="pg",
                            source_title="A PG Essay",
                        ),
                    ],
                )
            ],
        )
    )
    tones = {edge["to_document_id"]: edge["tone"] for edge in dm["edges"]}
    assert tones == {"On Liberty": "success", "A PG Essay": "warning"}


def test_notebook_export_edges_carry_rights_tone():
    from services.html_projection.adapters.notebook import ResolvedRefData
    from services.html_projection.adapters.notebook_export import (
        adapt_notebook_for_export,
    )

    dm = adapt_notebook_for_export(
        {"type": "doc", "content": []},
        title="Notebook",
        resolved_refs={
            "c1": ResolvedRefData(
                kind="claim",
                content_class="public_domain",
                ip_holder_id=None,
                title="On Liberty",
                payload={"statement": "PUBLIC TEXT"},
            ),
            "n1": ResolvedRefData(
                kind="note",
                content_class="personal_reading",
                ip_holder_id="pg",
                title="A PG Essay",
                payload={"body": "SECRET"},
            ),
        },
    )
    tones = {edge["to_document_id"]: edge["tone"] for edge in dm["edges"]}
    assert tones == {"On Liberty": "success", "A PG Essay": "warning"}
