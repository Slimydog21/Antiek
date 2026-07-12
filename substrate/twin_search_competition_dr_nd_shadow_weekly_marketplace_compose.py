"""Twin intelligent search overlay on competition DR + ND shadow weekly marketplace (pure).

live_dispatch_authorized / remote_fetched / backlog_mutated always False.
remote_index_queried / merge_executed / twin_written always False.
production_router_verdict always REJECT; live_router_authorized always False.
purchase_executed / hosted / store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.competition_dr_nd_shadow_weekly_marketplace_compose import (
    CompetitionDrNdShadowWeeklyMarketplaceCompose,
    CompetitionDrNdShadowWeeklyMarketplaceComposeError,
    compose_competition_dr_nd_shadow_weekly_marketplace,
)
from substrate.twin_substrate_search_merge_compose import (
    TwinSubstrateSearchMergeCompose,
    TwinSubstrateSearchMergeComposeError,
    compose_twin_substrate_search_merge,
)


class TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError(ValueError):
    """Fail-closed validation for twin search + competition ND weekly pack."""


@dataclass(frozen=True)
class TwinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose:
    session_id: str
    week_id: str
    parent_asset_id: str
    competition_pack: CompetitionDrNdShadowWeeklyMarketplaceCompose
    twin_search: TwinSubstrateSearchMergeCompose
    twin_corpus: tuple[dict[str, Any], ...]
    pack_ready: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    production_router_verdict: str
    live_router_authorized: bool
    store_mutated: bool
    purchase_executed: bool
    hosted: bool
    remote_index_queried: bool
    merge_executed: bool
    twin_written: bool
    prompts_injected: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    charge_executed: bool
    live_execution_authorized: bool
    draft_written: bool
    analysis_written: bool
    record_persisted: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "week_id": self.week_id,
            "parent_asset_id": self.parent_asset_id,
            "competition_pack": self.competition_pack.to_dict(),
            "twin_search": self.twin_search.to_dict(),
            "twin_corpus": list(self.twin_corpus),
            "pack_ready": self.pack_ready,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "store_mutated": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_index_queried": False,
            "merge_executed": False,
            "twin_written": False,
            "prompts_injected": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "charge_executed": False,
            "live_execution_authorized": False,
            "draft_written": False,
            "analysis_written": False,
            "record_persisted": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "notes": list(self.notes),
            "authority": (
                "twin_search_competition_dr_nd_shadow_weekly_marketplace_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_twin_corpus(
    parent_asset_id: str,
    pack: CompetitionDrNdShadowWeeklyMarketplaceCompose,
    extra: object | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    qs = pack.competition
    insights: list[str] = []
    questions: list[str] = []

    for c in qs.citations.citations:
        title = c.title
        cid = c.citation_id
        family = c.family
        insights.append(title)
        records.append(
            {
                "twin_id": f"twin-cite-{cid}",
                "parent_asset_id": f"cite-parent-{cid}",
                "insights": [title],
                "questions": [
                    f'How does "{title}" inform Antiek DR quality?'
                ],
                "source_label": family,
            }
        )

    for row in qs.competition.decisions:
        status = row.antiek_status
        residual = row.residual
        competitor = row.competitor
        area = row.area
        summary = row.decision_summary
        if status == "behind" and residual:
            questions.append(str(residual))
            records.append(
                {
                    "twin_id": f"twin-gap-{competitor}-{area}",
                    "parent_asset_id": f"gap-parent-{competitor}-{area}",
                    "insights": [str(summary)] if summary else [],
                    "questions": [str(residual)],
                    "source_label": f"{competitor}/{area}",
                }
            )
        elif summary:
            insights.append(f"{competitor}/{area}: {summary}")

    if not insights and not questions:
        questions.append(
            "What competition gaps remain for Antiek DR quality?"
        )

    records.insert(
        0,
        {
            "twin_id": f"twin-{parent_asset_id}",
            "parent_asset_id": parent_asset_id,
            "insights": insights,
            "questions": questions,
            "source_label": "competition_dr_nd_shadow_weekly_marketplace",
        },
    )

    if extra is not None:
        if not isinstance(extra, list):
            raise TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError(
                "extra_twin_records must be an array when set"
            )
        for r in extra:
            if isinstance(r, dict):
                records.append(r)

    return records


def compose_twin_search_competition_dr_nd_shadow_weekly_marketplace(
    *,
    competition_pack: object,
    search_query: object,
    operator_ack: object,
    extra_twin_records: object | None = None,
    search_limit: object | None = None,
    min_parents_for_merge: object | None = None,
    search_pack_id: object | None = None,
    require_both: object | None = None,
) -> TwinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose:
    """Twin search over competition DR ND weekly pack. Never dispatches/indexes/writes."""
    if not isinstance(operator_ack, bool):
        raise TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(competition_pack, dict):
        raise TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError(
            "competition_pack must be an object"
        )
    _require_nonempty(search_query, field="search_query")

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "remote_index_queried=false · merge_executed=false · twin_written=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
        "purchase_executed=false · hosted=false · store_mutated=false",
    ]

    try:
        pack = compose_competition_dr_nd_shadow_weekly_marketplace(
            competition=competition_pack.get("competition"),
            nd_weekly=competition_pack.get("nd_weekly"),
            operator_ack=operator_ack,
            require_both=competition_pack.get("require_both"),
        )
    except CompetitionDrNdShadowWeeklyMarketplaceComposeError as e:
        raise TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError(
            str(e)
        ) from e
    notes.extend(f"[competition_pack] {n}" for n in pack.notes)

    session = _require_nonempty(pack.session_id, field="session_id")
    week = _require_nonempty(pack.week_id, field="week_id")
    parent = _require_nonempty(pack.parent_asset_id, field="parent_asset_id")

    twin_corpus = _derive_twin_corpus(parent, pack, extra_twin_records)
    notes.append(f"twin_corpus_size={len(twin_corpus)}")

    if search_pack_id is not None and str(search_pack_id).strip():
        spid = str(search_pack_id).strip()
    else:
        spid = f"twin-search-cdnwm-{session}"

    try:
        twin_search = compose_twin_substrate_search_merge(
            pack_id=spid,
            search_query=search_query,
            twin_records=twin_corpus,
            operator_ack=operator_ack,
            search_limit=search_limit,
            min_parents_for_merge=min_parents_for_merge,
        )
    except TwinSubstrateSearchMergeComposeError as e:
        raise TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin_search] {n}" for n in twin_search.notes)

    if require:
        pack_ready = (
            pack.pack_ready is True
            and twin_search.pack_ready is True
            and pack.production_router_verdict == "REJECT"
            and pack.live_dispatch_authorized is False
            and pack.remote_fetched is False
            and twin_search.remote_index_queried is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and pack.production_router_verdict == "REJECT"
            and twin_search.remote_index_queried is False
            and (pack.pack_ready is True or twin_search.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — twin intelligent search over competition DR ND weekly pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — competition_pack, twin_search, or operator_ack gate open"
        )

    if (
        pack.live_dispatch_authorized is not False
        or pack.remote_fetched is not False
        or pack.backlog_mutated is not False
        or pack.production_router_verdict != "REJECT"
        or pack.live_router_authorized is not False
        or pack.purchase_executed is not False
        or pack.hosted is not False
        or pack.store_mutated is not False
        or twin_search.remote_index_queried is not False
        or twin_search.merge_executed is not False
        or twin_search.twin_written is not False
        or twin_search.store_mutated is not False
    ):
        raise TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "store_mutated=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_index_queried=false",
            "merge_executed=false",
            "twin_written=false",
            "prompts_injected=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "charge_executed=false",
            "live_execution_authorized=false",
            "draft_written=false",
            "analysis_written=false",
            "record_persisted=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
        )
    )

    return TwinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose(
        session_id=session,
        week_id=week,
        parent_asset_id=parent,
        competition_pack=pack,
        twin_search=twin_search,
        twin_corpus=tuple(twin_corpus),
        pack_ready=pack_ready,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        store_mutated=False,
        purchase_executed=False,
        hosted=False,
        remote_index_queried=False,
        merge_executed=False,
        twin_written=False,
        prompts_injected=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        charge_executed=False,
        live_execution_authorized=False,
        draft_written=False,
        analysis_written=False,
        record_persisted=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        notes=tuple(notes),
        authority=(
            "twin_search_competition_dr_nd_shadow_weekly_marketplace_compose_advisory"
        ),
    )


def format_twin_search_competition_dr_nd_shadow_weekly_marketplace_summary(
    c: TwinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"competition_pack_ready={c.competition_pack.pack_ready} · "
        f"twin_search_ready={c.twin_search.pack_ready} · "
        f"hits={len(c.twin_search.search.hits)} · "
        f"corpus={len(c.twin_corpus)} · "
        f"verdict={c.production_router_verdict} · "
        f"live_dispatch_authorized=false · remote_index_queried=false · "
        f"merge_executed=false · twin_written=false"
    )


__all__ = [
    "TwinSearchCompetitionDrNdShadowWeeklyMarketplaceCompose",
    "TwinSearchCompetitionDrNdShadowWeeklyMarketplaceComposeError",
    "compose_twin_search_competition_dr_nd_shadow_weekly_marketplace",
    "format_twin_search_competition_dr_nd_shadow_weekly_marketplace_summary",
]
