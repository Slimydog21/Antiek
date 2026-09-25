"""Probe-to-core proofs (reformat-provenance SPR-03).

Real DuckDB + the fixture generator: the derived asset's bites project into
unit 6's evidence base with their provenance refs (consumed, never
duplicated); the evidence API resolves a bite row's full provenance;
from-scratch rebuild parity holds on the new source (unit 6's stable-id
contract exercised); the pull-a-snippet probe is gate-served (metadata-only
for a withheld source); and the ORIGINAL document is byte-identical
end-to-end.
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write
from substrate.companions.evidence_index import read_scope
from substrate.companions.projector import rebuild_document
from substrate.reformat.pipeline import reformat_document
from tests.test_reformat_routes import _fixture_generator, _seed


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    db = tmp_path / "t.duckdb"
    events = tmp_path / "events"
    arts = tmp_path / "artifacts"
    events.mkdir()
    arts.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(arts))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(str(db))
    return {"db": str(db), "events": str(events), "arts": str(arts)}


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False))


def _source_hash(db: str, document_id: str = "doc-1") -> str:
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?", [document_id]
        ).fetchone()
    finally:
        con.close()
    return hashlib.sha256(str(row[0]).encode()).hexdigest()


def _reformatted(api_env) -> dict:
    """The full flow: reformat → the derived document's bites project."""
    result = reformat_document(
        api_env["db"],
        owner_user_id="__operator__",
        source_document_id="doc-1",
        prompt="the 20-minute version",
        mode="time_window",
        params={"model": "fixture-model"},
        generate_fn=_fixture_generator,
        events_dir=api_env["events"],
    )
    rebuild_document(
        api_env["db"],
        owner_user_id="__operator__",
        document_id=result.derived_document_id,
        events_dir=api_env["events"],
    )
    return {
        "generation_id": result.generation_id,
        "derived_document_id": result.derived_document_id,
    }


# ── Proof 2: the evidence-base projection + from-scratch parity ────────────


def test_bites_project_with_provenance_refs_and_stable_ids(api_env) -> None:
    _seed(api_env["db"])
    ids = _reformatted(api_env)
    con = connect_read(api_env["db"])
    try:
        rows = read_scope(
            con,
            owner_user_id="__operator__",
            scope="document",
            scope_id=ids["derived_document_id"],
        )
    finally:
        con.close()
    bite_rows = [r for r in rows if any(ref.startswith("bite:") for ref in r.refs)]
    assert len(bite_rows) == 5  # the fixture generator's five bites
    for row in bite_rows:
        # The full provenance rides the refs: the generation, the class, the
        # document — and the investigation / core spans where lawful.
        assert any(ref == f"generation:{ids['generation_id']}" for ref in row.refs)
        assert any(ref.startswith("class:") for ref in row.refs)
        assert any(ref == f"doc:{ids['derived_document_id']}" for ref in row.refs)
    supplemented = next(
        r for r in bite_rows if "class:research_supplemented" in r.refs
    )
    assert "investigation:inv-dil-1" in supplemented.refs
    compressed = next(r for r in bite_rows if "class:llm_compressed" in r.refs)
    assert any(ref.startswith("corespan:doc-1:") for ref in compressed.refs)
    novel = next(r for r in bite_rows if "class:llm_expanded" in r.refs and not any(ref.startswith("corespan:") for ref in r.refs))
    assert novel is not None  # the honestly sourceless bite projects too

    # The unit-6 parity contract on the NEW source: drop + rebuild →
    # identical ids.
    ids_before = [r.evidence_id for r in bite_rows]
    with connect_write(api_env["db"], purpose="test/drop-scope") as con:
        con.execute(
            "DELETE FROM evidence_index WHERE scope = 'document' AND scope_id = ?",
            [ids["derived_document_id"]],
        )
    rebuild_document(
        api_env["db"],
        owner_user_id="__operator__",
        document_id=ids["derived_document_id"],
        events_dir=api_env["events"],
    )
    con = connect_read(api_env["db"])
    try:
        after = read_scope(
            con,
            owner_user_id="__operator__",
            scope="document",
            scope_id=ids["derived_document_id"],
        )
    finally:
        con.close()
    assert [r.evidence_id for r in after if any(ref.startswith("bite:") for ref in r.refs)] == ids_before


