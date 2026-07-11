"""Research wrestle + competition quality supercompose (pure).

live_dispatch_authorized, remote_fetched, backlog_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.competition_dr_quality_source_pack_compose import (
    CompetitionDrQualitySourcePackCompose,
    CompetitionDrQualitySourcePackComposeError,
    compose_competition_dr_quality_source_pack,
)
from substrate.research_wrestle_session_supercompose import (
    ResearchWrestleSessionSupercompose,
    ResearchWrestleSessionSupercomposeError,
    compose_research_wrestle_session,
)


class ResearchWrestleCompetitionQualityComposeError(ValueError):
    """Fail-closed validation for wrestle + competition quality pack."""


@dataclass(frozen=True)
class ResearchWrestleCompetitionQualityCompose:
    session_id: str
    parent_asset_id: str
    wrestle: ResearchWrestleSessionSupercompose
    competition_quality: CompetitionDrQualitySourcePackCompose
    session_ready: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "wrestle": self.wrestle.to_dict(),
            "competition_quality": self.competition_quality.to_dict(),
            "session_ready": self.session_ready,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "notes": list(self.notes),
            "authority": "research_wrestle_competition_quality_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchWrestleCompetitionQualityComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_research_wrestle_competition_quality(
    *,
    session_id: object,
    parent_asset_id: object,
    floating_instance_count: object,
    completed_floating_count: object,
    twin_insight_count: object,
    twin_question_count: object,
    open_question_count: object,
    competitor_decisions: object,
    requested_families: object,
    citations: object,
    quality_overall: object,
    would_exceed: object,
    operator_ack: object,
    focus_areas: object | None = None,
    filter_to_selected_families: object | None = None,
    quality_floor: object | None = None,
    preferred_view_mode: object | None = None,
    operator_override: object | None = None,
    require_no_behind_gaps: object | None = None,
) -> ResearchWrestleCompetitionQualityCompose:
    """Compose wrestle session + competition quality pack. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise ResearchWrestleCompetitionQualityComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    notes: list[str] = [
        "live_dispatch_authorized=false — wrestle+quality pack is pure readiness",
        "remote_fetched=false — no arxiv/substack network fetch",
        "backlog_mutated=false — competition residuals advisory only",
    ]

    try:
        competition_quality = compose_competition_dr_quality_source_pack(
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
        raise ResearchWrestleCompetitionQualityComposeError(str(e)) from e
    notes.extend(competition_quality.notes)

    families = competition_quality.citations.selection.families
    family_count = len(families) if families else (
        len(requested_families) if isinstance(requested_families, list) else 0
    )

    try:
        wrestle = compose_research_wrestle_session(
            session_id=session,
            parent_asset_id=parent,
            floating_instance_count=floating_instance_count,
            completed_floating_count=completed_floating_count,
            twin_insight_count=twin_insight_count,
            twin_question_count=twin_question_count,
            open_question_count=open_question_count,
            source_family_count=family_count,
            citation_pack_ready=competition_quality.citations.pack_ready,
            quality_overall=quality_overall,
            would_exceed=would_exceed,
            quality_floor=quality_floor,
            preferred_view_mode=preferred_view_mode,
            operator_override=operator_override,
        )
    except ResearchWrestleSessionSupercomposeError as e:
        raise ResearchWrestleCompetitionQualityComposeError(str(e)) from e
    notes.extend(wrestle.notes)

    session_ready = (
        wrestle.wrestle_ready
        and competition_quality.pack_ready
        and wrestle.live_dispatch_authorized is False
        and competition_quality.live_dispatch_authorized is False
    )
    if not wrestle.wrestle_ready:
        notes.append("session_ready=false — wrestle substrate not ready")
    elif not competition_quality.pack_ready:
        notes.append(
            "session_ready=false — competition/quality/source pack not ready"
        )
    else:
        notes.append(
            "session_ready=true — wrestle+competition quality intent only; still pure"
        )

    if (
        wrestle.live_dispatch_authorized is not False
        or competition_quality.live_dispatch_authorized is not False
        or competition_quality.remote_fetched is not False
        or competition_quality.backlog_mutated is not False
    ):
        raise ResearchWrestleCompetitionQualityComposeError(
            "invariant: nested honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
        )
    )

    return ResearchWrestleCompetitionQualityCompose(
        session_id=session,
        parent_asset_id=parent,
        wrestle=wrestle,
        competition_quality=competition_quality,
        session_ready=session_ready,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        notes=tuple(notes),
        authority="research_wrestle_competition_quality_compose_advisory",
    )


def format_research_wrestle_competition_quality_summary(
    c: ResearchWrestleCompetitionQualityCompose,
) -> str:
    return (
        f"session_ready={c.session_ready} · "
        f"wrestle_ready={c.wrestle.wrestle_ready} · "
        f"quality_pack_ready={c.competition_quality.pack_ready} · "
        f"citations={c.competition_quality.citations.citation_count} · "
        f"behind={c.competition_quality.competition.behind_count} · "
        f"live_dispatch_authorized=false · remote_fetched=false · "
        f"backlog_mutated=false"
    )


__all__ = [
    "ResearchWrestleCompetitionQualityCompose",
    "ResearchWrestleCompetitionQualityComposeError",
    "compose_research_wrestle_competition_quality",
    "format_research_wrestle_competition_quality_summary",
]
