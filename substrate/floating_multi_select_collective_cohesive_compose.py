"""Floating multi-select → collective cohesive deep research pack (pure).

Multi-select floating/sub-agent instances as one cohesive unit prompt pack
with optional draft/full analysis intent.

live_dispatched, pack_dispatched, merge_executed, analysis_written always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.collective_deep_research_merge import (
    CollectiveAnalysisIntent,
    CollectiveAnalysisMergeError,
    propose_collective_analysis_merge,
)
from substrate.collective_floating_cohesive_prompt import (
    CohesiveUnitPromptIntent,
    CollectiveFloatingCohesivePromptError,
    build_collective_floating_cohesive_prompt,
)
from substrate.floating_instance_tray_compose import (
    FloatingInstanceTrayCompose,
    FloatingInstanceTrayComposeError,
    compose_floating_instance_tray,
)

PackMode = Literal[
    "cohesive_prompt", "collective_pack", "cohesive_plus_analysis"
]
AnalysisMergeKind = Literal["draft_analysis", "full_analysis"]
VALID_PACK_MODES = frozenset(
    ("cohesive_prompt", "collective_pack", "cohesive_plus_analysis")
)


class FloatingMultiSelectCollectiveCohesiveComposeError(ValueError):
    """Fail-closed validation for multi-select collective cohesive pack."""


@dataclass(frozen=True)
class FloatingMultiSelectCollectiveCohesiveCompose:
    session_id: str
    parent_asset_id: str
    pack_mode: PackMode
    tray: FloatingInstanceTrayCompose
    cohesive: CohesiveUnitPromptIntent | None
    analysis: CollectiveAnalysisIntent | None
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    analysis_written: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "pack_mode": self.pack_mode,
            "tray": self.tray.to_dict(),
            "cohesive": self.cohesive.to_dict() if self.cohesive else None,
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "analysis_written": False,
            "notes": list(self.notes),
            "authority": (
                "floating_multi_select_collective_cohesive_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingMultiSelectCollectiveCohesiveComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_floating_multi_select_collective_cohesive(
    *,
    session_id: object,
    parent_asset_id: object,
    members: object,
    selected_instance_ids: object,
    pack_mode: object,
    cohesive_prompt: object,
    operator_ack: object,
    extra_context: object | None = None,
    analysis_kind: object | None = None,
    extra_findings: object | None = None,
) -> FloatingMultiSelectCollectiveCohesiveCompose:
    """Multi-select floating → cohesive pack (+ optional analysis). Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise FloatingMultiSelectCollectiveCohesiveComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    if pack_mode not in VALID_PACK_MODES:
        raise FloatingMultiSelectCollectiveCohesiveComposeError(
            "pack_mode must be cohesive_prompt|collective_pack|cohesive_plus_analysis"
        )
    mode: PackMode = pack_mode  # type: ignore[assignment]
    if not isinstance(members, list) or len(members) < 2:
        raise FloatingMultiSelectCollectiveCohesiveComposeError(
            "members must be an array with at least 2 members"
        )
    if not isinstance(selected_instance_ids, list) or len(selected_instance_ids) < 2:
        raise FloatingMultiSelectCollectiveCohesiveComposeError(
            "selected_instance_ids must include at least 2 multi-selected instances"
        )

    notes: list[str] = [
        "live_dispatched=false — pure multi-select cohesive pack only",
        "pack_dispatched=false — no multi-agent pack execution",
        "merge_executed=false — no parent asset merge",
        "analysis_written=false — analysis intent only when requested",
    ]

    tray_action = (
        "collective_pack" if mode == "collective_pack" else "cohesive_prompt"
    )
    tray_members: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for i, m in enumerate(members):
        if not isinstance(m, dict):
            raise FloatingMultiSelectCollectiveCohesiveComposeError(
                f"members[{i}] must be an object"
            )
        mid = _require_nonempty(
            m.get("instance_id"), field=f"members[{i}].instance_id"
        )
        tray_members.append(
            {
                "instance_id": mid,
                "parent_asset_id": m.get("parent_asset_id"),
                "status": m.get("status"),
                "highlight": m.get("highlight"),
                "live_dispatched": m.get("live_dispatched"),
                "merge_executed": m.get("merge_executed"),
            }
        )
        by_id[mid] = m

    try:
        tray = compose_floating_instance_tray(
            parent_asset_id=parent,
            members=tray_members,
            selected_instance_ids=selected_instance_ids,
            action=tray_action,
            operator_ack=operator_ack,
        )
    except FloatingInstanceTrayComposeError as e:
        raise FloatingMultiSelectCollectiveCohesiveComposeError(str(e)) from e
    notes.extend(f"[tray] {n}" for n in tray.notes)

    selected_members: list[dict[str, Any]] = []
    for sid in tray.selected_instance_ids:
        m = by_id.get(sid)
        if m is None:
            raise FloatingMultiSelectCollectiveCohesiveComposeError(
                f"selected member missing: {sid}"
            )
        selected_members.append(m)

    cohesive: CohesiveUnitPromptIntent | None = None
    if mode in ("cohesive_prompt", "cohesive_plus_analysis"):
        for m in selected_members:
            if m.get("status") == "closed":
                raise FloatingMultiSelectCollectiveCohesiveComposeError(
                    "closed instances cannot join cohesive multi-select pack"
                )
        cohesive_members: list[dict[str, Any]] = []
        for m in selected_members:
            cohesive_members.append(
                {
                    "instance_id": m.get("instance_id"),
                    "parent_asset_id": m.get("parent_asset_id"),
                    "status": m.get("status"),
                    "highlight": m.get("highlight"),
                    "prior_prompt": m.get("prior_prompt"),
                    "context": m.get("context"),
                }
            )
        try:
            cohesive = build_collective_floating_cohesive_prompt(
                cohesive_members,
                cohesive_prompt=cohesive_prompt,
                operator_ack=operator_ack,
                extra_context=extra_context,
            )
        except CollectiveFloatingCohesivePromptError as e:
            raise FloatingMultiSelectCollectiveCohesiveComposeError(str(e)) from e
        notes.extend(f"[cohesive] {n}" for n in cohesive.notes)
    else:
        _require_nonempty(cohesive_prompt, field="cohesive_prompt")
        notes.append(
            "pack_mode=collective_pack — tray multi-select pack intent; "
            "cohesive prompt scaffold held for operator"
        )

    analysis: CollectiveAnalysisIntent | None = None
    analysis_path_ready = True
    if mode == "cohesive_plus_analysis":
        if analysis_kind not in ("draft_analysis", "full_analysis"):
            raise FloatingMultiSelectCollectiveCohesiveComposeError(
                "analysis_kind must be draft_analysis or full_analysis when "
                "pack_mode=cohesive_plus_analysis"
            )
        kind: AnalysisMergeKind = analysis_kind  # type: ignore[assignment]
        instances: list[dict[str, Any]] = []
        for m in selected_members:
            if m.get("status") == "closed":
                raise FloatingMultiSelectCollectiveCohesiveComposeError(
                    "closed instances cannot join analysis merge"
                )
            instances.append(
                {
                    "instance_id": m.get("instance_id"),
                    "parent_asset_id": m.get("parent_asset_id"),
                    "status": m.get("status"),
                    "highlight": m.get("highlight"),
                    "prompt": m.get("prior_prompt"),
                    "findings": m.get("findings"),
                }
            )
        all_completed = all(m.get("status") == "completed" for m in selected_members)
        if kind == "full_analysis" and not all_completed:
            analysis = None
            analysis_path_ready = False
            notes.append(
                "analysis_path_ready=false — full_analysis requires all selected completed"
            )
        else:
            try:
                analysis = propose_collective_analysis_merge(
                    instances,
                    kind=kind,
                    operator_ack=operator_ack,
                    extra_findings=extra_findings,
                )
            except CollectiveAnalysisMergeError as e:
                raise FloatingMultiSelectCollectiveCohesiveComposeError(
                    str(e)
                ) from e
            notes.extend(f"[analysis] {n}" for n in analysis.notes)
            if kind == "full_analysis":
                analysis_path_ready = operator_ack is True and all_completed
                if not operator_ack:
                    notes.append(
                        "analysis_path_ready=false — full_analysis requires operator_ack"
                    )
                else:
                    notes.append(
                        "analysis_path_ready=true — full analysis intent; "
                        "analysis_written=false"
                    )
            else:
                analysis_path_ready = len(selected_members) >= 2
                notes.append(
                    "analysis_path_ready=true — draft analysis intent; "
                    "analysis_written=false"
                    if analysis_path_ready
                    else "analysis_path_ready=false"
                )

    cohesive_ok = (
        True
        if mode == "collective_pack"
        else (cohesive is not None and cohesive.pack_ready is True)
    )
    pack_ready = (
        tray.tray_ready is True
        and cohesive_ok
        and analysis_path_ready
        and operator_ack is True
    )
    if pack_ready:
        notes.append(
            "pack_ready=true — multi-select cohesive pack intent ready; "
            "still no dispatch/write"
        )
    else:
        notes.append(
            "pack_ready=false — tray, cohesive, analysis, or operator_ack gate open"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "analysis_written=false",
        )
    )

    return FloatingMultiSelectCollectiveCohesiveCompose(
        session_id=session,
        parent_asset_id=parent,
        pack_mode=mode,
        tray=tray,
        cohesive=cohesive,
        analysis=analysis,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        analysis_written=False,
        notes=tuple(notes),
        authority="floating_multi_select_collective_cohesive_compose_advisory",
    )


def format_floating_multi_select_collective_cohesive_summary(
    c: FloatingMultiSelectCollectiveCohesiveCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · mode={c.pack_mode} · "
        f"selected={c.tray.selected_count}/{c.tray.member_count} · "
        f"live_dispatched=false · pack_dispatched=false · "
        f"merge_executed=false · analysis_written=false"
    )


__all__ = [
    "FloatingMultiSelectCollectiveCohesiveCompose",
    "FloatingMultiSelectCollectiveCohesiveComposeError",
    "compose_floating_multi_select_collective_cohesive",
    "format_floating_multi_select_collective_cohesive_summary",
]
