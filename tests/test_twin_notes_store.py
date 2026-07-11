"""Red-proofs: twin-notes substrate record/load/merge + HTTP."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_notes_routes import (
    register_twin_notes_routes,
    set_twin_notes_store,
)
from substrate.twin_notes.store import (
    TwinNotesStore,
    TwinNotFound,
    TwinParentMismatch,
)


def test_record_and_load_roundtrip(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    doc = store.record(
        "asset-1",
        insights=["Insight A", "  Insight A  "],  # dedupe
        questions=["Why?"],
        source_label="note_taker",
    )
    loaded = store.load(doc.twin_id, parent_asset_id="asset-1")
    assert loaded.insights == ["Insight A"]
    assert loaded.questions == ["Why?"]
    assert loaded.parent_asset_id == "asset-1"
    listed = store.list_for_parent("asset-1")
    assert len(listed) == 1 and listed[0].twin_id == doc.twin_id


def test_cross_parent_merge_rejected(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    a = store.record("asset-a", insights=["A"])
    b = store.record("asset-b", insights=["B"])
    try:
        store.merge([a.twin_id, b.twin_id])
        raise AssertionError("expected TwinParentMismatch")
    except TwinParentMismatch:
        pass


def test_same_parent_merge_unions_and_is_stable(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    a = store.record("doc-9", insights=["i1", "i2"], questions=["q1"])
    b = store.record("doc-9", insights=["i2", "i3"], questions=["q2"])
    m1 = store.merge([a.twin_id, b.twin_id], parent_asset_id="doc-9", now=100.0)
    assert set(m1.insights) == {"i1", "i2", "i3"}
    assert set(m1.questions) == {"q1", "q2"}
    assert a.twin_id in m1.merged_from and b.twin_id in m1.merged_from
    # Double-merge stable: same twin_id, same content multiset.
    m2 = store.merge([a.twin_id, b.twin_id], parent_asset_id="doc-9", now=200.0)
    assert m2.twin_id == m1.twin_id
    assert set(m2.insights) == set(m1.insights)
    assert set(m2.questions) == set(m1.questions)
    assert m2.created_at == m1.created_at  # preserved on upsert
    assert m2.updated_at == 200.0


def test_load_missing_raises(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    try:
        store.load("twin-nope")
        raise AssertionError("expected TwinNotFound")
    except TwinNotFound:
        pass


def test_sanitized_parent_filename_collision_does_not_clobber(tmp_path: Path) -> None:
    """Distinct parents that sanitize to the same stem must not share a file."""
    store = TwinNotesStore(tmp_path)
    first = store.record("../a", insights=["first"])
    second = store.record(".. ?a", insights=["second"])
    assert first.twin_id != second.twin_id
    assert store.load(first.twin_id).insights == ["first"]
    assert store.load(second.twin_id).insights == ["second"]
    assert len(store.list_for_parent("../a")) == 1
    assert len(store.list_for_parent(".. ?a")) == 1
    # Distinct on-disk files under root.
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 2


def test_http_record_list_merge(tmp_path: Path) -> None:
    store = TwinNotesStore(tmp_path)
    set_twin_notes_store(store)
    app = FastAPI()
    register_twin_notes_routes(app)
    client = TestClient(app)

    r1 = client.post(
        "/twins",
        json={
            "parent_asset_id": "html-asset-1",
            "insights": ["Alpha"],
            "questions": ["Q1?"],
        },
    )
    assert r1.status_code == 200, r1.text
    t1 = r1.json()["twin_id"]
    r2 = client.post(
        "/twins",
        json={
            "parent_asset_id": "html-asset-1",
            "insights": ["Beta"],
            "questions": ["Q2?"],
        },
    )
    t2 = r2.json()["twin_id"]

    listed = client.get("/twins/by-parent/html-asset-1")
    assert listed.status_code == 200
    assert len(listed.json()["twins"]) == 2

    merged = client.post(
        "/twins/merge",
        json={"twin_ids": [t1, t2], "parent_asset_id": "html-asset-1"},
    )
    assert merged.status_code == 200, merged.text
    body = merged.json()
    assert set(body["insights"]) == {"Alpha", "Beta"}

    # Cross-parent 409
    other = client.post(
        "/twins",
        json={"parent_asset_id": "other", "insights": ["X"]},
    ).json()["twin_id"]
    bad = client.post("/twins/merge", json={"twin_ids": [t1, other]})
    assert bad.status_code == 409
    assert bad.json()["detail"]["code"] == "cross_parent_merge_rejected"

    set_twin_notes_store(None)
