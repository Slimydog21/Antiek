from __future__ import annotations

from typing import Any

import pytest

from substrate.dispatch import dispatch, register_provider, reset_provider_registry
from substrate.dispatch.nd_attribution import (
    peek_nd_decision,
    push_nd_decision,
    reset_nd_decision,
)
from substrate.dispatch.notdiamond_shadow import ShadowAttribution
from substrate.event_log import trajectory
from substrate.schemas import DispatchCallPayload, Event
from tests.test_dispatch import (
    _MockAnthropicProvider,
    _MockOpenAICompatProvider,
    _two_tier_config,
)


@pytest.fixture(autouse=True)
def _providers() -> None:
    reset_provider_registry()
    yield
    reset_provider_registry()


def test_shadow_attribution_lands_without_reordering_provider(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    anthropic = _MockAnthropicProvider()
    fallback = _MockOpenAICompatProvider()
    register_provider(anthropic)
    register_provider(fallback)
    monkeypatch.setattr(
        "substrate.dispatch.notdiamond_shadow.evaluate_notdiamond_shadow",
        lambda **_: ShadowAttribution(
            "session-1", "mock-openai-compat", "mimo-flash", "quality", 12, "shadow"
        ),
    )

    result = dispatch(
        "research", "synthesizer", investigation_id="inv-shadow", config=_two_tier_config()
    )

    assert result.provider == "mock-anthropic"
    assert anthropic.calls == [{"model": "claude-opus-4-7", "max_tokens": 8192}]
    assert fallback.calls == []
    event = Event.model_validate(trajectory("inv-shadow")[0])
    assert isinstance(event.payload, DispatchCallPayload)
    assert event.payload.nd_session_id == "session-1"
    assert event.payload.nd_recommended_provider == "mock-openai-compat"
    assert event.payload.nd_bypassed is True
    assert event.payload.nd_bypass_reason == "shadow"


def test_pre_emission_provider_exception_clears_staged_attribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExplodingProvider(_MockAnthropicProvider):
        def call(self, **_: object) -> Any:
            raise RuntimeError("unexpected provider failure")

    register_provider(ExplodingProvider())
    register_provider(_MockOpenAICompatProvider())
    monkeypatch.setattr(
        "substrate.dispatch.notdiamond_shadow.evaluate_notdiamond_shadow",
        lambda **_: ShadowAttribution(
            "session-leak", "mock-anthropic", "claude-opus-4-7", "quality", 1, "shadow"
        ),
    )

    with pytest.raises(RuntimeError, match="unexpected provider failure"):
        dispatch(
            "research", "synthesizer", investigation_id="inv-error", config=_two_tier_config()
        )
    assert peek_nd_decision() is None


def test_fallback_attempts_share_shadow_attribution(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    register_provider(_MockAnthropicProvider(raise_on_call=True))
    register_provider(_MockOpenAICompatProvider())
    monkeypatch.setattr(
        "substrate.dispatch.notdiamond_shadow.evaluate_notdiamond_shadow",
        lambda **_: ShadowAttribution(
            "session-fallback", "mock-openai-compat", "mimo-flash", "quality", 9, "shadow"
        ),
    )
    dispatch(
        "research", "synthesizer", investigation_id="inv-fallback", config=_two_tier_config()
    )
    events = [Event.model_validate(row) for row in trajectory("inv-fallback")]
    assert len(events) == 2
    assert all(
        isinstance(event.payload, DispatchCallPayload)
        and event.payload.nd_session_id == "session-fallback"
        for event in events
    )


def test_nested_scope_restores_preexisting_attribution(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    register_provider(_MockAnthropicProvider())
    register_provider(_MockOpenAICompatProvider())
    outer = {
        "nd_session_id": "outer",
        "nd_recommended_provider": None,
        "nd_recommended_model": None,
        "nd_tradeoff": "quality",
        "nd_decision_latency_ms": 1,
        "nd_bypassed": True,
        "nd_bypass_reason": "shadow",
    }
    outer_scope = object()
    tokens = push_nd_decision(outer, scope=outer_scope)
    try:
        dispatch(
            "research", "synthesizer", investigation_id="inv-inner", config=_two_tier_config()
        )
        staged = peek_nd_decision()
        assert staged is not None and staged["nd_session_id"] == "outer"
    finally:
        reset_nd_decision(tokens)


def test_shadow_candidates_include_authoritative_primary_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_provider(_MockAnthropicProvider())
    register_provider(_MockOpenAICompatProvider())
    captured: dict[str, object] = {}

    def evaluate(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(
        "substrate.dispatch.notdiamond_shadow.evaluate_notdiamond_shadow", evaluate
    )
    dispatch(
        "research",
        "synthesizer",
        investigation_id="inv-override",
        config=_two_tier_config(),
        provider_override="mock-openai-compat",
        model_override="override-model",
    )
    candidates = captured["candidates"]
    assert isinstance(candidates, tuple)
    assert candidates[0] == "mock-openai-compat/override-model"
    assert "mock-openai-compat/mimo-flash" in candidates
