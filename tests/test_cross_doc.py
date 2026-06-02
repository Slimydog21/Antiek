"""Tests for cross-document question→answer linking (Sprint 4 day 2-3).

The operator's differentiator from Sprint 1: "a question in one
document can get the answer that gets delivered after wrestling with
another document".

Coverage:

1. Happy path — question identified on doc-A, related note emerges
   on doc-B above the cosine threshold → cross_doc.question_answered
   fires with both document_ids.
2. Same-doc skip — note emerges on the same document as the
   question's home → NOT a cross-doc match.
3. Threshold gate — note below threshold → no event.
4. Deduplication — once a question is cross-linked, a SECOND
   matching note doesn't fire a second event.
5. question.resolved_by_doc removes from open set — subsequent
   matching note doesn't fire (the question was resolved through
   another path).
6. Per-investigation isolation — events on inv-A don't link to
   questions on inv-B.
7. CROSS_DOC_QUESTION_ANSWERED has no envelope document_id (the
   payload carries both — verified for the §13.3 carve-out).
8. Multiple open questions: one note can resolve one of them; the
   others remain open for future notes.

Tests use the HashEmbedding fallback (env-pinned). The
ANTIEK_CROSS_DOC_THRESHOLD env var is pinned to 0.25 in the fixtures
so hash-based cosine similarity reliably crosses for word-overlapping
text without false positives.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import EventBroadcaster, create_app  # noqa: E402
from interfaces.research.api.cross_doc import _cosine  # noqa: E402
from processing.embedding import _reset_default_provider  # noqa: E402
from substrate.dispatch import reset_provider_registry  # noqa: E402
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    CrossDocQuestionAnsweredPayload,
    Event,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    # Threshold pinned LOW because the hash fallback's cosine sim
    # caps lower than semantic embeddings. With heavy word overlap
    # in the test data, ~0.25 is enough to cross while still
    # rejecting truly unrelated text.
    monkeypatch.setenv("ANTIEK_CROSS_DOC_THRESHOLD", "0.25")
    # Note-taker stays out of the way — high threshold so it doesn't
    # fire during cross-doc tests and pollute the trajectory with
    # spurious note.emerged events.
    monkeypatch.setenv("ANTIEK_NOTE_TAKER_THRESHOLD", "10000")
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


@pytest.fixture
def app_and_bus():
    bus = EventBroadcaster()
    app = create_app(broadcaster=bus, cors_origins=[])
    return app, bus


@pytest.fixture
async def async_client(app_and_bus):
    app, _ = app_and_bus
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helpers — post events directly
# ---------------------------------------------------------------------------


async def _post_question(ac, *, investigation_id, document_id, question_id, text):
    r = await ac.post(
        "/events/typed",
        json={
            "investigation_id": investigation_id,
            "document_id": document_id,
            "payload": {
                "action_type": "question.identified",
                "question_id": question_id,
                "question_text": text,
            },
            "role": "user_agent",
        },
    )
    assert r.status_code == 201, r.text


async def _post_note(ac, *, investigation_id, document_id, note_id, text,
                     source_event_ids=("evt-fake",)):
    r = await ac.post(
        "/events/typed",
        json={
            "investigation_id": investigation_id,
            "document_id": document_id,
            "payload": {
                "action_type": "note.emerged",
                "note_id": note_id,
                "note_text": text,
                "source_event_ids": list(source_event_ids),
            },
            "role": "note_taker",
        },
    )
    assert r.status_code == 201, r.text


async def _post_question_resolved(ac, *, investigation_id, document_id, question_id, answer_note_id):
    r = await ac.post(
        "/events/typed",
        json={
            "investigation_id": investigation_id,
            "document_id": document_id,
            "payload": {
                "action_type": "question.resolved_by_doc",
                "question_id": question_id,
                "answer_note_id": answer_note_id,
            },
            "role": "user_agent",
        },
    )
    assert r.status_code == 201, r.text


def _cross_doc_events(inv: str) -> list[dict]:
    return [
        r for r in trajectory(inv)
        if r["action_type"] == "cross_doc.question_answered"
    ]


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_question_in_doc_a_answered_by_note_in_doc_b(app_and_bus, async_client):
    _, bus = app_and_bus
    inv = "inv-happy"

    await _post_question(
        async_client, investigation_id=inv, document_id="doc-A",
        question_id="q-1",
        text="how does photonic measurement-based gate fidelity scale with qubit count",
    )
    await _post_note(
        async_client, investigation_id=inv, document_id="doc-B",
        note_id="n-1",
        text="photonic measurement-based gate fidelity scales sublinearly with qubit count due to loss tolerance",
    )
    await bus.wait_for_handlers(timeout=5.0)

    events = _cross_doc_events(inv)
    assert len(events) == 1, f"expected one cross-doc link, got {len(events)}"
    ev = Event.model_validate(events[0])
    assert isinstance(ev.payload, CrossDocQuestionAnsweredPayload)
    p = ev.payload
    assert p.question_id == "q-1"
    assert p.question_document_id == "doc-A"
    assert p.answer_document_id == "doc-B"
    assert p.answer_note_id == "n-1"
    assert ev.role == "connector"


# ---------------------------------------------------------------------------
# 2. Same-doc skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_doc_note_does_not_link(app_and_bus, async_client):
    _, bus = app_and_bus
    inv = "inv-same-doc"

    await _post_question(
        async_client, investigation_id=inv, document_id="doc-A",
        question_id="q-same",
        text="quantum error correction threshold theorem details",
    )
    # Note emerges on the SAME document.
    await _post_note(
        async_client, investigation_id=inv, document_id="doc-A",
        note_id="n-same",
        text="quantum error correction threshold theorem details exactly what was asked",
    )
    await bus.wait_for_handlers(timeout=5.0)

    assert _cross_doc_events(inv) == []


# ---------------------------------------------------------------------------
# 3. Threshold gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_below_threshold_note_does_not_link(app_and_bus, async_client):
    _, bus = app_and_bus
    inv = "inv-below"

    await _post_question(
        async_client, investigation_id=inv, document_id="doc-A",
        question_id="q-tech",
        text="quantum photonic measurement based architecture",
    )
    # Note about something completely different — should NOT match.
    await _post_note(
        async_client, investigation_id=inv, document_id="doc-B",
        note_id="n-weather",
        text="weather forecast tomorrow sunny warm afternoon",
    )
    await bus.wait_for_handlers(timeout=5.0)

    assert _cross_doc_events(inv) == []


# ---------------------------------------------------------------------------
# 4. Deduplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_question_is_cross_linked_at_most_once(app_and_bus, async_client):
    _, bus = app_and_bus
    inv = "inv-dedupe"

    await _post_question(
        async_client, investigation_id=inv, document_id="doc-A",
        question_id="q-once",
        text="superconducting qubit decoherence mechanisms in dilution refrigerators",
    )
    # First matching note — should produce ONE cross-doc event.
    await _post_note(
        async_client, investigation_id=inv, document_id="doc-B",
        note_id="n-first",
        text="superconducting qubit decoherence mechanisms in dilution refrigerators are studied here",
    )
    await bus.wait_for_handlers(timeout=5.0)
    # Second matching note on yet another doc — must NOT produce
    # another cross-doc event (the question was already resolved).
    await _post_note(
        async_client, investigation_id=inv, document_id="doc-C",
        note_id="n-second",
        text="superconducting qubit decoherence mechanisms in dilution refrigerators second match",
    )
    await bus.wait_for_handlers(timeout=5.0)

    events = _cross_doc_events(inv)
    assert len(events) == 1, f"deduplication failed, got {len(events)} events"
    assert Event.model_validate(events[0]).payload.answer_note_id == "n-first"


# ---------------------------------------------------------------------------
# 5. question.resolved_by_doc removes from open set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_question_resolved_by_doc_prevents_later_cross_link(app_and_bus, async_client):
    _, bus = app_and_bus
    inv = "inv-resolved"

    await _post_question(
        async_client, investigation_id=inv, document_id="doc-A",
        question_id="q-resolved",
        text="cryogenic control electronics for quantum systems",
    )
    # Some other path resolves the question in-doc.
    await _post_question_resolved(
        async_client, investigation_id=inv, document_id="doc-A",
        question_id="q-resolved", answer_note_id="n-other-path",
    )
    await bus.wait_for_handlers(timeout=5.0)

    # A later note on doc-B that WOULD have matched is now ignored
    # because the question was removed from the open set.
    await _post_note(
        async_client, investigation_id=inv, document_id="doc-B",
        note_id="n-late",
        text="cryogenic control electronics for quantum systems at the frontier",
    )
    await bus.wait_for_handlers(timeout=5.0)

    assert _cross_doc_events(inv) == []


# ---------------------------------------------------------------------------
# 6. Per-investigation isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_questions_isolated_per_investigation(app_and_bus, async_client):
    """A question on inv-A is invisible to notes on inv-B."""
    _, bus = app_and_bus

    await _post_question(
        async_client, investigation_id="inv-A", document_id="doc-A",
        question_id="q-isolated",
        text="topological qubit braiding error suppression",
    )
    # Note on inv-B with strong word overlap — must NOT link because
    # they're in different investigations.
    await _post_note(
        async_client, investigation_id="inv-B", document_id="doc-B",
        note_id="n-bleed",
        text="topological qubit braiding error suppression mechanism analysis",
    )
    await bus.wait_for_handlers(timeout=5.0)

    assert _cross_doc_events("inv-A") == []
    assert _cross_doc_events("inv-B") == []


# ---------------------------------------------------------------------------
# 7. Envelope document_id is null on the emitted event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emitted_event_has_no_envelope_document_id(app_and_bus, async_client):
    """Per architecture_notes §13.3 carve-out: CROSS_DOC events span
    two documents; the envelope's document_id is null and both IDs
    live on the payload."""
    _, bus = app_and_bus
    inv = "inv-envelope"

    await _post_question(
        async_client, investigation_id=inv, document_id="doc-A",
        question_id="q-env",
        text="photon loss channels in linear optical computing",
    )
    await _post_note(
        async_client, investigation_id=inv, document_id="doc-B",
        note_id="n-env",
        text="photon loss channels in linear optical computing are bounded by detector efficiency",
    )
    await bus.wait_for_handlers(timeout=5.0)

    events = _cross_doc_events(inv)
    assert len(events) == 1
    ev = Event.model_validate(events[0])
    assert ev.document_id is None, (
        f"expected envelope.document_id=None on CROSS_DOC event; got {ev.document_id}"
    )


# ---------------------------------------------------------------------------
# 8. Multiple open questions: matching note resolves only the matching one
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_note_resolves_one_question_others_remain_open(
    app_and_bus, async_client
):
    _, bus = app_and_bus
    inv = "inv-multi"

    # Two questions on doc-A about deliberately disjoint topics so
    # the hash embedding doesn't false-positive between them.
    await _post_question(
        async_client, investigation_id=inv, document_id="doc-A",
        question_id="q-photon",
        text="photonic measurement based gate fidelity",
    )
    await _post_question(
        async_client, investigation_id=inv, document_id="doc-A",
        question_id="q-cryo",
        text="dilution refrigerator vacuum chamber thermal stability",
    )
    # Note on doc-B answers the photonic question only.
    await _post_note(
        async_client, investigation_id=inv, document_id="doc-B",
        note_id="n-photon",
        text="photonic measurement based gate fidelity scales with qubit count",
    )
    await bus.wait_for_handlers(timeout=5.0)

    events = _cross_doc_events(inv)
    assert len(events) == 1
    p = Event.model_validate(events[0]).payload
    assert p.question_id == "q-photon"

    # Later note on doc-C answers the cryogenic question.
    await _post_note(
        async_client, investigation_id=inv, document_id="doc-C",
        note_id="n-cryo",
        text="dilution refrigerator vacuum chamber thermal stability ultimately bounds qubit coherence",
    )
    await bus.wait_for_handlers(timeout=5.0)

    events = _cross_doc_events(inv)
    assert len(events) == 2
    q_ids = {Event.model_validate(e).payload.question_id for e in events}
    assert q_ids == {"q-photon", "q-cryo"}


# ---------------------------------------------------------------------------
# Helpers — direct cosine tests
# ---------------------------------------------------------------------------


def test_cosine_identity():
    assert _cosine([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_is_zero():
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_zero_vector_returns_zero():
    """Degenerate case: a zero vector shouldn't trigger a divide-by-zero
    or a spurious cross-doc link."""
    assert _cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert _cosine([], [1.0]) == 0.0
    assert _cosine([1.0], []) == 0.0


def test_default_threshold_documented():
    """The DEFAULT_THRESHOLD value is part of the module contract —
    if it changes, the env-var override docs (and operator-facing
    behavior) change too. Fail fast on accidental tweaks."""
    from interfaces.research.api.cross_doc import DEFAULT_THRESHOLD
    assert DEFAULT_THRESHOLD == 0.5
