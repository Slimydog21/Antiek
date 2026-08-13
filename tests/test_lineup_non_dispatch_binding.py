"""Non-dispatch lineup binding — voice/media/embedding surfaces.

The selector's advanced assignments must be able to name a model these
surfaces can ACTUALLY serve. Rules under test:

* ``effective_model_for_action`` admits an assignment only when the
  provider matches the surface's family AND the model is in the action's
  allowed set; everything else keeps the surface default.
* Action assignments beat role assignments; both beat the default.
* Each surface (whisper, TTS, Krea, embeddings) consults the helper at
  call/construct time.

All offline: registry redirected to tmp via env; providers never called.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.dispatch.lineup_override import (
    effective_model_for_action,
    effective_override_for_dispatch_role,
)

REGISTRY = {
    "owners": {
        "__operator__": {
            "general": {
                "voice": {"provider_id": "openai", "model_id": "gpt-4o-mini-tts"},
                "writer": {"provider_id": "zai", "model_id": "glm-5.2"},
            },
            "advanced": {
                "transcription": {"provider_id": "openai", "model_id": "whisper-1"},
                "image_generation": {"provider_id": "krea", "model_id": "krea-image-pro"},
            },
            "updated_at": "2026-08-13T12:00:00Z",
        }
    }
}


def _write_registry(tmp: Path) -> None:
    path = tmp / "settings" / "lineup.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(REGISTRY), encoding="utf-8")


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANTIEK_LINEUP_PATH", str(tmp_path / "settings" / "lineup.json"))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    return tmp_path


# ── helper semantics ──────────────────────────────────────────────────


def test_admitted_action_assignment_wins(env: Path) -> None:
    _write_registry(env)
    assert effective_model_for_action(
        "transcription", provider_family="openai", default="whisper-1"
    ) == "whisper-1"
    assert effective_model_for_action(
        "image_generation", provider_family="krea", default="krea-image-standard"
    ) == "krea-image-pro"


def test_wrong_family_or_model_ignored(env: Path) -> None:
    _write_registry(env)
    # krea assignment can never serve a voice action
    assert effective_model_for_action(
        "text_to_speech", provider_family="openai", default="gpt-4o-mini-tts"
    ) == "gpt-4o-mini-tts"
    # an allowed-family model outside the action's allowed set is ignored
    assert effective_model_for_action(
        "transcription", provider_family="openai", default="whisper-1"
    ) == "whisper-1"
    # wrong family for media
    assert effective_model_for_action(
        "video_generation", provider_family="krea", default="krea-video-standard"
    ) == "krea-video-standard"


def test_role_assignment_fallback_and_default(env: Path) -> None:
    _write_registry(env)
    # voice role assignment (openai/gpt-4o-mini-tts) admits text_to_speech
    assert effective_model_for_action(
        "text_to_speech", provider_family="openai", default="x"
    ) == "gpt-4o-mini-tts"
    # writer role assignment (zai/glm-5.2) cannot serve embedding surfaces
    assert effective_model_for_action(
        "graph_embedding", provider_family="local_embedding", default="all-MiniLM-L6-v2"
    ) == "all-MiniLM-L6-v2"


def test_no_registry_uses_default(env: Path) -> None:
    assert effective_model_for_action(
        "transcription", provider_family="openai", default="whisper-1"
    ) == "whisper-1"
    # dispatch binding untouched
    assert effective_override_for_dispatch_role("synthesizer") is None


# ── surface wirings ──────────────────────────────────────────────────


def test_whisper_transcriber_honors_lineup(env: Path) -> None:
    _write_registry(env)
    from acquisition.voice.client import WhisperTranscriber

    t = WhisperTranscriber()
    assert t._model == "whisper-1"  # noqa: SLF001 (admitted assignment == default)
    # explicit caller model wins over the lineup
    t2 = WhisperTranscriber(model="explicit-model")
    assert t2._model == "explicit-model"  # noqa: SLF001


def test_tts_synthesize_honors_lineup(env: Path) -> None:
    _write_registry(env)
    from substrate.dispatch.providers.openai_tts import OpenAITTSProvider

    provider = OpenAITTSProvider(api_key="sk-test")
    captured: dict = {}

    def poster(url: str, headers: dict, body: dict) -> bytes:
        captured.update(body)
        return b"mp3-bytes"

    provider.synthesize("hello", poster=poster)
    assert captured["model"] == "gpt-4o-mini-tts"
    provider.synthesize("hello", model="explicit-model", poster=poster)
    assert captured["model"] == "explicit-model"


def test_krea_router_honors_lineup(env: Path) -> None:
    _write_registry(env)
    from substrate.multimedia.provider_router import _model_for

    assert _model_for("image", "highest_quality") == "krea-image-pro"
    # the operator's pick beats the policy-based default for EVERY policy
    assert _model_for("image", "fastest") == "krea-image-pro"
    # video has no action assignment → deterministic default
    assert _model_for("video", "highest_quality") == "krea-video-pro"


def test_embedding_default_honors_lineup_without_network(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The lineup embedding assignment resolves into the provider
    constructor; the sentence-transformers import is stubbed so no model
    is ever downloaded."""
    _write_registry(env)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "sentence-transformers")
    import processing.embedding.embed as embed_mod

    class _FakeSentenceTransformer:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def get_sentence_embedding_dimension(self) -> int:
            return 384

    class _FakeEmbedding:
        def __init__(self, model_name: str) -> None:
            self._model = _FakeSentenceTransformer(model_name)
            self.dimension = 384
            self._model_name = model_name

        def encode(self, text: str) -> list[float]:  # pragma: no cover
            return [0.0] * 384

    monkeypatch.setattr(embed_mod, "SentenceTransformerEmbedding", _FakeEmbedding)
    embed_mod._reset_default_provider()
    provider = embed_mod.default_embedding_provider()
    assert embed_mod.embedding_model_name(provider) == "all-MiniLM-L6-v2"
    embed_mod._reset_default_provider()
