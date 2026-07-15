"""Settings decision residual over competition DR ND shadow mow12 (pure).

Short residual moniker sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk.
secrets_stored / inventory_mutated / live_router_authorized always False.
live_dispatch_authorized / remote_fetched / backlog_mutated always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

AUTHORITY = (
    "sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose_advisory"
)

from dataclasses import dataclass
from typing import Any

from substrate.cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose import (
    CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose,
    CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError,
    compose_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk,
)
from substrate.settings_add_model_bench_decision_compose import (
    SettingsAddModelBenchDecisionCompose,
    SettingsAddModelBenchDecisionComposeError,
    compose_settings_add_model_bench_decision,
)


class SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(ValueError):
    """Fail-closed validation for settings decision + competition DR pack."""


@dataclass(frozen=True)
class SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    focus_task: str
    settings: SettingsAddModelBenchDecisionCompose
    competition_pack: CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose
    session_aligned: bool
    week_aligned: bool
    pack_ready: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    live_meter_read: bool
    suite_rewritten: bool
    backlog_mutated: bool
    store_mutated: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    twin_written: bool
    prompts_injected: bool
    merge_executed: bool
    draft_written: bool
    analysis_written: bool
    live_dispatched: bool
    pack_dispatched: bool
    live_execution_authorized: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    charge_executed: bool
    record_persisted: bool
    purchase_executed: bool
    hosted: bool
    remote_index_queried: bool
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
            "focus_task": self.focus_task,
            "settings": self.settings.to_dict(),
            "competition_pack": self.competition_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "week_aligned": self.week_aligned,
            "pack_ready": self.pack_ready,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "live_meter_read": False,
            "suite_rewritten": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "twin_written": False,
            "prompts_injected": False,
            "merge_executed": False,
            "draft_written": False,
            "analysis_written": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "live_execution_authorized": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "charge_executed": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_index_queried": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
    *,
    settings: object,
    competition_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose:
    """Settings decision + competition DR ND shadow twin weekly. Never secrets/routes."""
    if not isinstance(operator_ack, bool):
        raise SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(settings, dict):
        raise SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "settings must be an object"
        )
    if not isinstance(competition_pack, dict):
        raise SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "competition_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "secrets_stored=false · inventory_mutated=false · live_router_authorized=false",
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "production_router_verdict=REJECT",
    ]

    try:
        st = compose_settings_add_model_bench_decision(
            models=settings.get("models"),
            pending_add_model_ids=settings.get("pending_add_model_ids"),
            action=settings.get("action"),
            week_id=settings.get("week_id"),
            focus_task=settings.get("focus_task"),
            events=settings.get("events"),
            daily_cap_usd=settings.get("daily_cap_usd"),
            spent_usd=settings.get("spent_usd"),
            operator_ack=operator_ack,
            decision_models=settings.get("decision_models"),
            selected_model_id=settings.get("selected_model_id"),
            projected_cost_usd_high=settings.get("projected_cost_usd_high"),
            projected_cost_usd_low=settings.get("projected_cost_usd_low"),
            existing_tasks=settings.get("existing_tasks"),
            proposed_new_tasks=settings.get("proposed_new_tasks"),
            min_events_for_recommendation=settings.get(
                "min_events_for_recommendation"
            ),
            require_both=settings.get("require_both"),
        )
    except SettingsAddModelBenchDecisionComposeError as e:
        raise SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            str(e)
        ) from e
    notes.extend(f"[settings] {n}" for n in st.notes)

    try:
        cp = compose_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
            competition=competition_pack.get("competition"),
            nd_pack=competition_pack.get("nd_pack"),
            operator_ack=operator_ack,
            require_both=competition_pack.get("require_both"),
        )
    except CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError as e:
        raise SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            str(e)
        ) from e
    notes.extend(f"[competition_pack] {n}" for n in cp.notes)

    week = _require_nonempty(st.week_id, field="week_id")
    focus = _require_nonempty(st.focus_task, field="focus_task")
    session = _require_nonempty(cp.session_id, field="session_id")
    parent = _require_nonempty(cp.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(cp.asset_id, field="asset_id")
    title = _require_nonempty(cp.title, field="title")
    account = _require_nonempty(cp.account_id, field="account_id")

    week_aligned = cp.week_id == week
    if not week_aligned:
        notes.append(
            "week_id mismatch between settings and competition_pack — pack_ready blocked"
        )
    else:
        notes.append("week_aligned=true")

    session_aligned = cp.session_aligned is True
    if not session_aligned:
        notes.append(
            "competition_pack session_aligned=false — pack_ready blocked when require_both"
        )

    if require:
        pack_ready = (
            week_aligned is True
            and session_aligned is True
            and st.pack_ready is True
            and cp.pack_ready is True
            and st.secrets_stored is False
            and st.inventory_mutated is False
            and st.live_router_authorized is False
            and st.suite_rewritten is False
            and st.backlog_mutated is False
            and st.store_mutated is False
            and cp.live_dispatch_authorized is False
            and cp.remote_fetched is False
            and cp.backlog_mutated is False
            and cp.live_router_authorized is False
            and cp.twin_written is False
            and cp.pdf_primary is False
            and cp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            week_aligned is True
            and operator_ack is True
            and st.secrets_stored is False
            and st.inventory_mutated is False
            and cp.production_router_verdict == "REJECT"
            and cp.live_router_authorized is False
            and (st.pack_ready is True or cp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — settings decision + competition DR ND shadow twin "
            "weekly ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — settings, competition_pack, alignment, or "
            "operator_ack gate open"
        )

    if (
        st.secrets_stored is not False
        or st.inventory_mutated is not False
        or st.live_router_authorized is not False
        or st.suite_rewritten is not False
        or st.backlog_mutated is not False
        or st.store_mutated is not False
        or cp.live_dispatch_authorized is not False
        or cp.remote_fetched is not False
        or cp.backlog_mutated is not False
        or cp.live_router_authorized is not False
        or cp.twin_written is not False
        or cp.pdf_primary is not False
        or cp.production_router_verdict != "REJECT"
    ):
        raise SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "live_meter_read=false",
            "suite_rewritten=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "twin_written=false",
            "prompts_injected=false",
            "merge_executed=false",
            "draft_written=false",
            "analysis_written=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "live_execution_authorized=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "charge_executed=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_index_queried=false",
            "production_router_verdict=REJECT",
        )
    )

    return SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        focus_task=focus,
        settings=st,
        competition_pack=cp,
        session_aligned=session_aligned,
        week_aligned=week_aligned,
        pack_ready=pack_ready,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        live_meter_read=False,
        suite_rewritten=False,
        backlog_mutated=False,
        store_mutated=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        twin_written=False,
        prompts_injected=False,
        merge_executed=False,
        draft_written=False,
        analysis_written=False,
        live_dispatched=False,
        pack_dispatched=False,
        live_execution_authorized=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        charge_executed=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        remote_index_queried=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose_advisory"
        ),
    )


def format_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_summary(
    c: SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"settings_ready={c.settings.pack_ready} · "
        f"competition_ready={c.competition_pack.pack_ready} · "
        f"would_exceed={c.settings.bench_rec.decision_tree.would_exceed} · "
        f"week={c.week_id} · "
        f"verdict={c.production_router_verdict} · "
        "secrets_stored=false · inventory_mutated=false · live_router_authorized=false"
    )


__all__ = [
    "AUTHORITY",
    "SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkCompose",
    "SdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpkComposeError",
    "compose_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk",
    "format_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_summary",
]
