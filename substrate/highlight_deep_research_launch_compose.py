"""Highlight → deep research launch package (pure).

live_dispatched and merge_executed always False.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from substrate.floating_deep_research import (
    FloatingDeepResearchError,
    FloatingDeepResearchInstance,
    spawn_floating_from_highlight,
)

LaunchPreferredView = Literal["floating", "fullscreen"]
SourceFamilyHint = Literal["arxiv", "substack", "openalex", "web", "custom"]
VALID_FAMILIES = frozenset(
    ("arxiv", "substack", "openalex", "web", "custom")
)
_SECRETISH = re.compile(r"sk-|api[_-]?key|secret", re.I)


class HighlightDeepResearchLaunchComposeError(ValueError):
    """Fail-closed validation for highlight DR launch."""


@dataclass(frozen=True)
class HighlightDeepResearchLaunchCompose:
    instance: FloatingDeepResearchInstance
    preferred_view_mode: str
    selected_model_id: str | None
    source_families: tuple[str, ...]
    source_family_count: int
    budget_ready: bool
    would_exceed: bool | None
    launch_ready: bool
    live_dispatched: bool
    merge_executed: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance": self.instance.to_dict(),
            "preferred_view_mode": self.preferred_view_mode,
            "selected_model_id": self.selected_model_id,
            "source_families": list(self.source_families),
            "source_family_count": self.source_family_count,
            "budget_ready": self.budget_ready,
            "would_exceed": self.would_exceed,
            "launch_ready": self.launch_ready,
            "live_dispatched": False,
            "merge_executed": False,
            "notes": list(self.notes),
            "authority": "highlight_deep_research_launch_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HighlightDeepResearchLaunchComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_highlight_deep_research_launch(
    *,
    parent_asset_id: object,
    highlight: object,
    gated: object,
    would_exceed: object,
    operator_ack: object,
    prompt: object | None = None,
    preferred_view_mode: object | None = None,
    operator_override: object | None = None,
    selected_model_id: object | None = None,
    source_families: object | None = None,
) -> HighlightDeepResearchLaunchCompose:
    """Compose pure DR launch from highlight. Never live-dispatches."""
    if not isinstance(operator_ack, bool):
        raise HighlightDeepResearchLaunchComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(gated, bool):
        raise HighlightDeepResearchLaunchComposeError(
            "gated must be an explicit boolean from highlight provenance (fail closed)"
        )
    if would_exceed is not None and not isinstance(would_exceed, bool):
        raise HighlightDeepResearchLaunchComposeError(
            "would_exceed must be boolean or null"
        )
    override = False if operator_override is None else operator_override
    if not isinstance(override, bool):
        raise HighlightDeepResearchLaunchComposeError(
            "operator_override must be boolean when set"
        )

    view: LaunchPreferredView = "floating"
    if preferred_view_mode is not None:
        if preferred_view_mode not in ("floating", "fullscreen"):
            raise HighlightDeepResearchLaunchComposeError(
                "preferred_view_mode must be floating|fullscreen"
            )
        view = preferred_view_mode  # type: ignore[assignment]

    notes: list[str] = [
        "live_dispatched=false — launch package is pure intent only",
        "merge_executed=false — parent asset not mutated",
    ]

    try:
        instance = spawn_floating_from_highlight(
            parent_asset_id=parent_asset_id,
            highlight=highlight,
            gated=gated,
            prompt=prompt,
            view_mode=view,
        )
    except FloatingDeepResearchError as e:
        raise HighlightDeepResearchLaunchComposeError(str(e)) from e

    notes.append(
        f"spawned instance_id={instance.instance_id} · view_mode={instance.view_mode}"
    )
    notes.append("live_dispatched=false on instance")

    model_id: str | None = None
    if selected_model_id is not None:
        model_id = _require_nonempty(
            selected_model_id, field="selected_model_id"
        )
        if len(model_id) > 128 or _SECRETISH.search(model_id):
            raise HighlightDeepResearchLaunchComposeError(
                "selected_model_id must be a model id, not secret material"
            )
        notes.append(f"selected_model_id={model_id} (operator authority)")
    else:
        notes.append(
            "selected_model_id=null — operator may choose before live launch"
        )

    families: list[str] = []
    if source_families is not None:
        if not isinstance(source_families, list):
            raise HighlightDeepResearchLaunchComposeError(
                "source_families must be an array when set"
            )
        seen: set[str] = set()
        for i, f in enumerate(source_families):
            if f not in VALID_FAMILIES:
                raise HighlightDeepResearchLaunchComposeError(
                    f"source_families[{i}] must be arxiv|substack|openalex|web|custom"
                )
            if f in seen:
                raise HighlightDeepResearchLaunchComposeError(
                    f"duplicate source_family: {f}"
                )
            seen.add(str(f))
            families.append(str(f))
    notes.append(f"source_family_count={len(families)}")

    budget_ready = False
    if would_exceed is None:
        if override:
            budget_ready = True
            notes.append(
                "budget_ready=true via operator_override (would_exceed unknown)"
            )
        else:
            notes.append(
                "budget_ready=false — would_exceed unknown and no operator_override"
            )
    elif would_exceed is True:
        if override:
            budget_ready = True
            notes.append(
                "budget_ready=true via operator_override despite would_exceed=true"
            )
        else:
            notes.append("budget_ready=false — would_exceed=true")
    else:
        budget_ready = True
        notes.append("budget_ready=true — would_exceed=false")

    launch_ready = (
        operator_ack
        and budget_ready
        and instance.live_dispatched is False
        and instance.merge_executed is False
    )
    if not operator_ack:
        notes.append("launch_ready=false — operator_ack required")
    elif not budget_ready:
        notes.append("launch_ready=false — budget gate closed")
    else:
        notes.append(
            "launch_ready=true — pure package ready; still live_dispatched=false"
        )
    notes.extend(("live_dispatched=false", "merge_executed=false"))

    return HighlightDeepResearchLaunchCompose(
        instance=instance,
        preferred_view_mode=view,
        selected_model_id=model_id,
        source_families=tuple(families),
        source_family_count=len(families),
        budget_ready=budget_ready,
        would_exceed=would_exceed if isinstance(would_exceed, bool) or would_exceed is None else None,
        launch_ready=launch_ready,
        live_dispatched=False,
        merge_executed=False,
        notes=tuple(notes),
        authority="highlight_deep_research_launch_compose_advisory",
    )


__all__ = [
    "HighlightDeepResearchLaunchCompose",
    "HighlightDeepResearchLaunchComposeError",
    "compose_highlight_deep_research_launch",
]
