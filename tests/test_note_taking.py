"""Tests for the backend note-taker bridge (Sprint 4 day 1-2).

Coverage:

1. Parser (roles/note_taker/parser.py):
   - Clean JSON, code fences, prose preamble, missing fields, dropped
     unattributed notes, confidence coercion.
2. Threshold-based triggering:
   - N-1 events: no synthesis fires.
   - Nth event: synthesis fires, notes land.
   - N+1 events: counter resets correctly.
3. Per-investigation counter isolation — events on inv-A don't
   trigger synthesis on inv-B.
4. Provider unavailable / malformed response → no notes emitted (no
   crash, no fallback event).
5. Self-broadcast feedback-loop defense — note.emerged events from
   the note-taker don't trigger further synthesis.
6. Each emitted ``note.emerged`` round-trips through Event.model_validate
   with NoteEmergedPayload + envelope role="note_taker" +
   policy_id={provider}/{model}.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import EventBroadcaster, create_app  # noqa: E402
from processing.embedding import _reset_default_provider  # noqa: E402
from roles.note_taker import ExtractedNote, parse_notes_response  # noqa: E402
from substrate.dispatch import (  # noqa: E402
    DispatchConfig,
    NormalizedUsage,
    ProviderError,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import Event, NoteEmergedPayload  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    # Force a small threshold so tests trigger synthesis on a manageable
    # number of events (default 5 → 3 in tests).
    monkeypatch.setenv("ANTIEK_NOTE_TAKER_THRESHOLD", "3")
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


class _StubNoteTaker:
    """Provider returning canned note-taker JSON. The note-taker
    dispatches the ``note_taker`` role which defaults to the flash
    tier — same shape stub as elsewhere; just registered for that
    tier via _note_taker_config below."""

    name = "stub-notetaker"

    def __init__(self, text: str, *, raise_on_call: bool = False):
        self._text = text
        self._raise = raise_on_call
        self.call_count = 0

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.call_count += 1
        if self._raise:
            raise ProviderError("stub failure", provider=self.name, model=model, latency_ms=0)
        return RawProviderResponse(
            text=self._text,
            raw_usage={"input_tokens": 200, "output_tokens": 80},
            finish_reason="end_turn",
            latency_ms=8,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


def _note_taker_config(provider_name: str) -> DispatchConfig:
    """Wire the note_taker → flash → provider chain."""
    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    flash = TierConfig(
        name="flash", provider=provider_name, model="stub-flash",
        max_tokens=2048, temperature=0.2, context_budget_tokens=32_000,
        pricing=pricing, fallback=None,
    )
    return DispatchConfig(
        role_tiers={"note_taker": "flash"},
        tiers={"flash": flash},
    )


def _patch_dispatch_config(monkeypatch, config: DispatchConfig) -> None:
    import substrate.dispatch.router as router
    monkeypatch.setattr(
        router.DispatchConfig, "from_yaml",
        classmethod(lambda cls, path: config),
    )


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
# Helpers: post a distillation.delivered or grounding event directly
# (without going through the wrestling bridge) so the test controls
# the trigger cadence precisely.
# ---------------------------------------------------------------------------


async def _post_distillation_delivered(ac, *, investigation_id, document_id, request_event_id="evt-fake"):
    """Synthetic distillation.delivered — bypasses the synthesizer
    dispatch and just lands the event so the note-taker's subscription
    counter increments."""
    r = await ac.post(
        "/events/typed",
        json={
            "investigation_id": investigation_id,
            "document_id": document_id,
            "payload": {
                "action_type": "distillation.delivered",
                "request_event_id": request_event_id,
                "claims": [{
                    "claim_id": "c-1",
                    "text": "synthetic claim",
                    "confidence": "moderate",
                    "attribution_region_ids": [],
                }],
                "rendered_text": "synthetic rendered text",
                "rendered_text_hash": "sha256:fake",
                "token_count": 10,
            },
        },
    )
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# 1. Parser tests
# ---------------------------------------------------------------------------


def test_parse_notes_clean_json():
    text = """
    {
      "notes": [
        {"text": "the user keeps challenging causality claims",
         "confidence": "moderate",
         "source_event_ids": ["evt-1", "evt-2"]}
      ]
    }
    """
    notes = parse_notes_response(text)
    assert len(notes) == 1
    n = notes[0]
    assert isinstance(n, ExtractedNote)
    assert n.text == "the user keeps challenging causality claims"
    assert n.confidence == "moderate"
    assert n.source_event_ids == ("evt-1", "evt-2")
    assert n.note_id.startswith("n-")


def test_parse_notes_drops_unattributed():
    """Rule 4 of the prompt: notes without source_event_ids are
    hallucinations. The parser drops them."""
    text = (
        '{"notes": ['
        '{"text": "attributed", "confidence": "high", "source_event_ids": ["evt-1"]},'
        '{"text": "no attribution", "confidence": "high", "source_event_ids": []},'
        '{"text": "no attribution field at all", "confidence": "high"}'
        ']}'
    )
    notes = parse_notes_response(text)
    assert len(notes) == 1
    assert notes[0].text == "attributed"


def test_parse_notes_drops_empty_text():
    text = (
        '{"notes": ['
        '{"text": "", "confidence": "high", "source_event_ids": ["evt-1"]},'
        '{"text": "   ", "confidence": "high", "source_event_ids": ["evt-1"]},'
        '{"text": "real", "confidence": "high", "source_event_ids": ["evt-1"]}'
        ']}'
    )
    notes = parse_notes_response(text)
    assert len(notes) == 1
    assert notes[0].text == "real"


def test_parse_notes_coerces_unknown_confidence():
    text = (
        '{"notes": [{"text": "x", "confidence": "medium", "source_event_ids": ["e"]}]}'
    )
    notes = parse_notes_response(text)
    assert notes[0].confidence == "unknown"


def test_parse_notes_handles_code_fence():
    text = '```json\n{"notes": [{"text": "x", "confidence": "high", "source_event_ids": ["e"]}]}\n```'
    notes = parse_notes_response(text)
    assert len(notes) == 1


def test_parse_notes_malformed_returns_empty():
    assert parse_notes_response("not json") == []
    assert parse_notes_response("") == []
    assert parse_notes_response("{}") == []
    assert parse_notes_response('{"notes": "not a list"}') == []


# ---------------------------------------------------------------------------
# 2. Threshold-based triggering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_note_taker_does_not_fire_before_threshold(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    stub = _StubNoteTaker(
        '{"notes": [{"text": "n", "confidence": "high", "source_event_ids": ["e"]}]}'
    )
    register_provider(stub)
    _patch_dispatch_config(monkeypatch, _note_taker_config("stub-notetaker"))

    inv = "inv-pre-threshold"
    # Threshold is 3 (env). Post 2 events.
    for _ in range(2):
        await _post_distillation_delivered(
            async_client, investigation_id=inv, document_id="d",
        )
    await bus.wait_for_handlers(timeout=5.0)

    assert stub.call_count == 0
    note_events = [
        r for r in trajectory(inv) if r["action_type"] == "note.emerged"
    ]
    assert note_events == []


@pytest.mark.asyncio
async def test_note_taker_fires_at_threshold(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    stub = _StubNoteTaker(
        '{"notes": ['
        '{"text": "insight A", "confidence": "high", "source_event_ids": ["fake-1"]},'
        '{"text": "insight B", "confidence": "moderate", "source_event_ids": ["fake-2"]}'
        ']}'
    )
    register_provider(stub)
    _patch_dispatch_config(monkeypatch, _note_taker_config("stub-notetaker"))

    inv = "inv-threshold-hit"
    for _ in range(3):  # threshold is 3
        await _post_distillation_delivered(
            async_client, investigation_id=inv, document_id="d",
        )
    await bus.wait_for_handlers(timeout=5.0)

    assert stub.call_count == 1, (
        f"expected exactly 1 dispatch at threshold; got {stub.call_count}"
    )
    note_events = [
        r for r in trajectory(inv) if r["action_type"] == "note.emerged"
    ]
    assert len(note_events) == 2  # 2 notes parsed from stub response
    e0 = Event.model_validate(note_events[0])
    assert isinstance(e0.payload, NoteEmergedPayload)
    assert e0.payload.note_text == "insight A"
    assert e0.role == "note_taker"
    assert e0.document_id == "d"
    assert e0.policy_id == "stub-notetaker/stub-flash"


@pytest.mark.asyncio
async def test_note_taker_counter_resets_after_fire(
    monkeypatch, app_and_bus, async_client
):
    """After threshold-fire, the counter resets — the next fire only
    happens after another <threshold> qualifying events."""
    _, bus = app_and_bus
    stub = _StubNoteTaker(
        '{"notes": [{"text": "n", "confidence": "high", "source_event_ids": ["fake-1"]}]}'
    )
    register_provider(stub)
    _patch_dispatch_config(monkeypatch, _note_taker_config("stub-notetaker"))

    inv = "inv-reset"
    # First fire at event 3.
    for _ in range(3):
        await _post_distillation_delivered(
            async_client, investigation_id=inv, document_id="d",
        )
    await bus.wait_for_handlers(timeout=5.0)
    assert stub.call_count == 1

    # Next 2 events (4, 5) should NOT fire.
    for _ in range(2):
        await _post_distillation_delivered(
            async_client, investigation_id=inv, document_id="d",
        )
    await bus.wait_for_handlers(timeout=5.0)
    assert stub.call_count == 1

    # 6th event hits threshold again.
    await _post_distillation_delivered(
        async_client, investigation_id=inv, document_id="d",
    )
    await bus.wait_for_handlers(timeout=5.0)
    assert stub.call_count == 2


# ---------------------------------------------------------------------------
# 3. Per-investigation counter isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_counter_isolated_per_investigation(
    monkeypatch, app_and_bus, async_client
):
    """Events on inv-A don't increment inv-B's counter."""
    _, bus = app_and_bus
    stub = _StubNoteTaker(
        '{"notes": [{"text": "n", "confidence": "high", "source_event_ids": ["fake"]}]}'
    )
    register_provider(stub)
    _patch_dispatch_config(monkeypatch, _note_taker_config("stub-notetaker"))

    # 2 events on inv-A — below threshold.
    for _ in range(2):
        await _post_distillation_delivered(
            async_client, investigation_id="inv-A", document_id="d-A",
        )
    # 3 events on inv-B — hits threshold for inv-B only.
    for _ in range(3):
        await _post_distillation_delivered(
            async_client, investigation_id="inv-B", document_id="d-B",
        )
    await bus.wait_for_handlers(timeout=5.0)

    assert stub.call_count == 1
    # The synthesis fired against inv-B (the one that hit threshold).
    a_notes = [r for r in trajectory("inv-A") if r["action_type"] == "note.emerged"]
    b_notes = [r for r in trajectory("inv-B") if r["action_type"] == "note.emerged"]
    assert a_notes == []
    assert len(b_notes) == 1


# ---------------------------------------------------------------------------
# 4. Failure-mode discipline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_note_taker_handles_provider_failure(
    monkeypatch, app_and_bus, async_client
):
    """Provider raises → no notes emitted, no crash. Counter reset
    still happens (because synthesis was attempted), so the next
    threshold-window will retry — that's the right behavior for a
    transient provider hiccup."""
    _, bus = app_and_bus
    register_provider(_StubNoteTaker("never reached", raise_on_call=True))
    _patch_dispatch_config(monkeypatch, _note_taker_config("stub-notetaker"))

    inv = "inv-prov-fail"
    for _ in range(3):
        await _post_distillation_delivered(
            async_client, investigation_id=inv, document_id="d",
        )
    await bus.wait_for_handlers(timeout=5.0)

    note_events = [r for r in trajectory(inv) if r["action_type"] == "note.emerged"]
    assert note_events == []


@pytest.mark.asyncio
async def test_note_taker_handles_malformed_response(
    monkeypatch, app_and_bus, async_client
):
    _, bus = app_and_bus
    register_provider(_StubNoteTaker("this is not JSON at all"))
    _patch_dispatch_config(monkeypatch, _note_taker_config("stub-notetaker"))

    inv = "inv-malformed"
    for _ in range(3):
        await _post_distillation_delivered(
            async_client, investigation_id=inv, document_id="d",
        )
    await bus.wait_for_handlers(timeout=5.0)

    note_events = [r for r in trajectory(inv) if r["action_type"] == "note.emerged"]
    assert note_events == []


@pytest.mark.asyncio
async def test_note_taker_handles_empty_notes_array(
    monkeypatch, app_and_bus, async_client
):
    """Empty arrays are valid output per the prompt — the role correctly
    decided no notes are emergent yet. No events emitted; no error."""
    _, bus = app_and_bus
    register_provider(_StubNoteTaker('{"notes": []}'))
    _patch_dispatch_config(monkeypatch, _note_taker_config("stub-notetaker"))

    inv = "inv-empty"
    for _ in range(3):
        await _post_distillation_delivered(
            async_client, investigation_id=inv, document_id="d",
        )
    await bus.wait_for_handlers(timeout=5.0)

    note_events = [r for r in trajectory(inv) if r["action_type"] == "note.emerged"]
    assert note_events == []


# ---------------------------------------------------------------------------
# 5. Self-broadcast feedback-loop defense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_note_emerged_events_do_not_retrigger_synthesis(
    monkeypatch, app_and_bus, async_client
):
    """The note-taker emits note.emerged events. These are NOT in
    SUBSCRIBED_ACTION_TYPES, but as defense-in-depth the handler
    also short-circuits on role=='note_taker'. Verify: 3 events
    triggers 1 synthesis producing N notes → synthesis count stays
    at 1, doesn't loop."""
    _, bus = app_and_bus
    stub = _StubNoteTaker(
        '{"notes": ['
        '{"text": "a", "confidence": "high", "source_event_ids": ["fake"]},'
        '{"text": "b", "confidence": "high", "source_event_ids": ["fake"]},'
        '{"text": "c", "confidence": "high", "source_event_ids": ["fake"]}'
        ']}'
    )
    register_provider(stub)
    _patch_dispatch_config(monkeypatch, _note_taker_config("stub-notetaker"))

    inv = "inv-noloop"
    for _ in range(3):
        await _post_distillation_delivered(
            async_client, investigation_id=inv, document_id="d",
        )
    await bus.wait_for_handlers(timeout=5.0)

    assert stub.call_count == 1, "synthesis must run exactly once, no feedback loop"
    note_events = [r for r in trajectory(inv) if r["action_type"] == "note.emerged"]
    assert len(note_events) == 3
