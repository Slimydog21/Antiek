from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import hosted_document_routes as routes
from interfaces.research.api.marketplace_host_routes import reset_marketplace_host_store


def _app(owner_id: str) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        request.state.user_id = owner_id
        return await call_next(request)

    app.include_router(routes.hosted_document_router)
    return app


def _request_body() -> dict[str, str]:
    raw = " ".join(f"canonical-word-{i}" for i in range(80)).encode()
    return {
        "content_b64": base64.b64encode(raw).decode(),
        "source_format": "text",
        "investigation_id": "inv-wrestle",
        "title": "Canonical upload",
    }


def test_owner_bound_ingest_returns_canonical_html_and_reuses_event(monkeypatch):
    reset_marketplace_host_store()
    emitted: list[str] = []

    def emit(investigation_id, document_id, extracted, size_bytes, source_uri):
        emitted.append(document_id)
        return "evt-server-owned"

    monkeypatch.setattr(routes, "_emit_document_loaded", emit)
    client = TestClient(_app("owner-a"))
    first = client.post("/hosted-documents/ingest", json=_request_body())
    second = client.post("/hosted-documents/ingest", json=_request_body())

    assert first.status_code == 200
    assert first.json()["owner_id"] == "owner-a"
    assert first.json()["document_loaded_event_id"] == "evt-server-owned"
    assert first.json()["html"].lstrip().lower().startswith("<!doctype html")
    assert "%PDF" not in first.json()["html"]
    assert second.json()["already_hosted"] is True
    assert emitted == [first.json()["document_id"]]


def test_read_refuses_cross_owner_and_non_viewable(monkeypatch):
    reset_marketplace_host_store()
    monkeypatch.setattr(routes, "_emit_document_loaded", lambda *args: "evt")
    owner = TestClient(_app("owner-a"))
    ready = owner.post("/hosted-documents/ingest", json=_request_body()).json()

    forbidden = TestClient(_app("owner-b")).get(
        f"/hosted-documents/{ready['document_id']}/html"
    )
    assert forbidden.status_code == 403

    tiny = _request_body()
    tiny["content_b64"] = base64.b64encode(b"too small").decode()
    receipt = owner.post("/hosted-documents/ingest", json=tiny)
    assert receipt.status_code == 200
    assert receipt.json()["state"] == "non_viewable"
    assert receipt.json()["html"] is None
    blocked = owner.get(f"/hosted-documents/{receipt.json()['document_id']}/html")
    assert blocked.status_code == 409


def test_ingest_rejects_malformed_base64_without_storage():
    reset_marketplace_host_store()
    body = _request_body()
    body["content_b64"] = "%%%not-base64%%%"
    response = TestClient(_app("owner-a")).post("/hosted-documents/ingest", json=body)
    assert response.status_code == 400


def test_html_projection_preserves_the_end_of_a_long_single_block(monkeypatch):
    reset_marketplace_host_store()
    monkeypatch.setattr(routes, "_emit_document_loaded", lambda *args: "evt-long")
    raw = ("start " + "middle " * 1_000 + "canonical-final-token").encode()
    response = TestClient(_app("owner-a")).post(
        "/hosted-documents/ingest",
        json={
            "content_b64": base64.b64encode(raw).decode(),
            "source_format": "text",
            "investigation_id": "inv-long",
        },
    )
    assert response.status_code == 200
    assert "canonical-final-token" in response.json()["html"]


def test_event_emitter_recovers_prior_receipt_before_append(monkeypatch):
    monkeypatch.setattr(
        routes,
        "trajectory",
        lambda investigation_id: [
            {
                "event_id": "evt-before-crash",
                "action_type": "document.loaded",
                "document_id": "hdoc-one",
                "payload": {"content_hash": "sha256:canonical"},
            }
        ],
    )
    monkeypatch.setattr(
        routes,
        "emit_typed",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("prior receipt must prevent a duplicate append")
        ),
    )
    extracted = type(
        "Extracted",
        (),
        {
            "canonical_content_hash": "sha256:canonical",
            "source_format": "text",
            "title": None,
            "page_count": None,
        },
    )()
    event_id = routes._emit_document_loaded(
        "inv", "hdoc-one", extracted, 100, None
    )
    assert event_id == "evt-before-crash"


def test_event_emitter_refuses_generated_id_when_append_is_not_observable(monkeypatch):
    monkeypatch.setattr(routes, "trajectory", lambda investigation_id: [])
    monkeypatch.setattr(routes, "emit_typed", lambda *args, **kwargs: "evt-ghost")
    extracted = type(
        "Extracted",
        (),
        {
            "canonical_content_hash": "sha256:canonical",
            "source_format": "text",
            "title": None,
            "page_count": None,
        },
    )()
    with pytest.raises(RuntimeError, match="not durably observable"):
        routes._emit_document_loaded("inv", "hdoc-one", extracted, 100, None)
