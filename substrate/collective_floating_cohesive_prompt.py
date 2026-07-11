"""Collective floating deep research → cohesive unit prompt (pure).

Multi-select floating/sub-agent instances and prompt as one cohesive unit.
live_dispatched is always False. Context cards are caller-supplied only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

MemberStatus = Literal["proposed", "open", "completed", "closed"]


class CollectiveFloatingCohesivePromptError(ValueError):
    """Fail-closed validation for cohesive floating prompt packs."""


@dataclass(frozen=True)
class CohesiveUnitPromptIntent:
    parent_asset_id: str
    instance_ids: tuple[str, ...]
    cohesive_prompt: str
    context_cards: tuple[str, ...]
    member_count: int
    operator_ack: bool
    pack_ready: bool
    live_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "instance_ids": list(self.instance_ids),
            "cohesive_prompt": self.cohesive_prompt,
            "context_cards": list(self.context_cards),
            "member_count": self.member_count,
            "operator_ack": self.operator_ack,
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "notes": list(self.notes),
            "authority": "collective_floating_cohesive_prompt_advisory",
        }


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise CollectiveFloatingCohesivePromptError(
            f"{field} must be an explicit boolean"
        )
    return value


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CollectiveFloatingCohesivePromptError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def build_collective_floating_cohesive_prompt(
    members: object,
    *,
    cohesive_prompt: object,
    operator_ack: object,
    extra_context: object | None = None,
) -> CohesiveUnitPromptIntent:
    """Build cohesive-unit prompt pack. Never live-dispatches."""
    ack = _require_bool(operator_ack, field="operator_ack")
    prompt = _require_nonempty(cohesive_prompt, field="cohesive_prompt")
    if not isinstance(members, list) or len(members) < 2:
        raise CollectiveFloatingCohesivePromptError(
            "cohesive unit requires at least 2 members"
        )

    first = members[0]
    parent = _require_nonempty(
        first.get("parent_asset_id") if isinstance(first, dict) else None,
        field="members[0].parent_asset_id",
    )
    ids: list[str] = []
    context_cards: list[str] = []
    notes: list[str] = [
        "live_dispatched=false — cohesive pack intent only",
        "context cards are caller-supplied only (no invent)",
    ]

    for i, m in enumerate(members):
        if not isinstance(m, dict):
            raise CollectiveFloatingCohesivePromptError(
                f"members[{i}] must be an object"
            )
        iid = _require_nonempty(
            m.get("instance_id"), field=f"members[{i}].instance_id"
        )
        p = _require_nonempty(
            m.get("parent_asset_id"), field=f"members[{i}].parent_asset_id"
        )
        if p != parent:
            raise CollectiveFloatingCohesivePromptError(
                "cohesive unit requires same parent_asset_id"
            )
        status = m.get("status")
        if status not in ("proposed", "open", "completed"):
            raise CollectiveFloatingCohesivePromptError(
                f"members[{i}] status must be proposed|open|completed (not closed)"
            )
        ids.append(iid)

        highlight = m.get("highlight")
        if highlight is not None:
            if not isinstance(highlight, str) or not highlight.strip():
                raise CollectiveFloatingCohesivePromptError(
                    f"members[{i}].highlight must be non-empty string when set"
                )
            context_cards.append(f"[{iid} highlight] {highlight.strip()}")

        prior = m.get("prior_prompt")
        if prior is not None:
            if not isinstance(prior, str) or not prior.strip():
                raise CollectiveFloatingCohesivePromptError(
                    f"members[{i}].prior_prompt must be non-empty string when set"
                )
            context_cards.append(f"[{iid} prior_prompt] {prior.strip()}")

        ctx = m.get("context")
        if ctx is not None:
            if not isinstance(ctx, list):
                raise CollectiveFloatingCohesivePromptError(
                    f"members[{i}].context must be string[] when set"
                )
            for j, c in enumerate(ctx):
                if not isinstance(c, str) or not c.strip():
                    raise CollectiveFloatingCohesivePromptError(
                        f"members[{i}].context[{j}] must be non-empty string"
                    )
                context_cards.append(f"[{iid}] {c.strip()}")

    seen: set[str] = set()
    unique: list[str] = []
    for iid in ids:
        if iid in seen:
            continue
        seen.add(iid)
        unique.append(iid)
    if len(unique) < 2:
        raise CollectiveFloatingCohesivePromptError(
            "cohesive unit requires at least 2 distinct instance_ids"
        )

    if extra_context is not None:
        if not isinstance(extra_context, list):
            raise CollectiveFloatingCohesivePromptError(
                "extra_context must be string[] or null"
            )
        for j, c in enumerate(extra_context):
            if not isinstance(c, str) or not c.strip():
                raise CollectiveFloatingCohesivePromptError(
                    f"extra_context[{j}] must be non-empty string"
                )
            context_cards.append(c.strip())

    if not context_cards:
        notes.append(
            "no context cards supplied — prompt pack scaffold only (no invent content)"
        )
    else:
        notes.append(f"context_cards={len(context_cards)} caller-supplied only")

    pack_ready = ack is True
    if not pack_ready:
        notes.append(
            "pack_ready=false — operator_ack required before dispatch gate"
        )
    else:
        notes.append(
            "pack_ready=true — still live_dispatched=false (pure layer never dispatches)"
        )
    notes.append("live_dispatched=false")

    return CohesiveUnitPromptIntent(
        parent_asset_id=parent,
        instance_ids=tuple(unique),
        cohesive_prompt=prompt,
        context_cards=tuple(context_cards),
        member_count=len(unique),
        operator_ack=ack,
        pack_ready=pack_ready,
        live_dispatched=False,
        notes=tuple(notes),
        authority="collective_floating_cohesive_prompt_advisory",
    )


__all__ = [
    "CohesiveUnitPromptIntent",
    "CollectiveFloatingCohesivePromptError",
    "build_collective_floating_cohesive_prompt",
]
