"""Floating multi-select + sources + twin → write collective analysis (pure).

live_dispatched / twin_written / draft_written / analysis_written /
merge_executed / remote_fetched always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_multi_select_source_attach_quality_twin_compose import (
    FloatingMultiSelectSourceAttachQualityTwinCompose,
    FloatingMultiSelectSourceAttachQualityTwinComposeError,
    compose_floating_multi_select_source_attach_quality_twin,
)
from substrate.write_mode_twin_collective_analysis_compose import (
    WriteModeTwinCollectiveAnalysisCompose,
    WriteModeTwinCollectiveAnalysisComposeError,
    compose_write_mode_twin_collective_analysis,
)


class FloatingMultiSelectSourceTwinWriteComposeError(ValueError):
    """Fail-closed validation for multi-select source twin write pack."""


@dataclass(frozen=True)
class FloatingMultiSelectSourceTwinWriteCompose:
    session_id: str
    draft_id: str
    parent_asset_id: str
    multi_twin: FloatingMultiSelectSourceAttachQualityTwinCompose
    write_pack: WriteModeTwinCollectiveAnalysisCompose
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    twin_written: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    remote_fetched: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "draft_id": self.draft_id,
            "parent_asset_id": self.parent_asset_id,
            "multi_twin": self.multi_twin.to_dict(),
            "write_pack": self.write_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "twin_written": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "remote_fetched": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "floating_multi_select_source_twin_write_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingMultiSelectSourceTwinWriteComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_slices_and_slots(
    parent_asset_id: str,
    *,
    members: object,
    selected_instance_ids: object,
    sources: object,
    cohesive_prompt: object,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(members, list):
        raise FloatingMultiSelectSourceTwinWriteComposeError(
            "members must be an array"
        )
    if not isinstance(selected_instance_ids, list):
        raise FloatingMultiSelectSourceTwinWriteComposeError(
            "selected_instance_ids must be an array"
        )
    if not isinstance(sources, list):
        raise FloatingMultiSelectSourceTwinWriteComposeError(
            "sources must be an array"
        )
    selected = {str(x) for x in selected_instance_ids}
    insights: list[str] = []
    questions: list[str] = []
    slots: list[dict[str, Any]] = []

    for s in sources:
        if isinstance(s, dict):
            title = str(s.get("title", "")).strip()
            if title:
                insights.append(title)

    for m in members:
        if not isinstance(m, dict):
            continue
        iid = str(m.get("instance_id", "")).strip()
        if iid not in selected:
            continue
        hl = str(m.get("highlight") or "").strip()
        prior = str(m.get("prior_prompt") or "").strip()
        findings_list = m.get("findings")
        first_finding = ""
        if isinstance(findings_list, list) and findings_list:
            first_finding = str(findings_list[0]).strip()
        body = hl or prior or first_finding or iid
        status = str(m.get("status", "")).strip()
        completed = status == "completed" or bool(first_finding)
        if completed:
            insights.append(body)
            slots.append(
                {
                    "slot_id": f"ms-{iid}",
                    "question_id": iid,
                    "parent_asset_id": parent_asset_id,
                    "status": "completed",
                    "findings": (
                        [str(x) for x in findings_list]
                        if isinstance(findings_list, list) and findings_list
                        else [body]
                    ),
                    "body": body,
                }
            )
        elif status == "closed":
            questions.append(body)
            slots.append(
                {
                    "slot_id": f"ms-{iid}",
                    "question_id": iid,
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
                    "slot_id": f"ms-{iid}",
                    "question_id": iid,
                    "parent_asset_id": parent_asset_id,
                    "status": "open",
                    "findings": [body],
                    "body": body,
                }
            )

    prompt = str(cohesive_prompt or "").strip()
    if prompt:
        questions.append(prompt)
    if not insights and not questions:
        questions.append(f"Open multi-select write for {parent_asset_id}")

    slices = [
        {
            "parent_asset_id": parent_asset_id,
            "insights": insights,
            "questions": questions,
        }
    ]
    return slices, slots


def compose_floating_multi_select_source_twin_write(
    *,
    session_id: object,
    draft_id: object,
    parent_asset_id: object,
    members: object,
    selected_instance_ids: object,
    pack_mode: object,
    cohesive_prompt: object,
    operator_ack: object,
    requested_families: object,
    sources: object,
    quality_overall: object,
    would_exceed: object,
    extra_context: object | None = None,
    analysis_kind: object | None = None,
    extra_findings: object | None = None,
    citations: object | None = None,
    derive_citations_from_sources: object | None = None,
    quality_floor: object | None = None,
    operator_override: object | None = None,
    require_both: object | None = None,
    existing_twin_asset_id: object | None = None,
    analysis_excerpt: object | None = None,
    mark_for_prompt_context: object | None = None,
    twin_findings: object | None = None,
    require_both_with_twin: object | None = None,
    twin_slices: object | None = None,
    chase_slots: object | None = None,
    base_draft_html: object | None = None,
    extra_write_findings: object | None = None,
    require_both_with_write: object | None = None,
) -> FloatingMultiSelectSourceTwinWriteCompose:
    """Multi-select+twin + write pack. Never writes/dispatches."""
    if not isinstance(operator_ack, bool):
        raise FloatingMultiSelectSourceTwinWriteComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    draft = _require_nonempty(draft_id, field="draft_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    require_write = (
        True if require_both_with_write is None else require_both_with_write
    )
    if not isinstance(require_write, bool):
        raise FloatingMultiSelectSourceTwinWriteComposeError(
            "require_both_with_write must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · pack_dispatched=false",
        "twin_written=false · draft_written=false · analysis_written=false",
        "merge_executed=false · remote_fetched=false · store_mutated=false",
    ]

    try:
        multi_twin = compose_floating_multi_select_source_attach_quality_twin(
            session_id=session,
            parent_asset_id=parent,
            members=members,
            selected_instance_ids=selected_instance_ids,
            pack_mode=pack_mode,
            cohesive_prompt=cohesive_prompt,
            operator_ack=operator_ack,
            requested_families=requested_families,
            sources=sources,
            quality_overall=quality_overall,
            would_exceed=would_exceed,
            extra_context=extra_context,
            analysis_kind=analysis_kind,
            extra_findings=extra_findings,
            citations=citations,
            derive_citations_from_sources=derive_citations_from_sources,
            quality_floor=quality_floor,
            operator_override=operator_override,
            require_both=require_both,
            existing_twin_asset_id=existing_twin_asset_id,
            analysis_excerpt=analysis_excerpt,
            mark_for_prompt_context=mark_for_prompt_context,
            twin_findings=twin_findings,
            require_both_with_twin=require_both_with_twin,
        )
    except FloatingMultiSelectSourceAttachQualityTwinComposeError as e:
        raise FloatingMultiSelectSourceTwinWriteComposeError(str(e)) from e
    notes.extend(f"[multi_twin] {n}" for n in multi_twin.notes)

    if twin_slices is not None and chase_slots is not None:
        if not isinstance(twin_slices, list) or not isinstance(chase_slots, list):
            raise FloatingMultiSelectSourceTwinWriteComposeError(
                "twin_slices and chase_slots must be arrays when set"
            )
        slices = [s for s in twin_slices if isinstance(s, dict)]
        slots = [s for s in chase_slots if isinstance(s, dict)]
        notes.append("twin_slices/chase_slots caller-supplied")
    else:
        d_slices, d_slots = _derive_slices_and_slots(
            parent,
            members=members,
            selected_instance_ids=selected_instance_ids,
            sources=sources,
            cohesive_prompt=cohesive_prompt,
        )
        if twin_slices is not None:
            if not isinstance(twin_slices, list):
                raise FloatingMultiSelectSourceTwinWriteComposeError(
                    "twin_slices must be an array when set"
                )
            slices = [s for s in twin_slices if isinstance(s, dict)]
        else:
            slices = d_slices
        if chase_slots is not None:
            if not isinstance(chase_slots, list):
                raise FloatingMultiSelectSourceTwinWriteComposeError(
                    "chase_slots must be an array when set"
                )
            slots = [s for s in chase_slots if isinstance(s, dict)]
        else:
            slots = d_slots
        notes.append(
            f"derived twin_slices={len(slices)} slots={len(slots)} "
            "from multi-select+sources"
        )

    while len(slots) < 2:
        i = len(slots)
        slots.append(
            {
                "slot_id": f"ms-pad-{i}",
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

    if slices:
        s0 = slices[0]
        insights = s0.get("insights") if isinstance(s0.get("insights"), list) else []
        questions = (
            s0.get("questions") if isinstance(s0.get("questions"), list) else []
        )
        if len(insights) == 0 and len(questions) == 0:
            slices = [{**s0, "questions": [f"Open: {parent}"]}, *slices[1:]]
            notes.append("twin_slices padded with placeholder question")

    kind = "draft_analysis" if analysis_kind is None else analysis_kind
    if kind not in ("draft_analysis", "full_analysis"):
        raise FloatingMultiSelectSourceTwinWriteComposeError(
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

    write_extra = (
        extra_write_findings if extra_write_findings is not None else extra_findings
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
            extra_findings=write_extra,
            require_both=True,
        )
    except WriteModeTwinCollectiveAnalysisComposeError as e:
        raise FloatingMultiSelectSourceTwinWriteComposeError(str(e)) from e
    notes.extend(f"[write_pack] {n}" for n in write_pack.notes)

    if require_write:
        pack_ready = (
            multi_twin.pack_ready is True
            and write_pack.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            multi_twin.pack_ready is True or write_pack.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — multi-select+twin + write pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — multi_twin, write pack, or operator_ack gate open"
        )

    if (
        multi_twin.live_dispatched is not False
        or multi_twin.twin_written is not False
        or multi_twin.remote_fetched is not False
        or write_pack.draft_written is not False
        or write_pack.analysis_written is not False
        or write_pack.merge_executed is not False
        or write_pack.live_dispatched is not False
    ):
        raise FloatingMultiSelectSourceTwinWriteComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "twin_written=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "remote_fetched=false",
            "store_mutated=false",
        )
    )

    return FloatingMultiSelectSourceTwinWriteCompose(
        session_id=session,
        draft_id=draft,
        parent_asset_id=parent,
        multi_twin=multi_twin,
        write_pack=write_pack,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        twin_written=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        remote_fetched=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="floating_multi_select_source_twin_write_compose_advisory",
    )


def format_floating_multi_select_source_twin_write_summary(
    c: FloatingMultiSelectSourceTwinWriteCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"multi_twin_ready={c.multi_twin.pack_ready} · "
        f"write_ready={c.write_pack.pack_ready} · "
        f"live_dispatched=false · twin_written=false · draft_written=false · "
        f"analysis_written=false"
    )


__all__ = [
    "FloatingMultiSelectSourceTwinWriteCompose",
    "FloatingMultiSelectSourceTwinWriteComposeError",
    "compose_floating_multi_select_source_twin_write",
    "format_floating_multi_select_source_twin_write_summary",
]
