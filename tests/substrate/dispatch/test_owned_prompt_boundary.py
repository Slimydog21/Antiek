"""An owner-approved provider call cannot disclose its prompt to a shadow selector."""

from __future__ import annotations

from typing import Any

import pytest

from substrate.dispatch import dispatch, register_provider, reset_provider_registry
from substrate.dispatch.notdiamond_shadow import ShadowAttribution
from substrate.event_log import trajectory
from tests.test_dispatch import (
    _MockAnthropicProvider,
    _MockOpenAICompatProvider,
    _two_tier_config,
)


@pytest.mark.parametrize("allow_shadow", [False, True])
def test_owned_prompt_is_not_shared_while_ordinary_shadow_default_is_preserved(
    monkeypatch: pytest.MonkeyPatch, allow_shadow: bool,
) -> None:
    private_prompt = "Private fixture source and owner-approved processing instruction"
    approved_prompts: list[str] = []
    selector_prompts: list[str] = []
    investigation_id = f"owned-prompt-boundary-{allow_shadow}"

    class RecordingProvider(_MockAnthropicProvider):
        def call(self, **kwargs: Any) -> Any:
            approved_prompts.append(kwargs["prompt"])
            return super().call(**kwargs)

    def selector(**kwargs: Any) -> ShadowAttribution:
        selector_prompts.append(kwargs["prompt"])
        return ShadowAttribution(
            "fixture-shadow", "mock-anthropic", "claude-opus-4-7", "quality", 1, "shadow",
        )

    reset_provider_registry()
    try:
        register_provider(RecordingProvider())
        register_provider(_MockOpenAICompatProvider())
        monkeypatch.setenv("ANTIEK_NOTDIAMOND_MODE", "shadow")
        monkeypatch.setenv("ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE", "1")
        monkeypatch.setattr(
            "substrate.dispatch.notdiamond_shadow.evaluate_notdiamond_shadow", selector,
        )
        options = {} if allow_shadow else {"notdiamond_shadow": False}
        result = dispatch(
            private_prompt, "synthesizer", investigation_id=investigation_id,
            config=_two_tier_config(), operator_lineup=False, **options,
        )
        assert result.provider == "mock-anthropic"
        assert approved_prompts == [private_prompt]
        assert selector_prompts == ([private_prompt] if allow_shadow else [])
        calls = [row for row in trajectory(investigation_id)
                 if row["action_type"] == "dispatch.call"]
        assert len(calls) == 1
        assert calls[0]["payload"].get("nd_session_id") == (
            "fixture-shadow" if allow_shadow else None
        )
    finally:
        reset_provider_registry()
