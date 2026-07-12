"""Route tests for source attach + settings decision MO pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.source_attach_settings_decision_mo_compose_routes import (
    register_source_attach_settings_decision_mo_compose_routes,
)
from tests.test_settings_decision_mo_unattended_fullscreen_compose_routes import (
    _payload as _settings_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_source_attach_settings_decision_mo_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True) -> dict:
    sm = _settings_payload(operator_ack=operator_ack)
    return {
        "sources": {
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "requested_families": ["arxiv", "substack"],
            "sources": [
                {
                    "source_id": "arx-1",
                    "family": "arxiv",
                    "title": "Scaling Laws under Noise",
                    "external_id": "arxiv:2301.00001",
                    "html_fragment": "<article>abstract…</article>",
                },
                {
                    "source_id": "sub-1",
                    "family": "substack",
                    "title": "Research notes on evals",
                    "external_id": "substack:evals",
                    "url": "https://example.substack.com/p/evals",
                    "html_fragment": "<article>essay…</article>",
                },
            ],
        },
        "settings_mo": {
            "decision": sm["decision"],
            "mo_pack": sm["mo_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/source-attach-settings-decision-mo/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["remote_fetched"] is False
    assert body["pdf_primary"] is False
    assert body["live_router_authorized"] is False
    assert body["live_execution_authorized"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "source_attach_settings_decision_mo_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/source-attach-settings-decision-mo/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["remote_fetched"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/source-attach-settings-decision-mo/compose",
        json=payload,
    )
    assert r.status_code == 422
