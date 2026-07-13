"""SPR-05 M3: synthesis-artifact route — allowed / restricted / mixed / poisoned.

The resolver is mocked so the route logic + the in-path zero-script gate are
exercised without a live graph. The rights filtering itself is proven in
``services/html_projection/tests/test_synthesis_adapter.py``; here we prove the
route wires it correctly and refuses a poisoned render.
"""

from __future__ import annotations

import json

import duckdb
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import synthesis_artifact as mod
from services.html_projection.adapters.synthesis import (
    Claim,
    SourceRef,
    SynthesisExport,
)
from services.html_projection.gate import assert_script_free

SERVABLE = SourceRef(
    document_id="doc-pd",
    document_title="On Liberty",
    content_class="public_domain",
    ip_holder_id=None,
    locator="/read/doc-pd",
    chunk_text="PUBLIC DOMAIN TEXT",
)
PERSONAL = SourceRef(
    document_id="doc-pr",
    document_title="A Paul Graham essay",
    content_class="personal_reading",
    ip_holder_id="pg",
    locator="/read/doc-pr",
    chunk_text="SECRET THIRD PARTY TEXT",
)


def _client() -> TestClient:
    app = FastAPI()
    mod.register_synthesis_artifact_routes(app)
    return TestClient(app)


def _insert_synthesis_fixture(tmp_path, thesis: object) -> str:
    from substrate.graph.schema import init_database_at_path

    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    con = duckdb.connect(db_path)
    try:
        con.execute(
            "INSERT INTO documents "
            "(document_id, title, source_tier, document_type, content_class, ip_holder_id) "
            "VALUES ('doc-cited', 'Cited source', 1, 'paper', 'public_domain', 'holder-a'), "
            "('doc-unrelated', 'Unrelated source', 1, 'paper', 'personal_reading', 'holder-b')"
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
            "VALUES ('chunk-cited', 'doc-cited', 0, 'Exact supporting passage')"
        )
        con.execute(
            "INSERT INTO syntheses "
            "(synthesis_id, target_question, synthesis_timestamp, status, "
            "implicit_recommendation, thesis_text, thesis) "
            "VALUES ('syn-resolve', 'What is supported?', CURRENT_TIMESTAMP, "
            "'passed', 'proceed', 'A broader thesis.', ?)",
            [json.dumps(thesis)],
        )
        con.execute(
            "INSERT INTO synthesis_substrate_manifest (synthesis_id, entity_kind, entity_id) "
            "VALUES ('syn-resolve', 'document', 'doc-unrelated'), "
            "('syn-resolve', 'chunk', 'chunk-cited')"
        )
    finally:
        con.close()
    return db_path


def _delivered_thesis(*, chunk_ids: list[str]) -> dict[str, object]:
    return {
        "thesis_summary": "A broader thesis.",
        "implicit_recommendation": "proceed",
        "thesis_components": [
            {
                "claim": "The cited claim holds.",
                "confidence": "high",
                "supporting_chunk_ids": chunk_ids,
                "supporting_path_indices": [],
                "confidence_basis": "The cited passage states it directly.",
                "effective_source_tier": 1,
                "hedging_required": False,
            }
        ],
        "falsification_conditions": [],
        "execution_risks": [],
        "constraint_compliance": {
            "hard_constraints_satisfied": True,
            "soft_constraints_violated": [],
            "violations_justified": [],
        },
        "reasoning_paths_used": [],
        "conviction_level": 0.8,
        "constraint_loop_status": "passed",
        "constraint_loop_iterations": 1,
    }


def test_resolver_maps_claim_to_exact_manifest_chunk_only(tmp_path):
    db_path = _insert_synthesis_fixture(tmp_path, _delivered_thesis(chunk_ids=["chunk-cited"]))

    export = mod.resolve_synthesis_export("syn-resolve", db_path=db_path)

    assert export is not None
    assert export.thesis_text == "A broader thesis."
    assert [claim.statement for claim in export.claims] == ["The cited claim holds."]
    assert [source.document_id for source in export.claims[0].sources] == ["doc-cited"]
    assert export.claims[0].sources[0].locator == "/read/doc-cited?chunk=chunk-cited"
    assert export.claims[0].sources[0].chunk_text == "Exact supporting passage"
    assert export.attribution_manifest["document_ip_holders"]["doc-cited"] == "holder-a"
    assert "doc-unrelated" not in export.attribution_manifest["document_ip_holders"]


