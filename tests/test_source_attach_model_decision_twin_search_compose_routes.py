"""Route tests for source attach + model decision twin search pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.source_attach_model_decision_twin_search_compose_routes import (
    register_source_attach_model_decision_twin_search_compose_routes,
)
from tests.test_model_decision_twin_search_weekly_html_native_compose_routes import (
    _payload as _dp_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_source_attach_model_decision_twin_search_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, session_id: str = "sess-1") -> dict:
    dp = _dp_payload(operator_ack=operator_ack, session_id=session_id)
    return {
        "sources": {
            "session_id": session_id,
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
                    "url": "https://example.substack.com/p/evals",
                    "html_fragment": "<article>essay…</article>",
                },
            ],
        },
        "decision_pack": {
            "decision": dp["decision"],
            "twin_search_pack": dp["twin_search_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/source-attach-model-decision-twin-search/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["attach_ready"] is True
    assert body["remote_fetched"] is False
    assert body["pdf_primary"] is False
    assert body["live_router_authorized"] is False
    assert body["suite_rewritten"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert (
        body["authority"]
        == "source_attach_model_decision_twin_search_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/source-attach-model-decision-twin-search/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["remote_fetched"] is False


def test_compose_route_session_mismatch_blocks():
    c = _client()
    payload = _payload(operator_ack=True, session_id="sess-1")
    payload["sources"]["session_id"] = "sess-other"
    r = c.post(
        "/research/source-attach-model-decision-twin-search/compose",
        json=payload,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["pdf_primary"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/source-attach-model-decision-twin-search/compose",
        json=payload,
    )
    assert r.status_code == 422
