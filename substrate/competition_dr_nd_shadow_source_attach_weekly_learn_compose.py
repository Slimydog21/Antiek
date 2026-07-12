"""Competition DR quality over ND shadow source-attach weekly learn pack (pure).

live_dispatch_authorized / remote_fetched / backlog_mutated always False.
live_router_authorized / twin_written / merge_executed always False.
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
from substrate.nd_shadow_source_attach_weekly_learn_twin_presentation_compose import (
    NdShadowSourceAttachWeeklyLearnTwinPresentationCompose,
    NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError,
    compose_nd_shadow_source_attach_weekly_learn_twin_presentation,
)


class CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError(ValueError):
    """Fail-closed validation for competition DR + ND shadow source-attach pack."""


@dataclass(frozen=True)
class CompetitionDrNdShadowSourceAttachWeeklyLearnCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    competition: CompetitionDrQualitySourcePackCompose
    nd_pack: NdShadowSourceAttachWeeklyLearnTwinPresentationCompose
    session_aligned: bool
    pack_ready: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    twin_written: bool
    prompts_injected: bool
    merge_executed: bool
    draft_written: bool
    analysis_written: bool
    live_dispatched: bool
    pack_dispatched: bool
    live_execution_authorized: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    inventory_mutated: bool
    charge_executed: bool
    record_persisted: bool
    purchase_executed: bool
    hosted: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "competition": self.competition.to_dict(),
            "nd_pack": self.nd_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "pack_ready": self.pack_ready,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "twin_written": False,
            "prompts_injected": False,
            "merge_executed": False,
            "draft_written": False,
            "analysis_written": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "live_execution_authorized": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "inventory_mutated": False,
            "charge_executed": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "competition_dr_nd_shadow_source_attach_weekly_learn_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_competition_dr_nd_shadow_source_attach_weekly_learn(
    *,
    competition: object,
    nd_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> CompetitionDrNdShadowSourceAttachWeeklyLearnCompose:
    """Competition DR + ND shadow source-attach weekly learn. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(competition, dict):
        raise CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError(
            "competition must be an object"
        )
    if not isinstance(nd_pack, dict):
        raise CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError(
            "nd_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "live_router_authorized=false · twin_written=false · merge_executed=false",
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
        raise CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError(
            str(e)
        ) from e
    notes.extend(f"[competition] {n}" for n in comp.notes)

    try:
        nd = compose_nd_shadow_source_attach_weekly_learn_twin_presentation(
            nd_shadow=nd_pack.get("nd_shadow"),
            source_pack=nd_pack.get("source_pack"),
            operator_ack=operator_ack,
            require_both=nd_pack.get("require_both"),
        )
    except NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError as e:
        raise CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError(
            str(e)
        ) from e
    notes.extend(f"[nd_pack] {n}" for n in nd.notes)

    session = _require_nonempty(comp.session_id, field="session_id")
    parent = _require_nonempty(nd.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(nd.week_id, field="week_id")
    asset = _require_nonempty(nd.asset_id, field="asset_id")
    title = _require_nonempty(nd.title, field="title")
    account = _require_nonempty(nd.account_id, field="account_id")

    session_aligned = nd.session_id == session
    if not session_aligned:
        notes.append(
            "session_id mismatch between competition and nd_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and comp.pack_ready is True
            and nd.pack_ready is True
            and comp.live_dispatch_authorized is False
            and comp.remote_fetched is False
            and comp.backlog_mutated is False
            and nd.live_router_authorized is False
            and nd.remote_fetched is False
            and nd.backlog_mutated is False
            and nd.suite_rewritten is False
            and nd.twin_written is False
            and nd.merge_executed is False
            and nd.draft_written is False
            and nd.live_dispatched is False
            and nd.secrets_stored is False
            and nd.remote_index_queried is False
            and nd.pdf_primary is False
            and nd.production_router_verdict == "REJECT"
            and nd.nd_shadow.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and operator_ack is True
            and comp.remote_fetched is False
            and nd.production_router_verdict == "REJECT"
            and nd.pdf_primary is False
            and (comp.pack_ready is True or nd.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — competition DR + ND shadow source-attach weekly learn "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — competition, nd_pack, alignment, or operator_ack gate open"
        )

    if (
        comp.live_dispatch_authorized is not False
        or comp.remote_fetched is not False
        or comp.backlog_mutated is not False
        or nd.live_router_authorized is not False
        or nd.remote_fetched is not False
        or nd.backlog_mutated is not False
        or nd.suite_rewritten is not False
        or nd.twin_written is not False
        or nd.merge_executed is not False
        or nd.draft_written is not False
        or nd.live_dispatched is not False
        or nd.secrets_stored is not False
        or nd.remote_index_queried is not False
        or nd.pdf_primary is not False
        or nd.production_router_verdict != "REJECT"
        or nd.nd_shadow.production_router_verdict != "REJECT"
    ):
        raise CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "twin_written=false",
            "prompts_injected=false",
            "merge_executed=false",
            "draft_written=false",
            "analysis_written=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "live_execution_authorized=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "inventory_mutated=false",
            "charge_executed=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "production_router_verdict=REJECT",
        )
    )

    return CompetitionDrNdShadowSourceAttachWeeklyLearnCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        competition=comp,
        nd_pack=nd,
        session_aligned=session_aligned,
        pack_ready=pack_ready,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        twin_written=False,
        prompts_injected=False,
        merge_executed=False,
        draft_written=False,
        analysis_written=False,
        live_dispatched=False,
        pack_dispatched=False,
        live_execution_authorized=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        inventory_mutated=False,
        charge_executed=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "competition_dr_nd_shadow_source_attach_weekly_learn_compose_advisory"
        ),
    )


def format_competition_dr_nd_shadow_source_attach_weekly_learn_summary(
    c: CompetitionDrNdShadowSourceAttachWeeklyLearnCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"competition_ready={c.competition.pack_ready} · "
        f"nd_ready={c.nd_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "live_dispatch_authorized=false · remote_fetched=false · live_router_authorized=false"
    )


__all__ = [
    "CompetitionDrNdShadowSourceAttachWeeklyLearnCompose",
    "CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError",
    "compose_competition_dr_nd_shadow_source_attach_weekly_learn",
    "format_competition_dr_nd_shadow_source_attach_weekly_learn_summary",
]
