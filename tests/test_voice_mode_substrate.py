"""Voice mode substrate tests (Sprint 17 mainline)."""

from __future__ import annotations

import pytest

from acquisition.voice.webrtc import (
    WebRTCSessionRegistry,
    get_default_registry,
)
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
    """TTS doesn't have token usage; pricing is per character."""
    p = OpenAITTSProvider(api_key="dummy")
    usage = p.normalize_usage({})
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 0


def test_openai_tts_provider_requires_api_key():
    """Without OPENAI_API_KEY in env + no kwarg, calls fail loudly."""
    p = OpenAITTSProvider(api_key="")
    with pytest.raises(RuntimeError) as exc_info:
        p.call(model="gpt-4o-mini-tts", prompt="Hi", max_tokens=0, temperature=0)
    assert "OPENAI_API_KEY" in str(exc_info.value)


def test_openai_tts_provider_full_call_is_scaffold_only():
    """The scaffold raises NotImplementedError rather than burning
    real credits autonomously. Operator wires the real call when
    they're ready."""
    p = OpenAITTSProvider(api_key="dummy-key")
    with pytest.raises(NotImplementedError):
        p.call(model="gpt-4o-mini-tts", prompt="Test", max_tokens=0, temperature=0)
