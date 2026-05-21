"""Substrate stats + notebook block edit tests."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-stats-edit-")
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


# ── Substrate stats endpoint ───────────────────────────────────────


def test_stats_empty_substrate_returns_zeros(isolated_db):
    client = _client()
    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["counts"], dict)
    # Every documented table is at 0 on a fresh install.
    for key in (
        "investigations",
        "documents",
        "chunks",
        "outcomes",
        "notebooks",
        "notebook_blocks",
        "ip_holders",
        "skill_rules",
        "payout_transfers",
        "deletion_requests",
    ):
        assert body["counts"].get(key) == 0


def test_stats_reflects_inserts(isolated_db):
    client = _client()
    # Create a notebook (1 row).
    client.post(
        "/notebooks",
        json={"title": "test", "investigation_id": "inv-1"},
    )
    # Add two blocks.
    nb_id = client.post(
        "/notebooks",
        json={"title": "test2", "investigation_id": "inv-2"},
    ).json()["notebook_id"]
    for i in range(2):
        client.post(
            f"/notebooks/{nb_id}/blocks",
            json={
                "block_type": "prose",
                "content": {"text": f"block {i}"},
            },
        )
    resp = client.get("/stats")
    body = resp.json()
    assert body["counts"]["notebooks"] == 2
    assert body["counts"]["notebook_blocks"] == 2


# ── Notebook block PATCH ─────────────────────────────────────────


def _create_notebook_with_one_block(client: TestClient) -> tuple[str, str]:
    r = client.post(
        "/notebooks",
        json={"title": "test", "investigation_id": "inv-1"},
    )
    nb_id = r.json()["notebook_id"]
    ar = client.post(
        f"/notebooks/{nb_id}/blocks",
        json={
            "block_type": "prose",
            "ref_id": "ref-original",
            "content": {"text": "v1"},
        },
    )
    block_id = ar.json()["blocks"][0]["block_id"]
    return nb_id, block_id


def test_patch_block_replaces_content(isolated_db):
    client = _client()
    nb_id, block_id = _create_notebook_with_one_block(client)
    resp = client.patch(
        f"/notebooks/{nb_id}/blocks/{block_id}",
        json={"content": {"text": "v2 — edited"}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    [block] = body["blocks"]
    assert block["content_json"]["text"] == "v2 — edited"
    # ref_id should be untouched (we didn't pass it).
    assert block["ref_id"] == "ref-original"


def test_patch_block_sets_ref_id(isolated_db):
    client = _client()
    nb_id, block_id = _create_notebook_with_one_block(client)
    resp = client.patch(
        f"/notebooks/{nb_id}/blocks/{block_id}",
        json={"ref_id": "ref-new"},
    )
    assert resp.status_code == 200
    [block] = resp.json()["blocks"]
    assert block["ref_id"] == "ref-new"
    # content_json untouched.
    assert block["content_json"]["text"] == "v1"


def test_patch_block_clears_ref_id(isolated_db):
    client = _client()
    nb_id, block_id = _create_notebook_with_one_block(client)
    resp = client.patch(
        f"/notebooks/{nb_id}/blocks/{block_id}",
        json={"clear_ref_id": True},
    )
    assert resp.status_code == 200
    [block] = resp.json()["blocks"]
    assert block["ref_id"] is None


def test_patch_block_no_op_is_success(isolated_db):
    """Empty body (no content + no ref_id changes) is a no-op success
    — the substrate doesn't reject; the operator may be using PATCH
    as a touchpoint to bump updated_at."""
    client = _client()
    nb_id, block_id = _create_notebook_with_one_block(client)
    resp = client.patch(
        f"/notebooks/{nb_id}/blocks/{block_id}",
        json={},
    )
    assert resp.status_code == 200


def test_patch_missing_block_returns_404(isolated_db):
    client = _client()
    nb_id, _ = _create_notebook_with_one_block(client)
    resp = client.patch(
        f"/notebooks/{nb_id}/blocks/does-not-exist",
        json={"content": {"text": "ignored"}},
    )
    assert resp.status_code == 404


def test_patch_missing_notebook_returns_404(isolated_db):
    client = _client()
    resp = client.patch(
        "/notebooks/does-not-exist/blocks/does-not-exist",
        json={"content": {"text": "x"}},
    )
    assert resp.status_code == 404
