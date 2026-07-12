"""Settings add-model inventory + Antiek-bench task decision pack (pure).

secrets_stored / inventory_mutated / live_router_authorized always False.
suite_rewritten / backlog_mutated / store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.settings_add_model_inventory_compose import (
    SettingsAddModelInventoryCompose,
    SettingsAddModelInventoryComposeError,
    compose_settings_add_model_inventory,
)
from substrate.antiek_bench_task_model_recommendation_compose import (
    AntiekBenchTaskModelRecommendationCompose,
    AntiekBenchTaskModelRecommendationComposeError,
    compose_antiek_bench_task_model_recommendation,
)


class SettingsAddModelBenchDecisionComposeError(ValueError):
    """Fail-closed validation for settings add-model + bench decision pack."""


@dataclass(frozen=True)
class SettingsAddModelBenchDecisionCompose:
    week_id: str
    focus_task: str
    add_model: SettingsAddModelInventoryCompose
    bench_rec: AntiekBenchTaskModelRecommendationCompose
    pack_ready: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    live_meter_read: bool
    suite_rewritten: bool
    backlog_mutated: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "focus_task": self.focus_task,
            "add_model": self.add_model.to_dict(),
            "bench_rec": self.bench_rec.to_dict(),
            "pack_ready": self.pack_ready,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "live_meter_read": False,
            "suite_rewritten": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "settings_add_model_bench_decision_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsAddModelBenchDecisionComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _inventory_to_decision_models(
    models: object,
    pending: object,
    decision_models: object | None,
) -> list[dict[str, Any]]:
    if decision_models is not None:
        if not isinstance(decision_models, list) or len(decision_models) == 0:
            raise SettingsAddModelBenchDecisionComposeError(
                "decision_models must be a non-empty array when set"
            )
        out: list[dict[str, Any]] = []
        for m in decision_models:
            if not isinstance(m, dict):
                raise SettingsAddModelBenchDecisionComposeError(
                    "decision_models items must be objects"
                )
            out.append(m)
        return out
    ids: list[str] = []
    seen: set[str] = set()
    if isinstance(models, list):
        for m in models:
            if isinstance(m, dict):
                mid = str(m.get("model_id", "")).strip()
                if mid and mid not in seen:
                    seen.add(mid)
                    ids.append(mid)
    if isinstance(pending, list):
        for p in pending:
            mid = str(p).strip()
            if mid and mid not in seen:
                seen.add(mid)
                ids.append(mid)
    if not ids:
        raise SettingsAddModelBenchDecisionComposeError(
            "models inventory or pending_add_model_ids required"
        )
    return [{"model_id": mid} for mid in ids]


def compose_settings_add_model_bench_decision(
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
    decision_models: object | None = None,
    selected_model_id: object | None = None,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    existing_tasks: object | None = None,
    proposed_new_tasks: object | None = None,
    min_events_for_recommendation: object | None = None,
    require_both: object | None = None,
) -> SettingsAddModelBenchDecisionCompose:
    """Add-model inventory + bench decision tree. Never secrets/routes."""
    if not isinstance(operator_ack, bool):
        raise SettingsAddModelBenchDecisionComposeError(
            "operator_ack must be an explicit boolean"
        )
    week = _require_nonempty(week_id, field="week_id")
    focus = _require_nonempty(focus_task, field="focus_task")

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SettingsAddModelBenchDecisionComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "secrets_stored=false — BYOK inventory ids only",
        "inventory_mutated=false — pure propose only",
        "live_router_authorized=false — operator selects model",
        "suite_rewritten=false · backlog_mutated=false · store_mutated=false",
    ]

    try:
        add_model = compose_settings_add_model_inventory(
            models=models,
            pending_add_model_ids=pending_add_model_ids,
            action=action,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            operator_ack=operator_ack,
            selected_model_id=selected_model_id,
            projected_cost_usd_high=projected_cost_usd_high,
            projected_cost_usd_low=projected_cost_usd_low,
        )
    except SettingsAddModelInventoryComposeError as e:
        raise SettingsAddModelBenchDecisionComposeError(str(e)) from e
    notes.extend(f"[add_model] {n}" for n in add_model.notes)

    d_models = _inventory_to_decision_models(
        models, pending_add_model_ids, decision_models
    )
    notes.append(f"decision_models={len(d_models)}")

    try:
        bench_rec = compose_antiek_bench_task_model_recommendation(
            week_id=week,
            focus_task=focus,
            events=events,
            models=d_models,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            operator_ack=operator_ack,
            selected_model_id=selected_model_id,
            projected_cost_usd_high=projected_cost_usd_high,
            projected_cost_usd_low=projected_cost_usd_low,
            existing_tasks=existing_tasks,
            proposed_new_tasks=proposed_new_tasks,
            min_events_for_recommendation=min_events_for_recommendation,
        )
    except AntiekBenchTaskModelRecommendationComposeError as e:
        raise SettingsAddModelBenchDecisionComposeError(str(e)) from e
    notes.extend(f"[bench_rec] {n}" for n in bench_rec.notes)

    if require:
        pack_ready = (
            add_model.pack_ready is True
            and bench_rec.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            add_model.pack_ready is True or bench_rec.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — add-model inventory + bench decision ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — add_model, bench_rec, or operator_ack gate open"
        )

    if (
        add_model.secrets_stored is not False
        or add_model.inventory_mutated is not False
        or add_model.live_router_authorized is not False
        or bench_rec.live_router_authorized is not False
        or bench_rec.secrets_stored is not False
        or bench_rec.suite_rewritten is not False
        or bench_rec.store_mutated is not False
    ):
        raise SettingsAddModelBenchDecisionComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "live_meter_read=false",
            "suite_rewritten=false",
            "backlog_mutated=false",
            "store_mutated=false",
        )
    )

    return SettingsAddModelBenchDecisionCompose(
        week_id=week,
        focus_task=focus,
        add_model=add_model,
        bench_rec=bench_rec,
        pack_ready=pack_ready,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        live_meter_read=False,
        suite_rewritten=False,
        backlog_mutated=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="settings_add_model_bench_decision_compose_advisory",
    )


def format_settings_add_model_bench_decision_summary(
    c: SettingsAddModelBenchDecisionCompose,
) -> str:
    rec = (
        c.bench_rec.recommendation.recommended_model_id
        if c.bench_rec.recommendation is not None
        else "none"
    )
    return (
        f"pack_ready={c.pack_ready} · "
        f"add_ready={c.add_model.pack_ready} · "
        f"bench_ready={c.bench_rec.pack_ready} · "
        f"recommend={rec} · "
        f"would_exceed={c.bench_rec.decision_tree.would_exceed} · "
        f"secrets_stored=false · live_router_authorized=false · "
        f"inventory_mutated=false"
    )


__all__ = [
    "SettingsAddModelBenchDecisionCompose",
    "SettingsAddModelBenchDecisionComposeError",
    "compose_settings_add_model_bench_decision",
    "format_settings_add_model_bench_decision_summary",
]
