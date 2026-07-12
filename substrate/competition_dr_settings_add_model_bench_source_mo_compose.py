"""Competition DR quality over settings add-model + Antiek-bench source MO (pure).

live_dispatch_authorized / remote_fetched / backlog_mutated always False.
secrets_stored / inventory_mutated / live_router_authorized always False.
suite_rewritten / live_execution_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.competition_dr_quality_source_pack_compose import (
    CompetitionDrQualitySourcePackCompose,
    CompetitionDrQualitySourcePackComposeError,
    compose_competition_dr_quality_source_pack,
)
from substrate.settings_add_model_antiek_bench_source_attach_mo_compose import (
    SettingsAddModelAntiekBenchSourceAttachMoCompose,
    SettingsAddModelAntiekBenchSourceAttachMoComposeError,
    compose_settings_add_model_antiek_bench_source_attach_mo,
)


class CompetitionDrSettingsAddModelBenchSourceMoComposeError(ValueError):
    """Fail-closed validation for competition DR + settings add-model pack."""


@dataclass(frozen=True)
class CompetitionDrSettingsAddModelBenchSourceMoCompose:
    session_id: str
    week_id: str
    focus_task: str
    parent_asset_id: str
    title: str
    account_id: str
    asset_id: str
    competition: CompetitionDrQualitySourcePackCompose
    settings_pack: SettingsAddModelAntiekBenchSourceAttachMoCompose
    session_aligned: bool
    pack_ready: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    suite_rewritten: bool
    store_mutated: bool
    live_execution_authorized: bool
    charge_executed: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    remote_index_queried: bool
    twin_written: bool
    prompts_injected: bool
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
            "session_id": self.session_id,
            "week_id": self.week_id,
            "focus_task": self.focus_task,
            "parent_asset_id": self.parent_asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "asset_id": self.asset_id,
            "competition": self.competition.to_dict(),
            "settings_pack": self.settings_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "pack_ready": self.pack_ready,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "suite_rewritten": False,
            "store_mutated": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "remote_index_queried": False,
            "twin_written": False,
            "prompts_injected": False,
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
                "competition_dr_settings_add_model_bench_source_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitionDrSettingsAddModelBenchSourceMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_competition_dr_settings_add_model_bench_source_mo(
    *,
    competition: object,
    settings_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> CompetitionDrSettingsAddModelBenchSourceMoCompose:
    """Competition DR on settings add-model bench source MO. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise CompetitionDrSettingsAddModelBenchSourceMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(competition, dict):
        raise CompetitionDrSettingsAddModelBenchSourceMoComposeError(
            "competition must be an object"
        )
    if not isinstance(settings_pack, dict):
        raise CompetitionDrSettingsAddModelBenchSourceMoComposeError(
            "settings_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise CompetitionDrSettingsAddModelBenchSourceMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatch_authorized=false — competition DR pack is pure readiness",
        "remote_fetched=false — no arxiv/substack network fetch",
        "backlog_mutated=false — competition residuals advisory only",
        "secrets_stored=false · inventory_mutated=false · live_router_authorized=false",
        "suite_rewritten=false · production_router_verdict=REJECT",
    ]

    try:
        comp = compose_competition_dr_quality_source_pack(
            session_id=competition.get("session_id"),
            competitor_decisions=competition.get("competitor_decisions"),
            requested_families=competition.get("requested_families"),
            citations=competition.get("citations"),
            quality_overall=competition.get("quality_overall"),
            would_exceed=competition.get("would_exceed"),
            operator_ack=operator_ack,
            focus_areas=competition.get("focus_areas"),
            filter_to_selected_families=competition.get(
                "filter_to_selected_families"
            ),
            quality_floor=competition.get("quality_floor"),
            operator_override=competition.get("operator_override"),
            require_no_behind_gaps=competition.get("require_no_behind_gaps"),
        )
    except CompetitionDrQualitySourcePackComposeError as e:
        raise CompetitionDrSettingsAddModelBenchSourceMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[competition] {n}" for n in comp.notes)

    try:
        sp = compose_settings_add_model_antiek_bench_source_attach_mo(
            settings=settings_pack.get("settings"),
            bench_pack=settings_pack.get("bench_pack"),
            operator_ack=operator_ack,
            require_both=settings_pack.get("require_both"),
        )
    except SettingsAddModelAntiekBenchSourceAttachMoComposeError as e:
        raise CompetitionDrSettingsAddModelBenchSourceMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[settings_pack] {n}" for n in sp.notes)

    session = _require_nonempty(comp.session_id, field="session_id")
    week = _require_nonempty(sp.week_id, field="week_id")
    focus = _require_nonempty(sp.focus_task, field="focus_task")
    parent = _require_nonempty(sp.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(sp.title, field="title")
    account = _require_nonempty(sp.account_id, field="account_id")
    asset = _require_nonempty(sp.asset_id, field="asset_id")
    settings_session = _require_nonempty(
        sp.session_id, field="settings_pack.session_id"
    )

    session_aligned = session == settings_session
    if not session_aligned:
        notes.append(
            f"session_aligned=false — competition.session_id={session} "
            f"settings_pack.session_id={settings_session}"
        )
    else:
        notes.append("session_aligned=true")

    if require:
        pack_ready = (
            comp.pack_ready is True
            and sp.pack_ready is True
            and session_aligned is True
            and comp.live_dispatch_authorized is False
            and comp.remote_fetched is False
            and comp.backlog_mutated is False
            and sp.secrets_stored is False
            and sp.inventory_mutated is False
            and sp.live_router_authorized is False
            and sp.suite_rewritten is False
            and sp.remote_fetched is False
            and sp.live_execution_authorized is False
            and sp.purchase_executed is False
            and sp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and comp.live_dispatch_authorized is False
            and comp.remote_fetched is False
            and comp.backlog_mutated is False
            and sp.secrets_stored is False
            and sp.inventory_mutated is False
            and sp.live_router_authorized is False
            and sp.production_router_verdict == "REJECT"
            and (comp.pack_ready is True or sp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — competition DR + settings add-model bench source "
            "MO ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — competition, settings_pack, session align, or "
            "operator_ack gate open"
        )

    if (
        comp.live_dispatch_authorized is not False
        or comp.remote_fetched is not False
        or comp.backlog_mutated is not False
        or sp.secrets_stored is not False
        or sp.inventory_mutated is not False
        or sp.live_router_authorized is not False
        or sp.suite_rewritten is not False
        or sp.store_mutated is not False
        or sp.remote_fetched is not False
        or sp.live_execution_authorized is not False
        or sp.purchase_executed is not False
        or sp.production_router_verdict != "REJECT"
    ):
        raise CompetitionDrSettingsAddModelBenchSourceMoComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "suite_rewritten=false",
            "store_mutated=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "remote_index_queried=false",
            "twin_written=false",
            "prompts_injected=false",
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

    return CompetitionDrSettingsAddModelBenchSourceMoCompose(
        session_id=session,
        week_id=week,
        focus_task=focus,
        parent_asset_id=parent,
        title=title,
        account_id=account,
        asset_id=asset,
        competition=comp,
        settings_pack=sp,
        session_aligned=session_aligned,
        pack_ready=pack_ready,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        suite_rewritten=False,
        store_mutated=False,
        live_execution_authorized=False,
        charge_executed=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        remote_index_queried=False,
        twin_written=False,
        prompts_injected=False,
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
        authority=(
            "competition_dr_settings_add_model_bench_source_mo_compose_advisory"
        ),
    )


def format_competition_dr_settings_add_model_bench_source_mo_summary(
    c: CompetitionDrSettingsAddModelBenchSourceMoCompose,
) -> str:
    rec = (
        c.settings_pack.bench_pack.bench.recommendation.recommended_model_id
        if c.settings_pack.bench_pack.bench.recommendation is not None
        else "null"
    )
    return (
        f"pack_ready={c.pack_ready} · "
        f"comp_ready={c.competition.pack_ready} · "
        f"settings_ready={c.settings_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"rec={rec} · "
        f"vs={c.settings_pack.inventory_vs_bench} · "
        f"week={c.week_id} · task={c.focus_task} · "
        f"verdict={c.production_router_verdict} · "
        "live_dispatch_authorized=false · remote_fetched=false · "
        "backlog_mutated=false · inventory_mutated=false"
    )


__all__ = [
    "CompetitionDrSettingsAddModelBenchSourceMoCompose",
    "CompetitionDrSettingsAddModelBenchSourceMoComposeError",
    "compose_competition_dr_settings_add_model_bench_source_mo",
    "format_competition_dr_settings_add_model_bench_source_mo_summary",
]