def test_resolver_takedown_override_never_embeds_chunk_text(tmp_path):
    db_path = _insert_synthesis_fixture(tmp_path, _delivered_thesis(chunk_ids=["chunk-cited"]))
    con = duckdb.connect(db_path)
    try:
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES ('doc-cited', TRUE)"
        )
    finally:
        con.close()

    export = mod.resolve_synthesis_export("syn-resolve", db_path=db_path)

    assert export is not None
    assert export.claims[0].sources[0].servable is False
    assert "Exact supporting passage" not in json.dumps(mod.adapt_synthesis(export))


def test_resolver_keeps_unpinned_chunk_citation_unsourced(tmp_path):
    db_path = _insert_synthesis_fixture(
        tmp_path, _delivered_thesis(chunk_ids=["chunk-not-in-manifest"])
    )

    export = mod.resolve_synthesis_export("syn-resolve", db_path=db_path)

    assert export is not None
    assert len(export.claims) == 1
    assert len(export.claims[0].sources) == 1
    assert export.claims[0].sources[0].resolved is False


def test_resolver_mixed_valid_and_unpinned_citations_stays_incomplete(tmp_path):
    db_path = _insert_synthesis_fixture(
        tmp_path,
        _delivered_thesis(chunk_ids=["chunk-cited", "chunk-not-in-manifest"]),
    )

    export = mod.resolve_synthesis_export("syn-resolve", db_path=db_path)

    assert export is not None
    assert [source.resolved for source in export.claims[0].sources] == [True, False]
    doc_model = mod.adapt_synthesis(export)
    assert doc_model["metadata"]["provenance"] == {
        "fully_sourced": 0,
        "total": 1,
        "complete": False,
        "warnings": [],
    }


def test_resolver_malformed_thesis_never_inherits_manifest_sources(tmp_path):
    db_path = _insert_synthesis_fixture(tmp_path, {"thesis_components": "invalid"})

    export = mod.resolve_synthesis_export("syn-resolve", db_path=db_path)

    assert export is not None
    assert export.claims == []
    assert export.provenance_warnings == [
        "Archived synthesis payload could not be validated."
    ]
    assert mod.adapt_synthesis(export)["metadata"]["provenance"]["complete"] is False


def test_resolver_preserves_duplicate_claim_components_separately(tmp_path):
    thesis = _delivered_thesis(chunk_ids=["chunk-cited"])
    components = thesis["thesis_components"]
    assert isinstance(components, list)
    component = components[0]
    assert isinstance(component, dict)
    thesis["thesis_components"] = [
        component,
        {**component, "supporting_chunk_ids": []},
    ]
    db_path = _insert_synthesis_fixture(tmp_path, thesis)

    export = mod.resolve_synthesis_export("syn-resolve", db_path=db_path)

    assert export is not None
    assert len(export.claims) == 2
    assert [len(claim.sources) for claim in export.claims] == [1, 0]


def test_resolver_preserves_path_only_component_provenance(tmp_path):
    thesis = _delivered_thesis(chunk_ids=[])
    components = thesis["thesis_components"]
    assert isinstance(components, list) and isinstance(components[0], dict)
    components[0]["supporting_path_indices"] = [0]
    thesis["reasoning_paths_used"] = [
        {
            "path_node_ids": ["node-a", "node-b"],
            "path_edge_ids": ["edge-a-b"],
            "support_summary": "Node A provides a structural analogy for node B.",
        }
    ]
    db_path = _insert_synthesis_fixture(tmp_path, thesis)
    con = duckdb.connect(db_path)
    try:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('node-a', 'Node A', 'entity', 'cross_domain'), "
            "('node-b', 'Node B', 'entity', 'cross_domain')"
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "source_tier, extraction_confidence, graph_scope) "
            "VALUES ('edge-a-b', 'node-a', 'node-b', 'analogous_to', 1, 1.0, 'cross_domain')"
        )
        con.execute(
            "INSERT INTO synthesis_substrate_manifest "
            "(synthesis_id, entity_kind, entity_id) "
            "VALUES ('syn-resolve', 'edge', 'edge-a-b')"
        )
    finally:
        con.close()

    export = mod.resolve_synthesis_export("syn-resolve", db_path=db_path)

    assert export is not None
    assert export.claims[0].path_refs[0].node_ids == ["node-a", "node-b"]
    assert export.claims[0].path_refs[0].manifest_verified is True
    doc_model = mod.adapt_synthesis(export)
    assert doc_model["metadata"]["provenance"]["complete"] is True
    assert "Graph-path provenance 1" in json.dumps(doc_model)
    assert "node-a → node-b" in json.dumps(doc_model, ensure_ascii=False)


