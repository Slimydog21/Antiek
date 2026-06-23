"""Tests for substrate/attribution/ (Sprint 16 phase 1)."""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.attribution import (
    AttributionClaim,
    attribution_option_a,
    attribution_option_b,
    attribution_option_c,
    compute_attribution_for_synthesis,
)
from substrate.schemas import TYPED_PAYLOAD_ACTION_TYPES, ActionType

# ─────────────────────────────────────────────────────────────────────
# 1. Schema lock-in
# ─────────────────────────────────────────────────────────────────────


def test_new_action_type_in_typed_set():
    assert ActionType.PAGE_ATTRIBUTION_COMPUTED.value in TYPED_PAYLOAD_ACTION_TYPES


def test_attribution_payload_round_trip():
    from substrate.schemas import PageAttributionComputedPayload
    p = PageAttributionComputedPayload(
        synthesis_id="syn-1",
        algorithm_shares={
            "A": {"doc-1": 0.6, "doc-2": 0.4},
            "B": {"doc-1": 0.8, "doc-2": 0.2},
            "C": {"doc-1": 0.7, "doc-2": 0.3},
        },
        claim_count=3,
        document_count=2,
    )
    assert p.action_type == ActionType.PAGE_ATTRIBUTION_COMPUTED
    raw = p.model_dump()
    assert raw["algorithm_shares"]["B"]["doc-1"] == 0.8


# ─────────────────────────────────────────────────────────────────────
# 2. Algorithm math
# ─────────────────────────────────────────────────────────────────────


def _claims_two_docs() -> list[AttributionClaim]:
    return [
        AttributionClaim(
            claim_index=0,
            chunk_ids=("ch-1", "ch-2"),
            confidence="very_high",
            chunk_to_document={"ch-1": "doc-A", "ch-2": "doc-B"},
            document_to_tier={"doc-A": 1, "doc-B": 4},
        ),
        AttributionClaim(
            claim_index=1,
            chunk_ids=("ch-3",),
            confidence="low",
            chunk_to_document={"ch-3": "doc-A"},
            document_to_tier={"doc-A": 1, "doc-B": 4},
        ),
    ]


def test_option_a_equal_split_per_chunk():
    shares = attribution_option_a(_claims_two_docs())
    # 3 total citations: 2 to doc-A, 1 to doc-B
    assert shares["doc-A"] == pytest.approx(2 / 3)
    assert shares["doc-B"] == pytest.approx(1 / 3)
    assert sum(shares.values()) == pytest.approx(1.0)


def test_option_b_weights_high_tier_higher():
    shares = attribution_option_b(_claims_two_docs())
    # doc-A is tier 1 (factor 5); doc-B is tier 4 (factor 2).
    # Claim 0: very_high=1.0, doc-A → 1.0 * 5 = 5; doc-B → 1.0 * 2 = 2.
    # Claim 1: low=0.4, doc-A → 0.4 * 5 = 2.
    # doc-A total = 7, doc-B total = 2. Sum = 9.
    assert shares["doc-A"] == pytest.approx(7 / 9)
    assert shares["doc-B"] == pytest.approx(2 / 9)


def test_option_c_reduces_to_b_when_uniform_load_bearing():
    c = attribution_option_c(_claims_two_docs())
    b = attribution_option_b(_claims_two_docs())
    assert c == b


def test_option_c_load_bearing_weight_shifts_share():
    # Mark claim 0 as "more load-bearing"; doc-A and doc-B both benefit
    # by the same factor on claim 0, so the relative split is unchanged
    # but the math goes through cleanly.
    claims = [
        AttributionClaim(
            claim_index=0, chunk_ids=("ch-1",),
            confidence="very_high",
            chunk_to_document={"ch-1": "doc-A"},
            document_to_tier={"doc-A": 1, "doc-B": 1},
            load_bearing_weight=3.0,
        ),
        AttributionClaim(
            claim_index=1, chunk_ids=("ch-2",),
            confidence="very_high",
            chunk_to_document={"ch-2": "doc-B"},
            document_to_tier={"doc-A": 1, "doc-B": 1},
            load_bearing_weight=1.0,
        ),
    ]
    shares = attribution_option_c(claims)
    # Claim 0: weight 1*5*3 = 15 → doc-A; Claim 1: 1*5*1 = 5 → doc-B.
    assert shares["doc-A"] == pytest.approx(0.75)
    assert shares["doc-B"] == pytest.approx(0.25)


def test_option_a_empty_returns_empty():
    assert attribution_option_a([]) == {}


