from __future__ import annotations

import time
from typing import Any

from runtime.notdiamond import NotDiamondTimeout, Recommendation
from substrate.dispatch.notdiamond_shadow import evaluate_notdiamond_shadow


def _recommendation(**_: object) -> Recommendation:
    return Recommendation("zai", "glm-5.2", "session-1", 17)


def test_non_drw_roles_do_not_consult_notdiamond() -> None:
    assert evaluate_notdiamond_shadow(
        prompt="write", role="creative_writer", candidates=("zai/glm-5.2",), selector=_recommendation
    ) is None


def test_default_is_disabled_and_invalid_mode_fails_closed() -> None:
    disabled = evaluate_notdiamond_shadow(
        prompt="research", role="synthesizer", candidates=("zai/glm-5.2",), environ={}
    )
    invalid = evaluate_notdiamond_shadow(
        prompt="research",
        role="synthesizer",
        candidates=("zai/glm-5.2",),
        environ={"ANTIEK_NOTDIAMOND_MODE": "enabled"},
    )
    assert disabled is not None and disabled.bypass_reason == "disabled"
    assert invalid is not None and invalid.bypass_reason == "invalid_mode"


def test_shadow_records_in_set_recommendation_without_route_authority() -> None:
    result = evaluate_notdiamond_shadow(
        prompt="research",
        role="synthesizer",
        candidates=("zai/glm-5.2", "deepseek/deepseek-v4-pro"),
        environ={
            "ANTIEK_NOTDIAMOND_MODE": "shadow",
            "ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE": "true",
        },
        selector=_recommendation,
    )
    assert result is not None
    assert result.recommended_provider == "zai"
    assert result.recommended_model == "glm-5.2"
    assert result.bypass_reason == "shadow"


def test_shadow_classifies_timeout_and_off_candidate_set() -> None:
    def timeout(**_: object) -> Recommendation:
        raise NotDiamondTimeout("late")

    timed_out = evaluate_notdiamond_shadow(
        prompt="research",
        role="synthesizer",
        candidates=("zai/glm-5.2",),
        environ={
            "ANTIEK_NOTDIAMOND_MODE": "shadow",
            "ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE": "true",
        },
        selector=timeout,
    )
    off_set = evaluate_notdiamond_shadow(
        prompt="research",
        role="synthesizer",
        candidates=("deepseek/deepseek-v4-pro",),
        environ={
            "ANTIEK_NOTDIAMOND_MODE": "shadow",
            "ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE": "true",
        },
        selector=_recommendation,
    )
    assert timed_out is not None and timed_out.bypass_reason == "timeout"
    assert off_set is not None and off_set.bypass_reason == "off_candidate_set"


def test_shadow_requires_separate_prompt_disclosure_consent() -> None:
    result = evaluate_notdiamond_shadow(
        prompt="private research",
        role="synthesizer",
        candidates=("zai/glm-5.2",),
        environ={"ANTIEK_NOTDIAMOND_MODE": "shadow"},
        selector=lambda **_: (_ for _ in ()).throw(AssertionError("must not disclose")),
    )
    assert result is not None
    assert result.bypass_reason == "prompt_disclosure_not_approved"


def test_outer_deadline_bounds_a_hung_selector() -> None:
    def slow(**_: object) -> Recommendation:
        time.sleep(0.05)
        return _recommendation()

    started = time.monotonic()
    result = evaluate_notdiamond_shadow(
        prompt="research",
        role="synthesizer",
        candidates=("zai/glm-5.2",),
        environ={
            "ANTIEK_NOTDIAMOND_MODE": "shadow",
            "ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE": "true",
        },
        selector=slow,
        timeout_ms=5,
    )
    assert time.monotonic() - started < 0.04
    assert result is not None and result.bypass_reason == "timeout"
    time.sleep(0.06)  # Let the daemon release the single selector slot.


def test_malformed_recommendation_is_not_recorded_as_identity() -> None:
    result = evaluate_notdiamond_shadow(
        prompt="research",
        role="synthesizer",
        candidates=("zai/glm-5.2",),
        environ={
            "ANTIEK_NOTDIAMOND_MODE": "shadow",
            "ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE": "true",
        },
        selector=lambda **_: Recommendation("zai", "bad/model", "session", -1),
    )
    assert result is not None
    assert result.bypass_reason == "malformed_response"
    assert result.recommended_provider is None

    wrong_type = evaluate_notdiamond_shadow(
        prompt="research",
        role="synthesizer",
        candidates=("zai/glm-5.2",),
        environ={
            "ANTIEK_NOTDIAMOND_MODE": "shadow",
            "ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE": "true",
        },
        selector=lambda **_: Recommendation(Any, "glm-5.2", "session", 1),  # type: ignore[arg-type]
    )
    assert wrong_type is not None and wrong_type.bypass_reason == "malformed_response"

    namespaced = evaluate_notdiamond_shadow(
        prompt="research",
        role="synthesizer",
        candidates=("openrouter/anthropic/claude-sonnet",),
        environ={
            "ANTIEK_NOTDIAMOND_MODE": "shadow",
            "ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE": "true",
        },
        selector=lambda **_: Recommendation(
            "openrouter", "anthropic/claude-sonnet", "session", 1
        ),
    )
    assert namespaced is not None and namespaced.bypass_reason == "shadow"


def test_thread_start_failure_releases_selector_slot(monkeypatch) -> None:
    import substrate.dispatch.notdiamond_shadow as shadow

    original = shadow.threading.Thread.start
    monkeypatch.setattr(
        shadow.threading.Thread,
        "start",
        lambda self: (_ for _ in ()).throw(RuntimeError("thread unavailable")),
    )
    failed = evaluate_notdiamond_shadow(
        prompt="research",
        role="synthesizer",
        candidates=("zai/glm-5.2",),
        environ={
            "ANTIEK_NOTDIAMOND_MODE": "shadow",
            "ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE": "true",
        },
        selector=_recommendation,
    )
    assert failed is not None and failed.bypass_reason == "unexpected_error"
    monkeypatch.setattr(shadow.threading.Thread, "start", original)
    recovered = evaluate_notdiamond_shadow(
        prompt="research",
        role="synthesizer",
        candidates=("zai/glm-5.2",),
        environ={
            "ANTIEK_NOTDIAMOND_MODE": "shadow",
            "ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE": "true",
        },
        selector=_recommendation,
    )
    assert recovered is not None and recovered.bypass_reason == "shadow"
