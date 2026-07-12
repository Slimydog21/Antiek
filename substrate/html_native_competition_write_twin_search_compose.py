"""HTML-native view + competition quality write → twin search (pure).

pdf_view_authorized / pdf_primary always False.
live_dispatch_authorized / remote_fetched / backlog_mutated always False.
draft_written / analysis_written / merge_executed always False.
remote_index_queried / twin_written / store_mutated / live_dispatched always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.competition_dr_quality_write_twin_search_compose import (
    CompetitionDrQualityWriteTwinSearchCompose,
    CompetitionDrQualityWriteTwinSearchComposeError,
    compose_competition_dr_quality_write_twin_search,
)
from substrate.html_native_view_session_authority_compose import (
    HtmlNativeViewSessionAuthorityCompose,
    HtmlNativeViewSessionAuthorityComposeError,
    compose_html_native_view_session_authority,
)


class HtmlNativeCompetitionWriteTwinSearchComposeError(ValueError):
    """Fail-closed validation for HTML-native competition write twin search."""


@dataclass(frozen=True)
class HtmlNativeCompetitionWriteTwinSearchCompose:
    session_id: str
    asset_id: str
    html_view: HtmlNativeViewSessionAuthorityCompose
    competition_pack: CompetitionDrQualityWriteTwinSearchCompose
    pack_ready: bool
    pdf_view_authorized: bool
    pdf_primary: bool
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
            "asset_id": self.asset_id,
            "html_view": self.html_view.to_dict(),
            "competition_pack": self.competition_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "pdf_view_authorized": False,
            "pdf_primary": False,
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
                "html_native_competition_write_twin_search_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HtmlNativeCompetitionWriteTwinSearchComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_html_native_competition_write_twin_search(
    *,
    session_id: object,
    asset_id: object,
    html_projection_sha: object,
    view_requested: object,
    twin_bound: object,
    operator_ack: object,
    competition: object,
    twin_substrate_ready: object | None = None,
    claimed_format: object | None = None,
    reading: object | None = None,
    research: object | None = None,
    require_both: object | None = None,
) -> HtmlNativeCompetitionWriteTwinSearchCompose:
    """HTML-native view + competition write twin search. Never PDF/dispatch/writes."""
    if not isinstance(operator_ack, bool):
        raise HtmlNativeCompetitionWriteTwinSearchComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(competition, dict):
        raise HtmlNativeCompetitionWriteTwinSearchComposeError(
            "competition must be an object"
        )
    session = _require_nonempty(session_id, field="session_id")
    asset = _require_nonempty(asset_id, field="asset_id")

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise HtmlNativeCompetitionWriteTwinSearchComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "pdf_view_authorized=false · pdf_primary=false — HTML-native doctrine",
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "draft_written=false · analysis_written=false · merge_executed=false",
        "remote_index_queried=false · twin_written=false · store_mutated=false",
        "live_dispatched=false",
    ]

    try:
        html_view = compose_html_native_view_session_authority(
            session_id=session,
            asset_id=asset,
            html_projection_sha=html_projection_sha,
            view_requested=view_requested,
            twin_bound=twin_bound,
            operator_ack=operator_ack,
            twin_substrate_ready=twin_substrate_ready,
            claimed_format=claimed_format,
            reading=reading,
            research=research,
        )
    except HtmlNativeViewSessionAuthorityComposeError as e:
        raise HtmlNativeCompetitionWriteTwinSearchComposeError(str(e)) from e
    notes.extend(f"[html_view] {n}" for n in html_view.notes)

    try:
        competition_pack = compose_competition_dr_quality_write_twin_search(
            session_id=session,
            draft_id=competition.get("draft_id"),
            parent_asset_id=competition.get("parent_asset_id"),
            competitor_decisions=competition.get("competitor_decisions"),
            requested_families=competition.get("requested_families"),
            citations=competition.get("citations"),
            quality_overall=competition.get("quality_overall"),
            would_exceed=competition.get("would_exceed"),
            operator_ack=operator_ack,
            search_query=competition.get("search_query"),
            quality_floor=competition.get("quality_floor"),
            operator_override=competition.get("operator_override"),
            require_no_behind_gaps=competition.get("require_no_behind_gaps"),
            analysis_kind=competition.get("analysis_kind"),
            twin_slices=competition.get("twin_slices"),
            chase_slots=competition.get("chase_slots"),
            base_draft_html=competition.get("base_draft_html"),
            extra_write_findings=competition.get("extra_write_findings"),
            require_both_with_write=competition.get("require_both_with_write"),
            extra_twin_records=competition.get("extra_twin_records"),
            search_limit=competition.get("search_limit"),
            min_parents_for_merge=competition.get("min_parents_for_merge"),
            search_pack_id=competition.get("search_pack_id"),
            require_both_with_search=competition.get(
                "require_both_with_search"
            ),
        )
    except CompetitionDrQualityWriteTwinSearchComposeError as e:
        raise HtmlNativeCompetitionWriteTwinSearchComposeError(str(e)) from e
    notes.extend(f"[competition_pack] {n}" for n in competition_pack.notes)

    if require:
        pack_ready = (
            html_view.pack_ready is True
            and competition_pack.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            html_view.pack_ready is True or competition_pack.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — HTML-native view + competition write twin search ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — html_view, competition_pack, or operator_ack gate open"
        )

    if (
        html_view.pdf_view_authorized is not False
        or html_view.pdf_primary is not False
        or competition_pack.live_dispatch_authorized is not False
        or competition_pack.remote_fetched is not False
        or competition_pack.backlog_mutated is not False
        or competition_pack.draft_written is not False
        or competition_pack.analysis_written is not False
        or competition_pack.merge_executed is not False
        or competition_pack.remote_index_queried is not False
        or competition_pack.twin_written is not False
        or competition_pack.store_mutated is not False
    ):
        raise HtmlNativeCompetitionWriteTwinSearchComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "pdf_view_authorized=false",
            "pdf_primary=false",
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

    return HtmlNativeCompetitionWriteTwinSearchCompose(
        session_id=session,
        asset_id=asset,
        html_view=html_view,
        competition_pack=competition_pack,
        pack_ready=pack_ready,
        pdf_view_authorized=False,
        pdf_primary=False,
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
        authority="html_native_competition_write_twin_search_compose_advisory",
    )


def format_html_native_competition_write_twin_search_summary(
    c: HtmlNativeCompetitionWriteTwinSearchCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"html_ready={c.html_view.pack_ready} · "
        f"competition_ready={c.competition_pack.pack_ready} · "
        f"hits={len(c.competition_pack.twin_search.search.hits)} · "
        f"pdf_view_authorized=false · pdf_primary=false · "
        f"remote_index_queried=false · twin_written=false · draft_written=false"
    )


__all__ = [
    "HtmlNativeCompetitionWriteTwinSearchCompose",
    "HtmlNativeCompetitionWriteTwinSearchComposeError",
    "compose_html_native_competition_write_twin_search",
    "format_html_native_competition_write_twin_search_summary",
]
