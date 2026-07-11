"""Midnight Oil unattended recap → write-mode twin collective analysis (pure).

live_execution_authorized / draft_written / analysis_written /
merge_executed / store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil_unattended_recap_compose import (
    MidnightOilUnattendedRecapCompose,
    MidnightOilUnattendedRecapComposeError,
    compose_midnight_oil_unattended_recap,
)
from substrate.write_mode_twin_collective_analysis_compose import (
    WriteModeTwinCollectiveAnalysisCompose,
    WriteModeTwinCollectiveAnalysisComposeError,
    compose_write_mode_twin_collective_analysis,
)


class MidnightOilRecapWriteModeTwinCollectiveComposeError(ValueError):
    """Fail-closed validation for MO recap → write twin collective pack."""


@dataclass(frozen=True)
class MidnightOilRecapWriteModeTwinCollectiveCompose:
    run_id: str
    session_id: str
    draft_id: str
    parent_asset_id: str
    recap: MidnightOilUnattendedRecapCompose
    write_pack: WriteModeTwinCollectiveAnalysisCompose
    pack_ready: bool
    live_execution_authorized: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "draft_id": self.draft_id,
            "parent_asset_id": self.parent_asset_id,
            "recap": self.recap.to_dict(),
            "write_pack": self.write_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_execution_authorized": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "midnight_oil_recap_write_mode_twin_collective_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MidnightOilRecapWriteModeTwinCollectiveComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_slices_and_slots(
    parent_asset_id: str,
    goals: object,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(goals, list):
        raise MidnightOilRecapWriteModeTwinCollectiveComposeError(
            "goals must be an array"
        )
    insights: list[str] = []
    questions: list[str] = []
    slots: list[dict[str, Any]] = []
    for g in goals:
        if not isinstance(g, dict):
            raise MidnightOilRecapWriteModeTwinCollectiveComposeError(
                "goals items must be objects"
            )
        gid = str(g.get("goal_id", "")).strip()
        title = str(g.get("title", "")).strip()
        if not gid or not title:
            raise MidnightOilRecapWriteModeTwinCollectiveComposeError(
                "goals items need goal_id and title"
            )
        notes_raw = g.get("notes")
        notes_s = str(notes_raw).strip() if notes_raw is not None else ""
        body = f"{title}: {notes_s}" if notes_s else title
        status = str(g.get("status", "")).strip()
        if status == "done":
            insights.append(body)
            slots.append(
                {
                    "slot_id": f"mo-{gid}",
                    "question_id": gid,
                    "parent_asset_id": parent_asset_id,
                    "status": "completed",
                    "findings": [body],
                    "body": body,
                }
            )
        elif status == "blocked":
            questions.append(body)
            slots.append(
                {
                    "slot_id": f"mo-{gid}",
                    "question_id": gid,
                    "parent_asset_id": parent_asset_id,
                    "status": "closed",
                    "findings": [body],
                    "body": body,
                }
            )
        else:
            questions.append(body)
            slots.append(
                {
                    "slot_id": f"mo-{gid}",
                    "question_id": gid,
                    "parent_asset_id": parent_asset_id,
                    "status": "open",
                    "findings": [body],
                    "body": body,
                }
            )
    if not insights and not questions and goals:
        for g in goals:
            if isinstance(g, dict):
                title = str(g.get("title", "")).strip()
                if title:
                    questions.append(title)
    slices = [
        {
            "parent_asset_id": parent_asset_id,
            "insights": insights,
            "questions": questions,
        }
    ]
    return slices, slots


def compose_midnight_oil_recap_write_mode_twin_collective(
    *,
    run_id: object,
    operator_id: object,
    work_minutes_planned: object,
    work_minutes_actual: object,
    goals: object,
    price_ceiling_usd: object,
    spend_usd: object,
    operator_ack: object,
    session_id: object,
    draft_id: object,
    parent_asset_id: object,
    artifact_ids: object | None = None,
    analysis_kind: object | None = None,
    twin_slices: object | None = None,
    chase_slots: object | None = None,
    base_draft_html: object | None = None,
    extra_findings: object | None = None,
    require_both: object | None = None,
) -> MidnightOilRecapWriteModeTwinCollectiveCompose:
    """MO recap + write twin/analysis. Never re-launches or writes assets."""
    if not isinstance(operator_ack, bool):
        raise MidnightOilRecapWriteModeTwinCollectiveComposeError(
            "operator_ack must be an explicit boolean"
        )
    rid = _require_nonempty(run_id, field="run_id")
    session = _require_nonempty(session_id, field="session_id")
    draft = _require_nonempty(draft_id, field="draft_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MidnightOilRecapWriteModeTwinCollectiveComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_execution_authorized=false — recap never re-launches MO",
        "draft_written=false · analysis_written=false · merge_executed=false",
        "store_mutated=false",
    ]

    try:
        recap = compose_midnight_oil_unattended_recap(
            run_id=rid,
            operator_id=operator_id,
            work_minutes_planned=work_minutes_planned,
            work_minutes_actual=work_minutes_actual,
            goals=goals,
            price_ceiling_usd=price_ceiling_usd,
            spend_usd=spend_usd,
            operator_ack=operator_ack,
            artifact_ids=artifact_ids,
        )
    except MidnightOilUnattendedRecapComposeError as e:
        raise MidnightOilRecapWriteModeTwinCollectiveComposeError(str(e)) from e
    notes.extend(f"[recap] {n}" for n in recap.notes)

    if twin_slices is not None and chase_slots is not None:
        if not isinstance(twin_slices, list):
            raise MidnightOilRecapWriteModeTwinCollectiveComposeError(
                "twin_slices must be an array when set"
            )
        if not isinstance(chase_slots, list):
            raise MidnightOilRecapWriteModeTwinCollectiveComposeError(
                "chase_slots must be an array when set"
            )
        slices: list[dict[str, Any]] = [
            s for s in twin_slices if isinstance(s, dict)
        ]
        slots: list[dict[str, Any]] = [
            s for s in chase_slots if isinstance(s, dict)
        ]
        notes.append("twin_slices/chase_slots caller-supplied")
    else:
        derived_slices, derived_slots = _derive_slices_and_slots(parent, goals)
        if twin_slices is not None:
            if not isinstance(twin_slices, list):
                raise MidnightOilRecapWriteModeTwinCollectiveComposeError(
                    "twin_slices must be an array when set"
                )
            slices = [s for s in twin_slices if isinstance(s, dict)]
        else:
            slices = derived_slices
        if chase_slots is not None:
            if not isinstance(chase_slots, list):
                raise MidnightOilRecapWriteModeTwinCollectiveComposeError(
                    "chase_slots must be an array when set"
                )
            slots = [s for s in chase_slots if isinstance(s, dict)]
        else:
            slots = derived_slots
        notes.append(
            f"derived twin_slices={len(slices)} slots={len(slots)} from MO goals"
        )

    # Ensure ≥2 chase slots for write-mode collective analysis contract.
    while len(slots) < 2:
        i = len(slots)
        slots.append(
            {
                "slot_id": f"mo-pad-{i}",
                "question_id": f"pad-{i}",
                "parent_asset_id": parent,
                "status": "open",
                "findings": [f"padding-slot-{i}"],
                "body": f"padding-slot-{i}",
            }
        )
        notes.append(
            "chase_slots padded to ≥2 for write collective analysis contract"
        )

    # Ensure twin slice has ≥1 insight or question for draft_ready.
    if slices:
        s0 = slices[0]
        insights = s0.get("insights") if isinstance(s0.get("insights"), list) else []
        questions = (
            s0.get("questions") if isinstance(s0.get("questions"), list) else []
        )
        if len(insights) == 0 and len(questions) == 0:
            slices = [
                {
                    **s0,
                    "questions": [f"Open: {parent}"],
                },
                *slices[1:],
            ]
            notes.append("twin_slices padded with placeholder question")

    kind = "draft_analysis" if analysis_kind is None else analysis_kind
    if kind not in ("draft_analysis", "full_analysis"):
        raise MidnightOilRecapWriteModeTwinCollectiveComposeError(
            "analysis_kind must be draft_analysis or full_analysis when set"
        )

    completed = [s for s in slots if s.get("status") == "completed"]
    all_completed = len(slots) >= 2 and len(completed) == len(slots)

    if analysis_kind is None and all_completed and operator_ack is True:
        kind = "full_analysis"
    if kind == "full_analysis" and not all_completed:
        kind = "draft_analysis"
        notes.append(
            "analysis_kind demoted to draft_analysis — full_analysis needs "
            "all slots completed"
        )
    if kind == "full_analysis" and operator_ack is not True:
        kind = "draft_analysis"
        notes.append(
            "analysis_kind demoted to draft_analysis — full_analysis requires "
            "operator_ack"
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
            extra_findings=extra_findings,
            require_both=True,
        )
    except WriteModeTwinCollectiveAnalysisComposeError as e:
        raise MidnightOilRecapWriteModeTwinCollectiveComposeError(str(e)) from e
    notes.extend(f"[write_pack] {n}" for n in write_pack.notes)

    if require:
        pack_ready = (
            recap.recap_ready is True
            and write_pack.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            recap.recap_ready is True or write_pack.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — MO recap + write twin/analysis ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — recap, write pack, or operator_ack gate open"
        )

    if (
        recap.live_execution_authorized is not False
        or recap.store_mutated is not False
        or write_pack.draft_written is not False
        or write_pack.analysis_written is not False
        or write_pack.merge_executed is not False
        or write_pack.live_dispatched is not False
    ):
        raise MidnightOilRecapWriteModeTwinCollectiveComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_execution_authorized=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "store_mutated=false",
        )
    )

    return MidnightOilRecapWriteModeTwinCollectiveCompose(
        run_id=rid,
        session_id=session,
        draft_id=draft,
        parent_asset_id=parent,
        recap=recap,
        write_pack=write_pack,
        pack_ready=pack_ready,
        live_execution_authorized=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        store_mutated=False,
        notes=tuple(notes),
        authority=(
            "midnight_oil_recap_write_mode_twin_collective_compose_advisory"
        ),
    )


def format_midnight_oil_recap_write_mode_twin_collective_summary(
    c: MidnightOilRecapWriteModeTwinCollectiveCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"recap_ready={c.recap.recap_ready} · "
        f"write_ready={c.write_pack.pack_ready} · "
        f"done={c.recap.goals_done}/{c.recap.goal_count} · "
        f"live_execution_authorized=false · draft_written=false · "
        f"analysis_written=false"
    )


__all__ = [
    "MidnightOilRecapWriteModeTwinCollectiveCompose",
    "MidnightOilRecapWriteModeTwinCollectiveComposeError",
    "compose_midnight_oil_recap_write_mode_twin_collective",
    "format_midnight_oil_recap_write_mode_twin_collective_summary",
]
