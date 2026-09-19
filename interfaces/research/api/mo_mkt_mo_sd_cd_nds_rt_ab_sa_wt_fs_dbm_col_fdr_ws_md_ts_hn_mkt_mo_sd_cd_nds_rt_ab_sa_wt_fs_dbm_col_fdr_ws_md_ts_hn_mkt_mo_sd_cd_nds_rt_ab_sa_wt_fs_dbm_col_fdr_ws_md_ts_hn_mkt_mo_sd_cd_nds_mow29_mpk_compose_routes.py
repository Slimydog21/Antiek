"""Advisory routes for mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk (pure compose only; never dispatches)."""

from __future__ import annotations

from typing import Any

from substrate.mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_compose import (
    AUTHORITY,
    MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkComposeError,
    compose_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk,
    format_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_summary,
)


def post_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_compose(body: dict[str, Any]) -> dict[str, Any]:
    """Compose MO re-entry pack. Never live-executes or charges."""
    if not isinstance(body, dict):
        return {
            "ok": False,
            "error": "body must be an object",
            "authority": AUTHORITY,
            "live_execution_authorized": False,
            "charge_executed": False,
            "production_router_verdict": "REJECT",
        }
    try:
        c = compose_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk(
            mo=body.get("mo"),
            mkt_pack=body.get("mkt_pack"),
            operator_ack=body.get("operator_ack"),
            require_both=body.get("require_both"),
        )
    except MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkComposeError as e:
        return {
            "ok": False,
            "error": str(e),
            "authority": AUTHORITY,
            "live_execution_authorized": False,
            "charge_executed": False,
            "purchase_executed": False,
            "production_router_verdict": "REJECT",
        }
    d = c.to_dict()
    d["ok"] = True
    d["summary"] = format_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_summary(c)
    return d
