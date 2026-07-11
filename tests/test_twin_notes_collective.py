"""Red-proofs: collective twin pack for multi-instance deep research."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_notes_collective_routes import (
    register_twin_notes_collective_routes,
    set_twin_notes_collective_store,
)
from substrate.twin_notes.collective import build_collective_pack
from substrate.twin_notes.store import TwinNotesError, TwinNotesStore


def test_empty_twins_fail_closed() -> None:
    try:
        build_collective_pack([])
        raise AssertionError("expected TwinNotesError")
    except TwinNotesError:
        pass


def test_multi_twin_pack_includes_provenance(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    a = store.record(
        "asset-a",
        insights=["scaling holds"],
        questions=["What is the compute floor?"],
        source_label="research-1",
    )
    b = store.record(
        "asset-b",
        insights=["sample efficiency matters"],
        questions=[],
        source_label="research-2",
    )
    pack = build_collective_pack(
        [store.load(a.twin_id), store.load(b.twin_id)],
        instruction="Synthesize a joint position.",
    )
    assert a.twin_id in pack.twin_ids and b.twin_id in pack.twin_ids
    assert "asset-a" in pack.parent_asset_ids and "asset-b" in pack.parent_asset_ids
    assert pack.insight_count == 2
    assert pack.question_count == 1
    assert "Synthesize a joint position." in pack.pack_text
    assert a.twin_id in pack.pack_text
    assert "scaling holds" in pack.pack_text
    assert "sample efficiency matters" in pack.pack_text
    assert any("cross-parent" in n for n in pack.notes)
    assert any("does not dispatch" in n for n in pack.notes)


def test_same_parent_collective_no_cross_parent_note(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    a = store.record("one", insights=["A"])
    b = store.record("one", insights=["B"])
    pack = build_collective_pack([store.load(a.twin_id), store.load(b.twin_id)])
    assert pack.parent_asset_ids == ["one"]
    assert not any("cross-parent" in n for n in pack.notes)


def test_http_collective_route(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    a = store.record("p1", insights=["alpha"], questions=["Q?"])
    b = store.record("p2", insights=["beta"])
    set_twin_notes_collective_store(store)
    app = FastAPI()
    register_twin_notes_collective_routes(app)
    client = TestClient(app)
    r = client.post(
        "/twins/collective",
        json={
            "twin_ids": [a.twin_id, b.twin_id],
            "instruction": "Compare both threads.",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["insight_count"] == 2
    assert "Compare both threads." in body["pack_text"]
    assert a.twin_id in body["twin_ids"]
    # missing twin
    miss = client.post(
        "/twins/collective",
        json={"twin_ids": ["twin-nope"]},
    )
    assert miss.status_code == 404
    set_twin_notes_collective_store(None)
