"""Voice mode substrate tests (Sprint 17 mainline)."""

from __future__ import annotations

import pytest

from acquisition.voice.webrtc import (
    WebRTCSessionRegistry,
    get_default_registry,
)
from substrate.dispatch.base import ProviderError
from substrate.dispatch.providers.openai_tts import OpenAITTSProvider


def test_webrtc_registry_opens_session():
    reg = WebRTCSessionRegistry()
    handle = reg.open_session(interview_id="inv-bio-dad", informant_handle="uncle-fawzi")
    assert handle.session_id.startswith("webrtc-")
    assert handle.interview_id == "inv-bio-dad"
    assert handle.informant_handle == "uncle-fawzi"


def test_webrtc_session_end():
    reg = WebRTCSessionRegistry()
    handle = reg.open_session(interview_id="x")
    assert handle.session_id in reg.sessions
    reg.end_session(handle.session_id)
    assert handle.session_id not in reg.sessions


def test_webrtc_accept_offer_unknown_session_raises():
    reg = WebRTCSessionRegistry()
    with pytest.raises(ValueError):
        reg.accept_offer("unknown", "sdp-data")


def test_default_registry_is_module_level():
    """Module-level default registry for API endpoint integration."""
    reg = get_default_registry()
    assert reg is get_default_registry()  # same instance


def test_openai_tts_provider_normalize_usage_returns_zeros():
    """TTS dispatch accounts one input unit per character."""
    p = OpenAITTSProvider(api_key="dummy")
    usage = p.normalize_usage({"input_characters": 17})
    assert usage.input_tokens == 17
    assert usage.output_tokens == 0
    assert usage.cached_input_tokens == 0


def test_openai_tts_provider_requires_api_key():
    """Without OPENAI_API_KEY in env + no kwarg, calls fail loudly."""
    p = OpenAITTSProvider(api_key="")
    with pytest.raises(ProviderError) as exc_info:
        p.call(model="gpt-4o-mini-tts", prompt="Hi", max_tokens=0, temperature=0)
    assert "OPENAI_API_KEY" in str(exc_info.value)


def test_openai_tts_provider_call_returns_raw_provider_response():
    """Dispatch-shaped TTS call is live-when-keyed and test-injectable."""
    captured = {}

    def fake_poster(url, headers, body):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        return b"ID3-dispatch-audio"

    p = OpenAITTSProvider(api_key="dummy-key", poster=fake_poster)
    raw = p.call(
        model="gpt-4o-mini-tts",
        prompt="Test speech",
        max_tokens=0,
        temperature=0,
    )

    assert raw.text == "SUQzLWRpc3BhdGNoLWF1ZGlv"
    assert raw.raw_usage["input_characters"] == len("Test speech")
    assert raw.raw_usage["audio_bytes"] == len(b"ID3-dispatch-audio")
    assert raw.finish_reason == "stop"
    assert raw.extra == {"mime_type": "audio/mpeg", "encoding": "base64"}
    assert captured["url"].endswith("/audio/speech")
    assert captured["headers"]["Authorization"] == "Bearer dummy-key"
    assert captured["body"]["input"] == "Test speech"


def test_openai_tts_provider_composes_with_dispatch_router():
    """TTS provider reports character-priced usage through dispatch."""
    from substrate.dispatch import (
        DispatchConfig,
        TierConfig,
        TierPricing,
        dispatch,
        register_provider,
        reset_provider_registry,
    )

    provider = OpenAITTSProvider(
        api_key="dummy-key",
        poster=lambda _url, _headers, _body: b"ID3-router-audio",
    )
    config = DispatchConfig(
        role_tiers={"tts_reply": "tts"},
        tiers={
            "tts": TierConfig(
                name="tts",
                provider="openai",
                model="gpt-4o-mini-tts",
                max_tokens=0,
                temperature=0,
                context_budget_tokens=8_000,
                pricing=TierPricing(input_per_mtok=15.0, output_per_mtok=0.0),
            ),
        },
    )

    reset_provider_registry()
    try:
        register_provider(provider)
        result = dispatch(
            "router speech",
            role="tts_reply",
            investigation_id="inv-tts-router",
            config=config,
        )
    finally:
        reset_provider_registry()

    assert result.text == "SUQzLXJvdXRlci1hdWRpbw=="
    assert result.usage.input_tokens == len("router speech")
    assert result.usage.output_tokens == 0
    assert result.cost_usd == pytest.approx(len("router speech") * 15.0 / 1_000_000)
