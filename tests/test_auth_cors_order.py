"""CORS transport for ordinary operator-auth responses."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app

ALLOWED_ORIGIN = "https://frontend.example.test"
OTHER_ORIGIN = "https://other.example.test"
TOKEN = "synthetic-operator-token"


@pytest.fixture
def client_factory(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", TOKEN)
    for name in (
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
        "ANTIEK_AUTH_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    def make_client(*, cors_origins: list[str]) -> TestClient:
        return TestClient(
            create_app(
                register_wrestling=False,
                register_providers=False,
                cors_origins=cors_origins,
            )
        )

    return make_client


def _assert_auth_refusal(response):
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "message": (
                "Authentication required. One of: Antiek session cookie "
                "(sign in via /login), Cloudflare Access browser session, "
                "Cloudflare Access service token, or Authorization: "
                "Bearer <operator-token>."
            ),
            "code": "operator_auth_required",
        }
    }


def test_allowed_origin_can_read_auth_refusal(client_factory):
    response = client_factory(cors_origins=[ALLOWED_ORIGIN]).get(
        "/auth/me", headers={"Origin": ALLOWED_ORIGIN}
    )
    _assert_auth_refusal(response)
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "Origin" in response.headers["vary"].split(", ")


def test_other_origin_cannot_read_auth_refusal(client_factory):
    response = client_factory(cors_origins=[ALLOWED_ORIGIN]).get(
        "/auth/me", headers={"Origin": OTHER_ORIGIN}
    )
    _assert_auth_refusal(response)
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    ("origin", "status", "allowed"),
    [(ALLOWED_ORIGIN, 200, True), (OTHER_ORIGIN, 400, False)],
)
def test_preflight_uses_existing_origin_policy(client_factory, origin, status, allowed):
    response = client_factory(cors_origins=[ALLOWED_ORIGIN]).options(
        "/auth/me",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == status
    if allowed:
        assert response.headers["access-control-allow-origin"] == origin
    else:
        assert "access-control-allow-origin" not in response.headers


def test_empty_origin_list_disables_cors(client_factory):
    response = client_factory(cors_origins=[]).get(
        "/auth/me", headers={"Origin": ALLOWED_ORIGIN}
    )
    _assert_auth_refusal(response)
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


def test_authorized_route_still_succeeds_with_cors(client_factory):
    response = client_factory(cors_origins=[ALLOWED_ORIGIN]).get(
        "/auth/me",
        headers={"Origin": ALLOWED_ORIGIN, "Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["auth_method"] == "bearer_token"
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
