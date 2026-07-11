"""Research wrestle session super-compose (pure).

Operator vision: live in the research workstation; Interrogate, assess,
and wrestle; record twin insights/questions; attach sources; stay budget-honest.

live_dispatch_authorized is always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class ResearchWrestleSessionSupercomposeError(ValueError):
    """Fail-closed validation for wrestle session super-compose."""


@dataclass(frozen=True)
class ResearchWrestleSessionSupercompose:
    session_id: str
    parent_asset_id: str
    floating_ready: bool
    twin_ready: bool
    questions_active: bool
    sources_ready: bool
    citation_ready: bool
    quality_ready: bool
    budget_ready: bool
    preferred_view_mode: str | None
    wrestle_ready: bool
    live_dispatch_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "floating_ready": self.floating_ready,
            "twin_ready": self.twin_ready,
            "questions_active": self.questions_active,
            "sources_ready": self.sources_ready,
            "citation_ready": self.citation_ready,
            "quality_ready": self.quality_ready,
            "budget_ready": self.budget_ready,
            "preferred_view_mode": self.preferred_view_mode,
            "wrestle_ready": self.wrestle_ready,
            "live_dispatch_authorized": False,
            "notes": list(self.notes),
            "authority": "research_wrestle_session_supercompose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchWrestleSessionSupercomposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_nonneg_int(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ResearchWrestleSessionSupercomposeError(
            f"{field} must be a non-negative integer"
        )
    return value


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ResearchWrestleSessionSupercomposeError(
            f"{field} must be an explicit boolean"
        )
    return value


def compose_research_wrestle_session(
    *,
    session_id: object,
    parent_asset_id: object,
    floating_instance_count: object,
    completed_floating_count: object,
    twin_insight_count: object,
    twin_question_count: object,
    open_question_count: object,
    source_family_count: object,
    citation_pack_ready: object,
    quality_overall: object,
    would_exceed: object,
    quality_floor: object | None = None,
    preferred_view_mode: object | None = None,
    operator_override: object | None = None,
) -> ResearchWrestleSessionSupercompose:
    """Compose wrestle readiness. Never live-dispatches."""
    sid = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    floating = _require_nonneg_int(
        floating_instance_count, field="floating_instance_count"
    )
    completed = _require_nonneg_int(
        completed_floating_count, field="completed_floating_count"
    )
    if completed > floating:
        raise ResearchWrestleSessionSupercomposeError(
            "completed_floating_count cannot exceed floating_instance_count"
        )
    insights = _require_nonneg_int(twin_insight_count, field="twin_insight_count")
    twin_q = _require_nonneg_int(twin_question_count, field="twin_question_count")
    open_q = _require_nonneg_int(open_question_count, field="open_question_count")
    sources = _require_nonneg_int(source_family_count, field="source_family_count")
    citation = _require_bool(citation_pack_ready, field="citation_pack_ready")

    if would_exceed is not None and not isinstance(would_exceed, bool):
        raise ResearchWrestleSessionSupercomposeError(
            "would_exceed must be boolean or null"
        )

    override = False if operator_override is None else operator_override
    if not isinstance(override, bool):
        raise ResearchWrestleSessionSupercomposeError(
            "operator_override must be boolean when set"
        )

    pref: str | None = None
    if preferred_view_mode is not None:
        if preferred_view_mode not in ("floating", "fullscreen"):
            raise ResearchWrestleSessionSupercomposeError(
                "preferred_view_mode must be floating|fullscreen|null"
            )
        pref = preferred_view_mode  # type: ignore[assignment]

    notes: list[str] = [
        "live_dispatch_authorized=false — wrestle snapshot is advisory only",
        "counts and findings are caller-supplied only (no invent)",
    ]

    floating_ready = floating >= 1
    notes.append(
        f"floating_ready={str(floating_ready).lower()} · instances={floating} · "
        f"completed={completed}"
        if floating_ready
        else "floating_ready=false — no floating deep research instances"
    )

    twin_ready = insights + twin_q >= 1
    notes.append(
        f"twin_ready=true · insights={insights} · questions={twin_q}"
        if twin_ready
        else "twin_ready=false — no twin insights/questions recorded"
    )

    questions_active = open_q >= 1
    notes.append(
        f"questions_active=true · open_questions={open_q}"
        if questions_active
        else "questions_active=false — no open wrestle questions"
    )

    sources_ready = sources >= 1
    notes.append(
        f"sources_ready=true · families={sources}"
        if sources_ready
        else "sources_ready=false — no source families selected"
    )

    citation_ready = citation
    notes.append(
        "citation_ready=true" if citation_ready else "citation_ready=false — citation pack not ready"
    )

    floor = 0.5 if quality_floor is None else quality_floor
    if not isinstance(floor, (int, float)) or isinstance(floor, bool):
        raise ResearchWrestleSessionSupercomposeError(
            "quality_floor must be a finite number in [0,1]"
        )
    floor_f = float(floor)
    if not (0.0 <= floor_f <= 1.0) or floor_f != floor_f:  # NaN check
        raise ResearchWrestleSessionSupercomposeError(
            "quality_floor must be a finite number in [0,1]"
        )

    quality_ready = False
    if quality_overall is None:
        notes.append("quality_ready=false — quality_overall unknown (null honesty)")
    elif not isinstance(quality_overall, (int, float)) or isinstance(
        quality_overall, bool
    ):
        raise ResearchWrestleSessionSupercomposeError(
            "quality_overall must be number or null"
        )
    else:
        q = float(quality_overall)
        if q != q or q < 0.0 or q > 1.0:
            raise ResearchWrestleSessionSupercomposeError(
                "quality_overall must be in [0,1]"
            )
        quality_ready = q >= floor_f
        notes.append(
            f"quality_ready=true · overall={q} floor={floor_f}"
            if quality_ready
            else f"quality_ready=false · overall={q} < floor={floor_f}"
        )

    budget_ready = False
    if would_exceed is None:
        if override:
            budget_ready = True
            notes.append(
                "budget_ready=true via operator_override (would_exceed unknown)"
            )
        else:
            notes.append(
                "budget_ready=false — would_exceed unknown and no operator_override"
            )
    elif would_exceed is True:
        if override:
            budget_ready = True
            notes.append(
                "budget_ready=true via operator_override despite would_exceed=true"
            )
        else:
            notes.append("budget_ready=false — would_exceed=true")
    else:
        budget_ready = True
        notes.append("budget_ready=true — would_exceed=false")

    substrate = floating_ready or twin_ready or questions_active
    wrestle_ready = substrate and sources_ready and quality_ready and budget_ready
    notes.append(
        "wrestle_ready=true — substrate+sources+quality+budget gates pass"
        if wrestle_ready
        else "wrestle_ready=false — continue recording insights/questions or fix gates"
    )
    if pref:
        notes.append(f"preferred_view_mode={pref}")
    notes.append("live_dispatch_authorized=false")

    return ResearchWrestleSessionSupercompose(
        session_id=sid,
        parent_asset_id=parent,
        floating_ready=floating_ready,
        twin_ready=twin_ready,
        questions_active=questions_active,
        sources_ready=sources_ready,
        citation_ready=citation_ready,
        quality_ready=quality_ready,
        budget_ready=budget_ready,
        preferred_view_mode=pref,
        wrestle_ready=wrestle_ready,
        live_dispatch_authorized=False,
        notes=tuple(notes),
        authority="research_wrestle_session_supercompose_advisory",
    )


def format_research_wrestle_session_summary(
    s: ResearchWrestleSessionSupercompose,
) -> str:
    return (
        f"wrestle_ready={s.wrestle_ready} · floating={s.floating_ready} · "
        f"twin={s.twin_ready} · sources={s.sources_ready} · "
        f"quality={s.quality_ready} · budget={s.budget_ready} · "
        f"live_dispatch_authorized=false"
    )


__all__ = [
    "ResearchWrestleSessionSupercompose",
    "ResearchWrestleSessionSupercomposeError",
    "compose_research_wrestle_session",
    "format_research_wrestle_session_summary",
]
