"""Route-level attribution audit and replay checks."""

from __future__ import annotations

import json
import os
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write
from substrate.ad_inventory.attribution import compute_attribution_option_b
from substrate.ad_inventory.attribution_audit import (
    PRODUCER_AD_INVENTORY,
    PRODUCER_SYNTHESIS_TELEMETRY,
    SYNTHESIS_LETTER_TO_ALGORITHM,
    _canonical_json,
    load_for_impression_set,
    record_attribution,
    replay,
)
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database_at_path


@pytest.fixture
def seeded_substrate(monkeypatch):
    """Seed two source tiers and a synthesis citing both documents."""
    tmp = tempfile.mkdtemp(prefix="antiek-attr-audit-replay-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    init_database_at_path(db_path)

    with connect_write(db_path, purpose="seed") as con:
        insert_document(
            con, document_id="doc-A", source_tier=1,
            document_type="academic_paper", title="Tier-1 Paper",
        )
        insert_document(
            con, document_id="doc-B", source_tier=4,
            document_type="blog_post", title="Tier-4 Blog",
        )
        chunk_a_id = insert_chunk(
            con, document_id="doc-A", chunk_index=0, text="chunk A text.",
        )
        chunk_b_id = insert_chunk(
            con, document_id="doc-B", chunk_index=0, text="chunk B text.",
        )
        thesis = {
            "thesis_components": [
                {
                    "claim": "C1",
                    "confidence": "very_high",
                    "supporting_chunk_ids": [chunk_a_id, chunk_b_id],
                },
                {
                    "claim": "C2",
                    "confidence": "low",
                    "supporting_chunk_ids": [chunk_a_id],
                },
            ],
        }
        con.execute(
            "INSERT INTO syntheses "
            "(synthesis_id, investigation_id, target_question, "
            " synthesis_timestamp, status, implicit_recommendation, "
            " thesis, thesis_token_count) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, 0)",
            ["syn-test-1", "inv-1", "Why does X compound?",
             "passed", "proceed", json.dumps(thesis)],
        )
    return {"db_path": db_path, "synthesis_id": "syn-test-1"}


def _client() -> TestClient:
    return TestClient(create_app(
        register_wrestling=False, register_providers=False, cors_origins=[],
    ))


def test_synthesis_route_records_replayable_rows_stamped_with_module(seeded_substrate):
    db_path = seeded_substrate["db_path"]
    synthesis_id = seeded_substrate["synthesis_id"]
    client = _client()
    response = client.get(f"/attribution/synthesis/{synthesis_id}")
    assert response.status_code == 200
    assert response.headers["X-Antiek-Attribution-Audit"] == "recorded"
    body = response.json()

    with connect_read(db_path) as con:
        records = load_for_impression_set(con, f"synthesis:{synthesis_id}")
    assert len(records) == 3
    by_algorithm = {record.algorithm: record for record in records}
    for letter in ("A", "B", "C"):
        record = by_algorithm[SYNTHESIS_LETTER_TO_ALGORITHM[letter].value]
        assert record.producer_module == PRODUCER_SYNTHESIS_TELEMETRY
        assert record.shares == body[f"option_{letter.lower()}"]["shares"]

    with connect_write(db_path, purpose="mutate_source_tiers") as con:
        # DuckDB 1.5 treats an indexed tier update as a delete/insert and
        # rejects it while chunks reference the document's primary key.
        con.execute("DROP INDEX IF EXISTS idx_documents_tier")
        con.execute("UPDATE documents SET source_tier = 5 WHERE document_id IN ('doc-A', 'doc-B')")

    with connect_read(db_path) as con:
        for record in records:
            replayed = replay(con, record.audit_id)
            assert replayed.identical is True
            assert _canonical_json(replayed.recomputed_shares) == _canonical_json(
                replayed.recorded_shares
            )

    live_response = client.get(f"/attribution/synthesis/{synthesis_id}")
    assert live_response.status_code == 200
    recorded_b = by_algorithm[SYNTHESIS_LETTER_TO_ALGORITHM["B"].value]
    assert live_response.json()["option_b"]["shares"] != recorded_b.shares


def test_compute_route_records_replayable_row_stamped_with_module(seeded_substrate):
    db_path = seeded_substrate["db_path"]
    response = _client().post(
        "/attribution/compute",
        json={
            "page_id": "page-test-1",
            "algorithm": "option_b",
            "chunk_to_document": {"ch-1": "doc-A", "ch-2": "doc-B"},
            "chunk_to_claim_confidence": {"ch-1": 1.0, "ch-2": 0.4},
            "document_to_source_tier": {"doc-A": 1, "doc-B": 4},
        },
    )
    assert response.status_code == 200
    assert response.headers["X-Antiek-Attribution-Audit"] == "recorded"
    with connect_read(db_path) as con:
        records = load_for_impression_set(con, "page:page-test-1")
        assert len(records) == 1
        record = records[0]
        assert record.producer_module == PRODUCER_AD_INVENTORY
        assert record.shares == response.json()["shares"]
        assert replay(con, record.audit_id).identical is True


def test_repeat_request_is_idempotent(seeded_substrate):
    client = _client()
    for _ in range(2):
        response = client.get("/attribution/synthesis/syn-test-1")
        assert response.status_code == 200
        assert response.headers["X-Antiek-Attribution-Audit"] == "recorded"
    with connect_read(seeded_substrate["db_path"]) as con:
        assert len(load_for_impression_set(con, "synthesis:syn-test-1")) == 3


def test_unknown_producer_is_rejected(seeded_substrate):
    inputs = {
        "chunk_to_document": {"ch-1": "doc-A"},
        "chunk_to_claim_confidence": {"ch-1": 1.0},
        "document_to_source_tier": {"doc-A": 1},
    }
    result = compute_attribution_option_b(page_id="page-1", **inputs)
    with (
        connect_write(seeded_substrate["db_path"], purpose="reject_unknown_producer") as con,
        pytest.raises(ValueError, match="unknown attribution producer"),
    ):
        record_attribution(
            con, impression_set_ref="page:page-1", result=result,
            inputs=inputs, producer_module="nope",
        )


def test_a_busy_writer_does_not_block_the_read(seeded_substrate, monkeypatch):
    """The audit write waits a bounded time for the single-writer lock; while
    another writer holds it the report is still served, marked ``failed``."""
    import interfaces.research.api.app as app_module

    monkeypatch.setattr(app_module, "_ATTRIBUTION_AUDIT_WRITE_TIMEOUT_S", 0.3)
    client = _client()
    with connect_write(seeded_substrate["db_path"], purpose="hold_the_writer"):
        started = time.monotonic()
        response = client.get("/attribution/synthesis/syn-test-1")
        elapsed = time.monotonic() - started
    assert elapsed < 3.0, f"the read waited {elapsed:.1f}s on the audit write"
    assert response.status_code == 200
    assert response.headers["X-Antiek-Attribution-Audit"] == "failed"
    assert response.json()["option_a"]["shares"]
