"""Operator install entry: select model → decision-tree process registry.

Settings UI/API call this so research_bridge dispatch can read the choice.
Process-local by design (honest single-process / same-daemon limitation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .process_registry import (
    clear_decision_tree_registry,
    get_decision_tree_model_id,
    get_decision_tree_registry,
    set_decision_tree_registry,
)
from .registry import ModelRegistry, add_model, get_model, select_driver


@dataclass(frozen=True)
class DecisionTreeInstallResult:
    model_id: str
    provider_id: str
    installed: bool
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider_id": self.provider_id,
            "installed": self.installed,
            "notes": list(self.notes),
        }


def install_decision_tree_selection(
    model_id: str,
    *,
    provider_id: str | None = None,
    registry: ModelRegistry | None = None,
    ensure_registered: bool = True,
) -> DecisionTreeInstallResult:
    """Install operator model choice into the process-local decision-tree registry.

    If ``registry`` is None, reuses the active process registry or creates one.
    When ``ensure_registered`` and the model is missing, requires ``provider_id``
    to register a new entry (add-model residual path).
    """
    mid = (model_id or "").strip()
    if not mid:
        raise ValueError("model_id is required")

    reg = registry if registry is not None else get_decision_tree_registry()
    if reg is None:
        reg = ModelRegistry()

    entry = get_model(reg, mid)
    notes: list[str] = []
    if entry is None:
        if not ensure_registered:
            raise KeyError(f"unknown model_id: {mid}")
        pid = (provider_id or "").strip()
        if not pid:
            raise ValueError(
                "provider_id is required to register a new model for decision-tree install"
            )
        entry = add_model(reg, mid, provider_id=pid, select=True)
        notes.append(f"registered model {mid} under provider {pid}")
    else:
        select_driver(reg, mid)

    set_decision_tree_registry(reg, model_id=mid)
    notes.append(
        "installed into process-local decision-tree registry "
        "(same process as dispatch must receive this install)"
    )
    return DecisionTreeInstallResult(
        model_id=entry.model_id,
        provider_id=entry.provider_id,
        installed=True,
        notes=tuple(notes),
    )


def read_decision_tree_selection() -> dict[str, Any]:
    """Read back current process-local selection (for Settings GET)."""
    reg = get_decision_tree_registry()
    mid = get_decision_tree_model_id()
    if reg is None or mid is None:
        return {
            "model_id": None,
            "provider_id": None,
            "installed": False,
            "notes": [
                "no decision-tree selection installed in this process",
            ],
        }
    entry = get_model(reg, mid)
    return {
        "model_id": mid,
        "provider_id": entry.provider_id if entry else None,
        "installed": True,
        "notes": [
            "process-local selection; multi-worker daemons need install on each worker",
        ],
    }


def clear_decision_tree_selection() -> dict[str, Any]:
    clear_decision_tree_registry()
    return {
        "model_id": None,
        "provider_id": None,
        "installed": False,
        "notes": ["decision-tree selection cleared"],
    }


def register_operator_model(
    model_id: str,
    *,
    provider_id: str,
    display_name: str = "",
    select: bool = False,
) -> dict[str, Any]:
    """Add-model product path into the process-local decision-tree registry.

    Does not store API secrets (operator-gated elsewhere). Does not auto-
    install as driver unless ``select=True``.
    """
    from .registry import list_models

    mid = (model_id or "").strip()
    pid = (provider_id or "").strip()
    if not mid:
        raise ValueError("model_id is required")
    if not pid:
        raise ValueError("provider_id is required")

    reg = get_decision_tree_registry()
    if reg is None:
        reg = ModelRegistry()
    active_mid = get_decision_tree_model_id()
    entry = add_model(
        reg,
        mid,
        provider_id=pid,
        display_name=display_name or mid,
        select=select,
    )
    # Keep process registry pointer; only change active driver when select=True
    # or when no prior active selection exists.
    next_active = mid if select else (active_mid or reg.selected_model_id)
    set_decision_tree_registry(reg, model_id=next_active)

    return {
        "model_id": entry.model_id,
        "provider_id": entry.provider_id,
        "display_name": entry.display_name,
        "enabled": entry.enabled,
        "selected": get_decision_tree_model_id() == entry.model_id,
        "view_format": "html",
        "settings_panel": "add_model",
        "source": "substrate.model_registration.install",
        "notes": [
            f"Registered model {entry.model_id} under provider {entry.provider_id} "
            "(process-local; secrets remain operator-gated).",
        ],
        "registered_count": len(list_models(reg)),
    }


def list_operator_models() -> dict[str, Any]:
    """List process-local registered models for Settings."""
    from .registry import list_models

    reg = get_decision_tree_registry()
    active = get_decision_tree_model_id()
    if reg is None:
        return {
            "models": [],
            "count": 0,
            "active_model_id": None,
            "view_format": "html",
            "settings_panel": "add_model",
            "source": "substrate.model_registration.install",
            "notes": ["No process-local model registry yet — add a model below."],
        }
    rows = [
        {
            "model_id": m.model_id,
            "provider_id": m.provider_id,
            "display_name": m.display_name,
            "enabled": m.enabled,
            "selected": m.model_id == active,
        }
        for m in list_models(reg)
    ]
    return {
        "models": rows,
        "count": len(rows),
        "active_model_id": active,
        "view_format": "html",
        "settings_panel": "add_model",
        "source": "substrate.model_registration.install",
        "notes": [
            "Process-local registry only; multi-worker daemons need the same adds per worker.",
        ],
    }
