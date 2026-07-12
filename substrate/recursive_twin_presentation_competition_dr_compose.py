"""Recursive twin note-taker presentation over competition DR free-market pack.

twin_written / prompts_injected / merge_executed always False.
live_dispatch_authorized / purchase_executed / remote_fetched always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.competition_dr_marketplace_free_bench_mo_compose import (
    CompetitionDrMarketplaceFreeBenchMoCompose,
    CompetitionDrMarketplaceFreeBenchMoComposeError,
    compose_competition_dr_marketplace_free_bench_mo,
)
from substrate.recursive_twin_note_taker_compose import (
    RecursiveTwinNoteTakerCompose,
    RecursiveTwinNoteTakerComposeError,
    compose_recursive_twin_note_taker,
)

TwinPresentationViewMode = Literal[
    "side_panel", "overlay", "fullscreen_twin", "inline"
]

_VIEW_MODES: frozenset[str] = frozenset(
    ("side_panel", "overlay", "fullscreen_twin", "inline")
)


class RecursiveTwinPresentationCompetitionDrComposeError(ValueError):
    """Fail-closed validation for twin presentation + competition DR pack."""


@dataclass(frozen=True)
class TwinPresentationSurface:
    view_mode: str
    open_requested: bool
    merge_to_parent_preview: bool
    presented_insight_count: int
    presented_question_count: int
    presentation_sections: tuple[str, ...]
    presentation_ready: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "view_mode": self.view_mode,
            "open_requested": self.open_requested,
            "merge_to_parent_preview": self.merge_to_parent_preview,
            "presented_insight_count": self.presented_insight_count,
            "presented_question_count": self.presented_question_count,
            "presentation_sections": list(self.presentation_sections),
            "presentation_ready": self.presentation_ready,
        }


@dataclass(frozen=True)
class RecursiveTwinPresentationCompetitionDrCompose:
    parent_asset_id: str
    session_id: str
    title: str
    account_id: str
    week_id: str
    asset_id: str
    twin: RecursiveTwinNoteTakerCompose
    presentation: TwinPresentationSurface
    competition_pack: CompetitionDrMarketplaceFreeBenchMoCompose
    pack_ready: bool
    twin_written: bool
    prompts_injected: bool
    merge_executed: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    store_mutated: bool
    suite_rewritten: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_index_queried: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    draft_written: bool
    record_persisted: bool
    analysis_written: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "session_id": self.session_id,
            "title": self.title,
            "account_id": self.account_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "twin": self.twin.to_dict(),
            "presentation": self.presentation.to_dict(),
            "competition_pack": self.competition_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "twin_written": False,
            "prompts_injected": False,
            "merge_executed": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_index_queried": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "recursive_twin_presentation_competition_dr_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecursiveTwinPresentationCompetitionDrComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_string_list(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RecursiveTwinPresentationCompetitionDrComposeError(
            f"{field} must be an array when set"
        )
    out: list[str] = []
    for i, item in enumerate(value):
        out.append(_require_nonempty(item, field=f"{field}[{i}]"))
    return out


def compose_recursive_twin_presentation_competition_dr(
    *,
    twin: object,
    presentation: object,
    competition_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> RecursiveTwinPresentationCompetitionDrCompose:
    """Twin presentation + competition DR free-market pack. Never writes/merges."""
    if not isinstance(operator_ack, bool):
        raise RecursiveTwinPresentationCompetitionDrComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(twin, dict):
        raise RecursiveTwinPresentationCompetitionDrComposeError(
            "twin must be an object"
        )
    if not isinstance(presentation, dict):
        raise RecursiveTwinPresentationCompetitionDrComposeError(
            "presentation must be an object"
        )
    if not isinstance(competition_pack, dict):
        raise RecursiveTwinPresentationCompetitionDrComposeError(
            "competition_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise RecursiveTwinPresentationCompetitionDrComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "twin_written=false · prompts_injected=false · merge_executed=false",
        "live_dispatch_authorized=false · purchase_executed=false · "
        "remote_fetched=false",
        "production_router_verdict=REJECT",
    ]

    try:
        twin_c = compose_recursive_twin_note_taker(
            parent_asset_id=twin.get("parent_asset_id"),
            source_excerpt=twin.get("source_excerpt"),
            operator_ack=operator_ack,
            existing_twin_asset_id=twin.get("existing_twin_asset_id"),
            focus_questions=twin.get("focus_questions"),
        )
    except RecursiveTwinNoteTakerComposeError as e:
        raise RecursiveTwinPresentationCompetitionDrComposeError(str(e)) from e
    notes.extend(f"[twin] {n}" for n in twin_c.notes)

    view_mode = presentation.get("view_mode")
    if view_mode not in _VIEW_MODES:
        raise RecursiveTwinPresentationCompetitionDrComposeError(
            "presentation.view_mode must be "
            "side_panel|overlay|fullscreen_twin|inline"
        )
    open_requested = presentation.get("open_requested")
    if not isinstance(open_requested, bool):
        raise RecursiveTwinPresentationCompetitionDrComposeError(
            "presentation.open_requested must be an explicit boolean"
        )
    merge_preview = presentation.get("merge_to_parent_preview")
    if merge_preview is None:
        merge_preview = False
    if not isinstance(merge_preview, bool):
        raise RecursiveTwinPresentationCompetitionDrComposeError(
            "presentation.merge_to_parent_preview must be boolean when set"
        )

    presented_insights = _require_string_list(
        presentation.get("presented_insights"),
        field="presentation.presented_insights",
    )
    presented_questions = _require_string_list(
        presentation.get("presented_questions"),
        field="presentation.presented_questions",
    )

    presentation_sections: list[str] = list(twin_c.twin_scaffold_sections)
    presentation_sections.append(
        f'<section data-role="presentation-chrome" data-view-mode="{view_mode}" '
        f'data-open="{str(open_requested).lower()}" '
        f'data-merge-preview="{str(merge_preview).lower()}"></section>'
    )
    for insight in presented_insights:
        presentation_sections.append(
            f'<section data-role="presented-insight" '
            f'data-parent="{twin_c.parent_asset_id}">{insight}</section>'
        )
    for question in presented_questions:
        presentation_sections.append(
            f'<section data-role="presented-question" '
            f'data-parent="{twin_c.parent_asset_id}">{question}</section>'
        )

    presentation_ready = (
        operator_ack is True
        and twin_c.twin_propose_ready is True
        and open_requested is True
        and twin_c.twin_written is False
        and twin_c.prompts_injected is False
    )
    if presentation_ready:
        notes.append(
            f"presentation_ready=true · view_mode={view_mode} · "
            f"insights={len(presented_insights)} · "
            f"questions={len(presented_questions)}"
        )
    else:
        notes.append(
            "presentation_ready=false — operator_ack, twin_propose_ready, "
            "or open_requested gate open"
        )
    if merge_preview:
        notes.append(
            "merge_to_parent_preview=true — draft preview only; "
            "merge_executed=false"
        )

    try:
        comp = compose_competition_dr_marketplace_free_bench_mo(
            competition=competition_pack.get("competition"),
            free_pack=competition_pack.get("free_pack"),
            operator_ack=operator_ack,
            require_both=competition_pack.get("require_both"),
        )
    except CompetitionDrMarketplaceFreeBenchMoComposeError as e:
        raise RecursiveTwinPresentationCompetitionDrComposeError(str(e)) from e
    notes.extend(f"[competition_pack] {n}" for n in comp.notes)

    parent = _require_nonempty(twin_c.parent_asset_id, field="parent_asset_id")
    session = _require_nonempty(comp.session_id, field="session_id")
    title = _require_nonempty(comp.title, field="title")
    account = _require_nonempty(comp.account_id, field="account_id")
    week = _require_nonempty(comp.week_id, field="week_id")
    asset = _require_nonempty(comp.asset_id, field="asset_id")

    parent_aligned = comp.parent_asset_id == parent
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between twin and competition_pack — "
            "pack_ready blocked"
        )

    if require:
        pack_ready = (
            parent_aligned
            and presentation_ready is True
            and twin_c.twin_propose_ready is True
            and comp.pack_ready is True
            and twin_c.twin_written is False
            and twin_c.prompts_injected is False
            and twin_c.live_dispatch_authorized is False
            and comp.live_dispatch_authorized is False
            and comp.remote_fetched is False
            and comp.backlog_mutated is False
            and comp.purchase_executed is False
            and comp.hosted is False
            and comp.pdf_primary is False
            and comp.live_execution_authorized is False
            and comp.charge_executed is False
            and comp.suite_rewritten is False
            and comp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            parent_aligned
            and operator_ack is True
            and twin_c.twin_written is False
            and comp.purchase_executed is False
            and comp.hosted is False
            and comp.production_router_verdict == "REJECT"
            and comp.pdf_primary is False
            and (presentation_ready is True or comp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — twin presentation + competition DR free-market "
            "pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — twin, presentation, competition_pack, "
            "alignment, or operator_ack gate open"
        )

    if (
        twin_c.twin_written is not False
        or twin_c.prompts_injected is not False
        or twin_c.live_dispatch_authorized is not False
        or comp.live_dispatch_authorized is not False
        or comp.remote_fetched is not False
        or comp.backlog_mutated is not False
        or comp.purchase_executed is not False
        or comp.hosted is not False
        or comp.pdf_primary is not False
        or comp.live_execution_authorized is not False
        or comp.charge_executed is not False
        or comp.suite_rewritten is not False
        or comp.production_router_verdict != "REJECT"
    ):
        raise RecursiveTwinPresentationCompetitionDrComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "twin_written=false",
            "prompts_injected=false",
            "merge_executed=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_index_queried=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    surface = TwinPresentationSurface(
        view_mode=str(view_mode),
        open_requested=open_requested,
        merge_to_parent_preview=merge_preview,
        presented_insight_count=len(presented_insights),
        presented_question_count=len(presented_questions),
        presentation_sections=tuple(presentation_sections),
        presentation_ready=presentation_ready,
    )

    return RecursiveTwinPresentationCompetitionDrCompose(
        parent_asset_id=parent,
        session_id=session,
        title=title,
        account_id=account,
        week_id=week,
        asset_id=asset,
        twin=twin_c,
        presentation=surface,
        competition_pack=comp,
        pack_ready=pack_ready,
        twin_written=False,
        prompts_injected=False,
        merge_executed=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        store_mutated=False,
        suite_rewritten=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_index_queried=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "recursive_twin_presentation_competition_dr_compose_advisory"
        ),
    )


def format_recursive_twin_presentation_competition_dr_summary(
    c: RecursiveTwinPresentationCompetitionDrCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"presentation_ready={c.presentation.presentation_ready} · "
        f"view_mode={c.presentation.view_mode} · "
        f"twin_propose_ready={c.twin.twin_propose_ready} · "
        f"competition_ready={c.competition_pack.pack_ready} · "
        f"insights={c.presentation.presented_insight_count} · "
        f"questions={c.presentation.presented_question_count} · "
        f"verdict={c.production_router_verdict} · "
        f"twin_written=false · merge_executed=false · purchase_executed=false"
    )


__all__ = [
    "RecursiveTwinPresentationCompetitionDrCompose",
    "RecursiveTwinPresentationCompetitionDrComposeError",
    "TwinPresentationSurface",
    "compose_recursive_twin_presentation_competition_dr",
    "format_recursive_twin_presentation_competition_dr_summary",
]
