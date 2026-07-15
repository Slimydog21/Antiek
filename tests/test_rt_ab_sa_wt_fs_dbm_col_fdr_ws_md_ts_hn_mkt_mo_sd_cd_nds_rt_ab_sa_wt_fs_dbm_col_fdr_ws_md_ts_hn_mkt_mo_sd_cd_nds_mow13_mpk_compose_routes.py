"""Route tests for recursive twin residual over antiek-bench mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose_routes import (
    register_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose_routes,
)
from substrate.rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose import (
    AUTHORITY,
)
from tests.test_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose import (
    PRESENTATION,
    TWIN,
    WEEKLY_PACK,
)

_PATH = (
    "/research/rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-mow13-mpk/compose"
)


def _client() -> TestClient:
    app = FastAPI()
    register_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "twin": TWIN,
        "presentation": PRESENTATION,
        "weekly_pack": WEEKLY_PACK,
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["presentation"]["presentation_ready"] is True
    assert body["weekly_pack"]["pack_ready"] is True
    assert body["session_aligned"] is True
    assert body["parent_aligned"] is True
    assert body["twin_written"] is False
    assert body["backlog_mutated"] is False
    assert body["suite_rewritten"] is False
    assert body["remote_fetched"] is False
    assert body["pdf_primary"] is False
    assert body["draft_written"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert body["authority"] == AUTHORITY


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["twin_written"] is False
    assert body["backlog_mutated"] is False
    assert body["remote_fetched"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_session_mismatch():
    from tests.test_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose import (
        SOURCE_PACK,
        SOURCES,
    )

    c = _client()
    payload = _payload(operator_ack=True)
    payload["weekly_pack"] = {
        **WEEKLY_PACK,
        "source_pack": {
            **SOURCE_PACK,
            "sources": {**SOURCES, "session_id": "sess-other"},
        },
    }
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_aligned"] is False
    assert body["pack_ready"] is False
    assert body["production_router_verdict"] == "REJECT"


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
