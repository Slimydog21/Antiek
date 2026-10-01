"""Public Trust Center read and authenticated deletion sibling boundary."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app

ALLOWED_ORIGIN = "https://trust.example.test"
OTHER_ORIGIN = "https://other.example.test"
TOKEN = "synthetic-trust-center-operator-token"


@pytest.fixture
def client_factory(monkeypatch, tmp_path):
    db_path = tmp_path / "graph.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", TOKEN)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("ANTIEK_AUTH_SECRET", raising=False)

    from substrate.graph import ensure_initialized

    ensure_initialized(str(db_path))

    def make_client() -> TestClient:
        return TestClient(
            create_app(
                register_wrestling=False,
                register_providers=False,
                cors_origins=[ALLOWED_ORIGIN],
            )
        )

    return make_client


def _assert_auth_refusal(response) -> None:
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


def test_trust_center_public_get_uses_existing_dto_and_cors(client_factory):
    response = client_factory().get("/trust-center", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["differential_privacy_epsilon_budgets"]["query_content_telemetry"] == 0.0
    assert body["differential_privacy_epsilon_budgets"]["skill_invocation_frequency"] == 2.0
    assert body["deletion_sla_days"] == 30
    assert body["substrate_controls"]
    assert body["compliance_frameworks"]
    assert body["loop_3_unlock_status"]
    assert body["website_ads"]["max_sdk_on_web"] is False
    assert body["website_ads"]["paid_fill_gated"] is True
    assert body["speak_economics"]["paid_today"] is False
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "origin" in {part.strip().lower() for part in response.headers["vary"].split(",")}


def test_disallowed_origin_gets_public_body_without_cors_grant(client_factory):
    response = client_factory().get("/trust-center", headers={"Origin": OTHER_ORIGIN})

    assert response.status_code == 200, response.text
    assert response.json()["deletion_sla_days"] == 30
    assert "access-control-allow-origin" not in response.headers


def test_private_deletion_siblings_and_non_get_trust_center_stay_protected(
    client_factory,
):
    anonymous = client_factory()
    requests = (
        anonymous.get("/trust-center/deletion-requests"),
        anonymous.post("/trust-center/deletion-requests", json={"reason": "synthetic"}),
        anonymous.post("/trust-center/deletion-requests/del-synthetic/cancel"),
        anonymous.get("/trust-center/deletion-requests/del-synthetic/cancel"),
        anonymous.post("/trust-center"),
    )
    for response in requests:
        _assert_auth_refusal(response)


def test_authenticated_operator_keeps_existing_protected_access(client_factory):
    response = client_factory().get(
        "/trust-center/deletion-requests",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"requests": []}
