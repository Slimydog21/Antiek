"""Living Roadmap SPR-14 M3 (voice-in) — the shared voice-in capture event
carries the USER-SOURCED provenance label, and a voice transcript node is
distinguishable in the one graph from a model-output node.

These assert the SUBSTRATE side of the provenance discipline: the
``voice.captured`` event persists with ``source_kind="user"`` and is pinned to
that literal by the schema, so voice-in can NEVER be conflated with model
output (a §9 violation). The frontend half (the hook returning + persisting
the label) is covered by ``apps/reading/src/hooks/useVoiceCapture.test.ts``.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from pydantic import ValidationError

from substrate.event_log import emit_typed, trajectory
from substrate.schemas.events import (
    EVENT_SCHEMA_VERSION,
    TYPED_PAYLOAD_ACTION_TYPES,
    ProvenanceSourceKind,
    VoiceCapturedPayload,
)


@pytest.fixture(autouse=True)
def _events_dir(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-voice-cap-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmp, "events"))


# ── schema: source_kind vocabulary + the pinned "user" label ────────────────


def test_source_kind_vocabulary_is_the_shared_three():
    """The shared provenance vocab is exactly user/ai/system — one set, used by
    voice-in ("user") and (the other builder's) TTS-out ("ai")."""
    import typing

    assert set(typing.get_args(ProvenanceSourceKind)) == {"user", "ai", "system"}


def test_voice_capture_payload_defaults_to_user_sourced():
    p = VoiceCapturedPayload(transcript="the mind is not a vessel")
    assert p.source_kind == "user"
    assert p.action_type == "voice.captured"
    assert p.transcript_status == "ok"


def test_voice_capture_cannot_be_persisted_as_model_or_system():
    """The no-conflation invariant is enforced by the TYPE, not convention:
    source_kind is pinned to the literal "user", so a voice capture can never
    be stored as "ai"/"system"."""
    with pytest.raises(ValidationError):
        VoiceCapturedPayload(transcript="x", source_kind="ai")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        VoiceCapturedPayload(transcript="x", source_kind="system")  # type: ignore[arg-type]


def test_voice_captured_is_in_the_typed_union():
    assert "voice.captured" in TYPED_PAYLOAD_ACTION_TYPES


# ── persistence: the emitted event carries the user-sourced label ───────────


def test_emitted_voice_capture_event_carries_user_sourced_label():
    event_id = emit_typed(
        "inv-voice",
        VoiceCapturedPayload(
            transcript="the corrected text",
            language="en",
            duration_seconds=2.0,
            audio_ref="blob://audio-123",
        ),
        document_id="doc-book-1",
        role="voice/capture",
        policy_id="voice/capture",
    )
    assert event_id is not None

    events = trajectory("inv-voice")
    voice_events = [e for e in events if e.get("action_type") == "voice.captured"]
    assert len(voice_events) == 1
    payload = voice_events[0]["payload"]
    # The load-bearing assertion (§9): persisted as user-sourced.
    assert payload["source_kind"] == "user"
    assert payload["transcript"] == "the corrected text"
    # The blob rides by REFERENCE — the pointer is persisted, not the blob.
    assert payload["audio_ref"] == "blob://audio-123"
    assert voice_events[0]["schema_version"] == EVENT_SCHEMA_VERSION


def test_voice_capture_distinguishable_from_model_output_node():
    """A voice transcript node (source_kind 'user') is distinguishable in the
    graph from a model-output node. We model a model-output node with the same
    shared vocabulary value 'ai' and assert the two are NOT conflated — one
    field separates human speech from generated text."""
    emit_typed(
        "inv-distinguish",
        VoiceCapturedPayload(transcript="a spoken thought"),
        document_id="doc-1",
        role="voice/capture",
    )
    events = trajectory("inv-distinguish")
    voice = next(e for e in events if e.get("action_type") == "voice.captured")
    assert voice["payload"]["source_kind"] == "user"
    # A model-generated node would carry source_kind "ai" (the TTS-out / model
    # path uses the SAME vocabulary), which is != "user" — so a consumer
    # filtering on the label never mistakes one for the other.
    assert voice["payload"]["source_kind"] != "ai"
    assert voice["payload"]["source_kind"] != "system"


def test_empty_transcript_is_flagged_not_invented():
    """A silent capture persists a blank transcript flagged 'empty' — never a
    hallucinated one (rigor #3a, substrate side)."""
    emit_typed(
        "inv-silent",
        VoiceCapturedPayload(transcript="", transcript_status="empty"),
        document_id="doc-1",
    )
    events = trajectory("inv-silent")
    voice = next(e for e in events if e.get("action_type") == "voice.captured")
    assert voice["payload"]["transcript"] == ""
    assert voice["payload"]["transcript_status"] == "empty"
