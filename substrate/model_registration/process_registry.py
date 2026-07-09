"""Process-local decision-tree registry for production dispatch call sites.

Settings / workstation code sets the active registry when the operator
selects a driver. Production dispatch wrappers (e.g. research_bridge
``build_dispatch_llm_callable``) read it and apply both override halves.

Not a second budget ledger and not NotDiamond authority.
"""

from __future__ import annotations

from .registry import ModelRegistry

_active_registry: ModelRegistry | None = None
_active_model_id: str | None = None


def set_decision_tree_registry(
    registry: ModelRegistry | None,
    *,
    model_id: str | None = None,
) -> None:
    """Install (or clear) the process-local decision-tree selection."""
    global _active_registry, _active_model_id
    _active_registry = registry
    _active_model_id = model_id


def get_decision_tree_registry() -> ModelRegistry | None:
    return _active_registry


def get_decision_tree_model_id() -> str | None:
    """Explicit model id override; falls back to registry.selected_model_id."""
    if _active_model_id is not None:
        return _active_model_id
    if _active_registry is not None:
        return _active_registry.selected_model_id
    return None


def clear_decision_tree_registry() -> None:
    set_decision_tree_registry(None, model_id=None)
