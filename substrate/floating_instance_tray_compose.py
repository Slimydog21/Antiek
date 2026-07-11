"""Floating deep-research instance tray compose (pure).

pack_dispatched, merge_executed, live_dispatched always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TrayAction = Literal[
    "none",
    "fullscreen_one",
    "collective_pack",
    "cohesive_prompt",
    "draft_merge_one",
    "full_merge_one",
]
VALID_ACTIONS = frozenset(
    (
        "none",
        "fullscreen_one",
        "collective_pack",
        "cohesive_prompt",
        "draft_merge_one",
        "full_merge_one",
    )
)
VALID_STATUS = frozenset(("proposed", "open", "completed", "closed"))


class FloatingInstanceTrayComposeError(ValueError):
    """Fail-closed validation for floating instance tray."""


@dataclass(frozen=True)
class FloatingInstanceTrayCompose:
    parent_asset_id: str
    member_count: int
    selected_count: int
    selected_instance_ids: tuple[str, ...]
    action: str
    tray_ready: bool
    pack_dispatched: bool
    merge_executed: bool
    live_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "member_count": self.member_count,
            "selected_count": self.selected_count,
            "selected_instance_ids": list(self.selected_instance_ids),
            "action": self.action,
            "tray_ready": self.tray_ready,
            "pack_dispatched": False,
            "merge_executed": False,
            "live_dispatched": False,
            "notes": list(self.notes),
            "authority": "floating_instance_tray_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingInstanceTrayComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_floating_instance_tray(
    *,
    parent_asset_id: object,
    members: object,
    selected_instance_ids: object,
    action: object,
    operator_ack: object,
) -> FloatingInstanceTrayCompose:
    """Compose multi-instance tray readiness. Never dispatches or merges."""
    if not isinstance(operator_ack, bool):
        raise FloatingInstanceTrayComposeError(
            "operator_ack must be an explicit boolean"
        )
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    if not isinstance(members, list) or len(members) == 0:
        raise FloatingInstanceTrayComposeError(
            "members must be a non-empty array"
        )
    if not isinstance(selected_instance_ids, list):
        raise FloatingInstanceTrayComposeError(
            "selected_instance_ids must be an array"
        )
    if action not in VALID_ACTIONS:
        raise FloatingInstanceTrayComposeError("action invalid")

    notes: list[str] = [
        "pack_dispatched=false — tray is pure selection/intent only",
        "merge_executed=false — no parent merge from tray",
        "live_dispatched=false — no provider dispatch",
    ]

    by_id: dict[str, dict[str, Any]] = {}
    for i, m in enumerate(members):
        if not isinstance(m, dict):
            raise FloatingInstanceTrayComposeError(
                f"members[{i}] must be an object"
            )
        mid = _require_nonempty(m.get("instance_id"), field=f"members[{i}].instance_id")
        p = _require_nonempty(
            m.get("parent_asset_id"), field=f"members[{i}].parent_asset_id"
        )
        if p != parent:
            raise FloatingInstanceTrayComposeError(
                "all members must share parent_asset_id"
            )
        st = m.get("status")
        if st not in VALID_STATUS:
            raise FloatingInstanceTrayComposeError(
                f"members[{i}].status invalid"
            )
        if m.get("live_dispatched") is not None and m.get("live_dispatched") is not False:
            raise FloatingInstanceTrayComposeError(
                f"members[{i}].live_dispatched must be false when set"
            )
        if m.get("merge_executed") is not None and m.get("merge_executed") is not False:
            raise FloatingInstanceTrayComposeError(
                f"members[{i}].merge_executed must be false when set"
            )
        if mid in by_id:
            raise FloatingInstanceTrayComposeError(
                f"duplicate instance_id: {mid}"
            )
        by_id[mid] = m

    selected: list[str] = []
    seen: set[str] = set()
    for i, raw in enumerate(selected_instance_ids):
        sid = _require_nonempty(raw, field=f"selected_instance_ids[{i}]")
        if sid not in by_id:
            raise FloatingInstanceTrayComposeError(
                f"selected_instance_ids[{i}] not in members"
            )
        if sid in seen:
            raise FloatingInstanceTrayComposeError(
                f"duplicate selected_instance_id: {sid}"
            )
        seen.add(sid)
        selected.append(sid)

    member_count = len(by_id)
    selected_count = len(selected)
    notes.append(
        f"member_count={member_count} · selected_count={selected_count}"
    )

    tray_ready = False
    if action == "none":
        notes.append("action=none — no tray action selected")
    elif action in ("fullscreen_one", "draft_merge_one", "full_merge_one"):
        if selected_count != 1:
            notes.append(f"action={action} requires exactly 1 selected instance")
        else:
            m = by_id[selected[0]]
            st = m["status"]
            if st == "closed":
                notes.append(f"action={action} blocked — instance closed")
            elif action == "full_merge_one":
                if st != "completed":
                    notes.append("full_merge_one requires completed instance")
                elif not operator_ack:
                    notes.append("full_merge_one requires operator_ack")
                else:
                    tray_ready = True
                    notes.append("tray_ready=true · full_merge_one intent only")
            elif action == "draft_merge_one":
                if st not in ("proposed", "open", "completed"):
                    notes.append(
                        "draft_merge_one requires proposed|open|completed"
                    )
                else:
                    tray_ready = True
                    notes.append("tray_ready=true · draft_merge_one intent only")
            else:
                tray_ready = True
                notes.append("tray_ready=true · fullscreen_one view intent")
    else:
        if selected_count < 2:
            notes.append(f"action={action} requires ≥2 selected instances")
        else:
            ok = True
            for sid in selected:
                m = by_id[sid]
                if m["status"] == "closed":
                    ok = False
                    notes.append(f"selected {sid} is closed")
                    break
            if ok and not operator_ack:
                notes.append(f"{action} requires operator_ack")
            elif ok:
                tray_ready = True
                notes.append(
                    f"tray_ready=true · {action} multi-select intent only (no dispatch)"
                )

    notes.extend(
        (
            "pack_dispatched=false",
            "merge_executed=false",
            "live_dispatched=false",
        )
    )

    return FloatingInstanceTrayCompose(
        parent_asset_id=parent,
        member_count=member_count,
        selected_count=selected_count,
        selected_instance_ids=tuple(selected),
        action=str(action),
        tray_ready=tray_ready,
        pack_dispatched=False,
        merge_executed=False,
        live_dispatched=False,
        notes=tuple(notes),
        authority="floating_instance_tray_compose_advisory",
    )


__all__ = [
    "FloatingInstanceTrayCompose",
    "FloatingInstanceTrayComposeError",
    "compose_floating_instance_tray",
]