def test_option_a_excludes_unresolved_chunks():
    claim = AttributionClaim(
        claim_index=0, chunk_ids=("ch-orphan",),
        confidence="very_high",
        chunk_to_document={},  # nothing resolves
        document_to_tier={},
    )
    assert attribution_option_a([claim]) == {}


# ─────────────────────────────────────────────────────────────────────
# 3. compute_attribution_for_synthesis
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def seeded_substrate(monkeypatch):
    """Seed a temp DuckDB with documents + chunks + a synthesis row,
    then yield the (synthesis_id, db_path)."""
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    tmp = tempfile.mkdtemp(prefix="antiek-attr-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    init_database_at_path(db_path)

    chunk_a_id: str
    chunk_b_id: str
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
    yield {"db_path": db_path, "events_dir": events_dir,
           "synthesis_id": "syn-test-1"}


def test_compute_attribution_reads_synthesis_and_resolves_chunks(seeded_substrate):
    r = compute_attribution_for_synthesis(
        seeded_substrate["synthesis_id"],
        db_path=seeded_substrate["db_path"],
    )
    assert r.synthesis_id == seeded_substrate["synthesis_id"]
    assert r.option_a.document_count == 2
    assert r.option_a.claim_count == 2
    # Option A: 3 citations total, doc-A gets 2 of 3
    assert r.option_a.shares["doc-A"] == pytest.approx(2 / 3)
    # Option B: tier-weighted; doc-A is tier 1, doc-B is tier 4
    assert r.option_b.shares["doc-A"] > r.option_a.shares["doc-A"]
    assert r.option_b.shares["doc-B"] < r.option_a.shares["doc-B"]


def test_compute_attribution_unknown_synthesis_raises(seeded_substrate):
    with pytest.raises(ValueError, match="not found"):
        compute_attribution_for_synthesis(
            "syn-does-not-exist",
            db_path=seeded_substrate["db_path"],
        )


def test_compute_attribution_emit_event_writes_to_log(seeded_substrate):
    import glob
    r = compute_attribution_for_synthesis(
        seeded_substrate["synthesis_id"],
        db_path=seeded_substrate["db_path"],
        emit_event=True,
        investigation_id="inv-1",
    )
    found = False
    for ef in glob.glob(
        os.path.join(seeded_substrate["events_dir"], "**", "*.jsonl"),
        recursive=True,
    ):
        with open(ef) as f:
            for line in f:
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("action_type") == ActionType.PAGE_ATTRIBUTION_COMPUTED.value:
                    payload = ev.get("payload") or {}
                    assert payload["synthesis_id"] == seeded_substrate["synthesis_id"]
                    assert "A" in payload["algorithm_shares"]
                    found = True
    assert found, "PAGE_ATTRIBUTION_COMPUTED event not emitted"


# ─────────────────────────────────────────────────────────────────────
# 4. GET /attribution/synthesis/{id}
# ─────────────────────────────────────────────────────────────────────


def test_api_returns_three_algorithm_results(seeded_substrate):
    from interfaces.research.api.app import create_app
    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[],
    )
    client = TestClient(app)
    resp = client.get(
        f"/attribution/synthesis/{seeded_substrate['synthesis_id']}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["synthesis_id"] == seeded_substrate["synthesis_id"]
    assert body["option_a"]["algorithm"] == "A"
    assert body["option_b"]["algorithm"] == "B"
    assert body["option_c"]["algorithm"] == "C"
    assert body["option_b"]["shares"]["doc-A"] > body["option_a"]["shares"]["doc-A"]


def test_api_unknown_synthesis_404(seeded_substrate):
    from interfaces.research.api.app import create_app
    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[],
    )
    client = TestClient(app)
    resp = client.get("/attribution/synthesis/syn-nope")
    assert resp.status_code == 404


def test_api_surfaces_ip_holder_maps(seeded_substrate):
    """SPR-10 M1 — the attribution endpoint carries the provenance chain's last
    link (document_ip_holders / status). The seeded docs have no owner, so the
    maps are present but honestly carry null owners — never an invented one."""
    from interfaces.research.api.app import create_app
    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[],
    )
    client = TestClient(app)
    body = client.get(
        f"/attribution/synthesis/{seeded_substrate['synthesis_id']}"
    ).json()
    # The maps exist on every algorithm's result.
    for opt in ("option_a", "option_b", "option_c"):
        assert "document_ip_holders" in body[opt]
        assert "document_ip_holder_status" in body[opt]
    # Seeded docs carry no ip_holder → honest null, no fabricated owner/status.
    assert all(v is None for v in body["option_b"]["document_ip_holders"].values())
    assert body["option_b"]["document_ip_holder_status"] == {}
