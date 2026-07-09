"""Thin residual: operator add-model + decision-tree driver selection.

Main already ships settings inventory / budget bar / prompt cost projection
via ``interfaces/research/api/settings_budget.py`` (#440). This module does
**not** reimplement that stack.

It closes the proven residual:

* **add_model** — register a model id with optional provider binding for
  the decision-tree / settings panel.
* **select_driver** — produce a ``model_override`` string suitable for
  ``substrate.dispatch.router.dispatch(..., model_override=...)``.

Budget projection remains #440's ``estimate_prompt_cost`` /
``POST /settings/prompt-cost-estimate``.
"""

from __future__ import annotations

from .registry import (
    ModelEntry,
    ModelRegistry,
    add_model,
    get_model,
    list_models,
    select_driver,
    selected_driver,
)

__all__ = [
    "ModelEntry",
    "ModelRegistry",
    "add_model",
    "get_model",
    "list_models",
    "select_driver",
    "selected_driver",
]
