from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from orchestration.loop_one.federated_span_registry import parse_rendered_span_registry
from runtime.db_lock import connect_write
from substrate.corpus_evidence import EvidenceSpan, render_chunks_block
from substrate.event_log import emit_typed
from substrate.graph import ensure_initialized, insert_chunk, insert_document
from substrate.research_artifact.build_body import build_body
from substrate.research_artifact.import_notes import parse_body_from_html
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import (
    SCHEMA_VERSION,
    ArtifactCitation,
    ArtifactClaim,
    ResearchArtifactBody,
)
from substrate.schemas import EvidenceRetrieveRequestedPayload, SynthesizeDeliveredPayload


def _synthesis(ids: list[str]) -> SynthesizeDeliveredPayload:
    return SynthesizeDeliveredPayload.model_validate(
        {
            "thesis_summary": "Claim one and claim two.",
            "implicit_recommendation": "proceed",
            "thesis_components": [
                {
                    "claim": "Claim one.",
                    "confidence": "high",
                    "supporting_chunk_ids": ids,
                    "supporting_path_indices": [],
                    "confidence_basis": "exact cited records",
                    "effective_source_tier": 2,
                    "hedging_required": False,
                }
            ],
            "falsification_conditions": [
                {
                    "condition": "The evidence is withdrawn",
                    "specific_observable": "The governed records disappear",
                    "timeframe": None,
                }
            ],
            "execution_risks": [
                {
                    "risk": "Source drift",
                    "severity_if_manifested": "low",
                    "leading_indicator": None,
                }
            ],
            "constraint_compliance": {
                "hard_constraints_satisfied": True,
                "soft_constraints_violated": [],
                "violations_justified": [],
            },
            "reasoning_paths_used": [],
            "conviction_level": 0.8,
            "constraint_loop_status": "single_pass",
            "constraint_loop_iterations": 1,
        }
    )


def test_v2_handoff_carries_graph_federated_and_unresolved_citations_without_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    ensure_initialized(str(db))
    with connect_write(str(db), purpose="test:artifact-v2") as con:
        document_id = insert_document(
            con,
            document_id="doc-graph",
            source_tier=2,
            document_type="paper",
            title="Graph source",
            content_class="public_domain",
        )
        graph_id = insert_chunk(
            con,
            document_id=document_id,
            chunk_index=0,
            text="GRAPH SOURCE TEXT MUST NOT ENTER HANDOFF",
        )

    span_text = "FEDERATED SOURCE TEXT MUST NOT ENTER HANDOFF"
    span = EvidenceSpan(
        span_id="span_" + "a" * 32,
        corpus_id="core:work-1",
        text=span_text,
        start_char=5,
        end_char=5 + len(span_text),
        source_kind="core",
        origin_ref="work-1",
        retrieved_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        license_class="source_terms_governed_metadata",
        source_tier=5,
    )
    block = render_chunks_block((span,))
    assert parse_rendered_span_registry(block)[span.span_id].text == span_text
    emit_typed(
        "inv-v2",
        EvidenceRetrieveRequestedPayload(
            sub_question="Question?",
            category="technology_risk",
            evidence_type_required="mixed",
            top_k=3,
            chunks_block=block,
            subgraph_block="(none)",
        ),
        role="orchestrator",
        events_dir=str(events),
    )
    emit_typed(
        "inv-v2",
        _synthesis([graph_id, span.span_id, "unknown-id"]),
        role="synthesizer",
        events_dir=str(events),
    )

    body = build_body("inv-v2", db_path=str(db), events_dir=str(events))
    assert body.schema_version == 2 and len(body.claims) == 1
    claim = body.claims[0]
    assert claim.cited_ids == [graph_id, span.span_id, "unknown-id"]
    assert [citation.resolution for citation in claim.citations] == [
        "graph",
        "federated",
        "unresolved",
    ]
    assert claim.citations[0].document_id == "doc-graph"
    assert claim.citations[1].external_source_id == "core:work-1"
    assert claim.citations[1].rights_class == "source_terms_governed_metadata"
    payload = body.model_dump_json()
    html = render_html(body)
    assert "Graph source" in html and "core:work-1" in html
    assert "unknown-id" in html and "unresolved" in html
    assert "GRAPH SOURCE TEXT MUST NOT ENTER HANDOFF" not in payload + html
    assert span_text not in payload + html


def test_legacy_v1_html_migrates_for_note_import() -> None:
    legacy = {
        "schema_version": 1,
        "investigation_id": "inv-old",
        "problem_question": "Old question",
        "insights": [],
        "open_questions": [],
        "synthesis_excerpt": None,
        "synthesis_withheld": False,
        "source_event_ids": [],
        "agent_notes": ["carry me"],
    }
    html = (
        '<script type="application/json" id="antiek-artifact-v1">'
        + json.dumps(legacy)
        + "</script>"
    )
    migrated = parse_body_from_html(html)
    assert migrated.schema_version == SCHEMA_VERSION == 2
    assert migrated.claims == [] and migrated.agent_notes == ["carry me"]


def test_v2_hash_is_deterministic_and_hostile_labels_are_escaped() -> None:
    body = ResearchArtifactBody(
        investigation_id="inv-hostile",
        problem_question="Question",
        claims=[
            ArtifactClaim(
                statement="<script>alert(1)</script>",
                cited_ids=["citation-1"],
                citations=[
                    ArtifactCitation(
                        citation_id="citation-1",
                        resolution="federated",
                        external_source_id="<img src=x onerror=alert(1)>",
                    )
                ],
            )
        ],
    )
    assert body.content_hash() == body.content_hash()
    html = render_html(body)
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_v2_claim_and_citation_bounds_fail_closed() -> None:
    with pytest.raises(ValidationError):
        ResearchArtifactBody(
            investigation_id="inv-overflow",
            problem_question="Question",
            claims=[ArtifactClaim(statement="claim")] * 101,
        )
    with pytest.raises(ValidationError):
        ArtifactClaim(statement="claim", cited_ids=[f"id-{index}" for index in range(101)])
