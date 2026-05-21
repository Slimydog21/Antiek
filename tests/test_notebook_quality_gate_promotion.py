"""Notebook promote-to-public quality-gate enforcement tests.

Covers master-spec §13.9 binding behavior:
  - A failing gate refuses promotion with 422 + structured reasons.
  - ?force=true overrides the gate (operator-authorized publishing).
  - The gate verdict always lands in the typed event log
    (quality_gate.evaluated) regardless of the promotion outcome.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-notebook-qg-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class _RecordingBroadcaster:
    def __init__(self) -> None:
        self.events: list = []

    async def broadcast(self, event) -> None:
        self.events.append(event)


def _client_with_bus():
    app = create_app(register_wrestling=False)
    rec = _RecordingBroadcaster()
    app.state.broadcaster = rec
    return TestClient(app), rec


def _create_notebook(client: TestClient, *, title: str = "test") -> str:
    resp = client.post(
        "/notebooks",
        json={"title": title, "investigation_id": "inv-1"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["notebook_id"]


def _add_prose_block(client: TestClient, notebook_id: str, text: str) -> None:
    resp = client.post(
        f"/notebooks/{notebook_id}/blocks",
        json={
            "block_type": "prose",
            "ref_id": None,
            "content": {"text": text},
        },
    )
    assert resp.status_code in (200, 201), resp.text


# ── Failing gate refuses promotion ────────────────────────────────────


def test_promotion_blocked_when_quality_gate_fails(isolated_db):
    """Slop-laden notebook with no tier-1/2 citations → 422."""
    client, rec = _client_with_bus()
    nb_id = _create_notebook(client)
    # Voice-style heavy with em-dashes + padding phrases.
    slop_text = (
        "It is important to note that—indeed—the analysis—indeed—"
        "shows—indeed—the expected outcome. Furthermore, it is worth "
        "noting that—indeed—the pattern—indeed—holds. Additionally, "
        "it can be argued that—indeed—we may conclude—indeed—what "
        "we already believed. " * 10
    )
    _add_prose_block(client, nb_id, slop_text)

    resp = client.post(f"/notebooks/{nb_id}/promote-public")
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "quality_gate_failed"
    assert isinstance(detail["reasons"], list)
    assert detail["voice_style_passed"] is False

    # The quality-gate event should still have been emitted.
    quality_events = [
        e for e in rec.events
        if (e.action_type.value if hasattr(e.action_type, "value") else e.action_type)
        == "quality_gate.evaluated"
    ]
    assert len(quality_events) == 1
    assert quality_events[0].payload.accepted is False


# ── force=true overrides the gate ──────────────────────────────────


def test_force_override_promotes_despite_failing_gate(isolated_db):
    """force=true skips the 422 path. The event log still records
    accepted=False so the audit trail surfaces the override."""
    client, rec = _client_with_bus()
    nb_id = _create_notebook(client)
    slop = "Not great writing—indeed—" * 200
    _add_prose_block(client, nb_id, slop)

    resp = client.post(f"/notebooks/{nb_id}/promote-public?force=true")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["content_class"] == "user_public_contribution"

    quality_events = [
        e for e in rec.events
        if (e.action_type.value if hasattr(e.action_type, "value") else e.action_type)
        == "quality_gate.evaluated"
    ]
    assert len(quality_events) == 1
    # accepted=False but promotion proceeded — the audit trail shows it.
    assert quality_events[0].payload.accepted is False


# ── Successful gate path emits accepted=True event ─────────────────


def _seed_tier1_chunk(db_path: str) -> str:
    """Seed a tier-1 document + chunk so a notebook can cite it.
    Returns the chunk_id."""
    from runtime.db_lock import connect_write

    doc_id = f"doc-{uuid.uuid4().hex[:10]}"
    chunk_id = f"chunk-{uuid.uuid4().hex[:10]}"
    with connect_write(db_path, purpose="test:seed_tier1") as con:
        con.execute(
            "INSERT INTO documents ("
            "document_id, source_tier, document_type, source_uri, title"
            ") VALUES (?, 1, 'pdf', 'file:///test.pdf', 'Tier 1 paper')",
            [doc_id],
        )
        con.execute(
            "INSERT INTO chunks ("
            "chunk_id, document_id, chunk_index, text, token_count"
            ") VALUES (?, ?, 0, 'cited text', 5)",
            [chunk_id, doc_id],
        )
    return chunk_id


def test_promotion_succeeds_when_gate_passes(isolated_db):
    """Clean prose + tier-1 citation + acceptable rubric → 200 +
    accepted=True event."""
    client, rec = _client_with_bus()
    chunk_id = _seed_tier1_chunk(isolated_db)
    nb_id = _create_notebook(client)
    # Short, lean prose — no em-dash storm, no padding phrases.
    _add_prose_block(
        client, nb_id,
        "Neutral-atom platforms reached gate error rates below 10⁻³ "
        "at 100-qubit scale. The cross-comparison with trapped-ion "
        "systems shows similar performance. The pattern holds across "
        "all three independent measurements.",
    )
    # Citation block referencing the tier-1 chunk.
    add_resp = client.post(
        f"/notebooks/{nb_id}/blocks",
        json={
            "block_type": "region_embed",
            "ref_id": chunk_id,
            "content": {"caption": "tier-1 reference"},
        },
    )
    assert add_resp.status_code in (200, 201), add_resp.text

    resp = client.post(
        f"/notebooks/{nb_id}/promote-public?rubric_score=0.95",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["content_class"] == "user_public_contribution"

    quality_events = [
        e for e in rec.events
        if (e.action_type.value if hasattr(e.action_type, "value") else e.action_type)
        == "quality_gate.evaluated"
    ]
    assert len(quality_events) == 1
    assert quality_events[0].payload.accepted is True
    assert quality_events[0].payload.target_id == nb_id
    assert quality_events[0].payload.target_kind == "notebook"


# ── Missing notebook ──────────────────────────────────────────────


def test_promotion_404_on_missing_notebook(isolated_db):
    client, _ = _client_with_bus()
    resp = client.post("/notebooks/does-not-exist/promote-public")
    assert resp.status_code == 404
