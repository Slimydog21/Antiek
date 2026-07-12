"""Route tests for ND shadow + source-attach weekly learn twin presentation."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.nd_shadow_source_attach_weekly_learn_twin_presentation_compose_routes import (
    register_nd_shadow_source_attach_weekly_learn_twin_presentation_compose_routes,
)
from tests.test_nd_shadow_source_attach_weekly_learn_twin_presentation_compose import (
    ND_SHADOW,
    SOURCE_PACK,
)


def _client() -> TestClient:
    app = FastAPI()
    register_nd_shadow_source_attach_weekly_learn_twin_presentation_compose_routes(
        app
    )
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    return {
        "nd_shadow": ND_SHADOW,
        "source_pack": SOURCE_PACK,
        "operator_ack": operator_ack,
    }


_PATH = "/research/nd-shadow-source-attach-weekly-learn-twin-presentation/compose"


def test_compose_route():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=True))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["nd_shadow"]["production_router_verdict"] == "REJECT"
    assert body["nd_shadow"]["live_router_authorized"] is False
    assert body["source_pack"]["pack_ready"] is True
    assert body["live_router_authorized"] is False
    assert body["remote_fetched"] is False
    assert body["backlog_mutated"] is False
    assert body["suite_rewritten"] is False
    assert body["twin_written"] is False
    assert body["merge_executed"] is False
    assert body["draft_written"] is False
    assert body["pdf_primary"] is False
    assert body["secrets_stored"] is False
    assert body["remote_index_queried"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "nd_shadow_source_attach_weekly_learn_twin_presentation_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(_PATH, json=_payload(operator_ack=False))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is False
    assert body["live_router_authorized"] is False
    assert body["nd_shadow"]["production_router_verdict"] == "REJECT"


def test_compose_route_would_exceed():
    c = _client()
    payload = _payload(operator_ack=True)
    payload["source_pack"] = {
        **SOURCE_PACK,
        "sources": {**SOURCE_PACK["sources"], "would_exceed": True},
    }
    r = c.post(_PATH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source_pack"]["sources"]["pack_ready"] is False
    assert body["pack_ready"] is False
    assert body["live_router_authorized"] is False
    assert body["remote_fetched"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(_PATH, json=payload)
    assert r.status_code == 422
