from __future__ import annotations

import datetime
import json
from pathlib import Path

from interfaces.research.api.synthesis_artifact import resolve_synthesis_export
from orchestration.loop_one.federated_span_registry import (
    parse_rendered_span_registry,
    registry_archive_payload,
)
from runtime.db_lock import connect_write
from services.html_projection.adapters.synthesis import adapt_synthesis
from substrate.corpus_evidence import EvidenceSpan, render_chunks_block
from substrate.graph import ensure_initialized


def _archive_payload() -> tuple[str, dict[str, object]]:
    text = "SOURCE TEXT MUST REMAIN CITE ONLY"
    span = EvidenceSpan(
        span_id="span_" + "a" * 32,
        corpus_id="core:work-1",
        text=text,
        start_char=5,
        end_char=5 + len(text),
        source_kind="core",
        origin_ref="work-1",
        retrieved_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        license_class="source_terms_governed_metadata",
        source_tier=5,
    )
    registry = parse_rendered_span_registry(render_chunks_block((span,)))
    return span.span_id, registry_archive_payload(registry)


def _seed_synthesis(path: Path, *, substrate: object, thesis: object) -> None:
    ensure_initialized(str(path))
    with connect_write(str(path), purpose="test:federated-artifact") as con:
        con.execute(
            "INSERT INTO syntheses (synthesis_id, investigation_id, target_question, "
            "synthesis_timestamp, status, implicit_recommendation, thesis_text, "
            "model_versions, parameters, thesis, substrate) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "syn-inv-fed",
                "inv-fed",
                "Question?",
                datetime.datetime(2026, 1, 1),
                "passed",
                "proceed",
                "Summary",
                "{}",
                "{}",
                json.dumps(thesis),
                json.dumps(substrate),
            ],
        )


def test_artifact_resolves_each_federated_claim_without_fake_graph_identity(tmp_path: Path) -> None:
    span_id, substrate = _archive_payload()
    thesis = {
        "thesis_components": [
            {"claim": "Federated claim", "supporting_chunk_ids": [span_id]},
            {"claim": "Unknown claim", "supporting_chunk_ids": ["missing"]},
        ]
    }
    db = tmp_path / "graph.duckdb"
    _seed_synthesis(db, substrate=substrate, thesis=thesis)
    export = resolve_synthesis_export("syn-inv-fed", db_path=str(db))
    assert export is not None and len(export.claims) == 2
    source = export.claims[0].sources[0]
    assert source.document_id is None
    assert source.external_source_id == "core:work-1"
    assert source.resolved and not source.servable
    assert source.rights_class == "source_terms_governed_metadata"
    assert export.claims[1].sources == []
    doc_model = adapt_synthesis(export)
    rendered = json.dumps(doc_model)
    assert "Federated claim" in rendered
    assert "core:work-1" in rendered
    assert "source_terms_governed_metadata" in rendered
    assert "SOURCE TEXT MUST REMAIN CITE ONLY" not in rendered
    assert "cite-only" in rendered
    assert doc_model["metadata"]["provenance"] == {
        "fully_sourced": 1,
        "total": 2,
        "complete": False,
    }


def test_corrupt_archived_registry_stays_visibly_unsourced(tmp_path: Path) -> None:
    span_id, _ = _archive_payload()
    thesis = {"thesis_components": [{"claim": "Claim", "supporting_chunk_ids": [span_id]}]}
    db = tmp_path / "graph.duckdb"
    _seed_synthesis(
        db,
        substrate={"federated_span_registry": {"schema_version": 99, "records": []}},
        thesis=thesis,
    )
    export = resolve_synthesis_export("syn-inv-fed", db_path=str(db))
    assert export is not None
    assert export.claims[0].sources == []
    doc_model = adapt_synthesis(export)
    assert doc_model["metadata"]["provenance"]["fully_sourced"] == 0
