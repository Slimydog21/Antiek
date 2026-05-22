"""Tests for the voice-note audio-blob store."""

from __future__ import annotations

import base64
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


@pytest.fixture()
def antiek_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    return tmp_path


def test_store_and_load_roundtrip(antiek_home):
    from services.voice.audio_store import store_audio, load_audio
    payload = b"\x00\x01\x02\x03 audio bytes"
    path = store_audio(voice_note_id="voice-abc", audio_bytes=payload)
    assert os.path.exists(path)
    assert load_audio(path) == payload


def test_store_b64_decodes(antiek_home):
    from services.voice.audio_store import store_audio_b64, load_audio
    raw = b"opus-frame-data"
    b64 = base64.b64encode(raw).decode("ascii")
    path = store_audio_b64(voice_note_id="voice-b64", audio_b64=b64)
    assert load_audio(path) == raw


def test_store_idempotent_on_same_bytes(antiek_home):
    from services.voice.audio_store import store_audio
    p1 = store_audio(voice_note_id="voice-id1", audio_bytes=b"same")
    p2 = store_audio(voice_note_id="voice-id1", audio_bytes=b"same")
    assert p1 == p2


def test_store_overwrites_on_rerecord(antiek_home):
    """Re-recording the same voice_note_id overwrites — the id is the
    source of truth, not the bytes."""
    from services.voice.audio_store import store_audio, load_audio
    path = store_audio(voice_note_id="voice-rec", audio_bytes=b"v1")
    store_audio(voice_note_id="voice-rec", audio_bytes=b"v2")
    assert load_audio(path) == b"v2"


def test_exists_check(antiek_home):
    from services.voice.audio_store import store_audio, exists
    assert exists("voice-xyz") is False
    store_audio(voice_note_id="voice-xyz", audio_bytes=b"present")
    assert exists("voice-xyz") is True


def test_rejects_unsafe_voice_note_id(antiek_home):
    from services.voice.audio_store import store_audio
    with pytest.raises(ValueError):
        store_audio(voice_note_id="../escape", audio_bytes=b"x")
    with pytest.raises(ValueError):
        store_audio(voice_note_id="", audio_bytes=b"x")


def test_path_for_predicts_layout(antiek_home):
    from services.voice.audio_store import path_for, store_audio
    expected = path_for("voice-abc")
    actual = store_audio(voice_note_id="voice-abc", audio_bytes=b"a")
    assert expected == actual


def test_load_missing_raises(antiek_home):
    from services.voice.audio_store import load_audio
    with pytest.raises(FileNotFoundError):
        load_audio(str(antiek_home / "audio" / "nonexistent.opus"))
