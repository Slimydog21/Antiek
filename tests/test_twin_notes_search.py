"""Red-proofs: twin-notes offline search ranking + HTTP."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_notes_search_routes import (
    register_twin_notes_search_routes,
    set_twin_notes_search_store,
)
from substrate.twin_notes.search import search_store, search_twins
from substrate.twin_notes.store import TwinNotesStore


def test_empty_query_returns_no_hits(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    store.record("p", insights=["scaling laws"])
    assert search_store(store, "   ") == []
    assert search_twins("  ", store.list_for_parent("p")) == []


def test_ranks_matching_insight_higher(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    a = store.record("doc", insights=["scaling laws hold under compute"], questions=[])
    b = store.record("doc", insights=["unrelated gardening tips"], questions=[])
    hits = search_store(store, "scaling compute", parent_asset_id="doc")
    assert hits
    assert hits[0].twin_id == a.twin_id
    assert hits[0].score > 0
    ids = [h.twin_id for h in hits]
    assert a.twin_id in ids
    # gardening should rank lower or be absent
    if b.twin_id in ids:
        assert ids.index(a.twin_id) < ids.index(b.twin_id)


def test_question_match_surfaces_matched_questions(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    store.record(
        "doc",
        insights=["plain fact"],
        questions=["What is the sample-efficiency floor?"],
    )
    hits = search_store(store, "sample efficiency", parent_asset_id="doc")
    assert hits
    assert hits[0].matched_questions
    assert any("sample-efficiency" in q or "sample" in q.lower() for q in hits[0].matched_questions)


def test_http_search_route(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    store.record("asset-z", insights=["arxiv transformer scaling"])
    set_twin_notes_search_store(store)
    app = FastAPI()
    register_twin_notes_search_routes(app)
    client = TestClient(app)
    r = client.get("/twins/search", params={"q": "transformer", "parent_asset_id": "asset-z"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 1
    assert body["hits"][0]["parent_asset_id"] == "asset-z"
    set_twin_notes_search_store(None)


def test_source_label_alone_does_not_match(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    store.record(
        "doc",
        insights=["unrelated body"],
        questions=[],
        source_label="scaling-label-only",
    )
    hits = search_store(store, "scaling-label-only", parent_asset_id="doc")
    assert hits == []


def test_malformed_json_array_skipped_in_global_search(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    store.record("good", insights=["transformer attention"])
    (tmp_path / "junk.json").write_text("[]\n", encoding="utf-8")
    hits = search_store(store, "transformer")
    assert hits
    assert hits[0].parent_asset_id == "good"


def test_http_empty_q_rejected(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    set_twin_notes_search_store(store)
    app = FastAPI()
    register_twin_notes_search_routes(app)
    client = TestClient(app)
    r = client.get("/twins/search", params={"q": "   "})
    # FastAPI min_length or our strip → 422 or 400
    assert r.status_code in (400, 422)
    set_twin_notes_search_store(None)
