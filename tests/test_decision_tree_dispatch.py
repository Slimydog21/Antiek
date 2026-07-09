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
