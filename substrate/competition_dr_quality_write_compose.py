"""Competition DR quality + source pack → write twin collective analysis (pure).

live_dispatch_authorized / remote_fetched / backlog_mutated always False.
draft_written / analysis_written / merge_executed always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.competition_dr_quality_source_pack_compose import (
    CompetitionDrQualitySourcePackCompose,
    CompetitionDrQualitySourcePackComposeError,
    compose_competition_dr_quality_source_pack,
)
from substrate.write_mode_twin_collective_analysis_compose import (
    WriteModeTwinCollectiveAnalysisCompose,
    WriteModeTwinCollectiveAnalysisComposeError,
    compose_write_mode_twin_collective_analysis,
)


class CompetitionDrQualityWriteComposeError(ValueError):
    """Fail-closed validation for competition quality write pack."""


@dataclass(frozen=True)
class CompetitionDrQualityWriteCompose:
    session_id: str
    draft_id: str
    parent_asset_id: str
    quality_source: CompetitionDrQualitySourcePackCompose
    write_pack: WriteModeTwinCollectiveAnalysisCompose
    pack_ready: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    store_mutated: bool
    live_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "draft_id": self.draft_id,
            "parent_asset_id": self.parent_asset_id,
            "quality_source": self.quality_source.to_dict(),
            "write_pack": self.write_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "store_mutated": False,
            "live_dispatched": False,
            "notes": list(self.notes),
            "authority": "competition_dr_quality_write_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitionDrQualityWriteComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_from_competition(
    parent_asset_id: str,
    quality_source: CompetitionDrQualitySourcePackCompose,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    insights: list[str] = []
    questions: list[str] = []
    slots: list[dict[str, Any]] = []

    for c in quality_source.citations.citations:
        title = c.title if hasattr(c, "title") else str(c.get("title", ""))
        cid = (
            c.citation_id
            if hasattr(c, "citation_id")
            else str(c.get("citation_id", "c"))
        )
        insights.append(title)
        slots.append(
            {
                "slot_id": f"cite-{cid}",
                "question_id": str(cid),
                "parent_asset_id": parent_asset_id,
                "status": "completed",
                "findings": [title],
                "body": title,
            }
        )

    for row in quality_source.competition.decisions:
        status = (
            row.antiek_status
            if hasattr(row, "antiek_status")
            else row.get("antiek_status")
        )
        residual = (
            row.residual if hasattr(row, "residual") else row.get("residual")
        )
        competitor = (
            row.competitor
            if hasattr(row, "competitor")
            else row.get("competitor", "x")
        )
        area = row.area if hasattr(row, "area") else row.get("area", "a")
        summary = (
            row.decision_summary
            if hasattr(row, "decision_summary")
            else row.get("decision_summary")
        )
        if status == "behind" and residual:
            questions.append(str(residual))
            slots.append(
                {
                    "slot_id": f"gap-{competitor}-{area}",
                    "question_id": f"{competitor}-{area}",
                    "parent_asset_id": parent_asset_id,
                    "status": "open",
                    "findings": [str(residual)],
                    "body": str(residual),
                }
            )
        elif summary:
            insights.append(f"{competitor}/{area}: {summary}")

    if not insights and not questions:
        questions.append(
            "What competition gaps remain for Antiek DR quality?"
        )

    while len(slots) < 2:
        i = len(slots)
        slots.append(
            {
                "slot_id": f"cq-pad-{i}",
                "question_id": f"pad-{i}",
                "parent_asset_id": parent_asset_id,
                "status": "open",
                "findings": [f"padding-{i}"],
                "body": f"padding-{i}",
            }
        )

    return (
        [
            {
                "parent_asset_id": parent_asset_id,
                "insights": insights,
                "questions": questions,
            }
        ],
        slots,
    )


def compose_competition_dr_quality_write(
    *,
    session_id: object,
    draft_id: object,
    parent_asset_id: object,
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
    analysis_kind: object | None = None,
    twin_slices: object | None = None,
    chase_slots: object | None = None,
    base_draft_html: object | None = None,
    extra_write_findings: object | None = None,
    require_both_with_write: object | None = None,
) -> CompetitionDrQualityWriteCompose:
    """Competition quality/source + write pack. Never dispatches/writes."""
    if not isinstance(operator_ack, bool):
        raise CompetitionDrQualityWriteComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    draft = _require_nonempty(draft_id, field="draft_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    require_write = (
        True if require_both_with_write is None else require_both_with_write
    )
    if not isinstance(require_write, bool):
        raise CompetitionDrQualityWriteComposeError(
            "require_both_with_write must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "draft_written=false · analysis_written=false · merge_executed=false",
        "store_mutated=false · live_dispatched=false",
    ]

    try:
        quality_source = compose_competition_dr_quality_source_pack(
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
        raise CompetitionDrQualityWriteComposeError(str(e)) from e
    notes.extend(f"[quality_source] {n}" for n in quality_source.notes)

    if twin_slices is not None and chase_slots is not None:
        if not isinstance(twin_slices, list) or not isinstance(chase_slots, list):
            raise CompetitionDrQualityWriteComposeError(
                "twin_slices and chase_slots must be arrays when set"
            )
        slices = [s for s in twin_slices if isinstance(s, dict)]
        slots = [s for s in chase_slots if isinstance(s, dict)]
        notes.append("twin_slices/chase_slots caller-supplied")
    else:
        d_slices, d_slots = _derive_from_competition(parent, quality_source)
        slices = (
            [s for s in twin_slices if isinstance(s, dict)]
            if isinstance(twin_slices, list)
            else d_slices
        )
        slots = (
            [s for s in chase_slots if isinstance(s, dict)]
            if isinstance(chase_slots, list)
            else d_slots
        )
        notes.append(
            f"derived twin_slices={len(slices)} slots={len(slots)} "
            "from competition+citations"
        )

    while len(slots) < 2:
        i = len(slots)
        slots.append(
            {
                "slot_id": f"cq-pad-{i}",
                "question_id": f"pad-{i}",
                "parent_asset_id": parent,
                "status": "open",
                "findings": [f"padding-{i}"],
                "body": f"padding-{i}",
            }
        )
        notes.append("chase_slots padded to ≥2 for write collective analysis")

    kind = "draft_analysis" if analysis_kind is None else analysis_kind
    if kind not in ("draft_analysis", "full_analysis"):
        raise CompetitionDrQualityWriteComposeError(
            "analysis_kind must be draft_analysis or full_analysis when set"
        )
    completed = [s for s in slots if s.get("status") == "completed"]
    all_completed = len(slots) >= 2 and len(completed) == len(slots)
    if analysis_kind is None and all_completed and operator_ack is True:
        kind = "full_analysis"
    if kind == "full_analysis" and not all_completed:
        kind = "draft_analysis"
        notes.append(
            "analysis_kind demoted to draft_analysis — full needs all slots completed"
        )
    if kind == "full_analysis" and operator_ack is not True:
        kind = "draft_analysis"
        notes.append(
            "analysis_kind demoted to draft_analysis — full_analysis requires operator_ack"
        )

    try:
        write_pack = compose_write_mode_twin_collective_analysis(
            session_id=session,
            draft_id=draft,
            parent_asset_id=parent,
            twin_slices=slices,
            chase_slots=slots,
            analysis_kind=kind,
            operator_ack=operator_ack,
            base_draft_html=base_draft_html,
            extra_findings=extra_write_findings,
            require_both=True,
        )
    except WriteModeTwinCollectiveAnalysisComposeError as e:
        raise CompetitionDrQualityWriteComposeError(str(e)) from e
    notes.extend(f"[write_pack] {n}" for n in write_pack.notes)

    if require_write:
        pack_ready = (
            quality_source.pack_ready is True
            and write_pack.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            quality_source.pack_ready is True or write_pack.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — competition quality/source + write pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — quality_source, write pack, or operator_ack gate open"
        )

    if (
        quality_source.live_dispatch_authorized is not False
        or quality_source.remote_fetched is not False
        or quality_source.backlog_mutated is not False
        or write_pack.draft_written is not False
        or write_pack.analysis_written is not False
        or write_pack.merge_executed is not False
        or write_pack.live_dispatched is not False
    ):
        raise CompetitionDrQualityWriteComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "store_mutated=false",
            "live_dispatched=false",
        )
    )

    return CompetitionDrQualityWriteCompose(
        session_id=session,
        draft_id=draft,
        parent_asset_id=parent,
        quality_source=quality_source,
        write_pack=write_pack,
        pack_ready=pack_ready,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        store_mutated=False,
        live_dispatched=False,
        notes=tuple(notes),
        authority="competition_dr_quality_write_compose_advisory",
    )


def format_competition_dr_quality_write_summary(
    c: CompetitionDrQualityWriteCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"quality_ready={c.quality_source.pack_ready} · "
        f"write_ready={c.write_pack.pack_ready} · "
        f"behind={c.quality_source.competition.behind_count} · "
        f"live_dispatch_authorized=false · remote_fetched=false · "
        f"draft_written=false · analysis_written=false"
    )


__all__ = [
    "CompetitionDrQualityWriteCompose",
    "CompetitionDrQualityWriteComposeError",
    "compose_competition_dr_quality_write",
    "format_competition_dr_quality_write_summary",
]