def test_resolver_negative_path_index_stays_unresolved(tmp_path):
    thesis = _delivered_thesis(chunk_ids=[])
    components = thesis["thesis_components"]
    assert isinstance(components, list) and isinstance(components[0], dict)
    components[0]["supporting_path_indices"] = [-1]
    thesis["reasoning_paths_used"] = [
        {
            "path_node_ids": ["node-a", "node-b"],
            "path_edge_ids": ["edge-a-b"],
            "support_summary": "Node A provides a structural analogy for node B.",
        }
    ]
    db_path = _insert_synthesis_fixture(tmp_path, thesis)

    export = mod.resolve_synthesis_export("syn-resolve", db_path=db_path)

    assert export is not None
    assert export.claims[0].path_refs[0].resolved is False
    assert mod.adapt_synthesis(export)["metadata"]["provenance"]["complete"] is False


def test_resolver_rejects_pinned_edge_with_mismatched_node_path(tmp_path):
    thesis = _delivered_thesis(chunk_ids=[])
    components = thesis["thesis_components"]
    assert isinstance(components, list) and isinstance(components[0], dict)
    components[0]["supporting_path_indices"] = [0]
    thesis["reasoning_paths_used"] = [
        {
            "path_node_ids": ["node-b", "node-a"],
            "path_edge_ids": ["edge-a-b"],
            "support_summary": "The claimed direction reverses the stored graph edge.",
        }
    ]
    db_path = _insert_synthesis_fixture(tmp_path, thesis)
    con = duckdb.connect(db_path)
    try:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('node-a', 'Node A', 'entity', 'cross_domain'), "
            "('node-b', 'Node B', 'entity', 'cross_domain')"
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "source_tier, extraction_confidence, graph_scope) "
            "VALUES ('edge-a-b', 'node-a', 'node-b', 'analogous_to', 1, 1.0, 'cross_domain')"
        )
        con.execute(
            "INSERT INTO synthesis_substrate_manifest "
            "(synthesis_id, entity_kind, entity_id) "
            "VALUES ('syn-resolve', 'edge', 'edge-a-b')"
        )
    finally:
        con.close()

    export = mod.resolve_synthesis_export("syn-resolve", db_path=db_path)

    assert export is not None
    assert export.claims[0].path_refs[0].resolved is False


def test_resolver_empty_component_claim_adds_warning(tmp_path):
    thesis = _delivered_thesis(chunk_ids=["chunk-cited"])
    components = thesis["thesis_components"]
    assert isinstance(components, list) and isinstance(components[0], dict)
    components[0]["claim"] = "   "
    db_path = _insert_synthesis_fixture(tmp_path, thesis)

    export = mod.resolve_synthesis_export("syn-resolve", db_path=db_path)

    assert export is not None
    assert export.claims == []
    assert export.provenance_warnings == ["Thesis component 1 has empty claim text."]


def test_allowed_synthesis_200_gate_clean(monkeypatch):
    exp = SynthesisExport(
        synthesis_id="s1", target_question="Q?", claims=[Claim("A", [SERVABLE])]
    )
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    r = _client().get("/api/syntheses/s1/artifact.html")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert "synthesis-s1.html" in r.headers["content-disposition"]
    assert_script_free(r.text)  # gate-clean served bytes
    assert "PUBLIC DOMAIN TEXT" in r.text  # servable embedded


def test_restricted_synthesis_403_with_reason(monkeypatch):
    exp = SynthesisExport(
        synthesis_id="s2",
        target_question="Q?",
        restricted=True,
        restriction_reason="owner withheld this synthesis",
    )
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    r = _client().get("/api/syntheses/s2/artifact.html")
    assert r.status_code == 403
    body = r.json()
    assert body["error"] == "export_refused"
    assert body["reason"] == "owner withheld this synthesis"


