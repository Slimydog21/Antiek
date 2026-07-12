"""Settings add-model + Antiek-bench decision + NotDiamond shadow (pure).

production_router_verdict always REJECT.
live_router_authorized / secrets_stored / inventory_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.settings_add_model_bench_decision_compose import (
    SettingsAddModelBenchDecisionCompose,
    SettingsAddModelBenchDecisionComposeError,
    compose_settings_add_model_bench_decision,
)
from substrate.notdiamond_shadow_advisory_compose import (
    NotDiamondShadowAdvisoryCompose,
    NotDiamondShadowAdvisoryComposeError,
    compose_notdiamond_shadow_advisory,
)

BenchVsNd = Literal["agree", "disagree", "nd_hidden", "bench_none"]


class SettingsAddModelBenchNdShadowComposeError(ValueError):
    """Fail-closed validation for settings add-model bench ND shadow pack."""


@dataclass(frozen=True)
class SettingsAddModelBenchNdShadowCompose:
    week_id: str
    focus_task: str
    settings_pack: SettingsAddModelBenchDecisionCompose
    nd_shadow: NotDiamondShadowAdvisoryCompose
    operator_selected_model_id: str
    bench_vs_nd: BenchVsNd
    pack_ready: bool
    production_router_verdict: str
    live_router_authorized: bool
    secrets_stored: bool
    inventory_mutated: bool
    suite_rewritten: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "focus_task": self.focus_task,
            "settings_pack": self.settings_pack.to_dict(),
            "nd_shadow": self.nd_shadow.to_dict(),
            "operator_selected_model_id": self.operator_selected_model_id,
            "bench_vs_nd": self.bench_vs_nd,
            "pack_ready": self.pack_ready,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "suite_rewritten": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "settings_add_model_bench_nd_shadow_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsAddModelBenchNdShadowComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_settings_add_model_bench_nd_shadow(
    *,
    models: object,
    pending_add_model_ids: object,
    action: object,
    week_id: object,
    focus_task: object,
    events: object,
    daily_cap_usd: object,
    spent_usd: object,
    operator_ack: object,
    nd_recommended_model_id: object,
    kill_switch_on: object,
    decision_models: object | None = None,
    selected_model_id: object | None = None,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    existing_tasks: object | None = None,
    proposed_new_tasks: object | None = None,
    min_events_for_recommendation: object | None = None,
    nd_confidence: object | None = None,
    require_both: object | None = None,
) -> SettingsAddModelBenchNdShadowCompose:
    """Add-model + bench decision + ND shadow. Never live-routes."""
    if not isinstance(operator_ack, bool):
        raise SettingsAddModelBenchNdShadowComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(kill_switch_on, bool):
        raise SettingsAddModelBenchNdShadowComposeError(
            "kill_switch_on must be an explicit boolean"
        )
    week = _require_nonempty(week_id, field="week_id")
    focus = _require_nonempty(focus_task, field="focus_task")

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SettingsAddModelBenchNdShadowComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "production_router_verdict=REJECT — NotDiamond is not production router (§16)",
        "live_router_authorized=false — operator selects model",
        "secrets_stored=false · inventory_mutated=false",
        "suite_rewritten=false · store_mutated=false",
    ]

    try:
        settings_pack = compose_settings_add_model_bench_decision(
            models=models,
            pending_add_model_ids=pending_add_model_ids,
            action=action,
            week_id=week,
            focus_task=focus,
            events=events,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            operator_ack=operator_ack,
            decision_models=decision_models,
            selected_model_id=selected_model_id,
            projected_cost_usd_high=projected_cost_usd_high,
            projected_cost_usd_low=projected_cost_usd_low,
            existing_tasks=existing_tasks,
            proposed_new_tasks=proposed_new_tasks,
            min_events_for_recommendation=min_events_for_recommendation,
            require_both=True,
        )
    except SettingsAddModelBenchDecisionComposeError as e:
        raise SettingsAddModelBenchNdShadowComposeError(str(e)) from e
    notes.extend(f"[settings_pack] {n}" for n in settings_pack.notes)

    operator_selected = (
        settings_pack.bench_rec.decision_tree.driver.decision.selected_model_id
    )

    inventory_ids: list[str] = []
    seen: set[str] = set()
    if isinstance(models, list):
        for m in models:
            if isinstance(m, dict):
                mid = str(m.get("model_id", "")).strip()
                if mid and mid not in seen:
                    seen.add(mid)
                    inventory_ids.append(mid)
    if isinstance(pending_add_model_ids, list):
        for p in pending_add_model_ids:
            mid = str(p).strip()
            if mid and mid not in seen:
                seen.add(mid)
                inventory_ids.append(mid)
    if isinstance(decision_models, list):
        for m in decision_models:
            if isinstance(m, dict):
                mid = str(m.get("model_id", "")).strip()
                if mid and mid not in seen:
                    seen.add(mid)
                    inventory_ids.append(mid)

    try:
        nd_shadow = compose_notdiamond_shadow_advisory(
            selected_model_id=operator_selected,
            nd_recommended_model_id=nd_recommended_model_id,
            kill_switch_on=kill_switch_on,
            confidence=nd_confidence,
            task=focus,
            inventory_model_ids=inventory_ids,
        )
    except NotDiamondShadowAdvisoryComposeError as e:
        raise SettingsAddModelBenchNdShadowComposeError(str(e)) from e
    notes.extend(f"[nd] {n}" for n in nd_shadow.notes)

    if not nd_shadow.shadow_visible:
        bench_vs_nd: BenchVsNd = "nd_hidden"
        notes.append(
            "bench_vs_nd=nd_hidden — kill switch on or no valid ND rec"
        )
    elif settings_pack.bench_rec.recommendation is None:
        bench_vs_nd = "bench_none"
        notes.append(
            "bench_vs_nd=bench_none — insufficient usage for task rec"
        )
    elif (
        settings_pack.bench_rec.recommendation.recommended_model_id
        == nd_shadow.nd_recommended_model_id
    ):
        bench_vs_nd = "agree"
        notes.append(
            "bench_vs_nd=agree — bench and ND shadow recommend same model "
            "(still advisory)"
        )
    else:
        bench_vs_nd = "disagree"
        notes.append(
            f"bench_vs_nd=disagree — bench="
            f"{settings_pack.bench_rec.recommendation.recommended_model_id} "
            f"nd={nd_shadow.nd_recommended_model_id} "
            f"operator={operator_selected}"
        )

    if require:
        pack_ready = (
            settings_pack.pack_ready is True
            and nd_shadow.live_router_authorized is False
            and nd_shadow.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            settings_pack.pack_ready is True
            or (
                nd_shadow.production_router_verdict == "REJECT"
                and nd_shadow.live_router_authorized is False
            )
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — add-model+bench+ND shadow surface ready; "
            "still no live router"
        )
    else:
        notes.append(
            "pack_ready=false — settings pack, ND invariant, or operator_ack "
            "gate open"
        )

    if (
        settings_pack.live_router_authorized is not False
        or settings_pack.secrets_stored is not False
        or settings_pack.inventory_mutated is not False
        or nd_shadow.live_router_authorized is not False
        or nd_shadow.production_router_verdict != "REJECT"
    ):
        raise SettingsAddModelBenchNdShadowComposeError(
            "invariant: ND must remain REJECT; live_router/secrets/inventory "
            "honesty false"
        )

    notes.extend(
        (
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "suite_rewritten=false",
            "store_mutated=false",
        )
    )

    return SettingsAddModelBenchNdShadowCompose(
        week_id=week,
        focus_task=focus,
        settings_pack=settings_pack,
        nd_shadow=nd_shadow,
        operator_selected_model_id=operator_selected,
        bench_vs_nd=bench_vs_nd,
        pack_ready=pack_ready,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        secrets_stored=False,
        inventory_mutated=False,
        suite_rewritten=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="settings_add_model_bench_nd_shadow_compose_advisory",
    )


def format_settings_add_model_bench_nd_shadow_summary(
    c: SettingsAddModelBenchNdShadowCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · task={c.focus_task} · "
        f"operator={c.operator_selected_model_id} · "
        f"bench_vs_nd={c.bench_vs_nd} · "
        f"would_exceed={c.settings_pack.bench_rec.decision_tree.would_exceed} · "
        f"production_router_verdict=REJECT · live_router_authorized=false · "
        f"inventory_mutated=false"
    )


__all__ = [
    "SettingsAddModelBenchNdShadowCompose",
    "SettingsAddModelBenchNdShadowComposeError",
    "compose_settings_add_model_bench_nd_shadow",
    "format_settings_add_model_bench_nd_shadow_summary",
]
