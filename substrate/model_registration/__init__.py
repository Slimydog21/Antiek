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

from .depth_tiers import (
    DepthTierPreset,
    apply_depth_tier,
    clear_active_depth_tier,
    depth_tiers_settings_payload,
    get_active_depth_tier,
    get_depth_tier_preset,
    list_depth_tiers,
    project_depth_tiers_html,
    set_active_depth_tier,
)
from .dispatch_bridge import (
    DispatchOverride,
    apply_decision_tree_overrides,
    assert_dispatch_accepts_override_kwargs,
    build_dispatch_call_kwargs,
    dispatch_kwargs_from_selection,
    dispatch_with_selected_driver,
    resolve_dispatch_override,
    resolve_override_for_session,
    settings_budget_projection_still_owned_by_settings,
)
from .install import (
    DecisionTreeInstallResult,
    clear_decision_tree_selection,
    install_decision_tree_selection,
    list_operator_models,
    read_decision_tree_selection,
    register_operator_model,
)
from .process_registry import (
    clear_decision_tree_registry,
    get_decision_tree_model_id,
    get_decision_tree_registry,
    set_decision_tree_registry,
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
    "DecisionTreeInstallResult",
    "DepthTierPreset",
    "DispatchOverride",
    "ModelEntry",
    "ModelRegistry",
    "add_model",
    "apply_decision_tree_overrides",
    "apply_depth_tier",
    "assert_dispatch_accepts_override_kwargs",
    "build_dispatch_call_kwargs",
    "clear_active_depth_tier",
    "clear_decision_tree_registry",
    "clear_decision_tree_selection",
    "depth_tiers_settings_payload",
    "dispatch_kwargs_from_selection",
    "dispatch_with_selected_driver",
    "get_active_depth_tier",
    "get_decision_tree_model_id",
    "get_decision_tree_registry",
    "get_depth_tier_preset",
    "get_model",
    "install_decision_tree_selection",
    "list_depth_tiers",
    "list_models",
    "list_operator_models",
    "model_override_for_dispatch",
    "project_depth_tiers_html",
    "read_decision_tree_selection",
    "register_operator_model",
    "resolve_dispatch_override",
    "resolve_override_for_session",
    "select_driver",
    "selected_driver",
    "set_active_depth_tier",
    "set_decision_tree_registry",
    "settings_budget_projection_still_owned_by_settings",
]
