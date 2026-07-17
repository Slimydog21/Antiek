"""Model decision-tree residual over twin-search HTML-native marketplace free mow12 (pure).

Short residual moniker md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk.
live_router_authorized / secrets_stored / live_meter_read always False.
remote_index_queried / twin_written / purchase_executed always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

import sys
sys.setrecursionlimit(50000)

AUTHORITY = (
    "md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk_compose_advisory"
)

from dataclasses import dataclass
from typing import Any

from substrate.settings_decision_tree_usage_bar_compose import (
    SettingsDecisionTreeUsageBarCompose,
    SettingsDecisionTreeUsageBarComposeError,
    compose_settings_decision_tree_usage_bar,
)
from substrate.ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk_compose import (
    TsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkCompose,
    TsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError,
    compose_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk,
)


class MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError(ValueError):
    """Fail-closed validation for model decision + twin-search residual."""


@dataclass(frozen=True)
class MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    decision: SettingsDecisionTreeUsageBarCompose
    twin_search_pack: TsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkCompose
    pack_ready: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    twin_written: bool
    prompts_injected: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_dispatch_authorized: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_fetched: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    draft_written: bool
    record_persisted: bool
    analysis_written: bool
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
            "decision": self.decision.to_dict(),
            "twin_search_pack": self.twin_search_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "twin_written": False,
            "prompts_injected": False,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_dispatch_authorized": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": AUTHORITY,
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk(
    *,
    decision: object,
    twin_search_pack: object,
    operator_ack: object,
    require_both: object | None = None,
    block_on_budget_exceed: object | None = None,
) -> MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkCompose:
    """Model decision + twin-search residual. Never live-routes."""
    if not isinstance(operator_ack, bool):
        raise MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(decision, dict):
        raise MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError(
            "decision must be an object"
        )
    if not isinstance(twin_search_pack, dict):
        raise MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError(
            "twin_search_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError(
            "require_both must be boolean when set"
        )
    block_budget = (
        True if block_on_budget_exceed is None else block_on_budget_exceed
    )
    if not isinstance(block_budget, bool):
        raise MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError(
            "block_on_budget_exceed must be boolean when set"
        )

    notes: list[str] = [
        "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
        "remote_index_queried=false · twin_written=false · purchase_executed=false",
        "production_router_verdict=REJECT",
    ]

    try:
        dec = compose_settings_decision_tree_usage_bar(
            selected_model_id=decision.get("selected_model_id"),
            models=decision.get("models"),
            daily_cap_usd=decision.get("daily_cap_usd"),
            spent_usd=decision.get("spent_usd"),
            operator_ack=operator_ack,
            projected_cost_usd_high=decision.get("projected_cost_usd_high"),
            projected_cost_usd_low=decision.get("projected_cost_usd_low"),
            bench_bests=decision.get("bench_bests"),
            focus_task=decision.get("focus_task"),
            nd_shadow=decision.get("nd_shadow"),
            pending_add_model_ids=decision.get("pending_add_model_ids"),
        )
    except SettingsDecisionTreeUsageBarComposeError as e:
        raise MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError(
            str(e)
        ) from e
    notes.extend(f"[decision] {n}" for n in dec.notes)

    try:
        tsp = compose_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk(
            search_query=twin_search_pack.get("search_query"),
            twin_records=twin_search_pack.get("twin_records"),
            html_pack=twin_search_pack.get("html_pack"),
            operator_ack=operator_ack,
            search_limit=twin_search_pack.get("search_limit"),
            require_both=twin_search_pack.get("require_both"),
        )
    except TsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError as e:
        raise MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin_search_pack] {n}" for n in tsp.notes)

    week = _require_nonempty(tsp.week_id, field="week_id")
    session = _require_nonempty(tsp.session_id, field="session_id")
    asset = _require_nonempty(tsp.asset_id, field="asset_id")
    parent = _require_nonempty(tsp.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(tsp.title, field="title")
    account = _require_nonempty(tsp.account_id, field="account_id")

    budget_ok = (not block_budget) or (dec.would_exceed is not True)
    if not budget_ok:
        notes.append(
            "would_exceed=true — pack_ready blocked by budget projection gate"
        )

    if require:
        pack_ready = (
            dec.decision_ready is True
            and tsp.pack_ready is True
            and budget_ok
            and dec.live_router_authorized is False
            and dec.secrets_stored is False
            and dec.live_meter_read is False
            and tsp.remote_index_queried is False
            and tsp.twin_written is False
            and tsp.purchase_executed is False
            and tsp.hosted is False
            and tsp.pdf_primary is False
            and tsp.live_execution_authorized is False
            and tsp.charge_executed is False
            and tsp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and budget_ok
            and dec.live_router_authorized is False
            and tsp.production_router_verdict == "REJECT"
            and tsp.pdf_primary is False
            and tsp.purchase_executed is False
            and (dec.decision_ready is True or tsp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — model decision + twin-search residual ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — decision, twin_search_pack, budget, or operator_ack gate open"
        )

    if (
        dec.live_router_authorized is not False
        or dec.secrets_stored is not False
        or dec.live_meter_read is not False
        or tsp.remote_index_queried is not False
        or tsp.twin_written is not False
        or tsp.purchase_executed is not False
        or tsp.hosted is not False
        or tsp.pdf_primary is not False
        or tsp.live_execution_authorized is not False
        or tsp.charge_executed is not False
        or tsp.production_router_verdict != "REJECT"
    ):
        raise MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "twin_written=false",
            "prompts_injected=false",
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_dispatch_authorized=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        decision=dec,
        twin_search_pack=tsp,
        pack_ready=pack_ready,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        twin_written=False,
        prompts_injected=False,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_dispatch_authorized=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_fetched=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=AUTHORITY,
    )


def format_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk_summary(
    c: MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkCompose,
) -> str:
    exceed = "unknown" if c.decision.would_exceed is None else str(c.decision.would_exceed)
    return (
        f"pack_ready={c.pack_ready} · "
        f"decision_ready={c.decision.decision_ready} · "
        f"twin_ready={c.twin_search_pack.pack_ready} · "
        f"would_exceed={exceed} · "
        f"verdict={c.production_router_verdict} · "
        "live_router_authorized=false · secrets_stored=false"
    )


__all__ = [
    "AUTHORITY",
    "MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkCompose",
    "MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow25MpkComposeError",
    "compose_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk",
    "format_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk_summary",
]
