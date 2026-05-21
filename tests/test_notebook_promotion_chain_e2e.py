"""Notebook publication chain end-to-end.

Drives the full publication path:
  user_owned notebook with prose + tier-1 citation
    → POST /notebooks/{id}/promote-public
    → gather_quality_gate_inputs walks blocks
    → evaluate_notebook_for_public runs verification + voice-style + source-tier
    → typed quality_gate.evaluated event emitted
    → content_class flips to user_public_contribution
    → notebook now visible in user_public_contribution filter

The /force=true override path is also exercised: failing rubric +
force still records the verdict in the audit log.
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
    tmpdir = tempfile.mkdtemp(prefix="antiek-promo-chain-")
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


def _strip_action_type(evt) -> str:
    at = evt.action_type
    return at.value if hasattr(at, "value") else at


def _seed_tier1_chunk(db_path: str) -> str:
    """Seed one tier-1 document + chunk so the source-tier rubric
    can pass."""
    from runtime.db_lock import connect_write

    doc_id = f"doc-{uuid.uuid4().hex[:10]}"
    chunk_id = f"chunk-{uuid.uuid4().hex[:10]}"
    with connect_write(db_path, purpose="test:seed_tier1") as con:
        con.execute(
            "INSERT INTO documents ("
            "document_id, source_tier, document_type, source_uri, title"
            ") VALUES (?, 1, 'pdf', 'file:///t1.pdf', 'Tier 1 paper')",
            [doc_id],
        )
        con.execute(
            "INSERT INTO chunks ("
            "chunk_id, document_id, chunk_index, text, token_count"
            ") VALUES (?, ?, 0, 'cited text', 5)",
            [chunk_id, doc_id],
        )
    return chunk_id


def _create_notebook_with_block(
    client: TestClient,
    *,
    prose_text: str,
    citation_chunk_id: str | None,
) -> str:
    """Create a notebook + (optional) prose block + (optional) citation."""
    r = client.post(
        "/notebooks",
        json={"title": "test", "investigation_id": "inv-1"},
    )
    nb_id = r.json()["notebook_id"]
    client.post(
        f"/notebooks/{nb_id}/blocks",
        json={
            "block_type": "prose",
            "ref_id": None,
            "content": {"text": prose_text},
        },
    )
    if citation_chunk_id:
        client.post(
            f"/notebooks/{nb_id}/blocks",
            json={
                "block_type": "region_embed",
                "ref_id": citation_chunk_id,
                "content": {"caption": "tier-1 ref"},
            },
        )
    return nb_id


# ── Happy path: passes gate + lands public + emits event ─────────


def test_publication_happy_path_emits_event_and_flips_state(isolated_db):
    chunk_id = _seed_tier1_chunk(isolated_db)
    client, rec = _client_with_bus()
    nb_id = _create_notebook_with_block(
        client,
        prose_text=(
            "Neutral-atom platforms reached gate error rates below "
            "10⁻³ at 100-qubit scale. The cross-comparison with "
            "trapped-ion systems shows similar performance."
        ),
        citation_chunk_id=chunk_id,
    )

    resp = client.post(
        f"/notebooks/{nb_id}/promote-public?rubric_score=0.95",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["content_class"] == "user_public_contribution"

    # Audit event: quality_gate.evaluated with accepted=True.
    quality_events = [
        e for e in rec.events
        if _strip_action_type(e) == "quality_gate.evaluated"
    ]
    assert len(quality_events) == 1
    p = quality_events[0].payload
    assert p.accepted is True
    assert p.target_kind == "notebook"
    assert p.target_id == nb_id

    # Listing the public notebooks shows the promoted notebook.
    listing = client.get("/notebooks").json()
    public_notebooks = [
        n for n in listing["notebooks"]
        if n["content_class"] == "user_public_contribution"
    ]
    assert any(n["notebook_id"] == nb_id for n in public_notebooks)


# ── Failing path: gate refuses + event emits + state unchanged ───


def test_publication_failing_path_emits_event_but_blocks(isolated_db):
    client, rec = _client_with_bus()
    nb_id = _create_notebook_with_block(
        client,
        # Voice-style failure: em-dash storm + padding phrases.
        prose_text=(
            "It is important to note that—indeed—the analysis—"
            "indeed—shows the expected outcome. Furthermore, it is "
            "worth noting that—indeed—the pattern—indeed—holds. " * 6
        ),
        citation_chunk_id=None,  # no citations → source-tier fails too
    )

    resp = client.post(f"/notebooks/{nb_id}/promote-public")
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["code"] == "quality_gate_failed"

    # Event emits even on failure (audit-trail invariant).
    quality_events = [
        e for e in rec.events
        if _strip_action_type(e) == "quality_gate.evaluated"
    ]
    assert len(quality_events) == 1
    assert quality_events[0].payload.accepted is False

    # State unchanged — still user_owned.
    notebook = client.get(f"/notebooks/{nb_id}").json()
    assert notebook["content_class"] == "user_owned"


# ── force=true: skips refusal but records the gate verdict ───────


def test_force_override_records_failing_verdict_in_audit(isolated_db):
    client, rec = _client_with_bus()
    nb_id = _create_notebook_with_block(
        client,
        prose_text="thin—prose—" * 100,
        citation_chunk_id=None,
    )

    resp = client.post(f"/notebooks/{nb_id}/promote-public?force=true")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["content_class"] == "user_public_contribution"

    # Audit captures the failing verdict; the operator override is
    # implicit (force=true) but the event preserves the gate truth.
    quality_events = [
        e for e in rec.events
        if _strip_action_type(e) == "quality_gate.evaluated"
    ]
    assert len(quality_events) == 1
    assert quality_events[0].payload.accepted is False
    # ... yet the notebook is now public.
    notebook = client.get(f"/notebooks/{nb_id}").json()
    assert notebook["content_class"] == "user_public_contribution"


# ── Twice-promotion is a no-op (idempotent state machine) ───────


def test_double_promotion_is_idempotent(isolated_db):
    """Promoting an already-public notebook surfaces the gate
    verdict but the content_class doesn't toggle back."""
    chunk_id = _seed_tier1_chunk(isolated_db)
    client, rec = _client_with_bus()
    nb_id = _create_notebook_with_block(
        client,
        prose_text=(
            "Neutral-atom platforms reached gate error rates below "
            "10⁻³ at 100-qubit scale. Cross-comparison verified."
        ),
        citation_chunk_id=chunk_id,
    )

    first = client.post(
        f"/notebooks/{nb_id}/promote-public?rubric_score=0.95",
    )
    assert first.status_code == 200
    first_state = first.json()["content_class"]
    assert first_state == "user_public_contribution"

    second = client.post(
        f"/notebooks/{nb_id}/promote-public?rubric_score=0.95",
    )
    assert second.status_code == 200
    second_state = second.json()["content_class"]
    assert second_state == "user_public_contribution"

    # Two events emitted — operator can see the re-evaluation in
    # the audit log even though state didn't change.
    quality_events = [
        e for e in rec.events
        if _strip_action_type(e) == "quality_gate.evaluated"
    ]
    assert len(quality_events) == 2
