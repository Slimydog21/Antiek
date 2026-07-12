"""Route tests for Antiek-bench weekly learn + twin presentation write collective."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_routes import (
    register_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_routes,
)
from tests.test_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose import (
    TWIN_PRESENTATION_PACK,
    WEEKLY_LEARN,
)


def _client() -> TestClient:
    app = FastAPI()
    register_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "weekly_learn": WEEKLY_LEARN,
        "twin_presentation_pack": TWIN_PRESENTATION_PACK,
        "operator_ack": operator_ack,
    }


_PATH = (
    "/research/antiek-bench-weekly-learn-recursive-twin-presentation-write-collective/compose"
)


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["learn_ready"] is True
    assert body["weekly_learn"]["learn_ready"] is True
    assert body["twin_presentation_pack"]["pack_ready"] is True
    assert body["backlog_mutated"] is False
    assert body["store_mutated"] is False
    assert body["suite_rewritten"] is False
    assert body["twin_written"] is False
    assert body["merge_executed"] is False
    assert body["draft_written"] is False
    assert body["live_dispatched"] is False
    assert body["live_router_authorized"] is False
    assert body["secrets_stored"] is False
    assert body["remote_index_queried"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["learn_ready"] is False
    assert body["backlog_mutated"] is False


def test_compose_route_sparse_events():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["weekly_learn"] = {**WEEKLY_LEARN, "min_events_per_task": 5}
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["weekly_learn"]["learn_ready"] is False
    assert body["pack_ready"] is False
    assert body["backlog_mutated"] is False
    assert body["suite_rewritten"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
