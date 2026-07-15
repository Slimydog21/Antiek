"""HTML-native view residual over marketplace free MO mow12 (pure).

Short residual moniker hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk.
pdf_view_authorized / pdf_primary always False.
purchase_executed / hosted / charge_executed always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

AUTHORITY = (
    "hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk_compose_advisory"
)

from dataclasses import dataclass
from typing import Any

from substrate.html_native_view_session_authority_compose import (
    HtmlNativeViewSessionAuthorityCompose,
    HtmlNativeViewSessionAuthorityComposeError,
    compose_html_native_view_session_authority,
)
from substrate.mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk_compose import (
    MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose,
    MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError,
    compose_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk,
)


class HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(ValueError):
    """Fail-closed validation for HTML-native + marketplace free residual."""


@dataclass(frozen=True)
class HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose:
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    week_id: str
    operator_id: str
    focus_task: str
    html_view: HtmlNativeViewSessionAuthorityCompose
    market_pack: MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    store_mutated: bool
    purchase_executed: bool
    hosted: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    suite_rewritten: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_index_queried: bool
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
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "week_id": self.week_id,
            "operator_id": self.operator_id,
            "focus_task": self.focus_task,
            "html_view": self.html_view.to_dict(),
            "market_pack": self.market_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "store_mutated": False,
            "purchase_executed": False,
            "hosted": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "suite_rewritten": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_index_queried": False,
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
        raise HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(f"{field} must be a non-empty string")
    return value.strip()


def compose_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk(
    *,
    html_view: object,
    market_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose:
    """HTML-native view + marketplace free residual. Never PDF primary."""
    if not isinstance(operator_ack, bool):
        raise HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError("operator_ack must be an explicit boolean")
    if not isinstance(html_view, dict):
        raise HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError("html_view must be an object")
    if not isinstance(market_pack, dict):
        raise HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError("market_pack must be an object")

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError("require_both must be boolean when set")

    notes: list[str] = [
        "pdf_view_authorized=false · pdf_primary=false · store_mutated=false",
        "purchase_executed=false · hosted=false · charge_executed=false",
        "production_router_verdict=REJECT",
    ]

    try:
        hv = compose_html_native_view_session_authority(
            session_id=html_view.get("session_id"),
            asset_id=html_view.get("asset_id"),
            html_projection_sha=html_view.get("html_projection_sha"),
            view_requested=html_view.get("view_requested"),
            twin_bound=html_view.get("twin_bound"),
            operator_ack=operator_ack,
            twin_substrate_ready=html_view.get("twin_substrate_ready"),
            claimed_format=html_view.get("claimed_format"),
            reading=html_view.get("reading"),
            research=html_view.get("research"),
        )
    except HtmlNativeViewSessionAuthorityComposeError as e:
        raise HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(str(e)) from e
    notes.extend(f"[html_view] {n}" for n in hv.notes)

    try:
        mp = compose_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk(
            market=market_pack.get("market"),
            mo_pack=market_pack.get("mo_pack"),
            operator_ack=operator_ack,
            require_both=market_pack.get("require_both"),
        )
    except MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError as e:
        raise HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(str(e)) from e
    notes.extend(f"[market_pack] {n}" for n in mp.notes)

    session = _require_nonempty(hv.session_id, field="session_id")
    asset = _require_nonempty(hv.asset_id, field="asset_id")
    parent = _require_nonempty(mp.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(mp.title, field="title")
    account = _require_nonempty(mp.account_id, field="account_id")
    week = _require_nonempty(mp.week_id, field="week_id")
    operator = _require_nonempty(mp.operator_id, field="operator_id")
    focus = _require_nonempty(mp.focus_task, field="focus_task")

    session_aligned = mp.session_id == session
    parent_aligned = mp.parent_asset_id == asset or mp.asset_id == asset
    if not session_aligned:
        notes.append(
            f"session_aligned=false — html_view.session_id={session} "
            f"market_pack.session_id={mp.session_id}"
        )
    else:
        notes.append("session_aligned=true")
    if not parent_aligned:
        notes.append(
            f"parent_aligned=false — html_view.asset_id={asset} "
            f"market_pack.parent={parent} asset={mp.asset_id}"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and hv.pack_ready is True
            and mp.pack_ready is True
            and mp.production_router_verdict == "REJECT"
            and hv.pdf_view_authorized is False
            and hv.pdf_primary is False
            and hv.store_mutated is False
            and mp.pdf_view_authorized is False
            and mp.pdf_primary is False
            and mp.purchase_executed is False
            and mp.hosted is False
            and mp.live_execution_authorized is False
            and mp.charge_executed is False
            and mp.twin_written is False
            and mp.live_dispatch_authorized is False
            and mp.remote_fetched is False
            and mp.secrets_stored is False
            and mp.inventory_mutated is False
            and mp.live_router_authorized is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and operator_ack is True
            and mp.production_router_verdict == "REJECT"
            and hv.pdf_primary is False
            and mp.purchase_executed is False
            and mp.hosted is False
            and (hv.pack_ready is True or mp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — HTML-native view + marketplace free residual ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — html_view, market_pack, alignment, or operator_ack gate open"
        )

    if (
        hv.pdf_view_authorized is not False
        or hv.pdf_primary is not False
        or hv.store_mutated is not False
        or mp.pdf_view_authorized is not False
        or mp.pdf_primary is not False
        or mp.purchase_executed is not False
        or mp.hosted is not False
        or mp.live_execution_authorized is not False
        or mp.charge_executed is not False
        or mp.twin_written is not False
        or mp.live_dispatch_authorized is not False
        or mp.remote_fetched is not False
        or mp.secrets_stored is not False
        or mp.inventory_mutated is not False
        or mp.live_router_authorized is not False
        or mp.production_router_verdict != "REJECT"
    ):
        raise HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError("invariant: honesty flags must remain false / REJECT")

    notes.extend(
        (
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "store_mutated=false",
            "purchase_executed=false",
            "hosted=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "suite_rewritten=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_index_queried=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose(
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        week_id=week,
        operator_id=operator,
        focus_task=focus,
        html_view=hv,
        market_pack=mp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        pdf_view_authorized=False,
        pdf_primary=False,
        store_mutated=False,
        purchase_executed=False,
        hosted=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        suite_rewritten=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_index_queried=False,
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


def format_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk_summary(c: HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"html_ready={c.html_view.pack_ready} · "
        f"market_ready={c.market_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "pdf_primary=false · purchase_executed=false · hosted=false"
    )


__all__ = [
    "AUTHORITY",
    "HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose",
    "HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError",
    "compose_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk",
    "format_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk_summary",
]
