"""Floating deep research → open fullscreen compose (pure).

live_dispatched, merge_executed, pack_dispatched always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_deep_research import (
    FloatingDeepResearchError,
    FloatingDeepResearchInstance,
    spawn_floating_from_highlight,
)
from substrate.floating_instance_tray_compose import (
    FloatingInstanceTrayCompose,
    FloatingInstanceTrayComposeError,
    compose_floating_instance_tray,
)
from substrate.floating_research_view_mode_compose import (
    FloatingResearchViewModeCompose,
    FloatingResearchViewModeComposeError,
    compose_floating_research_view_mode,
)


class FloatingFullscreenOpenComposeError(ValueError):
    """Fail-closed validation for floating fullscreen open."""


@dataclass(frozen=True)
class FloatingFullscreenOpenCompose:
    session_id: str
    parent_asset_id: str
    instance: FloatingDeepResearchInstance
    tray: FloatingInstanceTrayCompose
    view_mode: FloatingResearchViewModeCompose
    fullscreen_ready: bool
    live_dispatched: bool
    merge_executed: bool
    pack_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "instance": self.instance.to_dict(),
            "tray": self.tray.to_dict(),
            "view_mode": self.view_mode.to_dict(),
            "fullscreen_ready": self.fullscreen_ready,
            "live_dispatched": False,
            "merge_executed": False,
            "pack_dispatched": False,
            "notes": list(self.notes),
            "authority": "floating_fullscreen_open_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingFullscreenOpenComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _coerce_instance(raw: object) -> FloatingDeepResearchInstance:
    if isinstance(raw, FloatingDeepResearchInstance):
        return raw
    if not isinstance(raw, dict):
        raise FloatingFullscreenOpenComposeError(
            "existing_instance must be an object when set"
        )
    notes_raw = raw.get("notes") or ()
    if isinstance(notes_raw, list):
        notes = tuple(str(n) for n in notes_raw)
    elif isinstance(notes_raw, tuple):
        notes = notes_raw
    else:
        notes = ()
    return FloatingDeepResearchInstance(
        instance_id=_require_nonempty(
            raw.get("instance_id"), field="existing_instance.instance_id"
        ),
        parent_asset_id=_require_nonempty(
            raw.get("parent_asset_id"),
            field="existing_instance.parent_asset_id",
        ),
        highlight=_require_nonempty(
            raw.get("highlight"), field="existing_instance.highlight"
        ),
        prompt=_require_nonempty(
            raw.get("prompt"), field="existing_instance.prompt"
        ),
        view_mode=raw.get("view_mode") or "floating",  # type: ignore[arg-type]
        status=raw.get("status") or "open",  # type: ignore[arg-type]
        live_dispatched=False,
        merge_executed=False,
        notes=notes,
        authority=str(raw.get("authority") or "operator_spawn_only"),
    )


def compose_floating_fullscreen_open(
    *,
    session_id: object,
    parent_asset_id: object,
    operator_ack: object,
    existing_instance: object | None = None,
    highlight: object | None = None,
    prompt: object | None = None,
    gated: object | None = None,
    tray_siblings: object | None = None,
) -> FloatingFullscreenOpenCompose:
    """Spawn/select float → tray fullscreen_one → view-mode fullscreen."""
    if not isinstance(operator_ack, bool):
        raise FloatingFullscreenOpenComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    notes: list[str] = [
        "live_dispatched=false — fullscreen is view-mode intent only",
        "merge_executed=false — parent asset not mutated",
        "pack_dispatched=false — no collective pack from this path",
    ]

    if existing_instance is not None:
        instance = _coerce_instance(existing_instance)
        if instance.parent_asset_id != parent:
            raise FloatingFullscreenOpenComposeError(
                "existing_instance.parent_asset_id must match parent"
            )
        if instance.live_dispatched is not False:
            raise FloatingFullscreenOpenComposeError(
                "existing_instance.live_dispatched must be false"
            )
        if instance.merge_executed is not False:
            raise FloatingFullscreenOpenComposeError(
                "existing_instance.merge_executed must be false"
            )
        if instance.status == "closed":
            raise FloatingFullscreenOpenComposeError(
                "cannot fullscreen a closed instance"
            )
        notes.append(
            f"using existing_instance={instance.instance_id} "
            f"status={instance.status}"
        )
    else:
        if not isinstance(gated, bool):
            raise FloatingFullscreenOpenComposeError(
                "gated must be an explicit boolean when spawning from highlight"
            )
        try:
            instance = spawn_floating_from_highlight(
                parent_asset_id=parent,
                highlight=highlight,
                gated=gated,
                prompt=prompt,
                view_mode="floating",
            )
        except FloatingDeepResearchError as e:
            raise FloatingFullscreenOpenComposeError(str(e)) from e
        notes.append(
            f"spawned floating instance={instance.instance_id} from highlight"
        )

    siblings: list[dict[str, Any]] = []
    if tray_siblings is not None:
        if not isinstance(tray_siblings, list):
            raise FloatingFullscreenOpenComposeError(
                "tray_siblings must be an array when set"
            )
        for s in tray_siblings:
            if isinstance(s, dict):
                siblings.append(dict(s))

    members: list[dict[str, Any]] = [
        {
            "instance_id": instance.instance_id,
            "parent_asset_id": instance.parent_asset_id,
            "status": instance.status,
            "highlight": instance.highlight,
            "view_mode": instance.view_mode,
            "live_dispatched": False,
            "merge_executed": False,
        }
    ]
    for s in siblings:
        if s.get("instance_id") != instance.instance_id:
            members.append(s)

    try:
        tray = compose_floating_instance_tray(
            parent_asset_id=parent,
            members=members,
            selected_instance_ids=[instance.instance_id],
            action="fullscreen_one",
            operator_ack=operator_ack,
        )
    except FloatingInstanceTrayComposeError as e:
        raise FloatingFullscreenOpenComposeError(str(e)) from e
    notes.extend(f"[tray] {n}" for n in tray.notes)

    try:
        view_mode = compose_floating_research_view_mode(
            instance=instance,
            action="fullscreen",
            operator_ack=operator_ack,
        )
    except FloatingResearchViewModeComposeError as e:
        raise FloatingFullscreenOpenComposeError(str(e)) from e
    notes.extend(f"[view] {n}" for n in view_mode.notes)

    fullscreen_ready = (
        tray.tray_ready is True
        and view_mode.action_applied is True
        and view_mode.view_mode == "fullscreen"
        and operator_ack is True
    )
    if fullscreen_ready:
        notes.append(
            "fullscreen_ready=true — open fullscreen intent ready; still pure"
        )
    else:
        notes.append(
            "fullscreen_ready=false — tray, view-mode, or operator_ack gate open"
        )

    if (
        tray.live_dispatched is not False
        or tray.merge_executed is not False
        or tray.pack_dispatched is not False
        or view_mode.live_dispatched is not False
        or view_mode.merge_executed is not False
        or view_mode.instance.live_dispatched is not False
        or view_mode.instance.merge_executed is not False
    ):
        raise FloatingFullscreenOpenComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "merge_executed=false",
            "pack_dispatched=false",
        )
    )

    return FloatingFullscreenOpenCompose(
        session_id=session,
        parent_asset_id=parent,
        instance=view_mode.instance,
        tray=tray,
        view_mode=view_mode,
        fullscreen_ready=fullscreen_ready,
        live_dispatched=False,
        merge_executed=False,
        pack_dispatched=False,
        notes=tuple(notes),
        authority="floating_fullscreen_open_compose_advisory",
    )


def format_floating_fullscreen_open_summary(
    c: FloatingFullscreenOpenCompose,
) -> str:
    return (
        f"fullscreen_ready={c.fullscreen_ready} · "
        f"view_mode={c.instance.view_mode} · "
        f"instance={c.instance.instance_id} · "
        f"live_dispatched=false · merge_executed=false · pack_dispatched=false"
    )


__all__ = [
    "FloatingFullscreenOpenCompose",
    "FloatingFullscreenOpenComposeError",
    "compose_floating_fullscreen_open",
    "format_floating_fullscreen_open_summary",
]
