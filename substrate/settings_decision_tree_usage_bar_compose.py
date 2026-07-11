"""Settings decision-tree + usage bar pack compose (pure).

live_router_authorized always False.
secrets_stored always False.
live_meter_read always False.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from substrate.settings_model_driver_tab_compose import (
    SettingsModelDriverTabCompose,
    SettingsModelDriverTabComposeError,
    compose_settings_model_driver_tab,
)


class SettingsDecisionTreeUsageBarComposeError(ValueError):
    """Fail-closed validation for decision tree usage bar pack."""


@dataclass(frozen=True)
class SettingsDecisionTreeUsageBarCompose:
    driver: SettingsModelDriverTabCompose
    usage_percent: float | None
    remaining_usd: float | None
    would_exceed: bool | None
    remaining_after_high_usd: float | None
    decision_ready: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "driver": self.driver.to_dict(),
            "usage_percent": self.usage_percent,
            "remaining_usd": self.remaining_usd,
            "would_exceed": self.would_exceed,
            "remaining_after_high_usd": self.remaining_after_high_usd,
            "decision_ready": self.decision_ready,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "notes": list(self.notes),
            "authority": "settings_decision_tree_usage_bar_compose_advisory",
        }


def compose_settings_decision_tree_usage_bar(
    *,
    selected_model_id: object,
    models: object,
    daily_cap_usd: object,
    spent_usd: object,
    operator_ack: object,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    bench_bests: object | None = None,
    focus_task: object | None = None,
    nd_shadow: object | None = None,
    pending_add_model_ids: object | None = None,
) -> SettingsDecisionTreeUsageBarCompose:
    """Compose decision-tree surface with usage% and prompt impact."""
    if not isinstance(operator_ack, bool):
        raise SettingsDecisionTreeUsageBarComposeError(
            "operator_ack must be an explicit boolean"
        )

    notes: list[str] = [
        "live_router_authorized=false — operator selects model",
        "secrets_stored=false — inventory ids only",
        "live_meter_read=false — bar/projection are pure advisory math",
    ]

    try:
        driver = compose_settings_model_driver_tab(
            selected_model_id=selected_model_id,
            models=models,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            projected_cost_usd_high=projected_cost_usd_high,
            projected_cost_usd_low=projected_cost_usd_low,
            bench_bests=bench_bests,
            focus_task=focus_task,
            nd_shadow=nd_shadow,
            pending_add_model_ids=pending_add_model_ids,
        )
    except SettingsModelDriverTabComposeError as e:
        raise SettingsDecisionTreeUsageBarComposeError(str(e)) from e
    notes.extend(driver.notes)

    bar = driver.decision.bar
    projection = driver.decision.projection

    usage_percent: float | None = None
    if bar.fraction_used is not None:
        usage_percent = bar.fraction_used * 100.0
        if not math.isfinite(usage_percent):
            raise SettingsDecisionTreeUsageBarComposeError(
                "usage_percent overflowed to non-finite"
            )
        notes.append(f"usage_percent={usage_percent:.2f} (advisory display)")
    else:
        notes.append(
            "usage_percent=null — cap/spent unknown (never invent 0% used)"
        )

    remaining_usd = bar.remaining_usd
    would_exceed = driver.decision.would_exceed
    remaining_after_high_usd = projection.remaining_after_high_usd

    if would_exceed is None:
        notes.append(
            "would_exceed=null — projection incomplete (remaining or high cost unknown)"
        )
    elif would_exceed:
        notes.append(
            "would_exceed=true — proposed prompt would exceed remaining budget"
        )
    else:
        notes.append("would_exceed=false — projected high cost fits remaining")

    decision_ready = driver.tab_ready and operator_ack
    if not driver.tab_ready:
        notes.append("decision_ready=false — driver tab not ready")
    elif not operator_ack:
        notes.append("decision_ready=false — operator_ack required")
    else:
        notes.append(
            "decision_ready=true — operator may proceed; still live_router_authorized=false"
        )

    if (
        driver.live_router_authorized is not False
        or driver.secrets_stored is not False
    ):
        raise SettingsDecisionTreeUsageBarComposeError(
            "invariant: driver honesty flags must remain false"
        )

    notes.extend(
        (
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
        )
    )

    return SettingsDecisionTreeUsageBarCompose(
        driver=driver,
        usage_percent=usage_percent,
        remaining_usd=remaining_usd,
        would_exceed=would_exceed,
        remaining_after_high_usd=remaining_after_high_usd,
        decision_ready=decision_ready,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        notes=tuple(notes),
        authority="settings_decision_tree_usage_bar_compose_advisory",
    )


def format_settings_decision_tree_usage_bar_summary(
    c: SettingsDecisionTreeUsageBarCompose,
) -> str:
    pct = (
        "usage%=null"
        if c.usage_percent is None
        else f"usage%={c.usage_percent:.1f}"
    )
    w = (
        "would_exceed=null"
        if c.would_exceed is None
        else f"would_exceed={c.would_exceed}"
    )
    return (
        f"decision_ready={c.decision_ready} · "
        f"model={c.driver.decision.selected_model_id} · "
        f"{pct} · {w} · live_router_authorized=false · "
        f"secrets_stored=false · live_meter_read=false"
    )


__all__ = [
    "SettingsDecisionTreeUsageBarCompose",
    "SettingsDecisionTreeUsageBarComposeError",
    "compose_settings_decision_tree_usage_bar",
    "format_settings_decision_tree_usage_bar_summary",
]
