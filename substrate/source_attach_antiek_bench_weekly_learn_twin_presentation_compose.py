"""arxiv/substack source attach over Antiek-bench weekly learn twin presentation (pure).

remote_fetched / live_dispatch_authorized always False.
backlog_mutated / store_mutated / suite_rewritten always False.
twin_written / merge_executed / draft_written always False.
pdf_primary always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose import (
    AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose,
    AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError,
    compose_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective,
)
from substrate.source_publication_dr_attach_quality_compose import (
    SourcePublicationDrAttachQualityCompose,
    SourcePublicationDrAttachQualityComposeError,
    compose_source_publication_dr_attach_quality,
)


class SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError(ValueError):
    """Fail-closed validation for source attach + weekly learn twin presentation."""


@dataclass(frozen=True)
class SourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    sources: SourcePublicationDrAttachQualityCompose
    weekly_pack: AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    remote_fetched: bool
    live_dispatch_authorized: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    twin_written: bool
    prompts_injected: bool
    merge_executed: bool
    draft_written: bool
    analysis_written: bool
    live_dispatched: bool
    pack_dispatched: bool
    live_execution_authorized: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    inventory_mutated: bool
    charge_executed: bool
    record_persisted: bool
    purchase_executed: bool
    hosted: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "sources": self.sources.to_dict(),
            "weekly_pack": self.weekly_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "remote_fetched": False,
            "live_dispatch_authorized": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "twin_written": False,
            "prompts_injected": False,
            "merge_executed": False,
            "draft_written": False,
            "analysis_written": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "live_execution_authorized": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "inventory_mutated": False,
            "charge_executed": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "source_attach_antiek_bench_weekly_learn_twin_presentation_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_source_attach_antiek_bench_weekly_learn_twin_presentation(
    *,
    sources: object,
    weekly_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose:
    """arxiv/substack attach + weekly learn twin presentation. Never fetches."""
    if not isinstance(operator_ack, bool):
        raise SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(sources, dict):
        raise SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError(
            "sources must be an object"
        )
    if not isinstance(weekly_pack, dict):
        raise SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError(
            "weekly_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "remote_fetched=false · live_dispatch_authorized=false",
        "backlog_mutated=false · store_mutated=false · suite_rewritten=false",
        "twin_written=false · merge_executed=false · draft_written=false",
        "pdf_primary=false · production_router_verdict=REJECT",
    ]

    try:
        src = compose_source_publication_dr_attach_quality(
            session_id=sources.get("session_id"),
            parent_asset_id=sources.get("parent_asset_id"),
            requested_families=sources.get("requested_families"),
            sources=sources.get("sources"),
            quality_overall=sources.get("quality_overall"),
            would_exceed=sources.get("would_exceed"),
            operator_ack=operator_ack,
            citations=sources.get("citations"),
            derive_citations_from_sources=sources.get(
                "derive_citations_from_sources"
            ),
            quality_floor=sources.get("quality_floor"),
            operator_override=sources.get("operator_override"),
        )
    except SourcePublicationDrAttachQualityComposeError as e:
        raise SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError(
            str(e)
        ) from e
    notes.extend(f"[sources] {n}" for n in src.notes)

    try:
        wp = compose_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective(
            weekly_learn=weekly_pack.get("weekly_learn"),
            twin_presentation_pack=weekly_pack.get("twin_presentation_pack"),
            operator_ack=operator_ack,
            require_both=weekly_pack.get("require_both"),
        )
    except AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError as e:
        raise SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError(
            str(e)
        ) from e
    notes.extend(f"[weekly_pack] {n}" for n in wp.notes)

    session = _require_nonempty(src.session_id, field="session_id")
    parent = _require_nonempty(src.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(wp.week_id, field="week_id")
    asset = _require_nonempty(wp.asset_id, field="asset_id")
    title = _require_nonempty(wp.title, field="title")
    account = _require_nonempty(wp.account_id, field="account_id")

    session_aligned = wp.session_id == session
    parent_aligned = wp.parent_asset_id == parent or wp.asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between sources and weekly_pack — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between sources and weekly_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and src.pack_ready is True
            and wp.pack_ready is True
            and src.remote_fetched is False
            and src.live_dispatch_authorized is False
            and src.pdf_view_authorized is False
            and src.store_mutated is False
            and wp.backlog_mutated is False
            and wp.store_mutated is False
            and wp.suite_rewritten is False
            and wp.twin_written is False
            and wp.merge_executed is False
            and wp.draft_written is False
            and wp.live_dispatched is False
            and wp.live_router_authorized is False
            and wp.secrets_stored is False
            and wp.remote_index_queried is False
            and wp.pdf_primary is False
            and wp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and src.remote_fetched is False
            and wp.production_router_verdict == "REJECT"
            and wp.pdf_primary is False
            and (src.pack_ready is True or wp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — arxiv/substack attach + weekly learn twin presentation "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — sources, weekly_pack, alignment, or operator_ack gate open"
        )

    if (
        src.remote_fetched is not False
        or src.live_dispatch_authorized is not False
        or src.pdf_view_authorized is not False
        or src.store_mutated is not False
        or wp.backlog_mutated is not False
        or wp.store_mutated is not False
        or wp.suite_rewritten is not False
        or wp.twin_written is not False
        or wp.merge_executed is not False
        or wp.draft_written is not False
        or wp.live_dispatched is not False
        or wp.live_router_authorized is not False
        or wp.secrets_stored is not False
        or wp.remote_index_queried is not False
        or wp.pdf_primary is not False
        or wp.production_router_verdict != "REJECT"
    ):
        raise SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "remote_fetched=false",
            "live_dispatch_authorized=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "twin_written=false",
            "prompts_injected=false",
            "merge_executed=false",
            "draft_written=false",
            "analysis_written=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "live_execution_authorized=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "inventory_mutated=false",
            "charge_executed=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "production_router_verdict=REJECT",
        )
    )

    return SourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        sources=src,
        weekly_pack=wp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        remote_fetched=False,
        live_dispatch_authorized=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        twin_written=False,
        prompts_injected=False,
        merge_executed=False,
        draft_written=False,
        analysis_written=False,
        live_dispatched=False,
        pack_dispatched=False,
        live_execution_authorized=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        inventory_mutated=False,
        charge_executed=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "source_attach_antiek_bench_weekly_learn_twin_presentation_compose_advisory"
        ),
    )


def format_source_attach_antiek_bench_weekly_learn_twin_presentation_summary(
    c: SourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"sources_ready={c.sources.pack_ready} · "
        f"weekly_ready={c.weekly_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "remote_fetched=false · backlog_mutated=false · twin_written=false"
    )


__all__ = [
    "SourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose",
    "SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError",
    "compose_source_attach_antiek_bench_weekly_learn_twin_presentation",
    "format_source_attach_antiek_bench_weekly_learn_twin_presentation_summary",
]
