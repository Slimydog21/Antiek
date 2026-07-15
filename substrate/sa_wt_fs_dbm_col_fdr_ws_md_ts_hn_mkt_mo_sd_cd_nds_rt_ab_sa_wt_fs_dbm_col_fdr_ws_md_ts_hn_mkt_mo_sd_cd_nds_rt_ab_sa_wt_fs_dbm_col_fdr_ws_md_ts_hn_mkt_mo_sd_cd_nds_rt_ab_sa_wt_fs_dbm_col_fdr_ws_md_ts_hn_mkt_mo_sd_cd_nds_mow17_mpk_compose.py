"""Source-attach residual over write-twin fullscreen FDR MD mow12 (pure).

Short residual moniker sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk.
remote_fetched / pdf_view_authorized / pdf_primary always False.
draft_written / analysis_written / twin_written always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 50000:
    sys.setrecursionlimit(50000)

from dataclasses import dataclass
from typing import Any

from substrate.html_native_source_attach_compose import (
    HtmlNativeSourceAttachCompose,
    HtmlNativeSourceAttachComposeError,
    compose_html_native_source_attach,
)
from substrate.wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk_compose import (
    WtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose,
    WtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError,
    compose_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk,
)

AUTHORITY = "sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk_compose_advisory"


class SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(ValueError):
    """Fail-closed validation for source-attach + write-twin FDR MD mow12 residual."""


@dataclass(frozen=True)
class SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    sources: HtmlNativeSourceAttachCompose
    write_pack: WtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    attach_ready: bool
    remote_fetched: bool
    store_mutated: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    live_dispatched: bool
    pack_dispatched: bool
    live_execution_authorized: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    backlog_mutated: bool
    suite_rewritten: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
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
            "week_id": self.week_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "sources": self.sources.to_dict(),
            "write_pack": self.write_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "attach_ready": self.attach_ready,
            "remote_fetched": False,
            "store_mutated": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "live_execution_authorized": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "backlog_mutated": False,
            "suite_rewritten": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "inventory_mutated": False,
            "charge_executed": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": AUTHORITY,
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk(
    *,
    sources: object,
    write_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose:
    """Source-attach + write-twin FDR MD mow12 residual. Never remote-fetches."""
    if not isinstance(operator_ack, bool):
        raise SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(sources, dict):
        raise SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(
            "sources must be an object"
        )
    if not isinstance(write_pack, dict):
        raise SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(
            "write_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "remote_fetched=false · pdf_view_authorized=false · pdf_primary=false",
        "draft_written=false · analysis_written=false · twin_written=false",
        "production_router_verdict=REJECT",
    ]

    try:
        src = compose_html_native_source_attach(
            session_id=sources.get("session_id"),
            parent_asset_id=sources.get("parent_asset_id"),
            requested_families=sources.get("requested_families"),
            sources=sources.get("sources"),
            operator_ack=operator_ack,
        )
    except HtmlNativeSourceAttachComposeError as e:
        raise SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(str(e)) from e
    notes.extend(f"[sources] {n}" for n in src.notes)

    try:
        wp = compose_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk(
            write=write_pack.get("write"),
            fullscreen_pack=write_pack.get("fullscreen_pack"),
            operator_ack=operator_ack,
            require_both=write_pack.get("require_both"),
        )
    except WtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError as e:
        raise SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(str(e)) from e
    notes.extend(f"[write_pack] {n}" for n in wp.notes)

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
            "session_id mismatch between sources and write_pack — pack_ready blocked"
        )
    else:
        notes.append("session_aligned=true")
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between sources and write_pack — pack_ready blocked"
        )
    else:
        notes.append("parent_aligned=true")

    attach_ready = src.attach_ready

    if require:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and attach_ready is True
            and wp.pack_ready is True
            and src.remote_fetched is False
            and src.pdf_view_authorized is False
            and src.store_mutated is False
            and wp.draft_written is False
            and wp.analysis_written is False
            and wp.merge_executed is False
            and wp.live_dispatched is False
            and wp.live_execution_authorized is False
            and wp.twin_written is False
            and wp.charge_executed is False
            and wp.remote_index_queried is False
            and wp.pdf_primary is False
            and wp.live_router_authorized is False
            and wp.secrets_stored is False
            and wp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and operator_ack is True
            and src.remote_fetched is False
            and wp.production_router_verdict == "REJECT"
            and wp.pdf_primary is False
            and (attach_ready is True or wp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — source attach + write twin FDR MD mow12 ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — sources, write_pack, alignment, or "
            "operator_ack gate open"
        )

    if (
        src.remote_fetched is not False
        or src.pdf_view_authorized is not False
        or src.store_mutated is not False
        or wp.draft_written is not False
        or wp.analysis_written is not False
        or wp.merge_executed is not False
        or wp.live_dispatched is not False
        or wp.live_execution_authorized is not False
        or wp.twin_written is not False
        or wp.charge_executed is not False
        or wp.remote_index_queried is not False
        or wp.pdf_primary is not False
        or wp.live_router_authorized is not False
        or wp.secrets_stored is not False
        or wp.production_router_verdict != "REJECT"
    ):
        raise SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "remote_fetched=false",
            "store_mutated=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "live_execution_authorized=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "backlog_mutated=false",
            "suite_rewritten=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "inventory_mutated=false",
            "charge_executed=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "production_router_verdict=REJECT",
        )
    )

    return SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        sources=src,
        write_pack=wp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        attach_ready=attach_ready,
        remote_fetched=False,
        store_mutated=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        live_dispatched=False,
        pack_dispatched=False,
        live_execution_authorized=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        backlog_mutated=False,
        suite_rewritten=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        inventory_mutated=False,
        charge_executed=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=AUTHORITY,
    )


def format_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk_summary(
    c: SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"attach_ready={c.attach_ready} · "
        f"write_ready={c.write_pack.pack_ready} · "
        f"sources={c.sources.source_count} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "remote_fetched=false · pdf_primary=false · draft_written=false"
    )


__all__ = [
    "SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkCompose",
    "SaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow17MpkComposeError",
    "compose_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk",
    "format_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow17_mpk_summary",
    "AUTHORITY",
]
