"""Competition DR quality + source pack compose (pure).

live_dispatch_authorized, remote_fetched, backlog_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.competition_deep_research_gap import (
    CompetitionDeepResearchGapError,
    CompetitionGapMatrix,
    build_competition_deep_research_gap,
)
from substrate.deep_research_quality_budget_gate_compose import (
    DeepResearchQualityBudgetGateCompose,
    DeepResearchQualityBudgetGateComposeError,
    compose_deep_research_quality_budget_gate,
)
from substrate.deep_research_source_citation_pack import (
    DeepResearchSourceCitationPack,
    DeepResearchSourceCitationPackError,
    build_deep_research_source_citation_pack,
)


class CompetitionDrQualitySourcePackComposeError(ValueError):
    """Fail-closed validation for competition DR quality+source pack."""


@dataclass(frozen=True)
class CompetitionDrQualitySourcePackCompose:
    session_id: str
    competition: CompetitionGapMatrix
    citations: DeepResearchSourceCitationPack
    quality_budget: DeepResearchQualityBudgetGateCompose
    pack_ready: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "competition": self.competition.to_dict(),
            "citations": self.citations.to_dict(),
            "quality_budget": self.quality_budget.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "notes": list(self.notes),
            "authority": "competition_dr_quality_source_pack_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitionDrQualitySourcePackComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_competition_dr_quality_source_pack(
    *,
    session_id: object,
    competitor_decisions: object,
    requested_families: object,
    citations: object,
    quality_overall: object,
    would_exceed: object,
    operator_ack: object,
    focus_areas: object | None = None,
    filter_to_selected_families: object | None = None,
    quality_floor: object | None = None,
    operator_override: object | None = None,
    require_no_behind_gaps: object | None = None,
) -> CompetitionDrQualitySourcePackCompose:
    """Compose competition + citations + quality/budget gate. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise CompetitionDrQualitySourcePackComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    require_no_behind = (
        False if require_no_behind_gaps is None else require_no_behind_gaps
    )
    if not isinstance(require_no_behind, bool):
        raise CompetitionDrQualitySourcePackComposeError(
            "require_no_behind_gaps must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatch_authorized=false — world-class DR pack is pure readiness",
        "remote_fetched=false — no arxiv/substack network fetch",
        "backlog_mutated=false — competition residuals advisory only",
    ]

    try:
        competition = build_competition_deep_research_gap(
            decisions=competitor_decisions,
            focus_areas=focus_areas,
        )
    except CompetitionDeepResearchGapError as e:
        raise CompetitionDrQualitySourcePackComposeError(str(e)) from e
    notes.extend(competition.notes)
    notes.append(
        f"competition behind={competition.behind_count} · "
        f"parity={competition.parity_count} · ahead={competition.ahead_count}"
    )

    filt = (
        True
        if filter_to_selected_families is None
        else filter_to_selected_families
    )
    try:
        citation_pack = build_deep_research_source_citation_pack(
            session_id=session,
            requested_families=requested_families,
            citations=citations,
            filter_to_selected_families=filt,
        )
    except DeepResearchSourceCitationPackError as e:
        raise CompetitionDrQualitySourcePackComposeError(str(e)) from e
    notes.extend(citation_pack.notes)

    try:
        quality_budget = compose_deep_research_quality_budget_gate(
            session_id=session,
            quality_overall=quality_overall,
            would_exceed=would_exceed,
            operator_ack=operator_ack,
            quality_floor=quality_floor,
            operator_override=operator_override,
            citation_pack_ready=citation_pack.pack_ready,
        )
    except DeepResearchQualityBudgetGateComposeError as e:
        raise CompetitionDrQualitySourcePackComposeError(str(e)) from e
    notes.extend(quality_budget.notes)

    competition_ok = True
    if require_no_behind and competition.behind_count > 0:
        competition_ok = False
        notes.append(
            f"competition_ok=false — behind_count={competition.behind_count} "
            "and require_no_behind_gaps=true"
        )
    elif competition.behind_count > 0:
        notes.append(
            f"competition_ok=true (advisory) — behind_count={competition.behind_count} "
            "recorded as residuals, not blocking"
        )
    else:
        notes.append("competition_ok=true — no behind residuals in matrix")

    pack_ready = (
        quality_budget.gate_ready
        and citation_pack.pack_ready
        and competition_ok
        and quality_budget.live_dispatch_authorized is False
    )
    if not citation_pack.pack_ready:
        notes.append("pack_ready=false — citation pack not ready")
    elif not quality_budget.gate_ready:
        notes.append("pack_ready=false — quality/budget gate not ready")
    elif not competition_ok:
        notes.append("pack_ready=false — competition behind residuals block")
    else:
        notes.append(
            "pack_ready=true — competition+sources+quality/budget intent; "
            "still live_dispatch_authorized=false"
        )

    if (
        competition.backlog_mutated is not False
        or citation_pack.remote_fetched is not False
        or quality_budget.live_dispatch_authorized is not False
    ):
        raise CompetitionDrQualitySourcePackComposeError(
            "invariant: nested honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
        )
    )

    return CompetitionDrQualitySourcePackCompose(
        session_id=session,
        competition=competition,
        citations=citation_pack,
        quality_budget=quality_budget,
        pack_ready=pack_ready,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        notes=tuple(notes),
        authority="competition_dr_quality_source_pack_compose_advisory",
    )


def format_competition_dr_quality_source_pack_summary(
    c: CompetitionDrQualitySourcePackCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · citations={c.citations.citation_count} · "
        f"behind={c.competition.behind_count} · "
        f"gate={c.quality_budget.gate_ready} · "
        f"live_dispatch_authorized=false · remote_fetched=false · "
        f"backlog_mutated=false"
    )


__all__ = [
    "CompetitionDrQualitySourcePackCompose",
    "CompetitionDrQualitySourcePackComposeError",
    "compose_competition_dr_quality_source_pack",
    "format_competition_dr_quality_source_pack_summary",
]
