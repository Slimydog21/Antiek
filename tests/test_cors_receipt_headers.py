"""Browser receipt visibility through the real application's CORS middleware."""

from __future__ import annotations

import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app

RECEIPT_HEADERS = {
    "X-Artifact-ID": "artifact-example",
    "X-Artifact-Style": "paper",
    "X-Artifact-Version": "1",
    "X-Content-SHA256": "a" * 64,
    "X-Source-SHA256": "b" * 64,
    "X-Artifact-Source-State": "current",
    "X-Artifact-Current-Source-SHA256": "b" * 64,
    "X-Document-ID": "document-example",
    "X-Reader-Revision": "revision-example",
    "ETag": '"revision-example"',
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "cors-test-token")
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    app = create_app(
        cors_origins=["https://antiek.ai"],
        register_wrestling=False,
        register_providers=False,
    )

    @app.get("/cors-receipt-test")
    def receipt() -> Response:
        return Response("saved output", headers=RECEIPT_HEADERS)

    @app.get("/cors-retry-after-test")
    def retry_after() -> Response:
        return Response("database busy", status_code=503, headers={"Retry-After": "2"})

    @app.get("/cors-no-retry-after-test")
    def no_retry_after() -> Response:
        return Response("service unavailable", status_code=503)

    return TestClient(app, headers={"Authorization": "Bearer cors-test-token"})


def test_receipts_and_etag_are_exposed_to_allowed_origin(client):
    response = client.get(
        "/cors-receipt-test", headers={"Origin": "https://antiek.ai"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://antiek.ai"
    assert response.headers["access-control-allow-credentials"] == "true"
    exposed = {
        header.strip().lower()
        for header in response.headers.get("access-control-expose-headers", "").split(",")
        if header.strip()
    }
    assert {name.lower() for name in RECEIPT_HEADERS} <= exposed
    assert "*" not in exposed
    for name, value in RECEIPT_HEADERS.items():
        assert response.headers[name] == value


def test_disallowed_origin_gets_no_read_permission(client):
    response = client.get(
        "/cors-receipt-test", headers={"Origin": "https://untrusted.example"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_retry_after_is_exposed_to_allowed_origin(client):
    response = client.get(
        "/cors-retry-after-test", headers={"Origin": "https://antiek.ai"},
    )
    assert response.status_code == 503
    assert response.text == "database busy"
    assert response.headers["retry-after"] == "2"
    assert response.headers["access-control-allow-origin"] == "https://antiek.ai"
    assert response.headers["access-control-allow-credentials"] == "true"
    exposed = {
        header.strip().lower()
        for header in response.headers.get("access-control-expose-headers", "").split(",")
        if header.strip()
    }
    assert "retry-after" in exposed
    assert "*" not in exposed


def test_retry_after_disallowed_origin_gets_no_read_permission(client):
    response = client.get(
        "/cors-retry-after-test", headers={"Origin": "https://untrusted.example"},
    )
    assert response.status_code == 503
    assert response.text == "database busy"
    assert response.headers["retry-after"] == "2"
    assert "access-control-allow-origin" not in response.headers


def test_cors_does_not_fabricate_retry_after(client):
    response = client.get(
        "/cors-no-retry-after-test", headers={"Origin": "https://antiek.ai"},
    )
    assert response.status_code == 503
    assert response.text == "service unavailable"
    assert "retry-after" not in response.headers
    assert response.headers["access-control-allow-origin"] == "https://antiek.ai"
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.parametrize(
    ("origin", "status"),
    [("https://antiek.ai", 200), ("https://untrusted.example", 400)],
)
def test_preflight_preserves_origin_policy(client, origin, status):
    response = client.options(
        "/cors-receipt-test",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == status
    if status == 200:
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["access-control-allow-credentials"] == "true"
    else:
        assert "access-control-allow-origin" not in response.headers
