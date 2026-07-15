"""Workstation residual over model-decision twin-search HTML-native marketplace free mow12 (pure).

Short residual moniker ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk.
record_persisted / prompts_injected always False.
live_router_authorized / secrets_stored / remote_index_queried always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

import sys
sys.setrecursionlimit(50000)

AUTHORITY = (
    "ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk_compose_advisory"
)

from dataclasses import dataclass
from typing import Any

from substrate.md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk_compose import (
    MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkCompose,
    MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkComposeError,
    compose_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk,
)
from substrate.workstation_recursive_record_pack import (
    WorkstationRecursiveRecordPack,
    WorkstationRecursiveRecordPackError,
    compose_workstation_recursive_record_pack,
)


class WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkComposeError(ValueError):
    """Fail-closed validation for workstation + model-decision residual."""


@dataclass(frozen=True)
class WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    records: WorkstationRecursiveRecordPack
    decision_pack: MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkCompose
    session_aligned: bool
    pack_ready: bool
    record_persisted: bool
    prompts_injected: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    twin_written: bool
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
            "records": self.records.to_dict(),
            "decision_pack": self.decision_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "pack_ready": self.pack_ready,
            "record_persisted": False,
            "prompts_injected": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "twin_written": False,
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
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": AUTHORITY,
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk(
    *,
    session_id: object,
    items: object,
    decision_pack: object,
    operator_ack: object,
    max_context_lines: object | None = None,
    require_both: object | None = None,
) -> WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkCompose:
    """Workstation records + model-decision residual. Never persists/injects."""
    if not isinstance(operator_ack, bool):
        raise WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(decision_pack, dict):
        raise WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkComposeError(
            "decision_pack must be an object"
        )
    if not isinstance(items, list):
        raise WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkComposeError(
            "items must be an array"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "record_persisted=false · prompts_injected=false",
        "live_router_authorized=false · secrets_stored=false · remote_index_queried=false",
        "production_router_verdict=REJECT",
    ]

    try:
        rec = compose_workstation_recursive_record_pack(
            session_id=session_id,
            items=items,
            max_context_lines=max_context_lines,
        )
    except WorkstationRecursiveRecordPackError as e:
        raise WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkComposeError(
            str(e)
        ) from e
    notes.extend(f"[records] {n}" for n in rec.notes)

    try:
        dp = compose_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk(
            decision=decision_pack.get("decision"),
            twin_search_pack=decision_pack.get("twin_search_pack"),
            operator_ack=operator_ack,
            require_both=decision_pack.get("require_both"),
            block_on_budget_exceed=decision_pack.get("block_on_budget_exceed"),
        )
    except MdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkComposeError as e:
        raise WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkComposeError(
            str(e)
        ) from e
    notes.extend(f"[decision_pack] {n}" for n in dp.notes)

    session = _require_nonempty(rec.session_id, field="session_id")
    week = _require_nonempty(dp.week_id, field="week_id")
    parent = _require_nonempty(dp.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(dp.asset_id, field="asset_id")
    title = _require_nonempty(dp.title, field="title")
    account = _require_nonempty(dp.account_id, field="account_id")

    session_aligned = dp.session_id == session
    if not session_aligned:
        notes.append(
            f"session_aligned=false — records.session_id={session} "
            f"decision_pack.session_id={dp.session_id}"
        )
    else:
        notes.append("session_aligned=true")

    if require:
        pack_ready = (
            session_aligned is True
            and rec.pack_ready is True
            and dp.pack_ready is True
            and rec.record_persisted is False
            and rec.prompts_injected is False
            and dp.live_router_authorized is False
            and dp.secrets_stored is False
            and dp.live_meter_read is False
            and dp.remote_index_queried is False
            and dp.twin_written is False
            and dp.purchase_executed is False
            and dp.hosted is False
            and dp.pdf_primary is False
            and dp.live_execution_authorized is False
            and dp.charge_executed is False
            and dp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and operator_ack is True
            and rec.record_persisted is False
            and rec.prompts_injected is False
            and dp.production_router_verdict == "REJECT"
            and dp.live_router_authorized is False
            and dp.purchase_executed is False
            and (rec.pack_ready is True or dp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — workstation records + model-decision residual ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — records, decision_pack, alignment, or operator_ack gate open"
        )

    if (
        rec.record_persisted is not False
        or rec.prompts_injected is not False
        or dp.live_router_authorized is not False
        or dp.secrets_stored is not False
        or dp.live_meter_read is not False
        or dp.remote_index_queried is not False
        or dp.twin_written is not False
        or dp.purchase_executed is not False
        or dp.hosted is not False
        or dp.pdf_primary is not False
        or dp.live_execution_authorized is not False
        or dp.charge_executed is not False
        or dp.production_router_verdict != "REJECT"
    ):
        raise WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "record_persisted=false",
            "prompts_injected=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "twin_written=false",
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
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        records=rec,
        decision_pack=dp,
        session_aligned=session_aligned,
        pack_ready=pack_ready,
        record_persisted=False,
        prompts_injected=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        twin_written=False,
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
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=AUTHORITY,
    )


def format_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk_summary(
    c: WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"records_ready={c.records.pack_ready} · "
        f"items={c.records.item_count} · "
        f"decision_ready={c.decision_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "record_persisted=false · prompts_injected=false · live_router_authorized=false"
    )


__all__ = [
    "AUTHORITY",
    "WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkCompose",
    "WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow18MpkComposeError",
    "compose_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk",
    "format_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk_summary",
]
