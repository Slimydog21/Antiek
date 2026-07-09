"""Thin residual: operator add-model + decision-tree driver selection.

Main already ships settings inventory / budget bar / prompt cost projection
via ``interfaces/research/api/settings_budget.py`` (#440). This module does
**not** reimplement that stack.

It closes the proven residual:

* **add_model** — register a model id with optional provider binding for
  the decision-tree / settings panel.
* **select_driver** — produce a ``model_override`` string for the model half.
* **dispatch_bridge** — both ``provider_override`` + ``model_override`` for the
  real ``substrate.dispatch.router.dispatch`` primary-swap contract.

Budget projection remains #440's ``estimate_prompt_cost`` /
``POST /settings/prompt-cost-estimate``.
"""

from __future__ import annotations

from .dispatch_bridge import (
    DispatchOverride,
    assert_dispatch_accepts_override_kwargs,
    build_dispatch_call_kwargs,
    dispatch_kwargs_from_selection,
    dispatch_with_selected_driver,
    resolve_dispatch_override,
    resolve_override_for_session,
    settings_budget_projection_still_owned_by_settings,
)
from .registry import (
    ModelEntry,
    ModelRegistry,
    add_model,
    get_model,
    list_models,
    model_override_for_dispatch,
    select_driver,
    selected_driver,
)

__all__ = [
    "DispatchOverride",
    "ModelEntry",
    "ModelRegistry",
    "add_model",
    "assert_dispatch_accepts_override_kwargs",
    "build_dispatch_call_kwargs",
    "dispatch_kwargs_from_selection",
    "dispatch_with_selected_driver",
    "get_model",
    "list_models",
    "model_override_for_dispatch",
    "resolve_dispatch_override",
    "resolve_override_for_session",
    "select_driver",
    "selected_driver",
    "settings_budget_projection_still_owned_by_settings",
]
