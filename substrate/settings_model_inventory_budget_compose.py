"""Settings model inventory + budget bar compose (pure).

secrets_stored and live_router_authorized always False.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from substrate.model_decision.usage_bar import (
    UsageBar,
    compute_usage_bar,
    usage_bar_to_dict,
)

_SECRETISH = re.compile(r"sk-|api[_-]?key|secret|bearer\s", re.I)


class SettingsModelInventoryBudgetComposeError(ValueError):
    """Fail-closed validation for settings inventory budget."""


@dataclass(frozen=True)
class SettingsModelInventoryBudgetCompose:
    inventory_count: int
    pending_add_count: int
    model_ids: tuple[str, ...]
    selected_model_id: str | None
    selected_in_inventory: bool | None
    bar: UsageBar
    secrets_stored: bool
    live_router_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "inventory_count": self.inventory_count,
            "pending_add_count": self.pending_add_count,
            "model_ids": list(self.model_ids),
            "selected_model_id": self.selected_model_id,
            "selected_in_inventory": self.selected_in_inventory,
            "bar": usage_bar_to_dict(self.bar),
            "secrets_stored": False,
            "live_router_authorized": False,
            "notes": list(self.notes),
            "authority": "settings_model_inventory_budget_compose_advisory",
        }


def _require_model_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsModelInventoryBudgetComposeError(
            f"{field} must be a non-empty string"
        )
    mid = value.strip()
    if len(mid) > 128 or _SECRETISH.search(mid) or " " in mid:
        raise SettingsModelInventoryBudgetComposeError(
            f"{field} must be a model id, not secret material"
        )
    return mid


def compose_settings_model_inventory_budget(
    *,
    models: object,
    daily_cap_usd: object,
    spent_usd: object,
    pending_add_model_ids: object | None = None,
    selected_model_id: object | None = None,
) -> SettingsModelInventoryBudgetCompose:
    """Compose inventory + usage bar. Never stores secrets; never auto-routes."""
    if not isinstance(models, list):
        raise SettingsModelInventoryBudgetComposeError("models must be an array")

    notes: list[str] = [
        "secrets_stored=false — model ids/inventory only; never raw API keys",
        "live_router_authorized=false — operator selects model",
    ]

    model_ids: list[str] = []
    seen: set[str] = set()
    for i, m in enumerate(models):
        if not isinstance(m, dict):
            raise SettingsModelInventoryBudgetComposeError(
                f"models[{i}] must be an object"
            )
        mid = _require_model_id(m.get("model_id"), field=f"models[{i}].model_id")
        if mid in seen:
            raise SettingsModelInventoryBudgetComposeError(
                f"duplicate model_id: {mid}"
            )
        seen.add(mid)
        model_ids.append(mid)
        prov = m.get("provider")
        if prov is not None:
            if not isinstance(prov, str) or not prov.strip():
                raise SettingsModelInventoryBudgetComposeError(
                    f"models[{i}].provider must be non-empty string when set"
                )
            if _SECRETISH.search(prov):
                raise SettingsModelInventoryBudgetComposeError(
                    f"models[{i}].provider must not contain secret material"
                )

    pending_add_count = 0
    if pending_add_model_ids is not None:
        if not isinstance(pending_add_model_ids, list):
            raise SettingsModelInventoryBudgetComposeError(
                "pending_add_model_ids must be an array when set"
            )
        pseen: set[str] = set()
        for i, raw in enumerate(pending_add_model_ids):
            pid = _require_model_id(raw, field=f"pending_add_model_ids[{i}]")
            if pid in pseen:
                raise SettingsModelInventoryBudgetComposeError(
                    f"duplicate pending_add_model_id: {pid}"
                )
            pseen.add(pid)
            if pid in seen:
                notes.append(f"pending {pid} already in inventory")
        pending_add_count = len(pseen)
        notes.append(f"pending_add_count={pending_add_count} (ids only)")

    inventory_count = len(model_ids)
    notes.append(f"inventory_count={inventory_count}")

    selected: str | None = None
    selected_in_inventory: bool | None = None
    if selected_model_id is not None:
        selected = _require_model_id(
            selected_model_id, field="selected_model_id"
        )
        selected_in_inventory = selected in seen
        notes.append(
            f"selected_model_id={selected} in inventory"
            if selected_in_inventory
            else f"selected_model_id={selected} not in inventory"
        )

    try:
        bar = compute_usage_bar(
            daily_cap_usd=daily_cap_usd if isinstance(daily_cap_usd, (int, float)) or daily_cap_usd is None else daily_cap_usd,  # type: ignore[arg-type]
            spent_usd=spent_usd if isinstance(spent_usd, (int, float)) or spent_usd is None else spent_usd,  # type: ignore[arg-type]
            spend_basis="settings_budget_display",
        )
    except ValueError as e:
        raise SettingsModelInventoryBudgetComposeError(str(e)) from e
    notes.extend(bar.notes)
    notes.extend(("secrets_stored=false", "live_router_authorized=false"))

    return SettingsModelInventoryBudgetCompose(
        inventory_count=inventory_count,
        pending_add_count=pending_add_count,
        model_ids=tuple(model_ids),
        selected_model_id=selected,
        selected_in_inventory=selected_in_inventory,
        bar=bar,
        secrets_stored=False,
        live_router_authorized=False,
        notes=tuple(notes),
        authority="settings_model_inventory_budget_compose_advisory",
    )


__all__ = [
    "SettingsModelInventoryBudgetCompose",
    "SettingsModelInventoryBudgetComposeError",
    "compose_settings_model_inventory_budget",
]
