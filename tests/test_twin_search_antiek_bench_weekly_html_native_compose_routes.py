"""Route tests for twin search + Antiek-bench weekly HTML-native pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.twin_search_antiek_bench_weekly_html_native_compose_routes import (
    register_twin_search_antiek_bench_weekly_html_native_compose_routes,
)
from tests.test_antiek_bench_weekly_html_native_recursive_twin_compose_routes import (
    _payload as _wh_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_twin_search_antiek_bench_weekly_html_native_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, session_id: str = "sess-1") -> dict:
    wh = _wh_payload(operator_ack=operator_ack, session_id=session_id)
    return {
        "search_query": "scaling laws noise",
        "twin_records": [
            {
                "twin_id": "twin-book-1",
                "parent_asset_id": "book-1",
                "insights": [
                    "scaling laws hold under noise in compute-optimal regimes"
                ],
                "questions": [
                    "Where does scaling break under distribution shift?"
                ],
                "source_label": "book-1-twin",
            }
        ],
        "weekly_html": {
            "weekly_learn": wh["weekly_learn"],
            "html_pack": wh["html_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/twin-search-antiek-bench-weekly-html-native/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["hit_count"] >= 1
    assert body["remote_index_queried"] is False
    assert body["suite_rewritten"] is False
    assert body["pdf_primary"] is False
    assert body["twin_written"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "twin_search_antiek_bench_weekly_html_native_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/twin-search-antiek-bench-weekly-html-native/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["remote_index_queried"] is False


def test_compose_route_session_mismatch_blocks():
    c = _client()
    payload = _payload(operator_ack=True, session_id="sess-1")
    payload["weekly_html"]["html_pack"]["html_view"]["session_id"] = "sess-other"
    r = c.post(
        "/research/twin-search-antiek-bench-weekly-html-native/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["twin_written"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/twin-search-antiek-bench-weekly-html-native/compose",
        json=payload,
    )
    assert r.status_code == 422
