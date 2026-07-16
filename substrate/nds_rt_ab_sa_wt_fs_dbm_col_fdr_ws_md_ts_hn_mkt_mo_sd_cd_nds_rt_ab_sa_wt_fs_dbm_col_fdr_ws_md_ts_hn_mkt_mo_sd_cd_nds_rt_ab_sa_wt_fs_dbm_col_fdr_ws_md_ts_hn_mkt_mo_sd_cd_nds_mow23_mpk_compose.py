"""NotDiamond shadow REJECT residual over recursive twin antiek-bench mow12 (pure).

Short residual moniker nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk.
live_router_authorized always False.
twin_written / backlog_mutated / remote_fetched always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

import sys
sys.setrecursionlimit(50000)

AUTHORITY = (
    "nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk_compose_advisory"
)

from dataclasses import dataclass
from typing import Any

from substrate.notdiamond_shadow_advisory_compose import (
    NotDiamondShadowAdvisoryCompose,
    NotDiamondShadowAdvisoryComposeError,
    compose_notdiamond_shadow_advisory,
)
from substrate.rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk_compose import (
    RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose,
    RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError,
    compose_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk,
)


class NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(ValueError):
    """Fail-closed validation for ND shadow + twin presentation weekly pack."""


@dataclass(frozen=True)
class NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    nd_shadow: NotDiamondShadowAdvisoryCompose
    twin_presentation: RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose
    pack_ready: bool
    live_router_authorized: bool
    twin_written: bool
    prompts_injected: bool
    merge_executed: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    secrets_stored: bool
    live_meter_read: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_index_queried: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
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
            "nd_shadow": self.nd_shadow.to_dict(),
            "twin_presentation": self.twin_presentation.to_dict(),
            "pack_ready": self.pack_ready,
            "live_router_authorized": False,
            "twin_written": False,
            "prompts_injected": False,
            "merge_executed": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_index_queried": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk(
    *,
    nd_shadow: object,
    twin_presentation: object,
    operator_ack: object,
    require_both: object | None = None,
) -> NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose:
    """ND shadow REJECT on twin presentation weekly source-attach. Never live-routes."""
    if not isinstance(operator_ack, bool):
        raise NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(nd_shadow, dict):
        raise NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            "nd_shadow must be an object"
        )
    if not isinstance(twin_presentation, dict):
        raise NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            "twin_presentation must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "production_router_verdict=REJECT — NotDiamond is not production router (§16)",
        "live_router_authorized=false · twin_written=false · backlog_mutated=false",
        "remote_fetched=false · suite_rewritten=false",
    ]

    try:
        nd = compose_notdiamond_shadow_advisory(
            selected_model_id=nd_shadow.get("selected_model_id"),
            nd_recommended_model_id=nd_shadow.get("nd_recommended_model_id"),
            kill_switch_on=nd_shadow.get("kill_switch_on"),
            confidence=nd_shadow.get("confidence"),
            task=nd_shadow.get("task"),
            inventory_model_ids=nd_shadow.get("inventory_model_ids"),
        )
    except NotDiamondShadowAdvisoryComposeError as e:
        raise NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            str(e)
        ) from e
    notes.extend(f"[nd_shadow] {n}" for n in nd.notes)

    if nd.production_router_verdict != "REJECT":
        raise NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            "invariant: production_router_verdict must be REJECT"
        )
    if nd.live_router_authorized is not False:
        raise NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            "invariant: live_router_authorized must be false"
        )

    try:
        twin = compose_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk(
            twin=twin_presentation.get("twin"),
            presentation=twin_presentation.get("presentation"),
            weekly_pack=twin_presentation.get("weekly_pack"),
            operator_ack=operator_ack,
            require_both=twin_presentation.get("require_both"),
        )
    except RtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError as e:
        raise NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin_presentation] {n}" for n in twin.notes)

    parent = _require_nonempty(twin.parent_asset_id, field="parent_asset_id")
    session = _require_nonempty(twin.session_id, field="session_id")
    title = _require_nonempty(twin.title, field="title")
    account = _require_nonempty(twin.account_id, field="account_id")
    week = _require_nonempty(twin.week_id, field="week_id")
    asset = _require_nonempty(twin.asset_id, field="asset_id")

    nd_gate = (
        nd.production_router_verdict == "REJECT"
        and nd.live_router_authorized is False
    )

    if require:
        pack_ready = (
            nd_gate
            and twin.pack_ready is True
            and twin.twin_written is False
            and twin.merge_executed is False
            and twin.backlog_mutated is False
            and twin.store_mutated is False
            and twin.suite_rewritten is False
            and twin.remote_fetched is False
            and twin.pdf_primary is False
            and twin.draft_written is False
            and twin.live_dispatched is False
            and twin.live_router_authorized is False
            and twin.secrets_stored is False
            and twin.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            nd_gate
            and operator_ack is True
            and twin.backlog_mutated is False
            and twin.production_router_verdict == "REJECT"
            and twin.pdf_primary is False
            and (twin.pack_ready is True or nd.shadow_visible is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — ND shadow REJECT + twin presentation weekly "
            "source attach ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — nd_shadow, twin_presentation, or operator_ack gate open"
        )

    if (
        nd.production_router_verdict != "REJECT"
        or nd.live_router_authorized is not False
        or twin.twin_written is not False
        or twin.backlog_mutated is not False
        or twin.remote_fetched is not False
        or twin.pdf_primary is not False
        or twin.production_router_verdict != "REJECT"
    ):
        raise NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_router_authorized=false",
            "twin_written=false",
            "prompts_injected=false",
            "merge_executed=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_index_queried=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        nd_shadow=nd,
        twin_presentation=twin,
        pack_ready=pack_ready,
        live_router_authorized=False,
        twin_written=False,
        prompts_injected=False,
        merge_executed=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        secrets_stored=False,
        live_meter_read=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_index_queried=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk_compose_advisory"
        ),
    )


def format_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk_summary(
    c: NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"nd_verdict={c.nd_shadow.production_router_verdict} · "
        f"shadow_visible={c.nd_shadow.shadow_visible} · "
        f"twin_presentation_ready={c.twin_presentation.pack_ready} · "
        f"week={c.week_id} · "
        "live_router_authorized=false · twin_written=false · backlog_mutated=false"
    )


__all__ = [
    "NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkCompose",
    "NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow23MpkComposeError",
    "compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk",
    "format_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow23_mpk_summary",
]
