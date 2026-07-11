"""Competition quality + workstation interrogation loop (pure).

live_dispatch_authorized, live_dispatched, remote_fetched, backlog_mutated,
record_persisted, prompts_injected always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.competition_dr_quality_source_pack_compose import (
    CompetitionDrQualitySourcePackCompose,
    CompetitionDrQualitySourcePackComposeError,
    compose_competition_dr_quality_source_pack,
)
from substrate.research_workstation_interrogation_loop_compose import (
    ResearchWorkstationInterrogationLoopCompose,
    ResearchWorkstationInterrogationLoopComposeError,
    compose_research_workstation_interrogation_loop,
)


class CompetitionQualityInterrogationLoopComposeError(ValueError):
    """Fail-closed validation for competition quality + interrogation loop."""


@dataclass(frozen=True)
class CompetitionQualityInterrogationLoopCompose:
    session_id: str
    parent_asset_id: str
    quality_pack: CompetitionDrQualitySourcePackCompose
    interrogation: ResearchWorkstationInterrogationLoopCompose
    session_ready: bool
    live_dispatch_authorized: bool
    live_dispatched: bool
    remote_fetched: bool
    backlog_mutated: bool
    record_persisted: bool
    prompts_injected: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "quality_pack": self.quality_pack.to_dict(),
            "interrogation": self.interrogation.to_dict(),
            "session_ready": self.session_ready,
            "live_dispatch_authorized": False,
            "live_dispatched": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "record_persisted": False,
            "prompts_injected": False,
            "notes": list(self.notes),
            "authority": (
                "competition_quality_interrogation_loop_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitionQualityInterrogationLoopComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_competition_quality_interrogation_loop(
    *,
    session_id: object,
    parent_asset_id: object,
    competitor_decisions: object,
    requested_families: object,
    citations: object,
    quality_overall: object,
    would_exceed: object,
    questions: object,
    chase_mode: object,
    user_prompt: object,
    selected_model_id: object,
    models: object,
    daily_cap_usd: object,
    spent_usd: object,
    operator_ack: object,
    focus_areas: object | None = None,
    filter_to_selected_families: object | None = None,
    quality_floor: object | None = None,
    require_no_behind_gaps: object | None = None,
    prior_records: object | None = None,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    operator_override: object | None = None,
    source_families: object | None = None,
    bench_bests: object | None = None,
    focus_task: object | None = None,
    nd_shadow: object | None = None,
) -> CompetitionQualityInterrogationLoopCompose:
    """Quality pack + interrogation loop. Never dispatches/fetches/persists."""
    if not isinstance(operator_ack, bool):
        raise CompetitionQualityInterrogationLoopComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    notes: list[str] = [
        "live_dispatch_authorized=false — quality+interrogation pure readiness",
        "live_dispatched=false — chase slots intent only",
        "remote_fetched=false — no arxiv/substack network fetch",
        "backlog_mutated=false · record_persisted=false · prompts_injected=false",
    ]

    try:
        quality_pack = compose_competition_dr_quality_source_pack(
            session_id=session,
            competitor_decisions=competitor_decisions,
            requested_families=requested_families,
            citations=citations,
            quality_overall=quality_overall,
            would_exceed=would_exceed,
            operator_ack=operator_ack,
            focus_areas=focus_areas,
            filter_to_selected_families=filter_to_selected_families,
            quality_floor=quality_floor,
            operator_override=operator_override,
            require_no_behind_gaps=require_no_behind_gaps,
        )
    except CompetitionDrQualitySourcePackComposeError as e:
        raise CompetitionQualityInterrogationLoopComposeError(str(e)) from e
    notes.extend(f"[quality] {n}" for n in quality_pack.notes)

    try:
        interrogation = compose_research_workstation_interrogation_loop(
            session_id=session,
            parent_asset_id=parent,
            questions=questions,
            chase_mode=chase_mode,
            user_prompt=user_prompt,
            selected_model_id=selected_model_id,
            models=models,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            operator_ack=operator_ack,
            prior_records=prior_records,
            projected_cost_usd_high=projected_cost_usd_high,
            projected_cost_usd_low=projected_cost_usd_low,
            would_exceed=would_exceed,
            operator_override=operator_override,
            source_families=source_families,
            bench_bests=bench_bests,
            focus_task=(
                "deep_research" if focus_task is None else focus_task
            ),
            nd_shadow=nd_shadow,
            mark_for_twin_record=True,
        )
    except ResearchWorkstationInterrogationLoopComposeError as e:
        raise CompetitionQualityInterrogationLoopComposeError(str(e)) from e
    notes.extend(f"[interrogation] {n}" for n in interrogation.notes)

    session_ready = (
        quality_pack.pack_ready is True
        and interrogation.loop_ready is True
        and operator_ack is True
    )
    if session_ready:
        notes.append(
            "session_ready=true — competition-quality DR + interrogation loop "
            "ready; still pure"
        )
    else:
        notes.append(
            "session_ready=false — quality pack, interrogation loop, or "
            "operator_ack gate open"
        )

    if (
        quality_pack.live_dispatch_authorized is not False
        or quality_pack.remote_fetched is not False
        or quality_pack.backlog_mutated is not False
        or interrogation.live_dispatched is not False
        or interrogation.record_persisted is not False
        or interrogation.prompts_injected is not False
    ):
        raise CompetitionQualityInterrogationLoopComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatch_authorized=false",
            "live_dispatched=false",
            "remote_fetched=false",
            "record_persisted=false",
            "prompts_injected=false",
        )
    )

    return CompetitionQualityInterrogationLoopCompose(
        session_id=session,
        parent_asset_id=parent,
        quality_pack=quality_pack,
        interrogation=interrogation,
        session_ready=session_ready,
        live_dispatch_authorized=False,
        live_dispatched=False,
        remote_fetched=False,
        backlog_mutated=False,
        record_persisted=False,
        prompts_injected=False,
        notes=tuple(notes),
        authority="competition_quality_interrogation_loop_compose_advisory",
    )


def format_competition_quality_interrogation_loop_summary(
    c: CompetitionQualityInterrogationLoopCompose,
) -> str:
    return (
        f"session_ready={c.session_ready} · "
        f"quality_pack_ready={c.quality_pack.pack_ready} · "
        f"loop_ready={c.interrogation.loop_ready} · "
        f"chase_slots={c.interrogation.chase.slot_count} · "
        f"live_dispatch_authorized=false · remote_fetched=false · "
        f"record_persisted=false"
    )


__all__ = [
    "CompetitionQualityInterrogationLoopCompose",
    "CompetitionQualityInterrogationLoopComposeError",
    "compose_competition_quality_interrogation_loop",
    "format_competition_quality_interrogation_loop_summary",
]
