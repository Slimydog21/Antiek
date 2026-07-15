"""Competition DR quality residual over ND shadow recursive twin mow12 (pure).

Short residual moniker cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk.
live_dispatch_authorized / remote_fetched / backlog_mutated always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

AUTHORITY = (
    "cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_compose_advisory"
)

from dataclasses import dataclass
from typing import Any

from substrate.competition_dr_quality_source_pack_compose import (
    CompetitionDrQualitySourcePackCompose,
    CompetitionDrQualitySourcePackComposeError,
    compose_competition_dr_quality_source_pack,
)
from substrate.nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_compose import (
    NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkCompose,
    NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkComposeError,
    compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk,
)


class CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkComposeError(ValueError):
    """Fail-closed validation for competition DR + ND shadow twin presentation weekly."""


@dataclass(frozen=True)
class CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkCompose:
    session_id: str
    week_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    competition: CompetitionDrQualitySourcePackCompose
    nd_pack: NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkCompose
    session_aligned: bool
    pack_ready: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    production_router_verdict: str
    live_router_authorized: bool
    twin_written: bool
    purchase_executed: bool
    hosted: bool
    prompts_injected: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    charge_executed: bool
    live_execution_authorized: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    record_persisted: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "week_id": self.week_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "competition": self.competition.to_dict(),
            "nd_pack": self.nd_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "pack_ready": self.pack_ready,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "twin_written": False,
            "purchase_executed": False,
            "hosted": False,
            "prompts_injected": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "charge_executed": False,
            "live_execution_authorized": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "record_persisted": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "notes": list(self.notes),
            "authority": (
                "cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
    *,
    competition: object,
    nd_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkCompose:
    """Competition DR quality over ND shadow twin presentation weekly. Never live-dispatches."""
    if not isinstance(operator_ack, bool):
        raise CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(competition, dict):
        raise CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkComposeError(
            "competition must be an object"
        )
    if not isinstance(nd_pack, dict):
        raise CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkComposeError(
            "nd_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
        "twin_written=false · suite_rewritten=false",
    ]

    try:
        comp = compose_competition_dr_quality_source_pack(
            session_id=competition.get("session_id"),
            competitor_decisions=competition.get("competitor_decisions"),
            focus_areas=competition.get("focus_areas"),
            requested_families=competition.get("requested_families"),
            citations=competition.get("citations"),
            filter_to_selected_families=competition.get(
                "filter_to_selected_families"
            ),
            quality_overall=competition.get("quality_overall"),
            quality_floor=competition.get("quality_floor"),
            would_exceed=competition.get("would_exceed"),
            operator_override=competition.get("operator_override"),
            operator_ack=operator_ack,
            require_no_behind_gaps=competition.get("require_no_behind_gaps"),
        )
    except CompetitionDrQualitySourcePackComposeError as e:
        raise CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkComposeError(str(e)) from e
    notes.extend(f"[competition] {n}" for n in comp.notes)

    try:
        nd = compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
            nd_shadow=nd_pack.get("nd_shadow"),
            twin_presentation=nd_pack.get("twin_presentation"),
            operator_ack=operator_ack,
            require_both=nd_pack.get("require_both"),
        )
    except NdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkComposeError as e:
        raise CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkComposeError(str(e)) from e
    notes.extend(f"[nd_pack] {n}" for n in nd.notes)

    session = _require_nonempty(comp.session_id, field="session_id")
    week = _require_nonempty(nd.week_id, field="week_id")
    parent = _require_nonempty(nd.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(nd.asset_id, field="asset_id")
    title = _require_nonempty(nd.title, field="title")
    account = _require_nonempty(nd.account_id, field="account_id")

    session_aligned = nd.session_id == session
    if not session_aligned:
        notes.append(
            "session_id mismatch between competition and nd_pack — pack_ready blocked"
        )
    else:
        notes.append("session_aligned=true")

    if require:
        pack_ready = (
            session_aligned is True
            and comp.pack_ready is True
            and nd.pack_ready is True
            and nd.production_router_verdict == "REJECT"
            and comp.live_dispatch_authorized is False
            and comp.remote_fetched is False
            and comp.backlog_mutated is False
            and nd.live_router_authorized is False
            and nd.twin_written is False
            and nd.backlog_mutated is False
            and nd.remote_fetched is False
            and nd.pdf_primary is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and operator_ack is True
            and nd.production_router_verdict == "REJECT"
            and comp.remote_fetched is False
            and nd.live_router_authorized is False
            and (comp.pack_ready is True or nd.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — competition DR + ND shadow twin presentation weekly "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — competition, nd_pack, alignment, or operator_ack gate open"
        )

    if (
        comp.live_dispatch_authorized is not False
        or comp.remote_fetched is not False
        or comp.backlog_mutated is not False
        or nd.production_router_verdict != "REJECT"
        or nd.live_router_authorized is not False
        or nd.twin_written is not False
        or nd.backlog_mutated is not False
        or nd.remote_fetched is not False
        or nd.pdf_primary is not False
    ):
        raise CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "twin_written=false",
            "purchase_executed=false",
            "hosted=false",
            "prompts_injected=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "charge_executed=false",
            "live_execution_authorized=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "record_persisted=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
        )
    )

    return CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkCompose(
        session_id=session,
        week_id=week,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        competition=comp,
        nd_pack=nd,
        session_aligned=session_aligned,
        pack_ready=pack_ready,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        twin_written=False,
        purchase_executed=False,
        hosted=False,
        prompts_injected=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        charge_executed=False,
        live_execution_authorized=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        record_persisted=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        notes=tuple(notes),
        authority=(
            "cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_compose_advisory"
        ),
    )


def format_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_summary(
    c: CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"competition_ready={c.competition.pack_ready} · "
        f"behind={c.competition.competition.behind_count} · "
        f"nd_pack_ready={c.nd_pack.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        "live_dispatch_authorized=false · live_router_authorized=false · remote_fetched=false"
    )


__all__ = [
    "AUTHORITY",
    "CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkCompose",
    "CdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow15MpkComposeError",
    "compose_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk",
    "format_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_summary",
]
