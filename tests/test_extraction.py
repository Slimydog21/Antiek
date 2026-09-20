"""Tests for processing/extraction/.

Coverage:

1. ``parse_extraction_response`` — clean JSON, code fences, malformed
   input → empty lists, type coercion ("market" → "entity" with
   original recorded), edges referencing undeclared nodes dropped,
   confidence clamping to [0, 1].
2. ``extract_from_chunk`` — full pipeline with a stub provider:
   reads chunk text, dispatches parameter_extractor, parses response,
   writes nodes + edges via ops, emits GRAPH_NODE_INSERTED /
   GRAPH_EDGE_INSERTED events.
3. Idempotency: re-extracting the same chunk produces no new nodes,
   no new events.
4. Provider failure paths: no provider registered / provider raises
   → empty result, no nodes written.
5. Edge resolution: edges whose source/target wasn't successfully
   written are skipped (defensive against FK violations).
"""

from __future__ import annotations

import os
import sys

import duckdb
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from processing.embedding import _reset_default_provider  # noqa: E402
from processing.extraction import (  # noqa: E402
    ANTIEK_NODE_TYPES,
    extract_from_chunk,
    parse_extraction_response,
)
from runtime.db_lock import connect_write  # noqa: E402
from substrate.dispatch import (  # noqa: E402
    DispatchConfig,
    NormalizedUsage,
    ProviderError,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.graph import ensure_initialized, insert_chunk, insert_document  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


class _StubExtractor:
    name = "stub-extractor"

    def __init__(self, text: str, *, raise_on_call: bool = False):
        self._text = text
        self._raise = raise_on_call

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        if self._raise:
            raise ProviderError("stub failure", provider=self.name, model=model, latency_ms=0)
        return RawProviderResponse(
            text=self._text,
            raw_usage={"input_tokens": 200, "output_tokens": 100},
            finish_reason="end_turn",
            latency_ms=10,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


def _extractor_config(provider_name: str) -> DispatchConfig:
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    flash = TierConfig(
        name="flash", provider=provider_name, model="stub-flash",
        max_tokens=4096, temperature=0.1, context_budget_tokens=32_000,
        pricing=pricing, fallback=None,
    )
    return DispatchConfig(
        role_tiers={"parameter_extractor": "flash"},
        tiers={"flash": flash},
    )


def _patch_dispatch_config(monkeypatch, config: DispatchConfig) -> None:
    import substrate.dispatch.router as router
    monkeypatch.setattr(
        router.DispatchConfig, "from_yaml",
        classmethod(lambda cls, path: config),
    )


def _seed_chunk(db_path: str, *, chunk_id: str, text: str, document_id: str = "doc-1",
                source_tier: int = 2) -> None:
    ensure_initialized(db_path)
    con = connect_write(db_path, purpose="test_seed")
    try:
        insert_document(
            con, document_id=document_id, source_tier=source_tier,
            document_type="peer_reviewed_paper", on_conflict="ignore",
        )
        insert_chunk(
            con, chunk_id=chunk_id, document_id=document_id,
            chunk_index=0, text=text,
        )
    finally:
        con.close()


def _count(db_path: str, table: str) -> int:
    con = duckdb.connect(db_path, read_only=True)
    try:
        return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        con.close()


# ---------------------------------------------------------------------------
# 1. parse_extraction_response
# ---------------------------------------------------------------------------


def test_parse_clean_json():
    text = """
    {
      "nodes": [
        {"node_id": "psi", "node_type": "organization",
         "canonical_label": "PsiQuantum", "description": "qubits",
         "confidence": 0.95}
      ],
      "edges": []
    }
    """
    nodes, edges = parse_extraction_response(text)
    assert len(nodes) == 1
    assert nodes[0].local_id == "psi"
    assert nodes[0].node_type == "organization"
    assert nodes[0].canonical_label == "PsiQuantum"
    assert nodes[0].confidence == pytest.approx(0.95)
    assert nodes[0].original_type is None
    assert edges == []


def test_parse_with_code_fence_and_prose_preamble():
    text = (
        "Sure thing!\n\n```json\n"
        '{"nodes": [{"node_id": "a", "node_type": "entity", '
        '"canonical_label": "X", "description": "", "confidence": 0.8}], '
        '"edges": []}'
        "\n```\n"
    )
    nodes, _ = parse_extraction_response(text)
    assert len(nodes) == 1
    assert nodes[0].canonical_label == "X"


def test_parse_coerces_concept_market_technology_to_entity():
    """Researchmaxx's broader node taxonomy maps onto Antiek's 9-value
    NodeType via "entity" + ``original_type`` metadata preservation."""
    for original in ("concept", "market", "technology", "weird_made_up"):
        text = (
            f'{{"nodes": [{{"node_id": "a", "node_type": "{original}", '
            '"canonical_label": "Foo", "description": "", "confidence": 0.7}], '
            '"edges": []}'
        )
        nodes, _ = parse_extraction_response(text)
        assert len(nodes) == 1
        assert nodes[0].node_type == "entity"
        assert nodes[0].original_type == original


def test_parse_drops_edges_referencing_undeclared_nodes():
    """An edge that points at a node_id we never declared is malformed
    — drop it before it can cause a FK violation downstream."""
    text = (
        '{"nodes": [{"node_id": "a", "node_type": "entity", '
        '"canonical_label": "A", "description": "", "confidence": 0.5}], '
        '"edges": ['
        '{"source_node_id": "a", "target_node_id": "GHOST", '
        '"relation": "uses", "confidence": 0.7}'
        ']}'
    )
    _, edges = parse_extraction_response(text)
    assert edges == []


def test_parse_clamps_confidence():
    text = (
        '{"nodes": [{"node_id": "a", "node_type": "entity", '
        '"canonical_label": "A", "description": "", "confidence": 1.7}], '
        '"edges": []}'
    )
    nodes, _ = parse_extraction_response(text)
    assert nodes[0].confidence == 1.0

    text2 = (
        '{"nodes": [{"node_id": "a", "node_type": "entity", '
        '"canonical_label": "A", "description": "", "confidence": -0.2}], '
        '"edges": []}'
    )
    nodes, _ = parse_extraction_response(text2)
    assert nodes[0].confidence == 0.0


def test_parse_malformed_returns_empty():
    assert parse_extraction_response("not json at all") == ([], [])
    assert parse_extraction_response("") == ([], [])
    assert parse_extraction_response("{}") == ([], [])


def test_parse_drops_nodes_with_missing_required_fields():
    text = (
        '{"nodes": ['
        '{"canonical_label": "no id"},'
        '{"node_id": "a"},'
        '{"node_id": "", "canonical_label": "empty id"},'
        '{"node_id": "valid", "node_type": "entity",'
        ' "canonical_label": "Valid", "description": "", "confidence": 0.5}'
        '], "edges": []}'
    )
    nodes, _ = parse_extraction_response(text)
    assert len(nodes) == 1
    assert nodes[0].local_id == "valid"


# ---------------------------------------------------------------------------
# 2. extract_from_chunk end-to-end
# ---------------------------------------------------------------------------


def test_extract_writes_nodes_edges_and_emits_events(monkeypatch, tmp_path):
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)

    _seed_chunk(db, chunk_id="chunk-1", text="PsiQuantum builds photonic qubits.")

    register_provider(_StubExtractor(
        '{"nodes": ['
        '{"node_id": "psi", "node_type": "organization", '
        ' "canonical_label": "PsiQuantum", "description": "co", "confidence": 0.95},'
        '{"node_id": "qb", "node_type": "entity", '
        ' "canonical_label": "photonic qubit", "description": "tech", "confidence": 0.9}'
        '], "edges": ['
        '{"source_node_id": "psi", "target_node_id": "qb", '
        ' "relation": "builds", "confidence": 0.95}'
        ']}'
    ))
    _patch_dispatch_config(monkeypatch, _extractor_config("stub-extractor"))

    result = extract_from_chunk(
        chunk_id="chunk-1",
        investigation_id="inv-extract",
        db_path=db,
    )

    assert result.nodes_written == 2
    assert result.edges_written == 1
    assert result.nodes_skipped == 0
    assert result.edges_skipped == 0
    assert _count(db, "nodes") == 2
    assert _count(db, "edges") == 1

    # Typed events landed.
    rows = trajectory("inv-extract")
    node_events = [r for r in rows if r["action_type"] == "graph.node.inserted"]
    edge_events = [r for r in rows if r["action_type"] == "graph.edge.inserted"]
    assert len(node_events) == 2
    assert len(edge_events) == 1


def test_extract_is_idempotent(monkeypatch, tmp_path):
    """Same chunk re-extracted produces no new rows AND no new events
    because insert_node/insert_edge with on_conflict='ignore' no-ops."""
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    _seed_chunk(db, chunk_id="chunk-idem", text="Sample text")
    register_provider(_StubExtractor(
        '{"nodes":[{"node_id":"a","node_type":"entity",'
        '"canonical_label":"A","description":"","confidence":0.5}],'
        '"edges":[]}'
    ))
    _patch_dispatch_config(monkeypatch, _extractor_config("stub-extractor"))

    extract_from_chunk(chunk_id="chunk-idem", investigation_id="inv-i", db_path=db)
    extract_from_chunk(chunk_id="chunk-idem", investigation_id="inv-i", db_path=db)
    extract_from_chunk(chunk_id="chunk-idem", investigation_id="inv-i", db_path=db)

    assert _count(db, "nodes") == 1
    rows = trajectory("inv-i")
    node_events = [r for r in rows if r["action_type"] == "graph.node.inserted"]
    assert len(node_events) == 1


def test_extract_with_unknown_chunk_returns_empty(tmp_path, monkeypatch):
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    ensure_initialized(db)
    result = extract_from_chunk(
        chunk_id="chunk-doesnt-exist", investigation_id="inv-x", db_path=db,
    )
    assert result.nodes_written == 0
    assert result.edges_written == 0


def test_extract_no_provider_returns_empty(monkeypatch, tmp_path):
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    _seed_chunk(db, chunk_id="chunk-noprov", text="text")
    # NO register_provider.
    _patch_dispatch_config(monkeypatch, _extractor_config("not-registered"))

    result = extract_from_chunk(
        chunk_id="chunk-noprov", investigation_id="inv-np", db_path=db,
    )
    assert result.nodes_written == 0
    assert _count(db, "nodes") == 0


def test_extract_provider_raises_returns_empty(monkeypatch, tmp_path):
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    _seed_chunk(db, chunk_id="chunk-fail", text="text")
    register_provider(_StubExtractor("never reached", raise_on_call=True))
    _patch_dispatch_config(monkeypatch, _extractor_config("stub-extractor"))

    result = extract_from_chunk(
        chunk_id="chunk-fail", investigation_id="inv-f", db_path=db,
    )
    assert result.nodes_written == 0


def test_extract_records_original_type_metadata_for_coerced_nodes(monkeypatch, tmp_path):
    """When the LLM returns node_type='market' (not in Antiek's 9
    values), the extractor coerces to 'entity' and records the
    original in metadata. Verify the metadata column carries it."""
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    _seed_chunk(db, chunk_id="chunk-coerce", text="text")
    register_provider(_StubExtractor(
        '{"nodes":[{"node_id":"m","node_type":"market",'
        '"canonical_label":"Quantum market","description":"",'
        '"confidence":0.7}],"edges":[]}'
    ))
    _patch_dispatch_config(monkeypatch, _extractor_config("stub-extractor"))

    extract_from_chunk(chunk_id="chunk-coerce", investigation_id="inv-c", db_path=db)

    con = duckdb.connect(db, read_only=True)
    try:
        row = con.execute(
            "SELECT node_type, metadata FROM nodes WHERE canonical_label = ?",
            ["Quantum market"],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    node_type, metadata_json = row
    assert node_type == "entity"
    import json as _json
    meta = _json.loads(metadata_json)
    assert meta["original_node_type"] == "market"


def test_antiek_node_types_is_subset_of_schema_literal():
    """Every value extraction can produce must be accepted by the schema's
    NodeType Literal, so extraction never emits a value the Pydantic
    payload would reject. This is a SUBSET relationship, not equality:
    DRW SPR-01 added promotion-only 'insight' + 'question', and account-memory
    S2a added the projection-only 'memory' type; chunk extraction emits none of
    those three."""
    import typing as _t

    from substrate.schemas.events import NodeType
    schema_values = set(_t.get_args(NodeType))
    assert schema_values >= ANTIEK_NODE_TYPES
    # The only members not produced by extraction are the two promotion types
    # and the account-memory projection type.
    assert schema_values - ANTIEK_NODE_TYPES == {"insight", "question", "memory"}
