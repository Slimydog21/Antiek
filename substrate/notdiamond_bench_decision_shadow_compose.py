"""NotDiamond + Antiek-bench decision shadow pack (pure).

production_router_verdict always REJECT.
live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.antiek_bench_task_model_recommendation_compose import (
    AntiekBenchTaskModelRecommendationCompose,
    AntiekBenchTaskModelRecommendationComposeError,
    compose_antiek_bench_task_model_recommendation,
)
from substrate.notdiamond_shadow_advisory_compose import (
    NotDiamondShadowAdvisoryCompose,
    NotDiamondShadowAdvisoryComposeError,
    compose_notdiamond_shadow_advisory,
)

BenchVsNd = Literal["agree", "disagree", "nd_hidden", "bench_none"]


class NotDiamondBenchDecisionShadowComposeError(ValueError):
    """Fail-closed validation for ND+bench decision shadow pack."""


@dataclass(frozen=True)
class NotDiamondBenchDecisionShadowCompose:
    week_id: str
    focus_task: str
    bench_rec: AntiekBenchTaskModelRecommendationCompose
    nd_shadow: NotDiamondShadowAdvisoryCompose
    operator_selected_model_id: str
    bench_vs_nd: BenchVsNd
    pack_ready: bool
    production_router_verdict: Literal["REJECT"]
    live_router_authorized: bool
    secrets_stored: bool
    suite_rewritten: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "focus_task": self.focus_task,
            "bench_rec": self.bench_rec.to_dict(),
            "nd_shadow": self.nd_shadow.to_dict(),
            "operator_selected_model_id": self.operator_selected_model_id,
            "bench_vs_nd": self.bench_vs_nd,
            "pack_ready": self.pack_ready,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "secrets_stored": False,
            "suite_rewritten": False,
            "notes": list(self.notes),
            "authority": (
                "notdiamond_bench_decision_shadow_compose_advisory"
            ),
        }


def compose_notdiamond_bench_decision_shadow(
    *,
    week_id: object,
    focus_task: object,
    events: object,
    models: object,
    daily_cap_usd: object,
    spent_usd: object,
    nd_recommended_model_id: object,
    kill_switch_on: object,
    operator_ack: object,
    selected_model_id: object | None = None,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    existing_tasks: object | None = None,
    proposed_new_tasks: object | None = None,
    nd_confidence: object | None = None,
    min_events_for_recommendation: object | None = None,
) -> NotDiamondBenchDecisionShadowCompose:
    """Bench rec + ND shadow. ND never becomes live router."""
    if not isinstance(operator_ack, bool):
        raise NotDiamondBenchDecisionShadowComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(kill_switch_on, bool):
        raise NotDiamondBenchDecisionShadowComposeError(
            "kill_switch_on must be an explicit boolean"
        )

    notes: list[str] = [
        "production_router_verdict=REJECT — NotDiamond is not production router (§16)",
        "live_router_authorized=false — operator selects model",
        "secrets_stored=false",
        "suite_rewritten=false — bench rec is advisory only",
    ]

    try:
        bench_rec = compose_antiek_bench_task_model_recommendation(
            week_id=week_id,
            focus_task=focus_task,
            events=events,
            models=models,
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
        raise NotDiamondBenchDecisionShadowComposeError(str(e)) from e
    notes.extend(f"[bench] {n}" for n in bench_rec.notes)

    operator_selected = bench_rec.decision_tree.driver.decision.selected_model_id
    if not isinstance(models, list):
        raise NotDiamondBenchDecisionShadowComposeError(
            "models must be a non-empty array"
        )
    inventory = []
    for m in models:
        if isinstance(m, dict) and m.get("model_id"):
            inventory.append(str(m["model_id"]))

    try:
        nd_shadow = compose_notdiamond_shadow_advisory(
            selected_model_id=operator_selected,
            nd_recommended_model_id=nd_recommended_model_id,
            kill_switch_on=kill_switch_on,
            confidence=nd_confidence,
            task=focus_task,
            inventory_model_ids=inventory,
        )
    except NotDiamondShadowAdvisoryComposeError as e:
        raise NotDiamondBenchDecisionShadowComposeError(str(e)) from e
    notes.extend(f"[nd] {n}" for n in nd_shadow.notes)

    if not nd_shadow.shadow_visible:
        bench_vs_nd: BenchVsNd = "nd_hidden"
        notes.append("bench_vs_nd=nd_hidden — kill switch on or no valid ND rec")
    elif bench_rec.recommendation is None:
        bench_vs_nd = "bench_none"
        notes.append("bench_vs_nd=bench_none — insufficient usage for task rec")
    elif (
        bench_rec.recommendation.recommended_model_id
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
            f"{bench_rec.recommendation.recommended_model_id} "
            f"nd={nd_shadow.nd_recommended_model_id} operator={operator_selected}"
        )

    pack_ready = (
        bench_rec.pack_ready is True
        and nd_shadow.live_router_authorized is False
        and nd_shadow.production_router_verdict == "REJECT"
        and operator_ack is True
    )
    if pack_ready:
        notes.append(
            "pack_ready=true — bench+ND shadow decision surface ready; "
            "still no live router"
        )
    else:
        notes.append("pack_ready=false — bench pack or operator_ack gate open")

    if (
        bench_rec.live_router_authorized is not False
        or nd_shadow.live_router_authorized is not False
        or nd_shadow.production_router_verdict != "REJECT"
    ):
        raise NotDiamondBenchDecisionShadowComposeError(
            "invariant: ND must remain REJECT and live_router_authorized false"
        )

    notes.extend(
        (
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
        )
    )

    return NotDiamondBenchDecisionShadowCompose(
        week_id=bench_rec.week_id,
        focus_task=bench_rec.focus_task,
        bench_rec=bench_rec,
        nd_shadow=nd_shadow,
        operator_selected_model_id=operator_selected,
        bench_vs_nd=bench_vs_nd,
        pack_ready=pack_ready,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        secrets_stored=False,
        suite_rewritten=False,
        notes=tuple(notes),
        authority="notdiamond_bench_decision_shadow_compose_advisory",
    )


def format_notdiamond_bench_decision_shadow_summary(
    c: NotDiamondBenchDecisionShadowCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · task={c.focus_task} · "
        f"operator={c.operator_selected_model_id} · "
        f"bench_vs_nd={c.bench_vs_nd} · "
        f"production_router_verdict=REJECT · live_router_authorized=false"
    )


__all__ = [
    "NotDiamondBenchDecisionShadowCompose",
    "NotDiamondBenchDecisionShadowComposeError",
    "compose_notdiamond_bench_decision_shadow",
    "format_notdiamond_bench_decision_shadow_summary",
]
