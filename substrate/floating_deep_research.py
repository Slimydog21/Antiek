"""Floating deep research instances (pure, fail-closed).

Operator vision: spawn a deep-research window from a reading/research
highlight; float it, open fullscreen, draft-merge into parent, fully merge
(with ack), or select multiple instances into a collective pack.

This module never:
* dispatches live providers
* mutates parent assets
* invents merge completion

live_dispatched, merge_executed, and pack_dispatched are always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ViewMode = Literal["floating", "fullscreen", "merged_draft", "merged_full", "collective"]
Status = Literal["proposed", "open", "completed", "closed"]

MAX_ID = 256
MAX_HIGHLIGHT = 8000
MAX_PROMPT = 4000


class FloatingDeepResearchError(ValueError):
    """Fail-closed validation for floating deep research."""


@dataclass(frozen=True)
class FloatingDeepResearchInstance:
    instance_id: str
    parent_asset_id: str
    highlight: str
    prompt: str
    view_mode: ViewMode
    status: Status
    live_dispatched: bool
    merge_executed: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "parent_asset_id": self.parent_asset_id,
            "highlight": self.highlight,
            "prompt": self.prompt,
            "view_mode": self.view_mode,
            "status": self.status,
            "live_dispatched": False,
            "merge_executed": False,
            "notes": list(self.notes),
            "authority": "operator_spawn_only",
        }


@dataclass(frozen=True)
class MergeIntent:
    kind: Literal["draft_merge", "full_merge"]
    instance_id: str
    parent_asset_id: str
    merge_executed: bool
    operator_ack: bool
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "instance_id": self.instance_id,
            "parent_asset_id": self.parent_asset_id,
            "merge_executed": False,
            "operator_ack": self.operator_ack,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class CollectivePackIntent:
    kind: Literal["collective_pack"]
    parent_asset_id: str
    instance_ids: tuple[str, ...]
    pack_dispatched: bool
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "collective_pack",
            "parent_asset_id": self.parent_asset_id,
            "instance_ids": list(self.instance_ids),
            "pack_dispatched": False,
            "notes": list(self.notes),
        }


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise FloatingDeepResearchError(f"{field} must be an explicit boolean")
    return value


def _require_nonempty(value: object, *, field: str, max_len: int) -> str:
    if not isinstance(value, str):
        raise FloatingDeepResearchError(f"{field} must be a string")
    text = value.strip()
    if not text:
        raise FloatingDeepResearchError(f"{field} must be non-empty")
    if len(text) > max_len:
        raise FloatingDeepResearchError(f"{field} exceeds {max_len} chars")
    return text


def _instance_id(parent: str, highlight: str) -> str:
    base = f"{parent}:{highlight[:48]}"
    h = 0
    for ch in base:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return f"fdr_{h:x}_{parent[:12]}"


def spawn_floating_from_highlight(
    *,
    parent_asset_id: object,
    highlight: object,
    gated: object,
    prompt: object | None = None,
    view_mode: object = "floating",
) -> FloatingDeepResearchInstance:
    """Spawn a pure client/server instance. Never live-dispatches."""
    if _require_bool(gated, field="gated") is True:
        raise FloatingDeepResearchError(
            "gated/withheld highlight cannot spawn floating deep research"
        )
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id", max_len=MAX_ID)
    hl = _require_nonempty(highlight, field="highlight", max_len=MAX_HIGHLIGHT)
    if prompt is None or (isinstance(prompt, str) and not prompt.strip()):
        prompt_s = f"Deep research on highlight from {parent}"
    else:
        prompt_s = _require_nonempty(prompt, field="prompt", max_len=MAX_PROMPT)
    if not isinstance(view_mode, str):
        raise FloatingDeepResearchError("view_mode must be a string")
    vm = view_mode.strip()
    if vm in ("merged_draft", "merged_full"):
        raise FloatingDeepResearchError(
            "spawn cannot start already-merged; use propose_draft_merge/propose_full_merge"
        )
    if vm == "collective":
        raise FloatingDeepResearchError(
            "spawn cannot start as collective; use propose_collective_pack"
        )
    if vm not in ("floating", "fullscreen"):
        raise FloatingDeepResearchError("view_mode invalid for spawn")

    notes = (
        "spawned from highlight — pure instance (no live dispatch)",
        "live_dispatched=false",
        "merge_executed=false",
    )
    return FloatingDeepResearchInstance(
        instance_id=_instance_id(parent, hl),
        parent_asset_id=parent,
        highlight=hl,
        prompt=prompt_s,
        view_mode=vm,  # type: ignore[arg-type]
        status="proposed",
        live_dispatched=False,
        merge_executed=False,
        notes=notes,
        authority="operator_spawn_only",
    )


def set_floating_view_mode(
    instance: FloatingDeepResearchInstance,
    view_mode: object,
) -> FloatingDeepResearchInstance:
    if not isinstance(instance, FloatingDeepResearchInstance):
        raise FloatingDeepResearchError("instance must be FloatingDeepResearchInstance")
    if instance.live_dispatched is not False or instance.merge_executed is not False:
        raise FloatingDeepResearchError("honesty flags must remain false")
    if not isinstance(view_mode, str):
        raise FloatingDeepResearchError("view_mode must be a string")
    vm = view_mode.strip()
    if vm in ("merged_draft", "merged_full"):
        raise FloatingDeepResearchError(
            "use propose_draft_merge/propose_full_merge for merge modes"
        )
    if vm == "collective":
        raise FloatingDeepResearchError("use propose_collective_pack for collective mode")
    if vm not in ("floating", "fullscreen"):
        raise FloatingDeepResearchError("view_mode invalid")
    status: Status = "open" if instance.status == "proposed" else instance.status
    return FloatingDeepResearchInstance(
        instance_id=instance.instance_id,
        parent_asset_id=instance.parent_asset_id,
        highlight=instance.highlight,
        prompt=instance.prompt,
        view_mode=vm,  # type: ignore[arg-type]
        status=status,
        live_dispatched=False,
        merge_executed=False,
        notes=instance.notes + (f"view_mode → {vm}",),
        authority="operator_spawn_only",
    )


def mark_floating_completed(
    instance: FloatingDeepResearchInstance,
) -> FloatingDeepResearchInstance:
    if not isinstance(instance, FloatingDeepResearchInstance):
        raise FloatingDeepResearchError("instance must be FloatingDeepResearchInstance")
    if instance.live_dispatched is not False:
        raise FloatingDeepResearchError("live_dispatched must be false")
    return FloatingDeepResearchInstance(
        instance_id=instance.instance_id,
        parent_asset_id=instance.parent_asset_id,
        highlight=instance.highlight,
        prompt=instance.prompt,
        view_mode=instance.view_mode,
        status="completed",
        live_dispatched=False,
        merge_executed=False,
        notes=instance.notes
        + ("marked completed by operator (no automatic provider completion)",),
        authority="operator_spawn_only",
    )


def propose_draft_merge(instance: FloatingDeepResearchInstance) -> MergeIntent:
    if not isinstance(instance, FloatingDeepResearchInstance):
        raise FloatingDeepResearchError("instance must be FloatingDeepResearchInstance")
    if instance.live_dispatched is not False:
        raise FloatingDeepResearchError("live_dispatched must be false")
    if instance.status not in ("proposed", "open", "completed"):
        raise FloatingDeepResearchError(
            "draft merge requires proposed, open, or completed instance"
        )
    return MergeIntent(
        kind="draft_merge",
        instance_id=instance.instance_id,
        parent_asset_id=instance.parent_asset_id,
        merge_executed=False,
        operator_ack=False,
        notes=(
            "draft merge intent only — provisional combined document not written",
            "merge_executed=false",
        ),
    )


def propose_full_merge(
    instance: FloatingDeepResearchInstance,
    *,
    operator_ack: object,
) -> MergeIntent:
    if not isinstance(instance, FloatingDeepResearchInstance):
        raise FloatingDeepResearchError("instance must be FloatingDeepResearchInstance")
    if _require_bool(operator_ack, field="operator_ack") is not True:
        raise FloatingDeepResearchError(
            "full merge requires operator_ack=true (fail closed)"
        )
    if instance.live_dispatched is not False:
        raise FloatingDeepResearchError("live_dispatched must be false")
    if instance.status != "completed":
        raise FloatingDeepResearchError("full merge requires completed instance")
    return MergeIntent(
        kind="full_merge",
        instance_id=instance.instance_id,
        parent_asset_id=instance.parent_asset_id,
        merge_executed=False,
        operator_ack=True,
        notes=(
            "full merge intent only — parent asset not mutated in pure layer",
            "merge_executed=false",
        ),
    )


def propose_collective_pack(
    instances: list[FloatingDeepResearchInstance] | tuple[FloatingDeepResearchInstance, ...],
) -> CollectivePackIntent:
    if not isinstance(instances, (list, tuple)) or len(instances) < 2:
        raise FloatingDeepResearchError("collective pack requires at least 2 instances")
    parent = instances[0].parent_asset_id
    ids: list[str] = []
    for inst in instances:
        if not isinstance(inst, FloatingDeepResearchInstance):
            raise FloatingDeepResearchError(
                "each instance must be FloatingDeepResearchInstance"
            )
        if inst.live_dispatched is not False:
            raise FloatingDeepResearchError(
                "live_dispatched must be false for all instances"
            )
        if inst.parent_asset_id != parent:
            raise FloatingDeepResearchError(
                "collective pack requires same parent_asset_id"
            )
        if inst.status not in ("open", "completed", "proposed"):
            raise FloatingDeepResearchError(
                "collective pack requires proposed, open, or completed instances"
            )
        ids.append(inst.instance_id)
    seen: set[str] = set()
    unique: list[str] = []
    for i in ids:
        if i in seen:
            continue
        seen.add(i)
        unique.append(i)
    if len(unique) < 2:
        raise FloatingDeepResearchError(
            "collective pack requires at least 2 distinct instance_ids"
        )
    return CollectivePackIntent(
        kind="collective_pack",
        parent_asset_id=parent,
        instance_ids=tuple(unique),
        pack_dispatched=False,
        notes=(
            "collective pack intent only — no multi-agent dispatch",
            "pack_dispatched=false",
        ),
    )


__all__ = [
    "CollectivePackIntent",
    "FloatingDeepResearchError",
    "FloatingDeepResearchInstance",
    "MergeIntent",
    "mark_floating_completed",
    "propose_collective_pack",
    "propose_draft_merge",
    "propose_full_merge",
    "set_floating_view_mode",
    "spawn_floating_from_highlight",
]
