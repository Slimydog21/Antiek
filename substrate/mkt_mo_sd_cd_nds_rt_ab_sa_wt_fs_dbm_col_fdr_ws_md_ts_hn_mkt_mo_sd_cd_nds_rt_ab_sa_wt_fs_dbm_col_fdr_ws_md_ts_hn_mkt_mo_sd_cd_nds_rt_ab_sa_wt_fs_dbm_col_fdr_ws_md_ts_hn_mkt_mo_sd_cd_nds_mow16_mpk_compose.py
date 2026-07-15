"""Marketplace free-before-buy residual over Midnight Oil settings mow12 (pure).

Short residual moniker mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk.
purchase_executed / hosted always False.
pdf_view_authorized / pdf_primary always False.
live_execution_authorized / charge_executed always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

AUTHORITY = (
    "mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk_compose_advisory"
)

from dataclasses import dataclass
from typing import Any

from substrate.marketplace_free_before_buy_html_port_compose import (
    MarketplaceFreeBeforeBuyHtmlPortCompose,
    MarketplaceFreeBeforeBuyHtmlPortComposeError,
    compose_marketplace_free_before_buy_html_port,
)
from substrate.mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk_compose import (
    MoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkCompose,
    MoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkComposeError,
    compose_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk,
)


class MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkComposeError(ValueError):
    """Fail-closed validation for marketplace free + MO settings residual."""


@dataclass(frozen=True)
class MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkCompose:
    title: str
    account_id: str
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    operator_id: str
    focus_task: str
    market: MarketplaceFreeBeforeBuyHtmlPortCompose
    mo_pack: MoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkCompose
    account_aligned: bool
    pack_ready: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
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
    record_persisted: bool
    remote_index_queried: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "account_id": self.account_id,
            "week_id": self.week_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "operator_id": self.operator_id,
            "focus_task": self.focus_task,
            "market": self.market.to_dict(),
            "mo_pack": self.mo_pack.to_dict(),
            "account_aligned": self.account_aligned,
            "pack_ready": self.pack_ready,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
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
            "record_persisted": False,
            "remote_index_queried": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": AUTHORITY,
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk(
    *,
    market: object,
    mo_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkCompose:
    """Free-before-buy HTML port + MO settings residual. Never purchases/hosts."""
    if not isinstance(operator_ack, bool):
        raise MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(market, dict):
        raise MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkComposeError(
            "market must be an object"
        )
    if not isinstance(mo_pack, dict):
        raise MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkComposeError(
            "mo_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "purchase_executed=false · hosted=false · pdf_view_authorized=false",
        "live_execution_authorized=false · charge_executed=false",
        "production_router_verdict=REJECT",
    ]

    try:
        mkt = compose_marketplace_free_before_buy_html_port(
            title=market.get("title"),
            account_id=market.get("account_id"),
            free_copy_available=market.get("free_copy_available"),
            purchase_ack=market.get("purchase_ack"),
            port_requested=market.get("port_requested"),
            free_html_projection_sha=market.get("free_html_projection_sha"),
            purchase_html_projection_sha=market.get(
                "purchase_html_projection_sha"
            ),
        )
    except MarketplaceFreeBeforeBuyHtmlPortComposeError as e:
        raise MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkComposeError(
            str(e)
        ) from e
    notes.extend(f"[market] {n}" for n in mkt.notes)

    try:
        mop = compose_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk(
            mo=mo_pack.get("mo"),
            settings_pack=mo_pack.get("settings_pack"),
            operator_ack=operator_ack,
            require_both=mo_pack.get("require_both"),
        )
    except MoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkComposeError as e:
        raise MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkComposeError(
            str(e)
        ) from e
    notes.extend(f"[mo_pack] {n}" for n in mop.notes)

    title = _require_nonempty(mkt.title, field="title")
    account = _require_nonempty(mkt.account_id, field="account_id")
    week = _require_nonempty(mop.week_id, field="week_id")
    session = _require_nonempty(mop.session_id, field="session_id")
    parent = _require_nonempty(mop.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(mop.asset_id, field="asset_id")
    operator = _require_nonempty(mop.operator_id, field="operator_id")
    focus = _require_nonempty(mop.focus_task, field="focus_task")

    account_aligned = mop.account_id == account
    if not account_aligned:
        notes.append(
            "account_id mismatch between market and mo_pack — pack_ready blocked"
        )
    else:
        notes.append("account_aligned=true")

    if require:
        pack_ready = (
            account_aligned
            and mkt.port_ready is True
            and mop.pack_ready is True
            and mkt.purchase_executed is False
            and mkt.hosted is False
            and mkt.pdf_view_authorized is False
            and mop.live_execution_authorized is False
            and mop.charge_executed is False
            and mop.secrets_stored is False
            and mop.inventory_mutated is False
            and mop.live_router_authorized is False
            and mop.live_dispatch_authorized is False
            and mop.remote_fetched is False
            and mop.twin_written is False
            and mop.pdf_primary is False
            and mop.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            account_aligned
            and operator_ack is True
            and mkt.purchase_executed is False
            and mkt.hosted is False
            and mop.production_router_verdict == "REJECT"
            and mop.live_execution_authorized is False
            and (mkt.port_ready is True or mop.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — marketplace free-before-buy + MO settings residual ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — market, mo_pack, alignment, or operator_ack gate open"
        )

    if (
        mkt.purchase_executed is not False
        or mkt.hosted is not False
        or mkt.pdf_view_authorized is not False
        or mop.live_execution_authorized is not False
        or mop.charge_executed is not False
        or mop.secrets_stored is not False
        or mop.inventory_mutated is not False
        or mop.live_router_authorized is not False
        or mop.live_dispatch_authorized is not False
        or mop.remote_fetched is not False
        or mop.twin_written is not False
        or mop.pdf_primary is not False
        or mop.production_router_verdict != "REJECT"
    ):
        raise MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_execution_authorized=false",
            "charge_executed=false",
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

    return MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkCompose(
        title=title,
        account_id=account,
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        operator_id=operator,
        focus_task=focus,
        market=mkt,
        mo_pack=mop,
        account_aligned=account_aligned,
        pack_ready=pack_ready,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
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
        record_persisted=False,
        remote_index_queried=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=AUTHORITY,
    )


def format_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk_summary(
    c: MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"port_ready={c.market.port_ready} · "
        f"path={c.market.path} · "
        f"mo_ready={c.mo_pack.pack_ready} · "
        f"account_aligned={c.account_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "purchase_executed=false · hosted=false · charge_executed=false"
    )


__all__ = [
    "AUTHORITY",
    "MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkCompose",
    "MktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow16MpkComposeError",
    "compose_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk",
    "format_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk_summary",
]
