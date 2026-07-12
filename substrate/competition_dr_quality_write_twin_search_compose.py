"""Competition DR quality → write → twin substrate search/merge (pure).

live_dispatch_authorized / remote_fetched / backlog_mutated always False.
draft_written / analysis_written / merge_executed always False.
remote_index_queried / twin_written / store_mutated / live_dispatched always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.competition_dr_quality_write_compose import (
    CompetitionDrQualityWriteCompose,
    CompetitionDrQualityWriteComposeError,
    compose_competition_dr_quality_write,
)
from substrate.twin_substrate_search_merge_compose import (
    TwinSubstrateSearchMergeCompose,
    TwinSubstrateSearchMergeComposeError,
    compose_twin_substrate_search_merge,
)


class CompetitionDrQualityWriteTwinSearchComposeError(ValueError):
    """Fail-closed validation for competition quality write + twin search."""


@dataclass(frozen=True)
class CompetitionDrQualityWriteTwinSearchCompose:
    session_id: str
    draft_id: str
    parent_asset_id: str
    quality_write: CompetitionDrQualityWriteCompose
    twin_search: TwinSubstrateSearchMergeCompose
    twin_corpus: tuple[dict[str, Any], ...]
    pack_ready: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    remote_index_queried: bool
    twin_written: bool
    store_mutated: bool
    live_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "draft_id": self.draft_id,
            "parent_asset_id": self.parent_asset_id,
            "quality_write": self.quality_write.to_dict(),
            "twin_search": self.twin_search.to_dict(),
            "twin_corpus": list(self.twin_corpus),
            "pack_ready": self.pack_ready,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "remote_index_queried": False,
            "twin_written": False,
            "store_mutated": False,
            "live_dispatched": False,
            "notes": list(self.notes),
            "authority": (
                "competition_dr_quality_write_twin_search_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitionDrQualityWriteTwinSearchComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_twin_corpus(
    parent_asset_id: str,
    quality_write: CompetitionDrQualityWriteCompose,
    extra: object | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    qs = quality_write.quality_source
    insights: list[str] = []
    questions: list[str] = []

    for c in qs.citations.citations:
        title = c.title if hasattr(c, "title") else str(c.get("title", ""))
        cid = (
            c.citation_id
            if hasattr(c, "citation_id")
            else str(c.get("citation_id", "c"))
        )
        family = c.family if hasattr(c, "family") else str(c.get("family", ""))
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
        status = (
            row.antiek_status
            if hasattr(row, "antiek_status")
            else row.get("antiek_status")
        )
        residual = (
            row.residual if hasattr(row, "residual") else row.get("residual")
        )
        competitor = (
            row.competitor
            if hasattr(row, "competitor")
            else row.get("competitor", "x")
        )
        area = row.area if hasattr(row, "area") else row.get("area", "a")
        summary = (
            row.decision_summary
            if hasattr(row, "decision_summary")
            else row.get("decision_summary")
        )
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
            "source_label": "competition_quality_write",
        },
    )

    if extra is not None:
        if not isinstance(extra, list):
            raise CompetitionDrQualityWriteTwinSearchComposeError(
                "extra_twin_records must be an array when set"
            )
        for r in extra:
            if isinstance(r, dict):
                records.append(r)

    return records


def compose_competition_dr_quality_write_twin_search(
    *,
    session_id: object,
    draft_id: object,
    parent_asset_id: object,
    competitor_decisions: object,
    requested_families: object,
    citations: object,
    quality_overall: object,
    would_exceed: object,
    operator_ack: object,
    search_query: object,
    focus_areas: object | None = None,
    filter_to_selected_families: object | None = None,
    quality_floor: object | None = None,
    operator_override: object | None = None,
    require_no_behind_gaps: object | None = None,
    analysis_kind: object | None = None,
    twin_slices: object | None = None,
    chase_slots: object | None = None,
    base_draft_html: object | None = None,
    extra_write_findings: object | None = None,
    require_both_with_write: object | None = None,
    extra_twin_records: object | None = None,
    search_limit: object | None = None,
    min_parents_for_merge: object | None = None,
    search_pack_id: object | None = None,
    require_both_with_search: object | None = None,
) -> CompetitionDrQualityWriteTwinSearchCompose:
    """Competition quality→write + twin search. Never dispatches/indexes/writes."""
    if not isinstance(operator_ack, bool):
        raise CompetitionDrQualityWriteTwinSearchComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    draft = _require_nonempty(draft_id, field="draft_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    _require_nonempty(search_query, field="search_query")

    require_search = (
        True if require_both_with_search is None else require_both_with_search
    )
    if not isinstance(require_search, bool):
        raise CompetitionDrQualityWriteTwinSearchComposeError(
            "require_both_with_search must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "draft_written=false · analysis_written=false · merge_executed=false",
        "remote_index_queried=false · twin_written=false · store_mutated=false",
        "live_dispatched=false",
    ]

    try:
        quality_write = compose_competition_dr_quality_write(
            session_id=session,
            draft_id=draft,
            parent_asset_id=parent,
            competitor_decisions=competitor_decisions,
            requested_families=requested_families,
            citations=citations,
            quality_overall=quality_overall,
            would_exceed=would_exceed,
            operator_ack=operator_ack,
            focus_areas=focus_areas,
            filter_to_selected_families=filter_to_selected_families,
            quality_floor=quality_floor,
            operator_override=operator_override,
            require_no_behind_gaps=require_no_behind_gaps,
            analysis_kind=analysis_kind,
            twin_slices=twin_slices,
            chase_slots=chase_slots,
            base_draft_html=base_draft_html,
            extra_write_findings=extra_write_findings,
            require_both_with_write=require_both_with_write,
        )
    except CompetitionDrQualityWriteComposeError as e:
        raise CompetitionDrQualityWriteTwinSearchComposeError(str(e)) from e
    notes.extend(f"[quality_write] {n}" for n in quality_write.notes)

    twin_corpus = _derive_twin_corpus(
        parent, quality_write, extra_twin_records
    )
    notes.append(f"twin_corpus_size={len(twin_corpus)}")

    if search_pack_id is not None and str(search_pack_id).strip():
        spid = str(search_pack_id).strip()
    else:
        spid = f"cqw-search-{session}"

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
        raise CompetitionDrQualityWriteTwinSearchComposeError(str(e)) from e
    notes.extend(f"[twin_search] {n}" for n in twin_search.notes)

    if require_search:
        pack_ready = (
            quality_write.pack_ready is True
            and twin_search.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            quality_write.pack_ready is True or twin_search.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — competition quality write + twin search ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — quality_write, twin_search, or operator_ack gate open"
        )

    if (
        quality_write.live_dispatch_authorized is not False
        or quality_write.remote_fetched is not False
        or quality_write.backlog_mutated is not False
        or quality_write.draft_written is not False
        or quality_write.analysis_written is not False
        or quality_write.merge_executed is not False
        or twin_search.remote_index_queried is not False
        or twin_search.merge_executed is not False
        or twin_search.twin_written is not False
        or twin_search.store_mutated is not False
    ):
        raise CompetitionDrQualityWriteTwinSearchComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "remote_index_queried=false",
            "twin_written=false",
            "store_mutated=false",
            "live_dispatched=false",
        )
    )

    return CompetitionDrQualityWriteTwinSearchCompose(
        session_id=session,
        draft_id=draft,
        parent_asset_id=parent,
        quality_write=quality_write,
        twin_search=twin_search,
        twin_corpus=tuple(twin_corpus),
        pack_ready=pack_ready,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        remote_index_queried=False,
        twin_written=False,
        store_mutated=False,
        live_dispatched=False,
        notes=tuple(notes),
        authority="competition_dr_quality_write_twin_search_compose_advisory",
    )


def format_competition_dr_quality_write_twin_search_summary(
    c: CompetitionDrQualityWriteTwinSearchCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"quality_write_ready={c.quality_write.pack_ready} · "
        f"twin_search_ready={c.twin_search.pack_ready} · "
        f"hits={len(c.twin_search.search.hits)} · "
        f"corpus={len(c.twin_corpus)} · "
        f"live_dispatch_authorized=false · remote_index_queried=false · "
        f"draft_written=false · merge_executed=false · twin_written=false"
    )


__all__ = [
    "CompetitionDrQualityWriteTwinSearchCompose",
    "CompetitionDrQualityWriteTwinSearchComposeError",
    "compose_competition_dr_quality_write_twin_search",
    "format_competition_dr_quality_write_twin_search_summary",
]
