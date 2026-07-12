"""Highlight float DR launch → twin intelligent search competition pack (pure).

live_dispatched / live_dispatch_authorized / remote_fetched always False.
remote_index_queried / merge_executed / twin_written always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.highlight_deep_research_launch_compose import (
    HighlightDeepResearchLaunchCompose,
    HighlightDeepResearchLaunchComposeError,
    compose_highlight_deep_research_launch,
)
from substrate.twin_search_competition_dr_nd_shadow_weekly_marketplace_compose import (
    TwinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose,
    TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError,
    compose_twin_search_competition_dr_nd_shadow_weekly_marketplace,
)


class HighlightFloatTwinSearchCompetitionComposeError(ValueError):
    """Fail-closed validation for highlight float + twin search competition."""


@dataclass(frozen=True)
class HighlightFloatTwinSearchCompetitionCompose:
    session_id: str
    parent_asset_id: str
    highlight_launch: HighlightDeepResearchLaunchCompose
    twin_search_pack: TwinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose
    pack_ready: bool
    live_dispatched: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    remote_index_queried: bool
    merge_executed: bool
    twin_written: bool
    production_router_verdict: str
    live_router_authorized: bool
    store_mutated: bool
    purchase_executed: bool
    hosted: bool
    backlog_mutated: bool
    pack_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "highlight_launch": self.highlight_launch.to_dict(),
            "twin_search_pack": self.twin_search_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "remote_index_queried": False,
            "merge_executed": False,
            "twin_written": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "store_mutated": False,
            "purchase_executed": False,
            "hosted": False,
            "backlog_mutated": False,
            "pack_dispatched": False,
            "notes": list(self.notes),
            "authority": "highlight_float_twin_search_competition_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HighlightFloatTwinSearchCompetitionComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_highlight_float_twin_search_competition(
    *,
    highlight: object,
    twin_search_pack: object,
    operator_ack: object,
    seed_search_from_highlight: object | None = None,
    require_both: object | None = None,
) -> HighlightFloatTwinSearchCompetitionCompose:
    """Highlight float DR + twin search competition. Never dispatches/indexes."""
    if not isinstance(operator_ack, bool):
        raise HighlightFloatTwinSearchCompetitionComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(highlight, dict):
        raise HighlightFloatTwinSearchCompetitionComposeError(
            "highlight must be an object"
        )
    if not isinstance(twin_search_pack, dict):
        raise HighlightFloatTwinSearchCompetitionComposeError(
            "twin_search_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise HighlightFloatTwinSearchCompetitionComposeError(
            "require_both must be boolean when set"
        )
    seed = True if seed_search_from_highlight is None else seed_search_from_highlight
    if not isinstance(seed, bool):
        raise HighlightFloatTwinSearchCompetitionComposeError(
            "seed_search_from_highlight must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · live_dispatch_authorized=false · remote_fetched=false",
        "remote_index_queried=false · merge_executed=false · twin_written=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
    ]

    try:
        highlight_launch = compose_highlight_deep_research_launch(
            parent_asset_id=highlight.get("parent_asset_id"),
            highlight=highlight.get("highlight"),
            gated=highlight.get("gated"),
            would_exceed=highlight.get("would_exceed"),
            operator_ack=operator_ack,
            prompt=highlight.get("prompt"),
            preferred_view_mode=highlight.get("preferred_view_mode"),
            operator_override=highlight.get("operator_override"),
            selected_model_id=highlight.get("selected_model_id"),
            source_families=highlight.get("source_families"),
        )
    except HighlightDeepResearchLaunchComposeError as e:
        raise HighlightFloatTwinSearchCompetitionComposeError(str(e)) from e
    notes.extend(f"[highlight_launch] {n}" for n in highlight_launch.notes)

    raw_q = twin_search_pack.get("search_query")
    search_query = (
        str(raw_q).strip() if raw_q is not None and str(raw_q).strip() else ""
    )
    if not search_query and seed:
        search_query = _require_nonempty(
            highlight.get("highlight"), field="highlight"
        )
        notes.append("search_query seeded from highlight text")
    if not search_query:
        raise HighlightFloatTwinSearchCompetitionComposeError(
            "search_query must be non-empty (or enable seed_search_from_highlight)"
        )

    try:
        twin_pack = compose_twin_search_competition_dr_nd_shadow_weekly_marketplace(
            competition_pack=twin_search_pack.get("competition_pack"),
            search_query=search_query,
            operator_ack=operator_ack,
            extra_twin_records=twin_search_pack.get("extra_twin_records"),
            search_limit=twin_search_pack.get("search_limit"),
            min_parents_for_merge=twin_search_pack.get("min_parents_for_merge"),
            search_pack_id=twin_search_pack.get("search_pack_id"),
            require_both=twin_search_pack.get("require_both"),
        )
    except TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError as e:
        raise HighlightFloatTwinSearchCompetitionComposeError(str(e)) from e
    notes.extend(f"[twin_search_pack] {n}" for n in twin_pack.notes)

    parent = _require_nonempty(
        highlight_launch.instance.parent_asset_id, field="parent_asset_id"
    )
    session = _require_nonempty(twin_pack.session_id, field="session_id")

    parent_aligned = twin_pack.parent_asset_id == parent
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between highlight and twin_search_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            parent_aligned
            and highlight_launch.launch_ready is True
            and twin_pack.pack_ready is True
            and twin_pack.production_router_verdict == "REJECT"
            and highlight_launch.live_dispatched is False
            and twin_pack.remote_index_queried is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            parent_aligned
            and operator_ack is True
            and twin_pack.production_router_verdict == "REJECT"
            and (
                highlight_launch.launch_ready is True
                or twin_pack.pack_ready is True
            )
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — highlight float launch + twin search competition pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — highlight_launch, twin_search_pack, alignment, or operator_ack gate open"
        )

    if (
        highlight_launch.live_dispatched is not False
        or highlight_launch.merge_executed is not False
        or twin_pack.live_dispatch_authorized is not False
        or twin_pack.remote_fetched is not False
        or twin_pack.remote_index_queried is not False
        or twin_pack.merge_executed is not False
        or twin_pack.twin_written is not False
        or twin_pack.production_router_verdict != "REJECT"
    ):
        raise HighlightFloatTwinSearchCompetitionComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "remote_index_queried=false",
            "merge_executed=false",
            "twin_written=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "store_mutated=false",
            "purchase_executed=false",
            "hosted=false",
            "backlog_mutated=false",
            "pack_dispatched=false",
        )
    )

    return HighlightFloatTwinSearchCompetitionCompose(
        session_id=session,
        parent_asset_id=parent,
        highlight_launch=highlight_launch,
        twin_search_pack=twin_pack,
        pack_ready=pack_ready,
        live_dispatched=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        remote_index_queried=False,
        merge_executed=False,
        twin_written=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        store_mutated=False,
        purchase_executed=False,
        hosted=False,
        backlog_mutated=False,
        pack_dispatched=False,
        notes=tuple(notes),
        authority="highlight_float_twin_search_competition_compose_advisory",
    )


def format_highlight_float_twin_search_competition_summary(
    c: HighlightFloatTwinSearchCompetitionCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"launch_ready={c.highlight_launch.launch_ready} · "
        f"twin_search_ready={c.twin_search_pack.pack_ready} · "
        f"hits={len(c.twin_search_pack.twin_search.search.hits)} · "
        f"verdict={c.production_router_verdict} · "
        f"live_dispatched=false · remote_index_queried=false · twin_written=false"
    )


__all__ = [
    "HighlightFloatTwinSearchCompetitionCompose",
    "HighlightFloatTwinSearchCompetitionComposeError",
    "compose_highlight_float_twin_search_competition",
    "format_highlight_float_twin_search_competition_summary",
]
