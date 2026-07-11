"""Settings add-model inventory pack (pure).

secrets_stored, live_router_authorized, inventory_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.settings_decision_tree_usage_bar_compose import (
    SettingsDecisionTreeUsageBarCompose,
    SettingsDecisionTreeUsageBarComposeError,
    compose_settings_decision_tree_usage_bar,
)
from substrate.settings_model_inventory_budget_compose import (
    SettingsModelInventoryBudgetCompose,
    SettingsModelInventoryBudgetComposeError,
    compose_settings_model_inventory_budget,
)

AddModelAction = Literal["preview", "propose_add"]
VALID_ACTIONS = frozenset(("preview", "propose_add"))


class SettingsAddModelInventoryComposeError(ValueError):
    """Fail-closed validation for settings add-model inventory."""


@dataclass(frozen=True)
class SettingsAddModelInventoryCompose:
    inventory: SettingsModelInventoryBudgetCompose
    decision_tree: SettingsDecisionTreeUsageBarCompose | None
    action: AddModelAction
    proposed_new_model_ids: tuple[str, ...]
    proposed_new_count: int
    pack_ready: bool
    secrets_stored: bool
    live_router_authorized: bool
    inventory_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "inventory": self.inventory.to_dict(),
            "decision_tree": (
                self.decision_tree.to_dict() if self.decision_tree else None
            ),
            "action": self.action,
            "proposed_new_model_ids": list(self.proposed_new_model_ids),
            "proposed_new_count": self.proposed_new_count,
            "pack_ready": self.pack_ready,
            "secrets_stored": False,
            "live_router_authorized": False,
            "inventory_mutated": False,
            "notes": list(self.notes),
            "authority": "settings_add_model_inventory_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsAddModelInventoryComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_model_id(value: object, *, field: str) -> str:
    mid = _require_nonempty(value, field=field)
    import re

    if (
        len(mid) > 128
        or re.search(r"sk-|api[_-]?key|secret|bearer\s", mid, re.I)
        or " " in mid
    ):
        raise SettingsAddModelInventoryComposeError(
            f"{field} must be a model id, not secret material"
        )
    return mid


def compose_settings_add_model_inventory(
    *,
    models: object,
    pending_add_model_ids: object,
    action: object,
    daily_cap_usd: object,
    spent_usd: object,
    operator_ack: object,
    selected_model_id: object | None = None,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
) -> SettingsAddModelInventoryCompose:
    """Add-model inventory propose/preview. Never stores secrets or mutates."""
    if not isinstance(operator_ack, bool):
        raise SettingsAddModelInventoryComposeError(
            "operator_ack must be an explicit boolean"
        )
    if action not in VALID_ACTIONS:
        raise SettingsAddModelInventoryComposeError(
            "action must be preview or propose_add"
        )
    action_s: AddModelAction = action  # type: ignore[assignment]
    if not isinstance(pending_add_model_ids, list):
        raise SettingsAddModelInventoryComposeError(
            "pending_add_model_ids must be an array"
        )

    notes: list[str] = [
        "secrets_stored=false — model ids only; never raw API keys",
        "live_router_authorized=false — operator selects model",
        "inventory_mutated=false — propose_add is intent only",
    ]

    try:
        inventory = compose_settings_model_inventory_budget(
            models=models,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            pending_add_model_ids=pending_add_model_ids,
            selected_model_id=selected_model_id,
        )
    except SettingsModelInventoryBudgetComposeError as e:
        raise SettingsAddModelInventoryComposeError(str(e)) from e
    notes.extend(f"[inventory] {n}" for n in inventory.notes)

    existing = set(inventory.model_ids)
    proposed_new: list[str] = []
    seen: set[str] = set()
    for i, raw in enumerate(pending_add_model_ids):
        mid = _require_model_id(raw, field=f"pending_add_model_ids[{i}]")
        if mid in seen:
            continue
        seen.add(mid)
        if mid not in existing:
            proposed_new.append(mid)
    notes.append(
        f"proposed_new_count={len(proposed_new)} (not yet in inventory)"
    )

    decision_tree: SettingsDecisionTreeUsageBarCompose | None = None
    if not isinstance(models, list):
        raise SettingsAddModelInventoryComposeError("models must be an array")
    model_options: list[dict[str, Any]] = []
    for m in models:
        if isinstance(m, dict) and m.get("model_id"):
            model_options.append(
                {
                    "model_id": m.get("model_id"),
                    "tier": m.get("tier"),
                }
            )
    if action_s == "propose_add":
        for mid in proposed_new:
            model_options.append({"model_id": mid, "tier": "pending_add"})

    if model_options:
        if selected_model_id is not None and str(selected_model_id).strip():
            selected = _require_model_id(
                selected_model_id, field="selected_model_id"
            )
        else:
            selected = str(model_options[0]["model_id"])
        ids = {str(m["model_id"]) for m in model_options}
        selected_final = selected if selected in ids else str(
            model_options[0]["model_id"]
        )
        try:
            decision_tree = compose_settings_decision_tree_usage_bar(
                selected_model_id=selected_final,
                models=model_options,
                daily_cap_usd=daily_cap_usd,
                spent_usd=spent_usd,
                operator_ack=operator_ack,
                projected_cost_usd_high=projected_cost_usd_high,
                projected_cost_usd_low=projected_cost_usd_low,
                pending_add_model_ids=pending_add_model_ids,
            )
        except SettingsDecisionTreeUsageBarComposeError as e:
            raise SettingsAddModelInventoryComposeError(str(e)) from e
        notes.extend(f"[decision] {n}" for n in decision_tree.notes)
    else:
        notes.append(
            "decision_tree skipped — empty inventory and no pending adds"
        )

    if action_s == "preview":
        pack_ready = operator_ack is True and inventory.secrets_stored is False
        notes.append(
            "pack_ready=true — inventory preview advisory"
            if pack_ready
            else "pack_ready=false — operator_ack required for preview pack"
        )
    else:
        if len(proposed_new) == 0:
            notes.append(
                "pack_ready=false — propose_add requires ≥1 new model id "
                "not already inventoried"
            )
            pack_ready = False
        elif not operator_ack:
            notes.append(
                "pack_ready=false — propose_add requires operator_ack"
            )
            pack_ready = False
        else:
            pack_ready = True
            notes.append(
                "pack_ready=true — propose_add intent ready; "
                "inventory_mutated=false"
            )

    if inventory.secrets_stored is not False or inventory.live_router_authorized is not False:
        raise SettingsAddModelInventoryComposeError(
            "invariant: inventory honesty flags must remain false"
        )
    if decision_tree is not None and (
        decision_tree.secrets_stored is not False
        or decision_tree.live_router_authorized is not False
    ):
        raise SettingsAddModelInventoryComposeError(
            "invariant: decision_tree honesty flags must remain false"
        )

    notes.extend(
        (
            "secrets_stored=false",
            "live_router_authorized=false",
            "inventory_mutated=false",
        )
    )

    return SettingsAddModelInventoryCompose(
        inventory=inventory,
        decision_tree=decision_tree,
        action=action_s,
        proposed_new_model_ids=tuple(proposed_new),
        proposed_new_count=len(proposed_new),
        pack_ready=pack_ready,
        secrets_stored=False,
        live_router_authorized=False,
        inventory_mutated=False,
        notes=tuple(notes),
        authority="settings_add_model_inventory_compose_advisory",
    )


def format_settings_add_model_inventory_summary(
    c: SettingsAddModelInventoryCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · action={c.action} · "
        f"inventory={c.inventory.inventory_count} · "
        f"proposed_new={c.proposed_new_count} · "
        f"secrets_stored=false · inventory_mutated=false · "
        f"live_router_authorized=false"
    )


__all__ = [
    "SettingsAddModelInventoryCompose",
    "SettingsAddModelInventoryComposeError",
    "compose_settings_add_model_inventory",
    "format_settings_add_model_inventory_summary",
]
