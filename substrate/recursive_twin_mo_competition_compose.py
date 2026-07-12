"""Recursive twin note-taker over MO + model decision + HTML competition (pure).

twin_written / prompts_injected / live_dispatch_authorized always False.
live_execution_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.mo_model_decision_html_native_competition_compose import (
    MoModelDecisionHtmlNativeCompetitionCompose,
    MoModelDecisionHtmlNativeCompetitionComposeError,
    compose_mo_model_decision_html_native_competition,
)
from substrate.recursive_twin_note_taker_compose import (
    RecursiveTwinNoteTakerCompose,
    RecursiveTwinNoteTakerComposeError,
    compose_recursive_twin_note_taker,
)


class RecursiveTwinMoCompetitionComposeError(ValueError):
    """Fail-closed validation for recursive twin + MO competition pack."""


@dataclass(frozen=True)
class RecursiveTwinMoCompetitionCompose:
    parent_asset_id: str
    mo_research: MoModelDecisionHtmlNativeCompetitionCompose
    twin: RecursiveTwinNoteTakerCompose
    pack_ready: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    live_execution_authorized: bool
    live_router_authorized: bool
    pdf_view_authorized: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "mo_research": self.mo_research.to_dict(),
            "twin": self.twin.to_dict(),
            "pack_ready": self.pack_ready,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "live_execution_authorized": False,
            "live_router_authorized": False,
            "pdf_view_authorized": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "recursive_twin_mo_competition_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecursiveTwinMoCompetitionComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_excerpt(
    mo_research: MoModelDecisionHtmlNativeCompetitionCompose,
) -> str:
    parts: list[str] = []
    entry = mo_research.mo.entry_readiness.entry
    # goals may be list of dicts or objects
    goals = getattr(entry, "goals", None)
    if isinstance(goals, (list, tuple)):
        for g in goals:
            title = g.get("title") if isinstance(g, dict) else getattr(g, "title", None)
            if title:
                parts.append(f"goal: {title}")

    qs = (
        mo_research.research.competition_view.competition_pack.quality_write.quality_source
    )
    for c in qs.citations.citations:
        title = c.title if hasattr(c, "title") else str(c.get("title", ""))
        parts.append(f"cite: {title}")
    for row in qs.competition.decisions:
        residual = (
            row.residual if hasattr(row, "residual") else row.get("residual")
        )
        summary = (
            row.decision_summary
            if hasattr(row, "decision_summary")
            else row.get("decision_summary")
        )
        competitor = (
            row.competitor
            if hasattr(row, "competitor")
            else row.get("competitor", "x")
        )
        area = row.area if hasattr(row, "area") else row.get("area", "a")
        if residual:
            parts.append(f"residual: {residual}")
        elif summary:
            parts.append(f"decision: {competitor}/{area}: {summary}")

    model = mo_research.research.decision.driver.decision.selected_model_id
    parts.append(f"model: {model}")
    body = "\n".join(parts).strip()
    return body or (
        "MO competition research pack — twin scaffold from empty residual set"
    )


def _derive_focus(
    mo_research: MoModelDecisionHtmlNativeCompetitionCompose,
    extra: object | None,
) -> list[str]:
    qs: list[str] = []
    if isinstance(extra, list):
        for q in extra:
            if isinstance(q, str) and q.strip():
                qs.append(q.strip())
    decisions = (
        mo_research.research.competition_view.competition_pack.quality_write.quality_source.competition.decisions
    )
    for row in decisions:
        status = (
            row.antiek_status
            if hasattr(row, "antiek_status")
            else row.get("antiek_status")
        )
        residual = (
            row.residual if hasattr(row, "residual") else row.get("residual")
        )
        if status == "behind" and residual:
            qs.append(str(residual))
    return qs


def compose_recursive_twin_mo_competition(
    *,
    parent_asset_id: object,
    mo: object,
    research: object,
    operator_ack: object,
    require_both: object | None = None,
    source_excerpt: object | None = None,
    existing_twin_asset_id: object | None = None,
    focus_questions: object | None = None,
    require_both_with_twin: object | None = None,
) -> RecursiveTwinMoCompetitionCompose:
    """Twin note-taker over MO competition research. Never writes/dispatches."""
    if not isinstance(operator_ack, bool):
        raise RecursiveTwinMoCompetitionComposeError(
            "operator_ack must be an explicit boolean"
        )
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    require_twin = (
        True if require_both_with_twin is None else require_both_with_twin
    )
    if not isinstance(require_twin, bool):
        raise RecursiveTwinMoCompetitionComposeError(
            "require_both_with_twin must be boolean when set"
        )

    notes: list[str] = [
        "twin_written=false · prompts_injected=false · live_dispatch_authorized=false",
        "live_execution_authorized=false · live_router_authorized=false",
        "pdf_view_authorized=false · store_mutated=false",
    ]

    try:
        mo_research = compose_mo_model_decision_html_native_competition(
            mo=mo,
            research=research,
            operator_ack=operator_ack,
            require_both=require_both,
        )
    except MoModelDecisionHtmlNativeCompetitionComposeError as e:
        raise RecursiveTwinMoCompetitionComposeError(str(e)) from e
    notes.extend(f"[mo_research] {n}" for n in mo_research.notes)

    if source_excerpt is not None and str(source_excerpt).strip():
        excerpt = str(source_excerpt).strip()
        notes.append("source_excerpt caller-supplied")
    else:
        excerpt = _derive_excerpt(mo_research)
        notes.append(
            "source_excerpt derived from MO goals + competition residuals/citations"
        )

    focus = _derive_focus(mo_research, focus_questions)

    try:
        twin = compose_recursive_twin_note_taker(
            parent_asset_id=parent,
            source_excerpt=excerpt,
            operator_ack=operator_ack,
            existing_twin_asset_id=existing_twin_asset_id,
            focus_questions=focus if focus else None,
        )
    except RecursiveTwinNoteTakerComposeError as e:
        raise RecursiveTwinMoCompetitionComposeError(str(e)) from e
    notes.extend(f"[twin] {n}" for n in twin.notes)

    if require_twin:
        pack_ready = (
            mo_research.pack_ready is True
            and twin.twin_propose_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            mo_research.pack_ready is True or twin.twin_propose_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — MO competition research + twin note-taker propose ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — mo_research, twin, or operator_ack gate open"
        )

    if (
        mo_research.live_execution_authorized is not False
        or mo_research.live_router_authorized is not False
        or mo_research.twin_written is not False
        or twin.twin_written is not False
        or twin.prompts_injected is not False
        or twin.live_dispatch_authorized is not False
    ):
        raise RecursiveTwinMoCompetitionComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "live_execution_authorized=false",
            "live_router_authorized=false",
            "pdf_view_authorized=false",
            "store_mutated=false",
        )
    )

    return RecursiveTwinMoCompetitionCompose(
        parent_asset_id=parent,
        mo_research=mo_research,
        twin=twin,
        pack_ready=pack_ready,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        live_execution_authorized=False,
        live_router_authorized=False,
        pdf_view_authorized=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="recursive_twin_mo_competition_compose_advisory",
    )


def format_recursive_twin_mo_competition_summary(
    c: RecursiveTwinMoCompetitionCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"mo_research_ready={c.mo_research.pack_ready} · "
        f"twin_propose_ready={c.twin.twin_propose_ready} · "
        f"sections={len(c.twin.twin_scaffold_sections)} · "
        f"twin_written=false · live_execution_authorized=false · prompts_injected=false"
    )


__all__ = [
    "RecursiveTwinMoCompetitionCompose",
    "RecursiveTwinMoCompetitionComposeError",
    "compose_recursive_twin_mo_competition",
    "format_recursive_twin_mo_competition_summary",
]
