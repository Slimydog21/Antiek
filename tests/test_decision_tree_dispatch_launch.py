"""Consumer double-run launch for decision-tree → dispatch override."""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.model_registration import (  # noqa: E402
    ModelRegistry,
    add_model,
    assert_dispatch_accepts_override_kwargs,
    clear_decision_tree_registry,
    dispatch_kwargs_from_selection,
    dispatch_with_selected_driver,
    resolve_dispatch_override,
    resolve_override_for_session,
    set_decision_tree_registry,
    settings_budget_projection_still_owned_by_settings,
)
from substrate.research_bridge import llm_dispatch  # noqa: E402


def _once() -> dict[str, object]:
    reg = ModelRegistry()
    add_model(reg, "launch-glm", provider_id="zhipu")
    add_model(reg, "launch-xai", provider_id="xai", select=False)
    ov = resolve_dispatch_override(reg, "launch-glm")
    kwargs = dispatch_kwargs_from_selection(reg, "launch-glm")
    assert kwargs == ov.as_dispatch_kwargs()
    assert kwargs["model_override"] == "launch-glm"
    assert kwargs["provider_override"] == "zhipu"
    assert_dispatch_accepts_override_kwargs()
    settings_budget_projection_still_owned_by_settings()

    captured: list[dict] = []

    def fake_dispatch(**kw):
        captured.append(dict(kw))
        usage = type("U", (), {"input_tokens": 0, "output_tokens": 0})()
        return type(
            "R",
            (),
            {
                "text": "ok",
                "provider": kw.get("provider_override"),
                "model": kw.get("model_override"),
                "usage": usage,
                "cost_usd": 0.0,
            },
        )()

    dispatch_with_selected_driver(
        "launch prompt",
        "synthesizer",
        investigation_id="inv_launch",
        registry=reg,
        model_id="launch-xai",
        dispatch_fn=fake_dispatch,
    )
    assert captured[0]["model_override"] == "launch-xai"
    assert captured[0]["provider_override"] == "xai"

    # Production research_bridge path
    set_decision_tree_registry(reg, model_id="launch-glm")
    try:
        orig = llm_dispatch.dispatch
        llm_dispatch.dispatch = fake_dispatch  # type: ignore[assignment]
        try:
            call = llm_dispatch.build_dispatch_llm_callable(investigation_id="inv_prod")
            call("prod prompt")
        finally:
            llm_dispatch.dispatch = orig  # type: ignore[assignment]
    finally:
        clear_decision_tree_registry()
    assert captured[-1]["model_override"] == "launch-glm"
    assert captured[-1]["provider_override"] == "zhipu"

    sess = resolve_override_for_session(reg, "launch-glm")
    assert sess is not None and sess.model_override == "launch-glm"

    return {
        "model_override": kwargs["model_override"],
        "provider_override": kwargs["provider_override"],
        "session_model": sess.model_override,
        "dispatch_model": captured[0]["model_override"],
        "dispatch_provider": captured[0]["provider_override"],
        "prod_model": captured[-1]["model_override"],
        "prod_provider": captured[-1]["provider_override"],
    }


def test_decision_tree_dispatch_consumer_double_run_stable():
    a = _once()
    b = _once()
    assert a == b
    assert a["model_override"] == "launch-glm"
    assert a["provider_override"] == "zhipu"
    assert a["dispatch_model"] == "launch-xai"
