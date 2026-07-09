"""In-process model registry for add-model + decision-tree select_driver.

Pure logic. Persistence of operator settings remains the API/settings
sidecar (#440); this substrate is the callable used by tests and by a
dispatch call site that needs ``model_override``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    provider_id: str
    display_name: str = ""
    enabled: bool = True
    input_usd_per_1m: float = 0.0
    output_usd_per_1m: float = 0.0


@dataclass
class ModelRegistry:
    """Mutable registry + currently selected driver id."""

    models: dict[str, ModelEntry] = field(default_factory=dict)
    selected_model_id: str | None = None


def add_model(
    registry: ModelRegistry,
    model_id: str,
    *,
    provider_id: str,
    display_name: str = "",
    enabled: bool = True,
    input_usd_per_1m: float = 0.0,
    output_usd_per_1m: float = 0.0,
    select: bool = False,
) -> ModelEntry:
    """Register (or replace) a model. Returns the entry.

    Raises ``ValueError`` on empty model_id / provider_id.
    """
    mid = (model_id or "").strip()
    pid = (provider_id or "").strip()
    if not mid:
        raise ValueError("model_id is required")
    if not pid:
        raise ValueError("provider_id is required")
    entry = ModelEntry(
        model_id=mid,
        provider_id=pid,
        display_name=(display_name or mid).strip(),
        enabled=bool(enabled),
        input_usd_per_1m=float(input_usd_per_1m),
        output_usd_per_1m=float(output_usd_per_1m),
    )
    registry.models[mid] = entry
    if select or registry.selected_model_id is None:
        registry.selected_model_id = mid
    return entry


def get_model(registry: ModelRegistry, model_id: str) -> ModelEntry | None:
    return registry.models.get(model_id)


def list_models(registry: ModelRegistry, *, enabled_only: bool = False) -> list[ModelEntry]:
    rows = list(registry.models.values())
    if enabled_only:
        rows = [m for m in rows if m.enabled]
    return sorted(rows, key=lambda m: m.model_id)


def select_driver(registry: ModelRegistry, model_id: str) -> str:
    """Select model as the decision-tree driver; return model_override string.

    The return value is intended for
    ``dispatch(..., model_override=select_driver(...))``.
    Raises ``KeyError`` if unknown; ``ValueError`` if disabled.
    """
    entry = registry.models.get(model_id)
    if entry is None:
        raise KeyError(f"unknown model_id: {model_id}")
    if not entry.enabled:
        raise ValueError(f"model {model_id} is disabled")
    registry.selected_model_id = model_id
    return entry.model_id


def selected_driver(registry: ModelRegistry) -> str | None:
    if registry.selected_model_id is None:
        return None
    entry = registry.models.get(registry.selected_model_id)
    if entry is None or not entry.enabled:
        return None
    return entry.model_id


def model_override_for_dispatch(registry: ModelRegistry, model_id: str | None = None) -> str | None:
    """Convenience: resolve override for a dispatch call site."""
    if model_id is not None:
        return select_driver(registry, model_id)
    return selected_driver(registry)
