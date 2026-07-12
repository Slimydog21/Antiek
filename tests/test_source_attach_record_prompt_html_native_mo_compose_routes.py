"""Route tests for source attach + record→prompt HTML pack."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.source_attach_record_prompt_html_native_mo_compose_routes import (
    register_source_attach_record_prompt_html_native_mo_compose_routes,
)
from tests.test_record_prompt_html_native_recursive_twin_mo_compose_routes import (
    _payload as _record_payload,
)


def _client() -> TestClient:
    app = FastAPI()
    register_source_attach_record_prompt_html_native_mo_compose_routes(app)
    return TestClient(app)


def _payload(*, operator_ack: bool = True, would_exceed: bool = False) -> dict:
    rp = _record_payload(operator_ack=operator_ack)
    return {
        "sources": {
            "session_id": "sess-1",
            "parent_asset_id": "book-1",
            "requested_families": ["arxiv", "substack"],
            "sources": [
                {
                    "source_id": "arx-1",
                    "family": "arxiv",
                    "title": "Scaling Laws for Neural Language Models",
                    "external_id": "arxiv:2001.08361",
                    "html_fragment": "<article>abstract…</article>",
                },
                {
                    "source_id": "sub-1",
                    "family": "substack",
                    "title": "The Batch essay",
                    "external_id": "substack:thebatch",
                    "url": "https://example.substack.com/p/x",
                    "html_fragment": "<article>essay…</article>",
                },
            ],
            "quality_overall": 0.85,
            "quality_floor": 0.7,
            "would_exceed": would_exceed,
        },
        "record_html": {
            "record_prompt": rp["record_prompt"],
            "html_pack": rp["html_pack"],
        },
        "operator_ack": operator_ack,
    }


def test_compose_route():
    c = _client()
    r = c.post(
        "/research/source-attach-record-prompt-html-native-mo/compose",
        json=_payload(operator_ack=True),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack_ready"] is True
    assert body["remote_fetched"] is False
    assert body["prompts_injected"] is False
    assert body["pdf_primary"] is False
    assert body["production_router_verdict"] == "REJECT"
    assert body["live_router_authorized"] is False
    assert (
        body["authority"]
        == "source_attach_record_prompt_html_native_mo_compose_advisory"
    )


def test_compose_route_ack_false():
    c = _client()
    r = c.post(
        "/research/source-attach-record-prompt-html-native-mo/compose",
        json=_payload(operator_ack=False),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["remote_fetched"] is False


def test_compose_route_would_exceed_blocks():
    c = _client()
    r = c.post(
        "/research/source-attach-record-prompt-html-native-mo/compose",
        json=_payload(operator_ack=True, would_exceed=True),
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_ready"] is False
    assert r.json()["remote_fetched"] is False


def test_compose_route_missing_operator_ack_422():
    c = _client()
    payload = _payload()
    del payload["operator_ack"]
    r = c.post(
        "/research/source-attach-record-prompt-html-native-mo/compose",
        json=payload,
    )
    assert r.status_code == 422
