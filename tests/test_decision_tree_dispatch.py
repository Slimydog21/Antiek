"""Real-path tests: decision-tree selection → dispatch override pair.

Drives shipped bridge + real dispatch signature. Injectable dispatch_fn —
no live multi-provider network.
"""

from __future__ import annotations

import inspect
import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.dispatch import router as dispatch_router  # noqa: E402
from substrate.model_registration import (  # noqa: E402
    ModelRegistry,
    add_model,
    assert_dispatch_accepts_override_kwargs,
    build_dispatch_call_kwargs,
    dispatch_kwargs_from_selection,
    dispatch_with_selected_driver,
    resolve_dispatch_override,
    resolve_override_for_session,
    select_driver,
    settings_budget_projection_still_owned_by_settings,
)


@pytest.fixture
def registry() -> ModelRegistry:
    reg = ModelRegistry()
    add_model(reg, "glm-5.2", provider_id="zhipu", display_name="GLM 5.2")
    add_model(reg, "composer-2.5", provider_id="xai", select=False)
    add_model(reg, "off-model", provider_id="p", enabled=False, select=False)
    return reg


def test_resolve_dispatch_override_both_halves(registry):
    ov = resolve_dispatch_override(registry, "glm-5.2")
    assert ov.model_override == "glm-5.2"
    assert ov.provider_override == "zhipu"
    assert ov.as_dispatch_kwargs() == {
        "provider_override": "zhipu",
        "model_override": "glm-5.2",
    }
    # select_driver half still works and matches
    assert select_driver(registry, "composer-2.5") == "composer-2.5"
    ov2 = resolve_dispatch_override(registry)  # uses selected
    assert ov2.model_override == "composer-2.5"
    assert ov2.provider_override == "xai"


def test_unknown_and_disabled_rejected(registry):
    with pytest.raises(KeyError):
        resolve_dispatch_override(registry, "missing")
    with pytest.raises(ValueError, match="disabled"):
        resolve_dispatch_override(registry, "off-model")


def test_dispatch_signature_accepts_override_kwargs():
    names = assert_dispatch_accepts_override_kwargs()
    assert "provider_override" in names
    assert "model_override" in names
    sig = inspect.signature(dispatch_router.dispatch)
    assert "provider_override" in sig.parameters
    assert "model_override" in sig.parameters


def test_build_dispatch_call_kwargs_shape(registry):
    kwargs = build_dispatch_call_kwargs(
        prompt="hello",
        role="synthesizer",
        investigation_id="inv_test",
        registry=registry,
        model_id="glm-5.2",
        parent_event_id="evt_1",
    )
    assert kwargs["prompt"] == "hello"
    assert kwargs["role"] == "synthesizer"
    assert kwargs["investigation_id"] == "inv_test"
    assert kwargs["provider_override"] == "zhipu"
    assert kwargs["model_override"] == "glm-5.2"
    assert kwargs["parent_event_id"] == "evt_1"
    # Usable against real signature
    sig = inspect.signature(dispatch_router.dispatch)
    for key in kwargs:
        if key == "prompt":
            continue  # positional in signature but also ok as kw in Python
        assert key in sig.parameters, f"unexpected kw {key}"


def test_dispatch_with_selected_driver_calls_real_path_with_overrides(registry):
    captured: dict = {}

    def fake_dispatch(**kwargs):
        captured.update(kwargs)
        return type("R", (), {"text": "ok", "provider": kwargs["provider_override"], "model": kwargs["model_override"]})()

    result = dispatch_with_selected_driver(
        "prompt body",
        "synthesizer",
        investigation_id="inv_x",
        registry=registry,
        model_id="composer-2.5",
        dispatch_fn=fake_dispatch,
    )
    assert captured["provider_override"] == "xai"
    assert captured["model_override"] == "composer-2.5"
    assert captured["role"] == "synthesizer"
    assert captured["investigation_id"] == "inv_x"
    assert result.model == "composer-2.5"


def test_session_model_id_handoff(registry):
    assert resolve_override_for_session(registry, None) is None
    assert resolve_override_for_session(registry, "") is None
    ov = resolve_override_for_session(registry, "glm-5.2")
    assert ov is not None
    assert ov.model_override == "glm-5.2"
    assert ov.provider_override == "zhipu"


def test_budget_projection_still_settings_owned():
    path = settings_budget_projection_still_owned_by_settings()
    assert "settings_budget" in path
    assert "estimate_prompt_cost" in path
    # No second projection module under model_registration
    import substrate.model_registration as mr

    assert not hasattr(mr, "estimate_prompt_cost")
    assert not hasattr(mr, "project_prompt_cost")


def test_dispatch_kwargs_from_selection_public_entry(registry):
    d = dispatch_kwargs_from_selection(registry, "glm-5.2")
    assert d["model_override"] == "glm-5.2"
    assert d["provider_override"] == "zhipu"


def test_research_bridge_llm_dispatch_applies_decision_tree(registry, monkeypatch):
    """Production call site: research_bridge.build_dispatch_llm_callable → dispatch."""
    from substrate.model_registration import (
        clear_decision_tree_registry,
        set_decision_tree_registry,
    )
    from substrate.research_bridge import llm_dispatch

    captured: dict = {}

    def fake_dispatch(**kwargs):
        captured.update(kwargs)
        usage = type("U", (), {"input_tokens": 1, "output_tokens": 2})()
        return type(
            "R",
            (),
            {
                "text": "ok",
                "provider": kwargs.get("provider_override") or "default",
                "model": kwargs.get("model_override") or "default",
                "usage": usage,
                "cost_usd": 0.0,
            },
        )()

    monkeypatch.setattr(llm_dispatch, "dispatch", fake_dispatch)
    set_decision_tree_registry(registry, model_id="glm-5.2")
    try:
        call = llm_dispatch.build_dispatch_llm_callable(investigation_id="inv_prod")
        out = call("extract claims from this note")
        assert out.text == "ok"
        assert captured["provider_override"] == "zhipu"
        assert captured["model_override"] == "glm-5.2"
        assert captured["role"] == "note_taker"
        assert captured["investigation_id"] == "inv_prod"
    finally:
        clear_decision_tree_registry()


def test_research_bridge_explicit_registry_kwarg(registry, monkeypatch):
    """Explicit registry on build_dispatch_llm_callable (no process global)."""
    from substrate.research_bridge import llm_dispatch

    captured: dict = {}

    def fake_dispatch(**kwargs):
        captured.update(kwargs)
        usage = type("U", (), {"input_tokens": 0, "output_tokens": 0})()
        return type(
            "R",
            (),
            {
                "text": "x",
                "provider": kwargs["provider_override"],
                "model": kwargs["model_override"],
                "usage": usage,
                "cost_usd": 0.0,
            },
        )()

    monkeypatch.setattr(llm_dispatch, "dispatch", fake_dispatch)
    call = llm_dispatch.build_dispatch_llm_callable(
        investigation_id="inv_y",
        registry=registry,
        model_id="composer-2.5",
    )
    call("prompt")
    assert captured["provider_override"] == "xai"
    assert captured["model_override"] == "composer-2.5"
