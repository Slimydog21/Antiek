"""Reading highlight → float DR → tray merge pack compose (pure).

Operator vision: from a reading highlight, spin floating deep research;
select among floating instances for fullscreen or draft/full merge into
the reading asset — one pure end-to-end pack without live dispatch.

live_dispatched always False.
merge_executed always False.
pack_dispatched always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.floating_instance_tray_compose import (
    FloatingInstanceTrayCompose,
    FloatingInstanceTrayComposeError,
    compose_floating_instance_tray,
)
from substrate.highlight_deep_research_launch_compose import (
    HighlightDeepResearchLaunchCompose,
    HighlightDeepResearchLaunchComposeError,
    compose_highlight_deep_research_launch,
)

ReadingSurfaceAction = Literal[
    "spawn_only",
    "spawn_and_fullscreen",
    "spawn_and_draft_merge",
    "spawn_and_full_merge",
    "tray_collective",
    "tray_cohesive",
]
VALID_SURFACE_ACTIONS = frozenset(
    (
        "spawn_only",
        "spawn_and_fullscreen",
        "spawn_and_draft_merge",
        "spawn_and_full_merge",
        "tray_collective",
        "tray_cohesive",
    )
)

_SURFACE_TO_TRAY: dict[str, str | None] = {
    "spawn_only": None,
    "spawn_and_fullscreen": "fullscreen_one",
    "spawn_and_draft_merge": "draft_merge_one",
    "spawn_and_full_merge": "full_merge_one",
    "tray_collective": "collective_pack",
    "tray_cohesive": "cohesive_prompt",
}


class ReadingHighlightFloatMergeTrayComposeError(ValueError):
    """Fail-closed validation for reading surface pack compose."""


@dataclass(frozen=True)
class ReadingHighlightFloatMergeTrayCompose:
    launch: HighlightDeepResearchLaunchCompose
    tray: FloatingInstanceTrayCompose | None
    surface_action: str
    surface_ready: bool
    live_dispatched: bool
    merge_executed: bool
    pack_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "launch": self.launch.to_dict(),
            "tray": self.tray.to_dict() if self.tray is not None else None,
            "surface_action": self.surface_action,
            "surface_ready": self.surface_ready,
            "live_dispatched": False,
            "merge_executed": False,
            "pack_dispatched": False,
            "notes": list(self.notes),
            "authority": "reading_highlight_float_merge_tray_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReadingHighlightFloatMergeTrayComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_reading_highlight_float_merge_tray(
    *,
    parent_asset_id: object,
    highlight: object,
    gated: object,
    would_exceed: object,
    surface_action: object,
    operator_ack: object,
    prompt: object | None = None,
    preferred_view_mode: object | None = None,
    operator_override: object | None = None,
    selected_model_id: object | None = None,
    source_families: object | None = None,
    existing_members: object | None = None,
    selected_instance_ids: object | None = None,
) -> ReadingHighlightFloatMergeTrayCompose:
    """Compose reading-surface highlight→float→tray/merge pack.

    Never live-dispatches; never merges into parent.
    """
    if not isinstance(operator_ack, bool):
        raise ReadingHighlightFloatMergeTrayComposeError(
            "operator_ack must be an explicit boolean"
        )
    if surface_action not in VALID_SURFACE_ACTIONS:
        raise ReadingHighlightFloatMergeTrayComposeError(
            "surface_action invalid"
        )

    notes: list[str] = [
        "live_dispatched=false — reading surface pack is pure intent only",
        "merge_executed=false — parent reading asset not mutated",
        "pack_dispatched=false — collective/cohesive never dispatch from pure layer",
    ]

    try:
        launch = compose_highlight_deep_research_launch(
            parent_asset_id=parent_asset_id,
            highlight=highlight,
            gated=gated,
            would_exceed=would_exceed,
            operator_ack=operator_ack,
            prompt=prompt,
            preferred_view_mode=preferred_view_mode,
            operator_override=operator_override,
            selected_model_id=selected_model_id,
            source_families=source_families,
        )
    except HighlightDeepResearchLaunchComposeError as e:
        raise ReadingHighlightFloatMergeTrayComposeError(str(e)) from e
    notes.extend(launch.notes)

    existing: list[dict[str, Any]] = []
    if existing_members is not None:
        if not isinstance(existing_members, list):
            raise ReadingHighlightFloatMergeTrayComposeError(
                "existing_members must be an array when set"
            )
        for m in existing_members:
            if not isinstance(m, dict):
                raise ReadingHighlightFloatMergeTrayComposeError(
                    "existing_members entries must be objects"
                )
            existing.append(dict(m))

    inst = launch.instance
    spawned_member: dict[str, Any] = {
        "instance_id": inst.instance_id,
        "parent_asset_id": inst.parent_asset_id,
        "status": inst.status,
        "view_mode": inst.view_mode,
        "highlight": inst.highlight,
        "live_dispatched": False,
        "merge_executed": False,
    }
    members: list[dict[str, Any]] = [
        m
        for m in existing
        if m.get("instance_id") != spawned_member["instance_id"]
    ]
    members.append(spawned_member)

    tray_action = _SURFACE_TO_TRAY[str(surface_action)]
    tray: FloatingInstanceTrayCompose | None = None
    surface_ready = False

    if tray_action is None:
        surface_ready = launch.launch_ready
        notes.append(
            "surface_action=spawn_only · surface_ready=launch_ready"
            if surface_ready
            else "surface_action=spawn_only · surface_ready=false (launch not ready)"
        )
    else:
        if surface_action in (
            "spawn_and_fullscreen",
            "spawn_and_draft_merge",
            "spawn_and_full_merge",
        ):
            selected = [inst.instance_id]
        else:
            if selected_instance_ids is None or not isinstance(
                selected_instance_ids, list
            ):
                raise ReadingHighlightFloatMergeTrayComposeError(
                    "selected_instance_ids required for tray_collective|tray_cohesive"
                )
            selected = [
                _require_nonempty(sid, field=f"selected_instance_ids[{i}]")
                for i, sid in enumerate(selected_instance_ids)
            ]
            if inst.instance_id not in selected:
                selected = [*selected, inst.instance_id]
                notes.append(
                    "appended spawned instance_id to selection for tray multi action"
                )

        parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
        try:
            tray = compose_floating_instance_tray(
                parent_asset_id=parent,
                members=members,
                selected_instance_ids=selected,
                action=tray_action,
                operator_ack=operator_ack,
            )
        except FloatingInstanceTrayComposeError as e:
            raise ReadingHighlightFloatMergeTrayComposeError(str(e)) from e
        notes.extend(tray.notes)

        surface_ready = launch.launch_ready and tray.tray_ready
        if not launch.launch_ready:
            notes.append("surface_ready=false — launch package not ready")
        elif not tray.tray_ready:
            notes.append(
                "surface_ready=false — tray action not ready "
                "(e.g. full_merge needs completed)"
            )
        else:
            notes.append(
                f"surface_ready=true · surface_action={surface_action} "
                "(still pure intent)"
            )

    if launch.live_dispatched is not False or launch.merge_executed is not False:
        raise ReadingHighlightFloatMergeTrayComposeError(
            "invariant: launch honesty flags must remain false"
        )
    if tray is not None and (
        tray.live_dispatched is not False
        or tray.merge_executed is not False
        or tray.pack_dispatched is not False
    ):
        raise ReadingHighlightFloatMergeTrayComposeError(
            "invariant: tray honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "merge_executed=false",
            "pack_dispatched=false",
        )
    )

    return ReadingHighlightFloatMergeTrayCompose(
        launch=launch,
        tray=tray,
        surface_action=str(surface_action),
        surface_ready=surface_ready,
        live_dispatched=False,
        merge_executed=False,
        pack_dispatched=False,
        notes=tuple(notes),
        authority="reading_highlight_float_merge_tray_compose_advisory",
    )


def format_reading_highlight_float_merge_tray_summary(
    c: ReadingHighlightFloatMergeTrayCompose,
) -> str:
    tray_ready = c.tray.tray_ready if c.tray is not None else "n/a"
    return (
        f"surface_ready={c.surface_ready} · action={c.surface_action} · "
        f"launch_ready={c.launch.launch_ready} · "
        f"tray_ready={tray_ready} · "
        f"live_dispatched=false · merge_executed=false · pack_dispatched=false"
    )


__all__ = [
    "ReadingHighlightFloatMergeTrayCompose",
    "ReadingHighlightFloatMergeTrayComposeError",
    "compose_reading_highlight_float_merge_tray",
    "format_reading_highlight_float_merge_tray_summary",
]
