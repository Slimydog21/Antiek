"""Midnight Oil price-ceiling residual re-entry over marketplace free mow28 (pure).

Short residual moniker mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk.
live_execution_authorized / charge_executed always False.
purchase_executed / hosted / pdf_primary always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

import sys
sys.setrecursionlimit(50000)

AUTHORITY = (
    "mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_compose_advisory"
)

from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil_price_ceiling_approval_compose import (
    MidnightOilPriceCeilingApprovalCompose,
    MidnightOilPriceCeilingApprovalComposeError,
    compose_midnight_oil_price_ceiling_approval,
)
from substrate.mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow28_mpk_compose import (
    MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow28MpkCompose,
    MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow28MpkComposeError,
    compose_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow28_mpk,
)


class MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkComposeError(ValueError):
    """Fail-closed validation for MO re-entry over marketplace free residual."""


@dataclass(frozen=True)
class MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    operator_id: str
    focus_task: str
    mo: MidnightOilPriceCeilingApprovalCompose
    mkt_pack: MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow28MpkCompose
    account_aligned: bool
    pack_ready: bool
    live_execution_authorized: bool
    charge_executed: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
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
    pdf_view_authorized: bool
    pdf_primary: bool
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
            "operator_id": self.operator_id,
            "focus_task": self.focus_task,
            "mo": self.mo.to_dict(),
            "mkt_pack": self.mkt_pack.to_dict(),
            "account_aligned": self.account_aligned,
            "pack_ready": self.pack_ready,
            "live_execution_authorized": False,
            "charge_executed": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
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
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_index_queried": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": AUTHORITY,
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkComposeError(f"{field} must be a non-empty string")
    return value.strip()


def compose_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk(
    *,
    mo: object,
    mkt_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkCompose:
    """MO price-ceiling re-entry + marketplace free residual. Never live-executes."""
    if not isinstance(operator_ack, bool):
        raise MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkComposeError("operator_ack must be an explicit boolean")
    if not isinstance(mo, dict):
        raise MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkComposeError("mo must be an object")
    if not isinstance(mkt_pack, dict):
        raise MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkComposeError("mkt_pack must be an object")

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkComposeError("require_both must be boolean when set")

    notes: list[str] = [
        "live_execution_authorized=false · charge_executed=false",
        "purchase_executed=false · hosted=false · pdf_primary=false",
        "production_router_verdict=REJECT",
    ]

    try:
        mo_c = compose_midnight_oil_price_ceiling_approval(
            operator_id=mo.get("operator_id"),
            work_minutes=mo.get("work_minutes"),
            goals=mo.get("goals"),
            usd_per_hour=mo.get("usd_per_hour"),
            goal_intensity=mo.get("goal_intensity"),
            approved_ceiling_usd=mo.get("approved_ceiling_usd"),
            below_recommend_override=mo.get("below_recommend_override"),
            price_ceiling_ack=mo.get("price_ceiling_ack"),
            operator_ack=operator_ack,
            unattended_ack=mo.get("unattended_ack"),
            spend_consent=mo.get("spend_consent"),
            stage=mo.get("stage"),
        )
    except MidnightOilPriceCeilingApprovalComposeError as e:
        raise MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkComposeError(str(e)) from e
    notes.extend(f"[mo] {n}" for n in mo_c.notes)

    try:
        mkt_c = compose_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow28_mpk(
            market=mkt_pack.get("market"),
            mo_pack=mkt_pack.get("mo_pack"),
            operator_ack=operator_ack,
            require_both=mkt_pack.get("require_both"),
        )
    except MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow28MpkComposeError as e:
        raise MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkComposeError(str(e)) from e
    notes.extend(f"[mkt_pack] {n}" for n in mkt_c.notes)

    operator = _require_nonempty(mo_c.operator_id, field="operator_id")
    week = _require_nonempty(mkt_c.week_id, field="week_id")
    session = _require_nonempty(mkt_c.session_id, field="session_id")
    parent = _require_nonempty(mkt_c.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(mkt_c.asset_id, field="asset_id")
    title = _require_nonempty(mkt_c.title, field="title")
    account = _require_nonempty(mkt_c.account_id, field="account_id")
    focus = _require_nonempty(mkt_c.focus_task, field="focus_task")

    account_aligned = mkt_c.account_id == account
    if not account_aligned:
        notes.append("account_id mismatch — pack_ready blocked")
    else:
        notes.append("account_aligned=true")

    if require:
        pack_ready = (
            account_aligned
            and mo_c.pack_ready is True
            and mkt_c.pack_ready is True
            and mo_c.live_execution_authorized is False
            and mo_c.charge_executed is False
            and mkt_c.purchase_executed is False
            and mkt_c.hosted is False
            and mkt_c.pdf_view_authorized is False
            and mkt_c.pdf_primary is False
            and mkt_c.live_execution_authorized is False
            and mkt_c.charge_executed is False
            and mkt_c.secrets_stored is False
            and mkt_c.inventory_mutated is False
            and mkt_c.live_router_authorized is False
            and mkt_c.live_dispatch_authorized is False
            and mkt_c.remote_fetched is False
            and mkt_c.twin_written is False
            and mkt_c.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            account_aligned
            and operator_ack is True
            and mo_c.live_execution_authorized is False
            and mo_c.charge_executed is False
            and mkt_c.purchase_executed is False
            and mkt_c.production_router_verdict == "REJECT"
            and (mo_c.pack_ready is True or mkt_c.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — Midnight Oil price-ceiling + marketplace free residual ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — mo, mkt_pack, alignment, or operator_ack gate open"
        )

    if (
        mo_c.live_execution_authorized is not False
        or mo_c.charge_executed is not False
        or mkt_c.purchase_executed is not False
        or mkt_c.hosted is not False
        or mkt_c.pdf_view_authorized is not False
        or mkt_c.pdf_primary is not False
        or mkt_c.live_execution_authorized is not False
        or mkt_c.charge_executed is not False
        or mkt_c.secrets_stored is not False
        or mkt_c.inventory_mutated is not False
        or mkt_c.live_router_authorized is not False
        or mkt_c.live_dispatch_authorized is not False
        or mkt_c.remote_fetched is not False
        or mkt_c.twin_written is not False
        or mkt_c.production_router_verdict != "REJECT"
    ):
        raise MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkComposeError("invariant: honesty flags must remain false / REJECT")

    notes.extend(
        (
            "live_execution_authorized=false",
            "charge_executed=false",
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
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
            "record_persisted=false",
            "remote_index_queried=false",
            "production_router_verdict=REJECT",
        )
    )

    return MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        operator_id=operator,
        focus_task=focus,
        mo=mo_c,
        mkt_pack=mkt_c,
        account_aligned=account_aligned,
        pack_ready=pack_ready,
        live_execution_authorized=False,
        charge_executed=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
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
        pdf_view_authorized=False,
        pdf_primary=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        remote_index_queried=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=AUTHORITY,
    )


def format_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_summary(c: MoMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow29MpkCompose) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"mo_ready={c.mo.pack_ready} · "
        f"ceiling_approved={c.mo.ceiling_approved} · "
        f"mkt_ready={c.mkt_pack.pack_ready} · "
        f"stage={c.mo.stage} · "
        f"verdict={c.production_router_verdict} · "
        f"live_execution_authorized=false · charge_executed=false · purchase_executed=false"
    )
