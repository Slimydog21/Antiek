"""Notebook block delete + reorder endpoint tests."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-nb-blocks-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client():
    return TestClient(create_app(register_wrestling=False))


def _create_notebook_with_blocks(client: TestClient, n: int = 3) -> tuple[str, list[str]]:
    r = client.post(
        "/notebooks",
        json={"title": "test", "investigation_id": "inv-1"},
    )
    assert r.status_code in (200, 201), r.text
    nb_id = r.json()["notebook_id"]
    block_ids: list[str] = []
    for i in range(n):
        ar = client.post(
            f"/notebooks/{nb_id}/blocks",
            json={
                "block_type": "prose",
                "ref_id": None,
                "content": {"text": f"block {i}"},
            },
        )
        assert ar.status_code in (200, 201), ar.text
        blocks = ar.json()["blocks"]
        # The most recently appended block has the highest index.
        block_ids.append(max(blocks, key=lambda b: b["block_index"])["block_id"])
    return nb_id, block_ids


# ── Delete block ────────────────────────────────────────────────────


def test_delete_block_removes_row_and_renumbers(isolated_db):
    client = _client()
    nb_id, block_ids = _create_notebook_with_blocks(client, n=3)
    # Delete the middle block.
    resp = client.delete(
        f"/notebooks/{nb_id}/blocks/{block_ids[1]}",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["blocks"]) == 2
    # Indexes should still be 0..1 contiguously.
    indexes = sorted(b["block_index"] for b in body["blocks"])
    assert indexes == [0, 1]
    # The middle block is gone; first and third remain.
    remaining_ids = {b["block_id"] for b in body["blocks"]}
    assert block_ids[0] in remaining_ids
    assert block_ids[2] in remaining_ids
    assert block_ids[1] not in remaining_ids


def test_delete_block_404_when_missing(isolated_db):
    client = _client()
    nb_id, _ = _create_notebook_with_blocks(client, n=1)
    resp = client.delete(
        f"/notebooks/{nb_id}/blocks/does-not-exist",
    )
    assert resp.status_code == 404


def test_delete_block_404_when_notebook_missing(isolated_db):
    client = _client()
    resp = client.delete(
        "/notebooks/does-not-exist/blocks/does-not-exist",
    )
    assert resp.status_code == 404


# ── Reorder blocks ─────────────────────────────────────────────────


def test_reorder_blocks_permutes_indexes(isolated_db):
    client = _client()
    nb_id, block_ids = _create_notebook_with_blocks(client, n=3)
    # Reverse the order.
    new_order = list(reversed(block_ids))
    resp = client.post(
        f"/notebooks/{nb_id}/blocks/reorder",
        json={"ordered_block_ids": new_order},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # The block at index 0 should now be what was originally last.
    by_index = sorted(body["blocks"], key=lambda b: b["block_index"])
    assert by_index[0]["block_id"] == new_order[0]
    assert by_index[1]["block_id"] == new_order[1]
    assert by_index[2]["block_id"] == new_order[2]


def test_reorder_blocks_rejects_partial_permutation(isolated_db):
    client = _client()
    nb_id, block_ids = _create_notebook_with_blocks(client, n=3)
    # Missing one — reorder must reject.
    resp = client.post(
        f"/notebooks/{nb_id}/blocks/reorder",
        json={"ordered_block_ids": block_ids[:2]},
    )
    assert resp.status_code == 422, resp.text


def test_reorder_blocks_rejects_unknown_block_id(isolated_db):
    client = _client()
    nb_id, block_ids = _create_notebook_with_blocks(client, n=2)
    resp = client.post(
        f"/notebooks/{nb_id}/blocks/reorder",
        json={
            "ordered_block_ids": block_ids + ["unknown-block-id"],
        },
    )
    assert resp.status_code == 422


def test_reorder_blocks_404_when_notebook_missing(isolated_db):
    client = _client()
    resp = client.post(
        "/notebooks/does-not-exist/blocks/reorder",
        json={"ordered_block_ids": ["whatever"]},
    )
    assert resp.status_code == 404


def test_reorder_blocks_idempotent_on_same_order(isolated_db):
    """Reordering to the existing order is a no-op."""
    client = _client()
    nb_id, block_ids = _create_notebook_with_blocks(client, n=3)
    resp = client.post(
        f"/notebooks/{nb_id}/blocks/reorder",
        json={"ordered_block_ids": block_ids},
    )
    assert resp.status_code == 200
    body = resp.json()
    by_index = sorted(body["blocks"], key=lambda b: b["block_index"])
    for i, b in enumerate(by_index):
        assert b["block_id"] == block_ids[i]
