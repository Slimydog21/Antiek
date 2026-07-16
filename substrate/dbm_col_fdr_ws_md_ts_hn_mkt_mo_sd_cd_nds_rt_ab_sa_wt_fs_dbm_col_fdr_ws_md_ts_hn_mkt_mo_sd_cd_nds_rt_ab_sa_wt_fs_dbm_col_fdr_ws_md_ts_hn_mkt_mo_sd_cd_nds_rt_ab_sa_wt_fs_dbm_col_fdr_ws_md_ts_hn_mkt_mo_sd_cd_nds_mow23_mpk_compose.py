"""Draft-before-full-merge residual over collective floating DR tip residual mow12 (pure).

Short residual moniker dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk.
draft_written / merge_executed always False.
live_dispatched / pack_dispatched / analysis_written always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 50000:
    sys.setrecursionlimit(50000)

from dataclasses import dataclass
from typing import Any

from substrate.col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk_compose import (
    ColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose,
    ColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError,
    compose_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk,
)
from substrate.floating_draft_before_full_merge_gate_compose import (
    FloatingDraftBeforeFullMergeGateCompose,
    FloatingDraftBeforeFullMergeGateComposeError,
    compose_floating_draft_before_full_merge_gate,
)

AUTHORITY = "dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk_compose_advisory"


class DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(ValueError):
    """Fail-closed validation for draft-before-merge + collective floating DR tip residual mow12."""


@dataclass(frozen=True)
class DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    draft_gate: FloatingDraftBeforeFullMergeGateCompose
    collective_pack: ColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    draft_written: bool
    merge_executed: bool
    live_dispatched: bool
    pack_dispatched: bool
    analysis_written: bool
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
            "draft_gate": self.draft_gate.to_dict(),
            "collective_pack": self.collective_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "draft_written": False,
            "merge_executed": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "analysis_written": False,
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
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": AUTHORITY,
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk(
    *,
    draft_gate: object,
    collective_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose:
    """Draft-before-merge + collective floating DR tip residual mow12. Never writes/merges."""
    if not isinstance(operator_ack, bool):
        raise DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(draft_gate, dict):
        raise DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            "draft_gate must be an object"
        )
    if not isinstance(collective_pack, dict):
        raise DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            "collective_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "draft_written=false · merge_executed=false · live_dispatched=false",
        "pack_dispatched=false · analysis_written=false · record_persisted=false",
        "prompts_injected=false · production_router_verdict=REJECT",
    ]

    try:
        dg = compose_floating_draft_before_full_merge_gate(
            session_id=draft_gate.get("session_id"),
            parent_asset_id=draft_gate.get("parent_asset_id"),
            sources=draft_gate.get("sources"),
            stage=draft_gate.get("stage"),
            operator_ack=operator_ack,
            parent_excerpt=draft_gate.get("parent_excerpt"),
            full_merge_ack=draft_gate.get("full_merge_ack"),
        )
    except FloatingDraftBeforeFullMergeGateComposeError as e:
        raise DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(str(e)) from e
    notes.extend(f"[draft_gate] {n}" for n in dg.notes)

    try:
        cp = compose_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk(
            multiselect=collective_pack.get("multiselect"),
            floating_pack=collective_pack.get("floating_pack"),
            operator_ack=operator_ack,
            require_both=collective_pack.get("require_both"),
        )
    except ColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError as e:
        raise DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(str(e)) from e
    notes.extend(f"[collective_pack] {n}" for n in cp.notes)

    week = _require_nonempty(cp.week_id, field="week_id")
    session = _require_nonempty(dg.session_id, field="session_id")
    parent = _require_nonempty(dg.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(cp.asset_id, field="asset_id")
    title = _require_nonempty(cp.title, field="title")
    account = _require_nonempty(cp.account_id, field="account_id")

    session_aligned = cp.session_id == session
    parent_aligned = cp.parent_asset_id == parent or cp.asset_id == parent
    if not session_aligned:
        notes.append(
            f"session_aligned=false — draft_gate.session_id={session} "
            f"collective_pack.session_id={cp.session_id}"
        )
    else:
        notes.append("session_aligned=true")
    if not parent_aligned:
        notes.append(
            f"parent_aligned=false — draft_gate.parent={parent} "
            f"collective_pack.parent={cp.parent_asset_id} asset={cp.asset_id}"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and dg.gate_ready is True
            and cp.pack_ready is True
            and dg.draft_written is False
            and dg.merge_executed is False
            and dg.live_dispatched is False
            and cp.live_dispatched is False
            and cp.pack_dispatched is False
            and cp.merge_executed is False
            and cp.analysis_written is False
            and cp.record_persisted is False
            and cp.prompts_injected is False
            and cp.live_router_authorized is False
            and cp.secrets_stored is False
            and cp.remote_index_queried is False
            and cp.twin_written is False
            and cp.purchase_executed is False
            and cp.hosted is False
            and cp.pdf_primary is False
            and cp.live_execution_authorized is False
            and cp.charge_executed is False
            and cp.draft_written is False
            and cp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and operator_ack is True
            and dg.draft_written is False
            and dg.merge_executed is False
            and cp.live_dispatched is False
            and cp.pack_dispatched is False
            and cp.record_persisted is False
            and cp.production_router_verdict == "REJECT"
            and cp.live_router_authorized is False
            and (dg.gate_ready is True or cp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — draft-before-merge + collective floating DR tip residual mow12 ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — draft_gate, collective_pack, alignment, or "
            "operator_ack gate open"
        )

    if (
        dg.draft_written is not False
        or dg.merge_executed is not False
        or dg.live_dispatched is not False
        or cp.live_dispatched is not False
        or cp.pack_dispatched is not False
        or cp.merge_executed is not False
        or cp.analysis_written is not False
        or cp.record_persisted is not False
        or cp.prompts_injected is not False
        or cp.live_router_authorized is not False
        or cp.secrets_stored is not False
        or cp.remote_index_queried is not False
        or cp.twin_written is not False
        or cp.purchase_executed is not False
        or cp.hosted is not False
        or cp.pdf_primary is not False
        or cp.live_execution_authorized is not False
        or cp.charge_executed is not False
        or cp.draft_written is not False
        or cp.production_router_verdict != "REJECT"
    ):
        raise DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "draft_written=false",
            "merge_executed=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "analysis_written=false",
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
            "production_router_verdict=REJECT",
        )
    )

    return DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        draft_gate=dg,
        collective_pack=cp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        draft_written=False,
        merge_executed=False,
        live_dispatched=False,
        pack_dispatched=False,
        analysis_written=False,
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
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=AUTHORITY,
    )


def format_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk_summary(
    c: DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"gate_ready={c.draft_gate.gate_ready} · "
        f"collective_ready={c.collective_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "draft_written=false · merge_executed=false · live_dispatched=false"
    )


__all__ = [
    "DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose",
    "DbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError",
    "compose_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk",
    "format_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk_summary",
    "AUTHORITY",
]
