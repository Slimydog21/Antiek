"""Auth-middleware state-population tests.

Confirms ``_operator_auth_middleware`` attaches ``user_id``, ``scopes``,
and ``auth_method`` to ``request.state`` on every accepted path, and
that ``/auth/whoami`` reads them back. Per master-spec §13.3: identity
resolution happens in middleware; endpoints trust request.state.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.multi_user import (
    encode_verified_claims_header,
    sign_verified_claims_header,
)


def _client():
    return TestClient(create_app(register_wrestling=False))


# ── Unauthenticated local path (default for tests + local dev) ─────


def test_whoami_unauthenticated_local_path(monkeypatch):
    """When no auth env vars are set, the middleware still attaches
    the static operator identity to request.state."""
    for env in (
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "ANTIEK_EXTERNAL_AUTH_VENDOR",
        "ANTIEK_EXTERNAL_AUTH_HEADER_SECRET",
    ):
        monkeypatch.delenv(env, raising=False)

    client = _client()
    resp = client.get("/auth/whoami")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "__operator__"
    assert body["is_operator"] is True
    assert body["auth_method"] == "unauthenticated_local"


# ── Bearer-token path ───────────────────────────────────────────────


def test_whoami_bearer_token_path(monkeypatch):
    """Valid bearer attaches auth_method='bearer_token'."""
    token = "test-token-not-secret"
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", token)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)

    client = _client()
    resp = client.get(
        "/auth/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "__operator__"
    assert body["auth_method"] == "bearer_token"


def test_bearer_rejected_when_token_mismatches(monkeypatch):
    """Wrong bearer → 401 regardless of other state."""
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "right-token")
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)

    client = _client()
    resp = client.get(
        "/auth/whoami",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


# ── Cloudflare Access email path ───────────────────────────────────


def test_whoami_cloudflare_email_path(monkeypatch):
    """Cf-Access email match attaches auth_method='cloudflare_access_email'."""
    email = "operator@example.com"
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", email)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)

    client = _client()
    resp = client.get(
        "/auth/whoami",
        headers={"Cf-Access-Authenticated-User-Email": email},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["auth_method"] == "cloudflare_access_email"


def test_cloudflare_email_mismatch_rejected(monkeypatch):
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "operator@example.com")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)

    client = _client()
    resp = client.get(
        "/auth/whoami",
        headers={"Cf-Access-Authenticated-User-Email": "intruder@elsewhere.com"},
    )
    assert resp.status_code == 401


# ── External provider trusted-claims path ───────────────────────────


def test_whoami_external_provider_operator_claims_path(monkeypatch):
    """Trusted Clerk/Supabase claims can authorize the current operator API
    only when they carry explicit operator scope."""
    secret = "trusted-hop-secret"
    monkeypatch.setenv("ANTIEK_EXTERNAL_AUTH_VENDOR", "clerk")
    monkeypatch.setenv("ANTIEK_EXTERNAL_AUTH_HEADER_SECRET", secret)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    encoded = encode_verified_claims_header({
        "sub": "user_2abc",
        "email": "operator@example.com",
        "public_metadata": {"antiek_scopes": ["operator", "private_research"]},
    })
    signature = sign_verified_claims_header(
        vendor="clerk",
        encoded_claims=encoded,
        secret=secret,
    )

    client = _client()
    resp = client.get(
        "/auth/whoami",
        headers={
            "X-Antiek-Verified-Claims": encoded,
            "X-Antiek-Verified-Claims-Signature": signature,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "clerk:user_2abc"
    assert body["is_operator"] is True
    assert body["auth_method"] == "external_clerk"
    assert body["scopes"] == ["authenticated", "operator", "private_research"]


def test_external_provider_bad_signature_rejected(monkeypatch):
    monkeypatch.setenv("ANTIEK_EXTERNAL_AUTH_VENDOR", "supabase")
    monkeypatch.setenv("ANTIEK_EXTERNAL_AUTH_HEADER_SECRET", "right-secret")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    encoded = encode_verified_claims_header({
        "sub": "9e7d03ec-0f16-4e52-b615-6f94807d5133",
        "app_metadata": {"antiek_scopes": ["operator"]},
    })
    bad_signature = sign_verified_claims_header(
        vendor="supabase",
        encoded_claims=encoded,
        secret="wrong-secret",
    )

    client = _client()
    resp = client.get(
        "/auth/whoami",
        headers={
            "X-Antiek-Verified-Claims": encoded,
            "X-Antiek-Verified-Claims-Signature": bad_signature,
        },
    )

    assert resp.status_code == 401


def test_external_provider_non_operator_claims_can_read_whoami(monkeypatch):
    """External non-operator claims are accepted on explicit self-service routes."""
    secret = "trusted-hop-secret"
    monkeypatch.setenv("ANTIEK_EXTERNAL_AUTH_VENDOR", "supabase")
    monkeypatch.setenv("ANTIEK_EXTERNAL_AUTH_HEADER_SECRET", secret)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    encoded = encode_verified_claims_header({
        "sub": "9e7d03ec-0f16-4e52-b615-6f94807d5133",
        "email": "reader@example.com",
        "app_metadata": {"antiek_scopes": ["private_research"]},
    })
    signature = sign_verified_claims_header(
        vendor="supabase",
        encoded_claims=encoded,
        secret=secret,
    )

    client = _client()
    resp = client.get(
        "/auth/whoami",
        headers={
            "X-Antiek-Verified-Claims": encoded,
            "X-Antiek-Verified-Claims-Signature": signature,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "supabase:9e7d03ec-0f16-4e52-b615-6f94807d5133"
    assert body["is_operator"] is False
    assert body["auth_method"] == "external_supabase"
    assert body["scopes"] == ["authenticated", "private_research"]


def test_external_provider_non_operator_claims_rejected_for_operator_api(monkeypatch):
    """The same non-operator identity must not unlock broad operator routes."""
    secret = "trusted-hop-secret"
    monkeypatch.setenv("ANTIEK_EXTERNAL_AUTH_VENDOR", "supabase")
    monkeypatch.setenv("ANTIEK_EXTERNAL_AUTH_HEADER_SECRET", secret)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    encoded = encode_verified_claims_header({
        "sub": "9e7d03ec-0f16-4e52-b615-6f94807d5133",
        "email": "reader@example.com",
        "app_metadata": {"antiek_scopes": ["private_research"]},
    })
    signature = sign_verified_claims_header(
        vendor="supabase",
        encoded_claims=encoded,
        secret=secret,
    )

    client = _client()
    resp = client.get(
        "/investigations",
        headers={
            "X-Antiek-Verified-Claims": encoded,
            "X-Antiek-Verified-Claims-Signature": signature,
        },
    )

    assert resp.status_code == 401


# ── /health bypass ───────────────────────────────────────────────────


def test_health_endpoint_bypasses_auth(monkeypatch):
    """/health is in the open-paths set — 200 even with auth enforced."""
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "anything")

    client = _client()
    resp = client.get("/health")
    assert resp.status_code == 200
