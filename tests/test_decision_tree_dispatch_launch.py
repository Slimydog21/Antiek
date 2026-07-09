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
    dispatch_kwargs_from_selection,
    dispatch_with_selected_driver,
    resolve_dispatch_override,
    resolve_override_for_session,
    settings_budget_projection_still_owned_by_settings,
)


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
        return type("R", (), {"text": "ok", "provider": kw["provider_override"], "model": kw["model_override"]})()

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

    sess = resolve_override_for_session(reg, "launch-glm")
    assert sess is not None and sess.model_override == "launch-glm"

    return {
        "model_override": kwargs["model_override"],
        "provider_override": kwargs["provider_override"],
        "session_model": sess.model_override,
        "dispatch_model": captured[0]["model_override"],
        "dispatch_provider": captured[0]["provider_override"],
    }


def test_decision_tree_dispatch_consumer_double_run_stable():
    a = _once()
    b = _once()
    assert a == b
    assert a["model_override"] == "launch-glm"
    assert a["provider_override"] == "zhipu"
    assert a["dispatch_model"] == "launch-xai"
