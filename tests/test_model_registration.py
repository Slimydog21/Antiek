"""Residual model registration: add-model + select_driver → model_override.

Does not re-test #440 settings budget projection — that lives in
tests/test_settings_budget_api.py on main.
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
    list_models,
    select_driver,
    selected_driver,
)
from substrate.model_registration.registry import model_override_for_dispatch  # noqa: E402


def test_add_model_and_list():
    reg = ModelRegistry()
    e = add_model(
        reg,
        "glm-5.2",
        provider_id="zhipu",
        display_name="GLM 5.2",
        input_usd_per_1m=0.5,
        output_usd_per_1m=1.5,
    )
    assert e.model_id == "glm-5.2"
    assert list_models(reg)[0].provider_id == "zhipu"
    assert selected_driver(reg) == "glm-5.2"


def test_select_driver_returns_model_override_string():
    reg = ModelRegistry()
    add_model(reg, "gpt-5.5", provider_id="openai")
    add_model(reg, "composer-2.5", provider_id="xai", select=False)
    override = select_driver(reg, "composer-2.5")
    assert override == "composer-2.5"
    assert selected_driver(reg) == "composer-2.5"
    assert model_override_for_dispatch(reg) == "composer-2.5"


def test_select_driver_unknown_and_disabled():
    reg = ModelRegistry()
    with pytest.raises(KeyError):
        select_driver(reg, "missing")
    add_model(reg, "off-model", provider_id="p", enabled=False, select=True)
    with pytest.raises(ValueError, match="disabled"):
        select_driver(reg, "off-model")


def test_dispatch_accepts_model_override_kwarg():
    """Structural: real dispatch signature exposes model_override for the residual."""
    sig = inspect.signature(dispatch_router.dispatch)
    assert "model_override" in sig.parameters
    # Decision-tree residual: select_driver output is a str usable as override.
    reg = ModelRegistry()
    add_model(reg, "mimo-v2.5", provider_id="xiaomi")
    override = select_driver(reg, "mimo-v2.5")
    assert isinstance(override, str)
    assert override == "mimo-v2.5"