def test_mixed_rights_cite_only_marked(monkeypatch):
    exp = SynthesisExport(
        synthesis_id="s3",
        target_question="Q?",
        claims=[Claim("A", [SERVABLE, PERSONAL])],
    )
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    r = _client().get("/api/syntheses/s3/artifact.html")
    assert r.status_code == 200
    assert "PUBLIC DOMAIN TEXT" in r.text  # servable embedded
    assert "SECRET THIRD PARTY TEXT" not in r.text  # personal_reading withheld
    assert "cite-only" in r.text  # the withheld source is visibly marked


def test_not_found_404(monkeypatch):
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: None)
    r = _client().get("/api/syntheses/nope/artifact.html")
    assert r.status_code == 404


def test_poisoned_render_is_refused(monkeypatch):
    # Prove the gate is wired in the route, not decorative: a render that
    # emits a script must be refused (500), never served as a 200.
    exp = SynthesisExport(
        synthesis_id="s4", target_question="Q?", claims=[Claim("A", [SERVABLE])]
    )
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    monkeypatch.setattr(
        mod,
        "render",
        lambda dm, ctx: "<html><body><script>alert(1)</script></body></html>",
    )
    r = _client().get("/api/syntheses/s4/artifact.html")
    assert r.status_code == 500
    assert "gate" in r.text.lower()  # refused with the gate reason


# ── multi-format export via the SPR-06 M4 routing map ──


def test_export_antiek_format_is_a_valid_signed_container(monkeypatch, tmp_path):
    from services.antiek_format import read_antiek

    exp = SynthesisExport(synthesis_id="s10", target_question="Q?", claims=[Claim("A", [SERVABLE])])
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    monkeypatch.setattr(mod, "_resolve_db_path", lambda: str(tmp_path / "graph.duckdb"))
    r = _client().get("/api/syntheses/s10/artifact?format=antiek")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    assert "s10.antiek" in r.headers["content-disposition"]
    assert read_antiek(r.content).signature_valid is True


def test_export_antiek_html_verifies(monkeypatch, tmp_path):
    from services.antiek_format.single_file import verify_single_file_html

    exp = SynthesisExport(synthesis_id="s11", target_question="Q?", claims=[Claim("A", [SERVABLE])])
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    monkeypatch.setattr(mod, "_resolve_db_path", lambda: str(tmp_path / "g.duckdb"))
    r = _client().get("/api/syntheses/s11/artifact?format=antiek_html")
    assert r.status_code == 200
    assert ".antiek.html" in r.headers["content-disposition"]
    assert verify_single_file_html(r.text) is True


def test_export_default_html_via_routing_route(monkeypatch):
    exp = SynthesisExport(synthesis_id="s12", target_question="Q?", claims=[Claim("A", [SERVABLE])])
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    r = _client().get("/api/syntheses/s12/artifact?format=html")
    assert r.status_code == 200 and "PUBLIC DOMAIN TEXT" in r.text


def test_export_unknown_format_is_400(monkeypatch):
    exp = SynthesisExport(synthesis_id="s13", target_question="Q?")
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    assert _client().get("/api/syntheses/s13/artifact?format=pdf").status_code == 400


def test_export_restricted_is_403_for_any_format(monkeypatch, tmp_path):
    exp = SynthesisExport(
        synthesis_id="s14", target_question="Q?", restricted=True, restriction_reason="withheld"
    )
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    monkeypatch.setattr(mod, "_resolve_db_path", lambda: str(tmp_path / "g.duckdb"))
    assert _client().get("/api/syntheses/s14/artifact?format=antiek").status_code == 403


def test_antiek_export_does_not_leak_personal_reading(monkeypatch, tmp_path):
    # The rights filter must hold through the .antiek container path: the
    # secret passage must not be in the signed container bytes.
    exp = SynthesisExport(synthesis_id="s15", target_question="Q?", claims=[Claim("A", [PERSONAL])])
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    monkeypatch.setattr(mod, "_resolve_db_path", lambda: str(tmp_path / "g.duckdb"))
    r = _client().get("/api/syntheses/s15/artifact?format=antiek")
    assert r.status_code == 200
    assert b"SECRET THIRD PARTY TEXT" not in r.content
