"""Decision-tree selection → real dispatch override pair.

``substrate.dispatch.router.dispatch`` only applies a primary swap when
**both** ``provider_override`` and ``model_override`` are set. Returning a
model id alone is insufficient. This bridge is the pure residual that turns
a decision-tree / settings selection into the kwargs the real call site uses.

Does **not** reimplement cost projection (#440 owns that). Does **not** make
NotDiamond authoritative.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from substrate.dispatch.router import dispatch as real_dispatch

from .registry import ModelRegistry, get_model, select_driver, selected_driver


@dataclass(frozen=True)
class DispatchOverride:
    """Both halves required by ``dispatch`` primary-swap contract."""

    provider_override: str
    model_override: str
    model_id: str
    provider_id: str

    def as_dispatch_kwargs(self) -> dict[str, str]:
        return {
            "provider_override": self.provider_override,
            "model_override": self.model_override,
        }


def resolve_dispatch_override(
    registry: ModelRegistry,
    model_id: str | None = None,
) -> DispatchOverride:
    """Resolve decision-tree selection to a full dispatch override pair.

    Uses ``select_driver`` (or current selection) for the model half, and the
    registered entry's ``provider_id`` for the provider half.

    Raises ``KeyError`` / ``ValueError`` for unknown or disabled models.
    Raises ``ValueError`` if no model is selected and none was passed.
    """
    if model_id is not None:
        mid = select_driver(registry, model_id)
    else:
        mid = selected_driver(registry)
        if mid is None:
            raise ValueError("no model selected on the decision-tree registry")
    entry = get_model(registry, mid)
    if entry is None:
        raise KeyError(f"unknown model_id: {mid}")
    if not entry.enabled:
        raise ValueError(f"model {mid} is disabled")
    if not entry.provider_id.strip():
        raise ValueError(f"model {mid} has empty provider_id")
    return DispatchOverride(
        provider_override=entry.provider_id,
        model_override=entry.model_id,
        model_id=entry.model_id,
        provider_id=entry.provider_id,
    )


def resolve_override_for_session(
    registry: ModelRegistry,
    session_model_id: str | None,
) -> DispatchOverride | None:
    """Handoff from floating_session.model_id → dispatch override.

    Returns None when the session has no model_id (caller uses config default).
    """
    if not session_model_id or not str(session_model_id).strip():
        return None
    return resolve_dispatch_override(registry, str(session_model_id).strip())


def dispatch_kwargs_from_selection(
    registry: ModelRegistry,
    model_id: str | None = None,
) -> dict[str, str]:
    """Public entry: kwargs fragment for ``dispatch(..., **kwargs)``."""
    return resolve_dispatch_override(registry, model_id).as_dispatch_kwargs()


def assert_dispatch_accepts_override_kwargs() -> list[str]:
    """Structural: real ``dispatch`` signature exposes both override params."""
    params = inspect.signature(real_dispatch).parameters
    missing = [
        name
        for name in ("provider_override", "model_override")
        if name not in params
    ]
    if missing:
        raise AssertionError(
            f"dispatch missing override params: {missing}; known={list(params)}"
        )
    return ["provider_override", "model_override"]


def build_dispatch_call_kwargs(
    *,
    prompt: str,
    role: str,
    investigation_id: str,
    registry: ModelRegistry,
    model_id: str | None = None,
    parent_event_id: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Build full kwargs for the real ``dispatch`` call site (no network).

    Tests assert shape; production callers pass this into ``dispatch(**kwargs)``
    or use ``dispatch_with_selected_driver``.
    """
    override = resolve_dispatch_override(registry, model_id)
    kwargs: dict[str, Any] = {
        "prompt": prompt,
        "role": role,
        "investigation_id": investigation_id,
        "provider_override": override.provider_override,
        "model_override": override.model_override,
    }
    if parent_event_id is not None:
        kwargs["parent_event_id"] = parent_event_id
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return kwargs


def dispatch_with_selected_driver(
    prompt: str,
    role: str,
    *,
    investigation_id: str,
    registry: ModelRegistry,
    model_id: str | None = None,
    parent_event_id: str | None = None,
    max_tokens: int | None = None,
    dispatch_fn: Callable[..., Any] | None = None,
) -> Any:
    """Call the real ``dispatch`` path with decision-tree overrides applied.

    ``dispatch_fn`` is injectable for tests (default: shipped router.dispatch).
    """
    kwargs = build_dispatch_call_kwargs(
        prompt=prompt,
        role=role,
        investigation_id=investigation_id,
        registry=registry,
        model_id=model_id,
        parent_event_id=parent_event_id,
        max_tokens=max_tokens,
    )
    fn = dispatch_fn if dispatch_fn is not None else real_dispatch
    return fn(**kwargs)


def settings_budget_projection_still_owned_by_settings() -> str:
    """Honesty: cost projection lives in #440 settings_budget, not here."""
    from interfaces.research.api import settings_budget

    if not hasattr(settings_budget, "estimate_prompt_cost"):
        raise RuntimeError("#440 estimate_prompt_cost missing from settings_budget")
    return "interfaces.research.api.settings_budget.estimate_prompt_cost"
