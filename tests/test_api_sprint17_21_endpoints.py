"""Sprint 17-21 endpoint contract tests.

Covers:
  - POST /thought-partner — AISidecar one-shot reply surface
  - POST /voice/sessions/{id}/upload — InterviewVoiceCapture raw-body
    upload contract
  - POST /cross-graph/citations — typed event emission verification
  - POST /quality-gate/evaluate — conditional typed event emission
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


def _client():
    return TestClient(create_app(register_wrestling=False))


# ── Thought partner ─────────────────────────────────────────────────


def test_thought_partner_returns_shape_and_text():
    client = _client()
    resp = client.post(
        "/thought-partner",
        json={"prompt": "Is liquid democracy compatible with multi-camera attention?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["shape"] in {"challenge", "synthesis", "extension"}
    assert isinstance(body["text"], str) and body["text"].strip()


def test_thought_partner_rejects_empty_prompt():
    client = _client()
    resp = client.post("/thought-partner", json={"prompt": "   "})
    assert resp.status_code == 400


# ── Voice upload ────────────────────────────────────────────────────


def test_voice_upload_accepts_raw_body():
    client = _client()
    audio_bytes = b"\x00" * 1024  # 1 KiB of silence — content doesn't matter
    resp = client.post(
        "/voice/sessions/session-xyz/upload?duration_seconds=12",
        content=audio_bytes,
        headers={"Content-Type": "audio/webm"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session_id"] == "session-xyz"
    assert body["bytes_received"] == 1024
    assert body["duration_seconds"] == 12
    assert body["audio_url"] == "/voice/sessions/session-xyz/audio"


def test_voice_upload_defaults_duration_to_zero():
    client = _client()
    resp = client.post(
        "/voice/sessions/s1/upload",
        content=b"abc",
        headers={"Content-Type": "audio/webm"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["duration_seconds"] == 0
    assert body["bytes_received"] == 3


# ── Typed event emission verification ──────────────────────────────


class _RecordingBroadcaster:
    """Captures every Event passed through broadcast()."""

    def __init__(self) -> None:
        self.events: list = []

    async def broadcast(self, event) -> None:
        self.events.append(event)


def test_cross_graph_citation_emits_typed_event(monkeypatch):
    """POST /cross-graph/citations broadcasts the typed
    cross_graph.citation.recorded event."""
    rec = _RecordingBroadcaster()
    app = create_app(register_wrestling=False)
    app.state.broadcaster = rec
    client = TestClient(app)
    resp = client.post(
        "/cross-graph/citations",
        json={
            "referencing_user_id": "user-B",
            "referencing_investigation_id": "inv-1",
            "referenced_user_id": "user-A",
            "referenced_note_id": "note-7",
        },
    )
    assert resp.status_code == 200
    assert len(rec.events) == 1
    evt = rec.events[0]
    assert evt.action_type == "cross_graph.citation.recorded"
    assert evt.payload.referenced_user_id == "user-A"


def _strip_action_type(evt) -> str:
    """The Event model has use_enum_values=True so action_type
    serializes to the str value, but the payload's discriminator is
    still the enum. This helper keeps the comparison code uniform."""
    at = evt.action_type
    return at.value if hasattr(at, "value") else at


def test_quality_gate_emits_event_only_when_target_identified():
    """The endpoint emits a typed event only when both target_id +
    target_kind are present in the request."""
    rec = _RecordingBroadcaster()
    app = create_app(register_wrestling=False)
    app.state.broadcaster = rec
    client = TestClient(app)

    # Generic evaluation — no target — must NOT emit.
    resp1 = client.post(
        "/quality-gate/evaluate",
        json={
            "text_content": "Some text content for evaluation.",
            "cited_chunk_tiers": [1, 2],
            "corpus_sector_terms": ["x"],
            "rubric_score": 0.8,
        },
    )
    assert resp1.status_code == 200
    assert rec.events == []

    # Targeted evaluation — both fields — must emit.
    resp2 = client.post(
        "/quality-gate/evaluate",
        json={
            "text_content": "Some text content for evaluation.",
            "cited_chunk_tiers": [1, 2],
            "corpus_sector_terms": ["x"],
            "rubric_score": 0.8,
            "target_id": "nb-42",
            "target_kind": "notebook",
        },
    )
    assert resp2.status_code == 200
    assert len(rec.events) == 1
    evt = rec.events[0]
    assert _strip_action_type(evt) == "quality_gate.evaluated"
    assert evt.payload.target_id == "nb-42"
    assert evt.payload.target_kind == "notebook"


def test_quality_gate_ignores_unknown_target_kind():
    """Unknown target_kind → no emission (defensive)."""
    rec = _RecordingBroadcaster()
    app = create_app(register_wrestling=False)
    app.state.broadcaster = rec
    client = TestClient(app)
    resp = client.post(
        "/quality-gate/evaluate",
        json={
            "text_content": "x",
            "cited_chunk_tiers": [1],
            "rubric_score": 0.5,
            "target_id": "x",
            "target_kind": "unrecognized_kind",
        },
    )
    assert resp.status_code == 200
    assert rec.events == []
