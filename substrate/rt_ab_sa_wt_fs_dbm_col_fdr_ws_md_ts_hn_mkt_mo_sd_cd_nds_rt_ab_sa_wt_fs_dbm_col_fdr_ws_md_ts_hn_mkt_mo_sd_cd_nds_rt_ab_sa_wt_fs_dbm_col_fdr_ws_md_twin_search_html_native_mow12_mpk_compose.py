"""Recursive twin presentation residual over antiek-bench source-attach mow12 (pure).

Short residual moniker rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk.
twin_written / prompts_injected / merge_executed always False.
backlog_mutated / store_mutated / suite_rewritten always False.
remote_fetched / pdf_primary / draft_written always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose import (
    AbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose,
    AbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError,
    compose_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk,
)
from substrate.recursive_twin_note_taker_compose import (
    RecursiveTwinNoteTakerCompose,
    RecursiveTwinNoteTakerComposeError,
    compose_recursive_twin_note_taker,
)

AUTHORITY = (
    "rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose_advisory"
)

TwinPresentationViewMode = Literal[
    "side_panel", "overlay", "fullscreen_twin", "inline"
]
_VIEW_MODES = frozenset(
    ("side_panel", "overlay", "fullscreen_twin", "inline")
)


class RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(ValueError):
    """Fail-closed validation for twin presentation + antiek-bench residual."""


@dataclass(frozen=True)
class PresentationSurface:
    view_mode: TwinPresentationViewMode
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
class RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    twin: RecursiveTwinNoteTakerCompose
    presentation: PresentationSurface
    weekly_pack: AbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    twin_written: bool
    prompts_injected: bool
    merge_executed: bool
    live_dispatch_authorized: bool
    draft_written: bool
    analysis_written: bool
    live_dispatched: bool
    pack_dispatched: bool
    live_execution_authorized: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    inventory_mutated: bool
    charge_executed: bool
    record_persisted: bool
    purchase_executed: bool
    hosted: bool
    remote_fetched: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "twin": self.twin.to_dict(),
            "presentation": self.presentation.to_dict(),
            "weekly_pack": self.weekly_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "twin_written": False,
            "prompts_injected": False,
            "merge_executed": False,
            "live_dispatch_authorized": False,
            "draft_written": False,
            "analysis_written": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "live_execution_authorized": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "inventory_mutated": False,
            "charge_executed": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": AUTHORITY,
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_string_list(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            f"{field} must be an array when set"
        )
    out: list[str] = []
    for i, item in enumerate(value):
        out.append(_require_nonempty(item, field=f"{field}[{i}]"))
    return out


def compose_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
    *,
    twin: object,
    presentation: object,
    weekly_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose:
    """Twin presentation + antiek-bench residual. Never writes twin."""
    if not isinstance(operator_ack, bool):
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(twin, dict):
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "twin must be an object"
        )
    if not isinstance(presentation, dict):
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "presentation must be an object"
        )
    if not isinstance(weekly_pack, dict):
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "weekly_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "twin_written=false · prompts_injected=false · merge_executed=false",
        "backlog_mutated=false · store_mutated=false · suite_rewritten=false",
        "remote_fetched=false · pdf_primary=false · draft_written=false",
        "production_router_verdict=REJECT",
    ]

    try:
        tw = compose_recursive_twin_note_taker(
            parent_asset_id=twin.get("parent_asset_id"),
            source_excerpt=twin.get("source_excerpt"),
            operator_ack=operator_ack,
            existing_twin_asset_id=twin.get("existing_twin_asset_id"),
            focus_questions=twin.get("focus_questions"),
        )
    except RecursiveTwinNoteTakerComposeError as e:
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin] {n}" for n in tw.notes)

    view_mode = presentation.get("view_mode")
    if view_mode not in _VIEW_MODES:
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "presentation.view_mode must be side_panel|overlay|fullscreen_twin|inline"
        )
    open_requested = presentation.get("open_requested")
    if not isinstance(open_requested, bool):
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "presentation.open_requested must be an explicit boolean"
        )
    merge_preview = presentation.get("merge_to_parent_preview")
    if merge_preview is None:
        merge_preview = False
    if not isinstance(merge_preview, bool):
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
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

    presentation_sections: list[str] = [
        *tw.twin_scaffold_sections,
        (
            f'<section data-role="presentation-chrome" data-view-mode="{view_mode}" '
            f'data-open="{open_requested}" data-merge-preview="{merge_preview}"></section>'
        ),
    ]
    for insight in presented_insights:
        presentation_sections.append(
            f'<section data-role="presented-insight" data-parent="{tw.parent_asset_id}">{insight}</section>'
        )
    for question in presented_questions:
        presentation_sections.append(
            f'<section data-role="presented-question" data-parent="{tw.parent_asset_id}">{question}</section>'
        )

    presentation_ready = (
        operator_ack is True
        and tw.twin_propose_ready is True
        and open_requested is True
        and tw.twin_written is False
        and tw.prompts_injected is False
    )
    if presentation_ready:
        notes.append(
            f"presentation_ready=true · view_mode={view_mode} · "
            f"insights={len(presented_insights)} · questions={len(presented_questions)}"
        )
    else:
        notes.append(
            "presentation_ready=false — operator_ack, twin_propose_ready, or open_requested gate open"
        )
    if merge_preview:
        notes.append(
            "merge_to_parent_preview=true — draft preview only; merge_executed=false"
        )

    try:
        wp = compose_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
            weekly_learn=weekly_pack.get("weekly_learn"),
            source_pack=weekly_pack.get("source_pack"),
            operator_ack=operator_ack,
            require_both=weekly_pack.get("require_both"),
        )
    except AbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError as e:
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            str(e)
        ) from e
    notes.extend(f"[weekly_pack] {n}" for n in wp.notes)

    parent = _require_nonempty(tw.parent_asset_id, field="parent_asset_id")
    session = _require_nonempty(wp.session_id, field="session_id")
    week = _require_nonempty(wp.week_id, field="week_id")
    asset = _require_nonempty(wp.asset_id, field="asset_id")
    title = _require_nonempty(wp.title, field="title")
    account = _require_nonempty(wp.account_id, field="account_id")

    session_aligned = wp.session_aligned is True
    parent_aligned_strict = (
        wp.parent_asset_id == parent or wp.asset_id == parent
    )
    if not parent_aligned_strict:
        notes.append(
            "parent_asset_id mismatch between twin and weekly_pack — pack_ready blocked"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            session_aligned is True
            and parent_aligned_strict is True
            and presentation_ready is True
            and tw.twin_propose_ready is True
            and wp.pack_ready is True
            and tw.twin_written is False
            and tw.prompts_injected is False
            and tw.live_dispatch_authorized is False
            and wp.backlog_mutated is False
            and wp.store_mutated is False
            and wp.suite_rewritten is False
            and wp.remote_fetched is False
            and wp.pdf_primary is False
            and wp.draft_written is False
            and wp.analysis_written is False
            and wp.twin_written is False
            and wp.merge_executed is False
            and wp.live_dispatched is False
            and wp.live_execution_authorized is False
            and wp.live_router_authorized is False
            and wp.secrets_stored is False
            and wp.remote_index_queried is False
            and wp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and parent_aligned_strict is True
            and operator_ack is True
            and tw.twin_written is False
            and wp.production_router_verdict == "REJECT"
            and wp.pdf_primary is False
            and wp.backlog_mutated is False
            and (presentation_ready is True or wp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — twin presentation + weekly source attach write twin ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — twin, presentation, weekly_pack, alignment, or operator_ack gate open"
        )

    if (
        tw.twin_written is not False
        or tw.prompts_injected is not False
        or tw.live_dispatch_authorized is not False
        or wp.backlog_mutated is not False
        or wp.store_mutated is not False
        or wp.suite_rewritten is not False
        or wp.remote_fetched is not False
        or wp.pdf_primary is not False
        or wp.draft_written is not False
        or wp.analysis_written is not False
        or wp.twin_written is not False
        or wp.merge_executed is not False
        or wp.live_dispatched is not False
        or wp.live_execution_authorized is not False
        or wp.live_router_authorized is not False
        or wp.secrets_stored is not False
        or wp.remote_index_queried is not False
        or wp.production_router_verdict != "REJECT"
    ):
        raise RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "twin_written=false",
            "prompts_injected=false",
            "merge_executed=false",
            "live_dispatch_authorized=false",
            "draft_written=false",
            "analysis_written=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "live_execution_authorized=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "inventory_mutated=false",
            "charge_executed=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "production_router_verdict=REJECT",
        )
    )

    return RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        twin=tw,
        presentation=PresentationSurface(
            view_mode=view_mode,  # type: ignore[arg-type]
            open_requested=open_requested,
            merge_to_parent_preview=merge_preview,
            presented_insight_count=len(presented_insights),
            presented_question_count=len(presented_questions),
            presentation_sections=tuple(presentation_sections),
            presentation_ready=presentation_ready,
        ),
        weekly_pack=wp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned_strict,
        pack_ready=pack_ready,
        twin_written=False,
        prompts_injected=False,
        merge_executed=False,
        live_dispatch_authorized=False,
        draft_written=False,
        analysis_written=False,
        live_dispatched=False,
        pack_dispatched=False,
        live_execution_authorized=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        inventory_mutated=False,
        charge_executed=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=AUTHORITY,
    )


def format_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_summary(
    c: RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"presentation_ready={c.presentation.presentation_ready} · "
        f"weekly_ready={c.weekly_pack.pack_ready} · "
        f"learn_ready={c.weekly_pack.learn_ready} · "
        f"view_mode={c.presentation.view_mode} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "twin_written=false · backlog_mutated=false · remote_fetched=false"
    )


__all__ = [
    "PresentationSurface",
    "RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose",
    "RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError",
    "compose_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk",
    "format_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_summary",
    "AUTHORITY",
]
