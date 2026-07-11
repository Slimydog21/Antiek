"""Research workstation full-loop super-compose (pure).

live_dispatch_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.research_wrestle_session_supercompose import (
    ResearchWrestleSessionSupercompose,
    ResearchWrestleSessionSupercomposeError,
    compose_research_wrestle_session,
)


class ResearchWorkstationFullLoopSupercomposeError(ValueError):
    """Fail-closed validation for full-loop super-compose."""


@dataclass(frozen=True)
class ResearchWorkstationFullLoopSupercompose:
    wrestle: ResearchWrestleSessionSupercompose
    source_attach_ready: bool
    view_mode_ready: bool
    budget_ready: bool
    full_loop_ready: bool
    live_dispatch_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "wrestle": self.wrestle.to_dict(),
            "source_attach_ready": self.source_attach_ready,
            "view_mode_ready": self.view_mode_ready,
            "budget_ready": self.budget_ready,
            "full_loop_ready": self.full_loop_ready,
            "live_dispatch_authorized": False,
            "notes": list(self.notes),
            "authority": "research_workstation_full_loop_supercompose_advisory",
        }


def compose_research_workstation_full_loop(
    *,
    wrestle: dict[str, Any],
    source_attach: dict[str, Any],
    view_mode: dict[str, Any],
    budget: dict[str, Any],
) -> ResearchWorkstationFullLoopSupercompose:
    """Compose full research loop readiness. Never live-dispatches."""
    if not isinstance(wrestle, dict):
        raise ResearchWorkstationFullLoopSupercomposeError(
            "wrestle must be an object"
        )
    if not isinstance(source_attach, dict):
        raise ResearchWorkstationFullLoopSupercomposeError(
            "source_attach must be an object"
        )
    if not isinstance(view_mode, dict):
        raise ResearchWorkstationFullLoopSupercomposeError(
            "view_mode must be an object"
        )
    if not isinstance(budget, dict):
        raise ResearchWorkstationFullLoopSupercomposeError(
            "budget must be an object"
        )

    if not isinstance(source_attach.get("attach_ready"), bool):
        raise ResearchWorkstationFullLoopSupercomposeError(
            "source_attach.attach_ready must be an explicit boolean"
        )
    if source_attach.get("remote_fetched") is not False:
        raise ResearchWorkstationFullLoopSupercomposeError(
            "source_attach.remote_fetched must be false (pure layer)"
        )
    sc = source_attach.get("source_count")
    if not isinstance(sc, int) or isinstance(sc, bool) or sc < 0:
        raise ResearchWorkstationFullLoopSupercomposeError(
            "source_attach.source_count must be a non-negative integer"
        )
    fic = view_mode.get("floating_instance_count")
    if not isinstance(fic, int) or isinstance(fic, bool) or fic < 0:
        raise ResearchWorkstationFullLoopSupercomposeError(
            "view_mode.floating_instance_count must be a non-negative integer"
        )
    pvm = view_mode.get("preferred_view_mode")
    if pvm is not None and pvm not in ("floating", "fullscreen"):
        raise ResearchWorkstationFullLoopSupercomposeError(
            "view_mode.preferred_view_mode must be floating|fullscreen|null"
        )
    we = budget.get("would_exceed")
    if we is not None and not isinstance(we, bool):
        raise ResearchWorkstationFullLoopSupercomposeError(
            "budget.would_exceed must be boolean or null"
        )

    notes: list[str] = [
        "live_dispatch_authorized=false — full loop is advisory readiness only",
        "remote_fetched=false on source attach signal",
    ]

    wrestle_kwargs = dict(wrestle)
    if pvm is not None:
        wrestle_kwargs["preferred_view_mode"] = pvm
    if "would_exceed" in budget:
        wrestle_kwargs["would_exceed"] = we
    if "operator_override" in budget:
        wrestle_kwargs["operator_override"] = budget.get("operator_override")
    base_float = wrestle_kwargs.get("floating_instance_count", 0)
    if not isinstance(base_float, int) or isinstance(base_float, bool):
        base_float = 0
    wrestle_kwargs["floating_instance_count"] = max(base_float, fic)

    try:
        wrestle_result = compose_research_wrestle_session(**wrestle_kwargs)
    except ResearchWrestleSessionSupercomposeError as e:
        raise ResearchWorkstationFullLoopSupercomposeError(str(e)) from e
    notes.extend(wrestle_result.notes)

    source_attach_ready = (
        source_attach["attach_ready"] is True and sc >= 1
    )
    notes.append(
        f"source_attach_ready=true · sources={sc}"
        if source_attach_ready
        else "source_attach_ready=false"
    )

    view_mode_ready = (
        fic >= 1
        or wrestle_result.floating_ready
        or wrestle_result.twin_ready
        or wrestle_result.questions_active
    )
    notes.append(
        f"view_mode_ready=true · preferred={pvm}"
        if view_mode_ready
        else "view_mode_ready=false — no floating/twin/question substrate"
    )

    budget_ready = wrestle_result.budget_ready
    notes.append(
        "budget_ready=true" if budget_ready else "budget_ready=false"
    )

    sel = budget.get("selected_model_id")
    if sel is not None:
        if not isinstance(sel, str) or not sel.strip():
            raise ResearchWorkstationFullLoopSupercomposeError(
                "budget.selected_model_id must be non-empty string when set"
            )
        notes.append(f"selected_model_id={sel.strip()} (operator authority)")

    full_loop_ready = (
        wrestle_result.wrestle_ready
        and source_attach_ready
        and view_mode_ready
        and budget_ready
    )
    notes.append(
        "full_loop_ready=true — wrestle+sources+view+budget pass"
        if full_loop_ready
        else "full_loop_ready=false — continue closing gates"
    )
    notes.append("live_dispatch_authorized=false")

    return ResearchWorkstationFullLoopSupercompose(
        wrestle=wrestle_result,
        source_attach_ready=source_attach_ready,
        view_mode_ready=view_mode_ready,
        budget_ready=budget_ready,
        full_loop_ready=full_loop_ready,
        live_dispatch_authorized=False,
        notes=tuple(notes),
        authority="research_workstation_full_loop_supercompose_advisory",
    )


__all__ = [
    "ResearchWorkstationFullLoopSupercompose",
    "ResearchWorkstationFullLoopSupercomposeError",
    "compose_research_workstation_full_loop",
]
