"""Highlight / selection → deep-research spawn.

Spawning is **reservation-first**: we mint a stable ``spawn_id`` and
``investigation_id``, persist the reserved work unit, and return it.
Nothing is launched over the network here — a separate research runner
takes the reserved id later. That matches
living-note escalation (``question.escalated_to_research`` reserves, does
not launch).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from .store import EngagementStore

SpawnStatus = Literal["reserved", "running", "complete", "failed"]


@dataclass(frozen=True)
class HighlightSelection:
    """A user selection on an information asset (book, paper, research doc)."""

    asset_id: str
    selection_text: str
    region_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    page: int | None = None
    goal_hint: str | None = None


@dataclass(frozen=True)
class ResearchSpawn:
    spawn_id: str
    investigation_id: str
    parent_asset_id: str
    goal: str
    selection_text: str
    status: SpawnStatus
    model_id: str | None = None
    region_id: str | None = None
    output_text: str | None = None
    output_insights: tuple[str, ...] = ()
    output_questions: tuple[str, ...] = ()


def _stable_spawn_id(asset_id: str, selection_text: str, region_id: str | None) -> str:
    """Content-addressed when region_id present; otherwise random (new work)."""
    if region_id:
        raw = f"spawn:v1:{asset_id}:{region_id}:{selection_text.strip()}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"spn_{digest}"
    return f"spn_{uuid.uuid4().hex[:16]}"


def _investigation_id_for(spawn_id: str) -> str:
    return f"inv_{spawn_id.removeprefix('spn_')}"


def _goal_from_selection(sel: HighlightSelection) -> str:
    if sel.goal_hint and sel.goal_hint.strip():
        return sel.goal_hint.strip()
    excerpt = sel.selection_text.strip()
    if len(excerpt) > 280:
        excerpt = excerpt[:277] + "..."
    return f"Deep-research the highlighted passage: {excerpt}"


def spawn_from_highlight(
    selection: HighlightSelection,
    *,
    store: EngagementStore,
    model_id: str | None = None,
    force_new: bool = False,
) -> ResearchSpawn:
    """Reserve a deep-research work unit from a highlight/selection.

    Idempotent when ``region_id`` is set and ``force_new`` is False: re-selecting
    the same region returns the existing spawn without creating a duplicate.
    """
    if not selection.asset_id or not selection.asset_id.strip():
        raise ValueError("asset_id is required")
    if not selection.selection_text or not selection.selection_text.strip():
        raise ValueError("selection_text is required")

    if selection.region_id and not force_new:
        # Prefer existing spawn for this region on this asset.
        for existing in store.list_spawns(selection.asset_id):
            if existing.get("region_id") == selection.region_id:
                return _from_row(existing)

    spawn_id = _stable_spawn_id(
        selection.asset_id,
        selection.selection_text,
        None if force_new else selection.region_id,
    )
    if not force_new:
        prior = store.get_spawn(spawn_id)
        if prior is not None:
            return _from_row(prior)

    inv_id = _investigation_id_for(spawn_id)
    spawn = ResearchSpawn(
        spawn_id=spawn_id,
        investigation_id=inv_id,
        parent_asset_id=selection.asset_id.strip(),
        goal=_goal_from_selection(selection),
        selection_text=selection.selection_text.strip(),
        status="reserved",
        model_id=model_id,
        region_id=selection.region_id,
    )
    store.put_spawn(_to_row(spawn))
    return spawn


def complete_spawn(
    spawn_id: str,
    *,
    store: EngagementStore,
    output_text: str,
    insights: list[str] | tuple[str, ...] = (),
    questions: list[str] | tuple[str, ...] = (),
    status: SpawnStatus = "complete",
) -> ResearchSpawn:
    """Mark a spawn complete (or failed) with its research output.

    Does not auto-merge — the operator / UI chooses merge mode separately.
    """
    row = store.get_spawn(spawn_id)
    if row is None:
        raise KeyError(f"unknown spawn_id: {spawn_id}")
    if status not in ("complete", "failed", "running"):
        raise ValueError(f"invalid terminal/transition status: {status}")
    row = dict(row)
    row["status"] = status
    row["output_text"] = output_text
    row["output_insights"] = list(insights)
    row["output_questions"] = list(questions)
    store.put_spawn(row)
    return _from_row(row)


def get_spawn(spawn_id: str, *, store: EngagementStore) -> ResearchSpawn | None:
    row = store.get_spawn(spawn_id)
    return _from_row(row) if row else None


def list_spawns_for_asset(asset_id: str, *, store: EngagementStore) -> list[ResearchSpawn]:
    return [_from_row(r) for r in store.list_spawns(asset_id)]


def _to_row(spawn: ResearchSpawn) -> dict[str, Any]:
    return {
        "spawn_id": spawn.spawn_id,
        "investigation_id": spawn.investigation_id,
        "parent_asset_id": spawn.parent_asset_id,
        "goal": spawn.goal,
        "selection_text": spawn.selection_text,
        "status": spawn.status,
        "model_id": spawn.model_id,
        "region_id": spawn.region_id,
        "output_text": spawn.output_text,
        "output_insights": list(spawn.output_insights),
        "output_questions": list(spawn.output_questions),
    }


def _from_row(row: dict[str, Any]) -> ResearchSpawn:
    status = row["status"]
    if status not in ("reserved", "running", "complete", "failed"):
        raise ValueError(f"invalid spawn status: {status!r}")
    return ResearchSpawn(
        spawn_id=row["spawn_id"],
        investigation_id=row["investigation_id"],
        parent_asset_id=row["parent_asset_id"],
        goal=row["goal"],
        selection_text=row["selection_text"],
        status=status,
        model_id=row.get("model_id"),
        region_id=row.get("region_id"),
        output_text=row.get("output_text"),
        output_insights=tuple(row.get("output_insights") or ()),
        output_questions=tuple(row.get("output_questions") or ()),
    )
