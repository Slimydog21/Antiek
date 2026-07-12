"""Route tests for settings add-model + Antiek-bench source-attach MO pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_add_model_antiek_bench_source_attach_mo_compose_routes import (
    register_settings_add_model_antiek_bench_source_attach_mo_compose_routes,
)
from tests.test_antiek_bench_source_attach_settings_mo_compose_routes import (
    _payload as _bench_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_settings_add_model_antiek_bench_source_attach_mo_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    bp = _bench_payload(operator_ack=operator_ack)
    return {
        "settings": {
            "models": [
                {"model_id": "gpt-5.5", "provider": "openai"},
                {"model_id": "grok-4.5", "provider": "xai"},
            ],
            "pending_add_model_ids": ["mimo-v2", "composer-2.5"],
            "action": "propose_add",
            "daily_cap_usd": 50,
            "spent_usd": 10,
            "selected_model_id": "gpt-5.5",
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
        },
        "bench_pack": {
            "bench": bp["bench"],
            "source_pack": bp["source_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/settings-add-model-antiek-bench-source-attach-mo/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["settings"]["pack_ready"] is True
    assert body["settings"]["inventory_mutated"] is False
    assert body["settings"]["secrets_stored"] is False
    assert body["bench_pack"]["pack_ready"] is True
    assert body["inventory_vs_bench"] == "agree"
    assert body["live_router_authorized"] is False
    assert body["suite_rewritten"] is False
    assert body["inventory_mutated"] is False
    assert body["secrets_stored"] is False
    assert body["remote_fetched"] is False
    assert body["live_execution_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "settings_add_model_antiek_bench_source_attach_mo_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/settings-add-model-antiek-bench-source-attach-mo/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["inventory_mutated"] is False
    assert body["secrets_stored"] is False
    assert body["live_router_authorized"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/settings-add-model-antiek-bench-source-attach-mo/compose",
        json=payload,
    )
    assert r.status_code == 422


def test_compose_route_preview():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["settings"]["action"] = "preview"
    payload["settings"]["pending_add_model_ids"] = []
    r = c.post(
        "/research/settings-add-model-antiek-bench-source-attach-mo/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["settings"]["proposed_new_count"] == 0
    assert body["pack_ready"] is True
    assert body["inventory_mutated"] is False
    assert body["production_router_verdict"] == "REJECT"
