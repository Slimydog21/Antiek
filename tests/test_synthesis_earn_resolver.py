"""End-to-end DB tests for ``resolve_and_split_synthesis_earn`` (AFA-S3-M3 bridge).

These seed a real DuckDB synthesis whose sources span the three monetization-relevant
content classes and prove the whole chain — provenance resolution → earn gate → §9.3
split → conserved per-source cents — against the actual schema, not a hand-built fixture.
The load-bearing test is ``test_display_drops_restricted_but_earn_retains_it``: it runs
BOTH surfaces over the SAME seeded synthesis and shows they diverge exactly where §9.10
says they must, which is the whole reason the two share one resolution but apply two gates.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from substrate.ad_inventory.synthesis_earn_split import (
    resolve_and_split_synthesis_earn,
)
from substrate.attribution.compute import compute_attribution_for_synthesis

PUBLIC = "public_domain"
RESTRICTED = "restricted_pending_opt_in"  # earns to escrow (§9.10)
PERSONAL = "personal_reading"  # never earns


@pytest.fixture
def synthesis_with_mixed_sources(monkeypatch):
    """Seed a synthesis grounded equally in a public, a restricted, and a personal source
    (one chunk each, one claim each), and yield (synthesis_id, db_path)."""
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    tmp = tempfile.mkdtemp(prefix="antiek-earn-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    init_database_at_path(db_path)

    with connect_write(db_path, purpose="seed") as con:
        specs = [
            ("doc-public", PUBLIC, "h_pub"),
            ("doc-restricted", RESTRICTED, "h_rest"),
            ("doc-personal", PERSONAL, "h_pers"),
        ]
        chunk_ids = {}
        for doc_id, cc, holder in specs:
            insert_document(
                con, document_id=doc_id, source_tier=1, document_type="academic_paper",
                title=f"Title {doc_id}", content_class=cc, ip_holder_id=holder,
            )
            chunk_ids[doc_id] = insert_chunk(
                con, document_id=doc_id, chunk_index=0, text=f"{doc_id} text.",
            )
        thesis = {
            "thesis_components": [
                {"claim": f"C-{doc_id}", "confidence": "high",
                 "supporting_chunk_ids": [chunk_ids[doc_id]]}
                for doc_id, _, _ in specs
            ],
        }
        con.execute(
            "INSERT INTO syntheses "
            "(synthesis_id, investigation_id, target_question, synthesis_timestamp, "
            " status, implicit_recommendation, thesis, thesis_token_count) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, 0)",
            ["syn-earn-1", "inv-1", "Q?", "passed", "proceed", json.dumps(thesis)],
        )
    yield {"synthesis_id": "syn-earn-1", "db_path": db_path}


def test_earn_split_retains_restricted_excludes_personal_and_conserves(
    synthesis_with_mixed_sources,
) -> None:
    """The §9.10 invariant against a real synthesis: personal_reading earns nothing,
    restricted_pending_opt_in earns to escrow, every cent conserved."""
    lines = resolve_and_split_synthesis_earn(
        synthesis_with_mixed_sources["synthesis_id"], total_cents=300,
        db_path=synthesis_with_mixed_sources["db_path"], algorithm="A",
    )
    by_doc = {ln.document_id: ln for ln in lines}

    assert "doc-personal" not in by_doc, "personal_reading must never earn"
    assert "doc-restricted" in by_doc, "restricted_pending_opt_in must earn (§9.10)"
    assert by_doc["doc-restricted"].ip_holder_id == "h_rest"
    # public + restricted split 300 equally after personal is gated out.
    assert by_doc["doc-public"].cents == 150
    assert by_doc["doc-restricted"].cents == 150
    assert sum(ln.cents for ln in lines) == 300


def test_display_drops_restricted_but_earn_retains_it(
    synthesis_with_mixed_sources,
) -> None:
    """The two surfaces over the SAME synthesis diverge exactly at §9.10. Display
    attribution (compute.py) drops BOTH restricted and personal; the earn split retains
    restricted. This is the entire point of sharing one resolution but applying two gates."""
    sid = synthesis_with_mixed_sources["synthesis_id"]
    db = synthesis_with_mixed_sources["db_path"]

    display = compute_attribution_for_synthesis(sid, db_path=db).option_a.shares
    earn = {ln.document_id for ln in resolve_and_split_synthesis_earn(
        sid, total_cents=300, db_path=db, algorithm="A")}

    # Display: neither restricted nor personal receives a surfaced share.
    assert "doc-restricted" not in display
    assert "doc-personal" not in display
    assert "doc-public" in display
    # Earn: restricted IS retained (the §9.10 escrow accrual), personal still excluded.
    assert "doc-restricted" in earn
    assert "doc-personal" not in earn
    assert "doc-public" in earn


def test_unknown_synthesis_raises(synthesis_with_mixed_sources) -> None:
    with pytest.raises(ValueError, match="not found"):
        resolve_and_split_synthesis_earn(
            "syn-nope", total_cents=100,
            db_path=synthesis_with_mixed_sources["db_path"],
        )
