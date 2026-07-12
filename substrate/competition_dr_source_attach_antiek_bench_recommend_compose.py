"""Competition DR quality residual over source-attach Antiek-bench recommend (pure).

live_dispatch_authorized / remote_fetched / backlog_mutated always False.
purchase_executed / hosted / pdf_primary always False.
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
from substrate.source_attach_antiek_bench_recommend_mo_unattended_compose import (
    SourceAttachAntiekBenchRecommendMoUnattendedCompose,
    SourceAttachAntiekBenchRecommendMoUnattendedComposeError,
    compose_source_attach_antiek_bench_recommend_mo_unattended,
)


class CompetitionDrSourceAttachAntiekBenchRecommendComposeError(ValueError):
    """Fail-closed validation for competition DR + source-attach recommend pack."""


@dataclass(frozen=True)
class CompetitionDrSourceAttachAntiekBenchRecommendCompose:
    session_id: str
    parent_asset_id: str
    asset_id: str
    week_id: str
    focus_task: str
    title: str
    account_id: str
    operator_id: str
    competition: CompetitionDrQualitySourcePackCompose
    source_pack: SourceAttachAntiekBenchRecommendMoUnattendedCompose
    session_aligned: bool
    pack_ready: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    store_mutated: bool
    suite_rewritten: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_index_queried: bool
    twin_written: bool
    prompts_injected: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    draft_written: bool
    record_persisted: bool
    analysis_written: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "week_id": self.week_id,
            "focus_task": self.focus_task,
            "title": self.title,
            "account_id": self.account_id,
            "operator_id": self.operator_id,
            "competition": self.competition.to_dict(),
            "source_pack": self.source_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "pack_ready": self.pack_ready,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_index_queried": False,
            "twin_written": False,
            "prompts_injected": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "competition_dr_source_attach_antiek_bench_recommend_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitionDrSourceAttachAntiekBenchRecommendComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_competition_dr_source_attach_antiek_bench_recommend(
    *,
    competition: object,
    source_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> CompetitionDrSourceAttachAntiekBenchRecommendCompose:
    """Competition DR quality + source-attach recommend pack. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise CompetitionDrSourceAttachAntiekBenchRecommendComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(competition, dict):
        raise CompetitionDrSourceAttachAntiekBenchRecommendComposeError(
            "competition must be an object"
        )
    if not isinstance(source_pack, dict):
        raise CompetitionDrSourceAttachAntiekBenchRecommendComposeError(
            "source_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise CompetitionDrSourceAttachAntiekBenchRecommendComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "purchase_executed=false · hosted=false · pdf_primary=false",
        "suite_rewritten=false · live_execution_authorized=false",
        "production_router_verdict=REJECT",
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
        raise CompetitionDrSourceAttachAntiekBenchRecommendComposeError(
            str(e)
        ) from e
    notes.extend(f"[competition] {n}" for n in comp.notes)

    try:
        sp = compose_source_attach_antiek_bench_recommend_mo_unattended(
            sources=source_pack.get("sources"),
            recommend_pack=source_pack.get("recommend_pack"),
            operator_ack=operator_ack,
            require_both=source_pack.get("require_both"),
        )
    except SourceAttachAntiekBenchRecommendMoUnattendedComposeError as e:
        raise CompetitionDrSourceAttachAntiekBenchRecommendComposeError(
            str(e)
        ) from e
    notes.extend(f"[source_pack] {n}" for n in sp.notes)

    session = _require_nonempty(comp.session_id, field="session_id")
    parent = _require_nonempty(sp.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(sp.asset_id, field="asset_id")
    week = _require_nonempty(sp.week_id, field="week_id")
    focus = _require_nonempty(sp.focus_task, field="focus_task")
    title = _require_nonempty(sp.title, field="title")
    account = _require_nonempty(sp.account_id, field="account_id")
    op = _require_nonempty(sp.operator_id, field="operator_id")

    session_aligned = sp.session_id == session
    if not session_aligned:
        notes.append(
            "session_id mismatch between competition and source_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and comp.pack_ready is True
            and sp.pack_ready is True
            and comp.live_dispatch_authorized is False
            and comp.remote_fetched is False
            and comp.backlog_mutated is False
            and sp.remote_fetched is False
            and sp.purchase_executed is False
            and sp.hosted is False
            and sp.pdf_primary is False
            and sp.live_dispatch_authorized is False
            and sp.live_execution_authorized is False
            and sp.charge_executed is False
            and sp.suite_rewritten is False
            and sp.live_router_authorized is False
            and sp.secrets_stored is False
            and sp.remote_index_queried is False
            and sp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and operator_ack is True
            and comp.live_dispatch_authorized is False
            and sp.purchase_executed is False
            and sp.hosted is False
            and sp.production_router_verdict == "REJECT"
            and sp.pdf_primary is False
            and (comp.pack_ready is True or sp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — competition DR + source-attach Antiek-bench recommend "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — competition, source_pack, alignment, or operator_ack "
            "gate open"
        )

    if (
        comp.live_dispatch_authorized is not False
        or comp.remote_fetched is not False
        or comp.backlog_mutated is not False
        or sp.remote_fetched is not False
        or sp.purchase_executed is not False
        or sp.hosted is not False
        or sp.pdf_primary is not False
        or sp.live_execution_authorized is not False
        or sp.charge_executed is not False
        or sp.suite_rewritten is not False
        or sp.live_router_authorized is not False
        or sp.secrets_stored is not False
        or sp.remote_index_queried is not False
        or sp.production_router_verdict != "REJECT"
    ):
        raise CompetitionDrSourceAttachAntiekBenchRecommendComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_index_queried=false",
            "twin_written=false",
            "prompts_injected=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return CompetitionDrSourceAttachAntiekBenchRecommendCompose(
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        week_id=week,
        focus_task=focus,
        title=title,
        account_id=account,
        operator_id=op,
        competition=comp,
        source_pack=sp,
        session_aligned=session_aligned,
        pack_ready=pack_ready,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        store_mutated=False,
        suite_rewritten=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_index_queried=False,
        twin_written=False,
        prompts_injected=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "competition_dr_source_attach_antiek_bench_recommend_compose_advisory"
        ),
    )


def format_competition_dr_source_attach_antiek_bench_recommend_summary(
    c: CompetitionDrSourceAttachAntiekBenchRecommendCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"competition_ready={c.competition.pack_ready} · "
        f"source_ready={c.source_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"behind={c.competition.competition.behind_count} · "
        f"focus={c.focus_task} · "
        f"week={c.week_id} · "
        f"verdict={c.production_router_verdict} · "
        "live_dispatch_authorized=false · remote_fetched=false · "
        "suite_rewritten=false"
    )


__all__ = [
    "CompetitionDrSourceAttachAntiekBenchRecommendCompose",
    "CompetitionDrSourceAttachAntiekBenchRecommendComposeError",
    "compose_competition_dr_source_attach_antiek_bench_recommend",
    "format_competition_dr_source_attach_antiek_bench_recommend_summary",
]