def test_evidence_api_resolves_a_bites_full_provenance(api_env) -> None:
    _seed(api_env["db"])
    ids = _reformatted(api_env)
    client = _client()
    con = connect_read(api_env["db"])
    try:
        rows = read_scope(
            con,
            owner_user_id="__operator__",
            scope="document",
            scope_id=ids["derived_document_id"],
        )
    finally:
        con.close()
    verbatim = next(r for r in rows if "class:author_verbatim" in r.refs)
    resp = client.get(f"/evidence/{verbatim.evidence_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bite"]["contribution_class"] == "author_verbatim"
    assert body["bite"]["byte_verified"] is True
    assert body["bite"]["generation"]["generation_id"] == ids["generation_id"]
    # The owner lane serves the derived document — the bite's text rides.
    assert body["bite"]["text"] is not None
    # The supplemented bite names its investigation.
    supplemented = next(r for r in rows if "class:research_supplemented" in r.refs)
    body2 = client.get(f"/evidence/{supplemented.evidence_id}").json()
    assert body2["bite"]["investigation_id"] == "inv-dil-1"
    # The honestly sourceless bite resolves with null refs, never a
    # fabricated span.
    novel = next(
        r
        for r in rows
        if "class:llm_expanded" in r.refs
        and not any(ref.startswith("corespan:") for ref in r.refs)
    )
    body3 = client.get(f"/evidence/{novel.evidence_id}").json()
    assert body3["bite"]["source_refs"] is None


# ── Proof 4: pull-a-snippet, gate-served ────────────────────────────────────


def test_pull_a_snippet_is_gate_served_and_metadata_only_when_withheld(api_env) -> None:
    _seed(api_env["db"])
    client = _client()
    # Servable: the passage text comes back, the span honestly echoing.
    resp = client.get(
        "/books/doc-1/passage",
        params={"chunk_id": "c-1-doc-1", "start_scalar": 0, "end_scalar": 32},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["servable"] is True
    assert body["text"] == "The pricing argument opens here."
    assert body["page_index_hint"] == 0

    # Withheld (taken-down is absolute — the owner lane too): metadata only.
    _seed(api_env["db"], document_id="doc-dead", content_class="personal_reading")
    with connect_write(api_env["db"], purpose="test/takedown") as con:
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) "
            "VALUES ('doc-dead', TRUE) ON CONFLICT DO NOTHING"
        )
    withheld = client.get(
        "/books/doc-dead/passage",
        params={"chunk_id": "c-1-doc-dead", "start_scalar": 0, "end_scalar": 10},
    )
    assert withheld.status_code == 200
    assert withheld.json()["servable"] is False
    assert withheld.json()["text"] is None
    assert withheld.json()["page_index_hint"] == 0  # position is metadata

    # Unknown chunk → honest 404.
    assert (
        client.get(
            "/books/doc-1/passage",
            params={"chunk_id": "no-such", "start_scalar": 0, "end_scalar": 5},
        ).status_code
        == 404
    )


# ── Proof 5: the original is byte-identical end-to-end ──────────────────────


def test_the_original_is_byte_identical_through_the_whole_flow(api_env) -> None:
    _seed(api_env["db"])
    before = _source_hash(api_env["db"])
    ids = _reformatted(api_env)
    client = _client()
    # Probe: pull the snippet + resolve a bite + re-read the provenance.
    client.get(
        "/books/doc-1/passage",
        params={"chunk_id": "c-1-doc-1", "start_scalar": 0, "end_scalar": 32},
    )
    client.get(f"/documents/{ids['derived_document_id']}/provenance")
    con = connect_read(api_env["db"])
    try:
        rows = read_scope(
            con,
            owner_user_id="__operator__",
            scope="document",
            scope_id=ids["derived_document_id"],
        )
    finally:
        con.close()
    first_bite = next(r for r in rows if any(ref.startswith("bite:") for ref in r.refs))
    client.get(f"/evidence/{first_bite.evidence_id}")
    assert _source_hash(api_env["db"]) == before
