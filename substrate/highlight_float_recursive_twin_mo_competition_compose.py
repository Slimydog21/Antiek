"""Highlight float/twin feed → recursive twin MO competition (pure).

live_dispatched / merge_executed / pack_dispatched / twin_written always False.
live_execution_authorized / prompts_injected always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.reading_highlight_float_twin_feed_compose import (
    ReadingHighlightFloatTwinFeedCompose,
    ReadingHighlightFloatTwinFeedComposeError,
    compose_reading_highlight_float_twin_feed,
)
from substrate.recursive_twin_mo_competition_compose import (
    RecursiveTwinMoCompetitionCompose,
    RecursiveTwinMoCompetitionComposeError,
    compose_recursive_twin_mo_competition,
)


class HighlightFloatRecursiveTwinMoCompetitionComposeError(ValueError):
    """Fail-closed validation for highlight float → twin MO competition."""


@dataclass(frozen=True)
class HighlightFloatRecursiveTwinMoCompetitionCompose:
    session_id: str
    parent_asset_id: str
    highlight_surface: ReadingHighlightFloatTwinFeedCompose
    mo_competition: RecursiveTwinMoCompetitionCompose
    pack_ready: bool
    live_dispatched: bool
    merge_executed: bool
    pack_dispatched: bool
    twin_written: bool
    record_persisted: bool
    live_execution_authorized: bool
    prompts_injected: bool
    live_router_authorized: bool
    pdf_view_authorized: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "highlight_surface": self.highlight_surface.to_dict(),
            "mo_competition": self.mo_competition.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "merge_executed": False,
            "pack_dispatched": False,
            "twin_written": False,
            "record_persisted": False,
            "live_execution_authorized": False,
            "prompts_injected": False,
            "live_router_authorized": False,
            "pdf_view_authorized": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "highlight_float_recursive_twin_mo_competition_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HighlightFloatRecursiveTwinMoCompetitionComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_highlight_float_recursive_twin_mo_competition(
    *,
    highlight_surface: object,
    mo_competition: object,
    operator_ack: object,
    seed_excerpt_from_highlight: object | None = None,
    require_both: object | None = None,
) -> HighlightFloatRecursiveTwinMoCompetitionCompose:
    """Highlight float + recursive twin MO competition. Never live-dispatches."""
    if not isinstance(operator_ack, bool):
        raise HighlightFloatRecursiveTwinMoCompetitionComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(highlight_surface, dict):
        raise HighlightFloatRecursiveTwinMoCompetitionComposeError(
            "highlight_surface must be an object"
        )
    if not isinstance(mo_competition, dict):
        raise HighlightFloatRecursiveTwinMoCompetitionComposeError(
            "mo_competition must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise HighlightFloatRecursiveTwinMoCompetitionComposeError(
            "require_both must be boolean when set"
        )
    seed = (
        True
        if seed_excerpt_from_highlight is None
        else seed_excerpt_from_highlight
    )
    if not isinstance(seed, bool):
        raise HighlightFloatRecursiveTwinMoCompetitionComposeError(
            "seed_excerpt_from_highlight must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · merge_executed=false · pack_dispatched=false",
        "twin_written=false · record_persisted=false · prompts_injected=false",
        "live_execution_authorized=false · live_router_authorized=false",
        "pdf_view_authorized=false · store_mutated=false",
    ]

    try:
        surface = compose_reading_highlight_float_twin_feed(
            session_id=highlight_surface.get("session_id"),
            parent_asset_id=highlight_surface.get("parent_asset_id"),
            highlight=highlight_surface.get("highlight"),
            gated=highlight_surface.get("gated"),
            would_exceed=highlight_surface.get("would_exceed"),
            surface_action=highlight_surface.get("surface_action"),
            operator_ack=operator_ack,
            prompt=highlight_surface.get("prompt"),
            preferred_view_mode=highlight_surface.get("preferred_view_mode"),
            operator_override=highlight_surface.get("operator_override"),
            selected_model_id=highlight_surface.get("selected_model_id"),
            source_families=highlight_surface.get("source_families"),
            existing_members=highlight_surface.get("existing_members"),
            selected_instance_ids=highlight_surface.get(
                "selected_instance_ids"
            ),
            twin_findings=highlight_surface.get("twin_findings"),
            existing_twin_asset_id=highlight_surface.get(
                "existing_twin_asset_id"
            ),
            mark_for_prompt_context=highlight_surface.get(
                "mark_for_prompt_context"
            ),
            include_twin_feed=highlight_surface.get("include_twin_feed"),
        )
    except ReadingHighlightFloatTwinFeedComposeError as e:
        raise HighlightFloatRecursiveTwinMoCompetitionComposeError(
            str(e)
        ) from e
    notes.extend(f"[highlight_surface] {n}" for n in surface.notes)

    session = _require_nonempty(surface.session_id, field="session_id")
    parent = _require_nonempty(
        mo_competition.get("parent_asset_id")
        or highlight_surface.get("parent_asset_id"),
        field="parent_asset_id",
    )

    source_excerpt = mo_competition.get("source_excerpt")
    if seed and (source_excerpt is None or not str(source_excerpt).strip()):
        source_excerpt = f"highlight: {highlight_surface.get('highlight')}"
        notes.append("source_excerpt seeded from reading highlight")

    try:
        mo_pack = compose_recursive_twin_mo_competition(
            parent_asset_id=parent,
            mo=mo_competition.get("mo"),
            research=mo_competition.get("research"),
            operator_ack=operator_ack,
            require_both=mo_competition.get("require_both"),
            source_excerpt=source_excerpt,
            existing_twin_asset_id=mo_competition.get(
                "existing_twin_asset_id"
            ),
            focus_questions=mo_competition.get("focus_questions"),
            require_both_with_twin=mo_competition.get(
                "require_both_with_twin"
            ),
        )
    except RecursiveTwinMoCompetitionComposeError as e:
        raise HighlightFloatRecursiveTwinMoCompetitionComposeError(
            str(e)
        ) from e
    notes.extend(f"[mo_competition] {n}" for n in mo_pack.notes)

    if require:
        pack_ready = (
            surface.pack_ready is True
            and mo_pack.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            surface.pack_ready is True or mo_pack.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — highlight float + recursive twin MO competition ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — highlight_surface, mo_competition, or operator_ack gate open"
        )

    if (
        surface.live_dispatched is not False
        or surface.merge_executed is not False
        or surface.pack_dispatched is not False
        or surface.twin_written is not False
        or mo_pack.twin_written is not False
        or mo_pack.live_execution_authorized is not False
        or mo_pack.prompts_injected is not False
    ):
        raise HighlightFloatRecursiveTwinMoCompetitionComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "merge_executed=false",
            "pack_dispatched=false",
            "twin_written=false",
            "record_persisted=false",
            "live_execution_authorized=false",
            "prompts_injected=false",
            "live_router_authorized=false",
            "pdf_view_authorized=false",
            "store_mutated=false",
        )
    )

    return HighlightFloatRecursiveTwinMoCompetitionCompose(
        session_id=session,
        parent_asset_id=parent,
        highlight_surface=surface,
        mo_competition=mo_pack,
        pack_ready=pack_ready,
        live_dispatched=False,
        merge_executed=False,
        pack_dispatched=False,
        twin_written=False,
        record_persisted=False,
        live_execution_authorized=False,
        prompts_injected=False,
        live_router_authorized=False,
        pdf_view_authorized=False,
        store_mutated=False,
        notes=tuple(notes),
        authority=(
            "highlight_float_recursive_twin_mo_competition_compose_advisory"
        ),
    )


def format_highlight_float_recursive_twin_mo_competition_summary(
    c: HighlightFloatRecursiveTwinMoCompetitionCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"highlight_ready={c.highlight_surface.pack_ready} · "
        f"mo_twin_ready={c.mo_competition.pack_ready} · "
        f"live_dispatched=false · twin_written=false · "
        f"live_execution_authorized=false · prompts_injected=false"
    )


__all__ = [
    "HighlightFloatRecursiveTwinMoCompetitionCompose",
    "HighlightFloatRecursiveTwinMoCompetitionComposeError",
    "compose_highlight_float_recursive_twin_mo_competition",
    "format_highlight_float_recursive_twin_mo_competition_summary",
]
