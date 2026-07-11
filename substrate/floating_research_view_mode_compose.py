"""Floating research view-mode compose (pure).

Operator vision: from a floating deep-research instance, choose float,
fullscreen, draft-merge intent, or full-merge intent — without live
dispatch or executed merges.

Composes substrate.floating_deep_research helpers into one advisory snapshot.
live_dispatched and merge_executed are always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.floating_deep_research import (
    FloatingDeepResearchError,
    FloatingDeepResearchInstance,
    MergeIntent,
    mark_floating_completed,
    propose_draft_merge,
    propose_full_merge,
    set_floating_view_mode,
    spawn_floating_from_highlight,
)

ViewModeAction = Literal[
    "float",
    "fullscreen",
    "propose_draft_merge",
    "propose_full_merge",
]

VALID_ACTIONS: frozenset[str] = frozenset(
    ("float", "fullscreen", "propose_draft_merge", "propose_full_merge")
)


class FloatingResearchViewModeComposeError(ValueError):
    """Fail-closed validation for view-mode compose."""


@dataclass(frozen=True)
class FloatingViewModeCapabilities:
    can_float: bool
    can_fullscreen: bool
    can_draft_merge: bool
    can_full_merge: bool
    current_view_mode: str
    status: str
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_float": self.can_float,
            "can_fullscreen": self.can_fullscreen,
            "can_draft_merge": self.can_draft_merge,
            "can_full_merge": self.can_full_merge,
            "current_view_mode": self.current_view_mode,
            "status": self.status,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class FloatingResearchViewModeCompose:
    instance: FloatingDeepResearchInstance
    action: str
    view_mode: str
    merge_intent: MergeIntent | None
    capabilities: FloatingViewModeCapabilities
    action_applied: bool
    live_dispatched: bool
    merge_executed: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance": self.instance.to_dict(),
            "action": self.action,
            "view_mode": self.view_mode,
            "merge_intent": (
                self.merge_intent.to_dict() if self.merge_intent is not None else None
            ),
            "capabilities": self.capabilities.to_dict(),
            "action_applied": self.action_applied,
            "live_dispatched": False,
            "merge_executed": False,
            "notes": list(self.notes),
            "authority": "floating_research_view_mode_compose_advisory",
        }


def _require_instance(instance: object) -> FloatingDeepResearchInstance:
    if not isinstance(instance, FloatingDeepResearchInstance):
        raise FloatingResearchViewModeComposeError(
            "instance must be FloatingDeepResearchInstance"
        )
    if instance.live_dispatched is not False:
        raise FloatingResearchViewModeComposeError(
            "live_dispatched must be false (pure layer)"
        )
    if instance.merge_executed is not False:
        raise FloatingResearchViewModeComposeError(
            "merge_executed must be false (pure layer)"
        )
    return instance


def assess_floating_view_mode_capabilities(
    instance: FloatingDeepResearchInstance,
) -> FloatingViewModeCapabilities:
    """Assess valid pure view-mode actions. Never dispatches or merges."""
    inst = _require_instance(instance)
    notes: list[str] = [
        "capabilities are pure advisory — no live dispatch",
        "live_dispatched=false",
        "merge_executed=false",
    ]
    closed = inst.status == "closed"
    can_float = not closed
    can_fullscreen = not closed
    can_draft_merge = (not closed) and inst.status in (
        "proposed",
        "open",
        "completed",
    )
    can_full_merge = (not closed) and inst.status == "completed"
    if closed:
        notes.append("status=closed — no view-mode actions")
    else:
        notes.append(
            f"can_float={can_float} can_fullscreen={can_fullscreen} "
            f"can_draft_merge={can_draft_merge} can_full_merge={can_full_merge}"
        )
    return FloatingViewModeCapabilities(
        can_float=can_float,
        can_fullscreen=can_fullscreen,
        can_draft_merge=can_draft_merge,
        can_full_merge=can_full_merge,
        current_view_mode=inst.view_mode,
        status=inst.status,
        notes=tuple(notes),
    )


def compose_floating_research_view_mode(
    *,
    instance: FloatingDeepResearchInstance,
    action: object,
    operator_ack: object | None = None,
) -> FloatingResearchViewModeCompose:
    """Apply pure view-mode action. Never live-dispatches; never merges."""
    inst0 = _require_instance(instance)
    if not isinstance(action, str) or action not in VALID_ACTIONS:
        raise FloatingResearchViewModeComposeError(
            "action must be float|fullscreen|propose_draft_merge|propose_full_merge"
        )
    capabilities = assess_floating_view_mode_capabilities(inst0)
    notes: list[str] = [
        "live_dispatched=false — no provider dispatch from view-mode compose",
        "merge_executed=false — parent asset never mutated in pure layer",
        *capabilities.notes,
    ]

    inst = inst0
    merge_intent: MergeIntent | None = None
    action_applied = False

    try:
        if action == "float":
            if not capabilities.can_float:
                raise FloatingResearchViewModeComposeError(
                    "cannot float: instance closed or invalid"
                )
            inst = set_floating_view_mode(inst0, "floating")
            action_applied = True
            notes.append("action=float → view_mode=floating")
        elif action == "fullscreen":
            if not capabilities.can_fullscreen:
                raise FloatingResearchViewModeComposeError(
                    "cannot fullscreen: instance closed or invalid"
                )
            inst = set_floating_view_mode(inst0, "fullscreen")
            action_applied = True
            notes.append("action=fullscreen → view_mode=fullscreen")
        elif action == "propose_draft_merge":
            if not capabilities.can_draft_merge:
                raise FloatingResearchViewModeComposeError(
                    "cannot propose draft merge: requires proposed|open|completed"
                )
            merge_intent = propose_draft_merge(inst0)
            action_applied = True
            notes.append(
                "action=propose_draft_merge · merge_intent kind=draft_merge · "
                "merge_executed=false"
            )
        else:
            # propose_full_merge
            if not capabilities.can_full_merge:
                raise FloatingResearchViewModeComposeError(
                    "cannot propose full merge: requires completed status"
                )
            if not isinstance(operator_ack, bool):
                raise FloatingResearchViewModeComposeError(
                    "operator_ack must be an explicit boolean for propose_full_merge"
                )
            merge_intent = propose_full_merge(inst0, operator_ack=operator_ack)
            action_applied = True
            notes.append(
                "action=propose_full_merge · merge_intent kind=full_merge · "
                "merge_executed=false"
            )
    except FloatingDeepResearchError as e:
        raise FloatingResearchViewModeComposeError(str(e)) from e

    if inst.live_dispatched is not False or inst.merge_executed is not False:
        raise FloatingResearchViewModeComposeError(
            "invariant: honesty flags must remain false on instance"
        )
    if merge_intent is not None and merge_intent.merge_executed is not False:
        raise FloatingResearchViewModeComposeError(
            "invariant: merge_intent.merge_executed must be false"
        )

    notes.append("live_dispatched=false")
    notes.append("merge_executed=false")

    return FloatingResearchViewModeCompose(
        instance=inst,
        action=action,
        view_mode=inst.view_mode,
        merge_intent=merge_intent,
        capabilities=capabilities,
        action_applied=action_applied,
        live_dispatched=False,
        merge_executed=False,
        notes=tuple(notes),
        authority="floating_research_view_mode_compose_advisory",
    )


def format_floating_view_mode_compose_summary(
    c: FloatingResearchViewModeCompose,
) -> str:
    intent = c.merge_intent.kind if c.merge_intent is not None else "none"
    return (
        f"action={c.action} · view_mode={c.view_mode} · intent={intent} · "
        f"applied={c.action_applied} · live_dispatched=false · merge_executed=false"
    )


# Re-export spawn helpers for routes that accept raw highlight fields.
__all__ = [
    "FloatingResearchViewModeCompose",
    "FloatingResearchViewModeComposeError",
    "FloatingViewModeCapabilities",
    "VALID_ACTIONS",
    "assess_floating_view_mode_capabilities",
    "compose_floating_research_view_mode",
    "format_floating_view_mode_compose_summary",
    "mark_floating_completed",
    "spawn_floating_from_highlight",
]
