"""Antiek-bench task→model rec over source-attach settings MO pack.

live_router_authorized always False.
suite_rewritten / backlog_mutated / store_mutated always False.
remote_fetched / live_execution_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_task_model_recommendation_compose import (
    AntiekBenchTaskModelRecommendationCompose,
    AntiekBenchTaskModelRecommendationComposeError,
    compose_antiek_bench_task_model_recommendation,
)
from substrate.source_attach_settings_decision_mo_compose import (
    SourceAttachSettingsDecisionMoCompose,
    SourceAttachSettingsDecisionMoComposeError,
    compose_source_attach_settings_decision_mo,
)


class AntiekBenchSourceAttachSettingsMoComposeError(ValueError):
    """Fail-closed validation for Antiek-bench + source attach settings MO."""


@dataclass(frozen=True)
class AntiekBenchSourceAttachSettingsMoCompose:
    week_id: str
    focus_task: str
    session_id: str
    parent_asset_id: str
    title: str
    account_id: str
    asset_id: str
    bench: AntiekBenchTaskModelRecommendationCompose
    source_pack: SourceAttachSettingsDecisionMoCompose
    pack_ready: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_fetched: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    remote_index_queried: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    draft_written: bool
    record_persisted: bool
    analysis_written: bool
    purchase_executed: bool
    hosted: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "focus_task": self.focus_task,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "asset_id": self.asset_id,
            "bench": self.bench.to_dict(),
            "source_pack": self.source_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_fetched": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "remote_index_queried": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "purchase_executed": False,
            "hosted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "antiek_bench_source_attach_settings_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AntiekBenchSourceAttachSettingsMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_antiek_bench_source_attach_settings_mo(
    *,
    bench: object,
    source_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> AntiekBenchSourceAttachSettingsMoCompose:
    """Antiek-bench rec + source attach settings MO. Never live-routes."""
    if not isinstance(operator_ack, bool):
        raise AntiekBenchSourceAttachSettingsMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(bench, dict):
        raise AntiekBenchSourceAttachSettingsMoComposeError(
            "bench must be an object"
        )
    if not isinstance(source_pack, dict):
        raise AntiekBenchSourceAttachSettingsMoComposeError(
            "source_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise AntiekBenchSourceAttachSettingsMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_router_authorized=false — bench recommendation advisory only",
        "suite_rewritten=false · backlog_mutated=false · store_mutated=false",
        "remote_fetched=false · live_execution_authorized=false",
        "production_router_verdict=REJECT",
    ]

    try:
        b = compose_antiek_bench_task_model_recommendation(
            week_id=bench.get("week_id"),
            focus_task=bench.get("focus_task"),
            events=bench.get("events"),
            models=bench.get("models"),
            daily_cap_usd=bench.get("daily_cap_usd"),
            spent_usd=bench.get("spent_usd"),
            operator_ack=operator_ack,
            selected_model_id=bench.get("selected_model_id"),
            projected_cost_usd_high=bench.get("projected_cost_usd_high"),
            projected_cost_usd_low=bench.get("projected_cost_usd_low"),
            existing_tasks=bench.get("existing_tasks"),
            proposed_new_tasks=bench.get("proposed_new_tasks"),
            min_events_per_task=bench.get("min_events_per_task"),
            min_events_for_recommendation=bench.get(
                "min_events_for_recommendation"
            ),
        )
    except AntiekBenchTaskModelRecommendationComposeError as e:
        raise AntiekBenchSourceAttachSettingsMoComposeError(str(e)) from e
    notes.extend(f"[bench] {n}" for n in b.notes)

    try:
        sp = compose_source_attach_settings_decision_mo(
            sources=source_pack.get("sources"),
            settings_mo=source_pack.get("settings_mo"),
            operator_ack=operator_ack,
            require_both=source_pack.get("require_both"),
        )
    except SourceAttachSettingsDecisionMoComposeError as e:
        raise AntiekBenchSourceAttachSettingsMoComposeError(str(e)) from e
    notes.extend(f"[source_pack] {n}" for n in sp.notes)

    week = _require_nonempty(b.week_id, field="week_id")
    focus = _require_nonempty(b.focus_task, field="focus_task")
    session = _require_nonempty(sp.session_id, field="session_id")
    parent = _require_nonempty(sp.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(sp.title, field="title")
    account = _require_nonempty(sp.account_id, field="account_id")
    asset = _require_nonempty(sp.asset_id, field="asset_id")

    if require:
        pack_ready = (
            b.pack_ready is True
            and sp.pack_ready is True
            and b.live_router_authorized is False
            and b.suite_rewritten is False
            and b.backlog_mutated is False
            and b.store_mutated is False
            and sp.remote_fetched is False
            and sp.pdf_primary is False
            and sp.live_router_authorized is False
            and sp.live_execution_authorized is False
            and sp.purchase_executed is False
            and sp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and b.live_router_authorized is False
            and sp.remote_fetched is False
            and sp.production_router_verdict == "REJECT"
            and (b.pack_ready is True or sp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — Antiek-bench recommend + source attach settings "
            "MO ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — bench, source_pack, or operator_ack gate open"
        )

    if (
        b.live_router_authorized is not False
        or b.secrets_stored is not False
        or b.suite_rewritten is not False
        or b.backlog_mutated is not False
        or b.store_mutated is not False
        or sp.remote_fetched is not False
        or sp.pdf_primary is not False
        or sp.live_router_authorized is not False
        or sp.live_execution_authorized is not False
        or sp.purchase_executed is not False
        or sp.production_router_verdict != "REJECT"
    ):
        raise AntiekBenchSourceAttachSettingsMoComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_fetched=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "remote_index_queried=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "purchase_executed=false",
            "hosted=false",
            "production_router_verdict=REJECT",
        )
    )

    return AntiekBenchSourceAttachSettingsMoCompose(
        week_id=week,
        focus_task=focus,
        session_id=session,
        parent_asset_id=parent,
        title=title,
        account_id=account,
        asset_id=asset,
        bench=b,
        source_pack=sp,
        pack_ready=pack_ready,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_fetched=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        remote_index_queried=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        purchase_executed=False,
        hosted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority="antiek_bench_source_attach_settings_mo_compose_advisory",
    )


def format_antiek_bench_source_attach_settings_mo_summary(
    c: AntiekBenchSourceAttachSettingsMoCompose,
) -> str:
    rec = (
        c.bench.recommendation.recommended_model_id
        if c.bench.recommendation is not None
        else None
    )
    return (
        f"pack_ready={c.pack_ready} · "
        f"bench_ready={c.bench.pack_ready} · "
        f"rec={rec} · "
        f"source_ready={c.source_pack.pack_ready} · "
        f"week={c.week_id} · task={c.focus_task} · "
        f"verdict={c.production_router_verdict} · "
        f"live_router_authorized=false · remote_fetched=false · "
        f"suite_rewritten=false"
    )


__all__ = [
    "AntiekBenchSourceAttachSettingsMoCompose",
    "AntiekBenchSourceAttachSettingsMoComposeError",
    "compose_antiek_bench_source_attach_settings_mo",
    "format_antiek_bench_source_attach_settings_mo_summary",
]
