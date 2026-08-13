"""Tests for the H4 operator-bearer middleware.

When ``ANTIEK_OPERATOR_TOKEN`` is set, every path except ``/health``
+ CORS preflights requires ``Authorization: Bearer <token>``. When
unset, enforcement is bypassed (test / local-dev default).
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-h4-")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmp, "g.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"events_dir": events_dir, "tmpdir": tmp}


def _client_with_token(
    _, token: str | None, monkeypatch, *,
    email: str | None = None,
    service_token_client_id: str | None = None,
    service_token_client_secret: str | None = None,
):
    if token is None:
        monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", token)
    if email is None:
        monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    else:
        monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", email)
    if service_token_client_id is None:
        monkeypatch.delenv(
            "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False,
        )
    else:
        monkeypatch.setenv(
            "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
            service_token_client_id,
        )
    if service_token_client_secret is None:
        monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    else:
        monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", service_token_client_secret)
    from interfaces.research.api.app import create_app
    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[],
    )
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────
# 1. Disabled by default (no env var)
# ─────────────────────────────────────────────────────────────────────


def test_no_env_var_no_enforcement(temp_substrate, monkeypatch):
    """Default state: both ANTIEK_OPERATOR_TOKEN and
    ANTIEK_OPERATOR_EMAIL unset → everything open. Existing tests +
    local dev work unchanged."""
    client = _client_with_token(temp_substrate, None, monkeypatch)
    # /investigations is a write endpoint — would be gated when token set
    resp = client.get("/investigations")
    assert resp.status_code == 200


def test_no_env_var_health_open(temp_substrate, monkeypatch):
    client = _client_with_token(temp_substrate, None, monkeypatch)
    resp = client.get("/health")
    assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────
# 2. Health stays open even with token enforcement on
# ─────────────────────────────────────────────────────────────────────


def test_health_open_with_token_set(temp_substrate, monkeypatch):
    """The probe + uptime monitors must be able to hit /health
    without credentials. Returns only binary up/down state +
    registered providers; no operator-sensitive content."""
    client = _client_with_token(temp_substrate, "op_secret", monkeypatch)
    resp = client.get("/health")  # no Authorization header
    assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────
# 3. Everything else requires the bearer when token is set
# ─────────────────────────────────────────────────────────────────────


def test_gated_path_missing_auth_rejected(temp_substrate, monkeypatch):
    client = _client_with_token(temp_substrate, "op_secret", monkeypatch)
    resp = client.get("/investigations")  # no Authorization header
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "operator_auth_required"


def test_gated_path_wrong_bearer_rejected(temp_substrate, monkeypatch):
    client = _client_with_token(temp_substrate, "op_secret", monkeypatch)
    resp = client.get(
        "/investigations", headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "operator_auth_required"


def test_gated_path_correct_bearer_passes(temp_substrate, monkeypatch):
    client = _client_with_token(temp_substrate, "op_secret", monkeypatch)
    resp = client.get(
        "/investigations", headers={"Authorization": "Bearer op_secret"},
    )
    assert resp.status_code == 200


def test_malformed_scheme_rejected(temp_substrate, monkeypatch):
    """Authorization header without ``Bearer`` scheme → 401."""
    client = _client_with_token(temp_substrate, "op_secret", monkeypatch)
    resp = client.get(
        "/investigations", headers={"Authorization": "Basic op_secret"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "operator_auth_required"


# ─────────────────────────────────────────────────────────────────────
# 4. POST endpoints (cost-bearing) also gated
# ─────────────────────────────────────────────────────────────────────


def test_post_investigations_requires_bearer(temp_substrate, monkeypatch):
    client = _client_with_token(temp_substrate, "op_secret", monkeypatch)
    resp = client.post(
        "/investigations", json={"question": "x"},
    )
    assert resp.status_code == 401


def test_post_investigations_with_bearer_proceeds(temp_substrate, monkeypatch):
    client = _client_with_token(temp_substrate, "op_secret", monkeypatch)
    resp = client.post(
        "/investigations",
        json={"question": "valid question for the handler"},
        headers={"Authorization": "Bearer op_secret"},
    )
    # 202 Accepted — the bearer passed and the request reached the
    # FastAPI handler. The handler accepts the start request.
    assert resp.status_code == 202


@pytest.mark.parametrize("declared_length", ["0", "not-a-number", str(512 * 1024 + 1)])
def test_tts_gateway_body_ceiling_runs_before_open_path_dispatch(
    temp_substrate, monkeypatch, declared_length
):
    client = _client_with_token(temp_substrate, "operator-secret", monkeypatch)
    response = client.post(
        "/multimedia/tts-gateway/synthesize",
        content=b"{}",
        headers={"Content-Length": declared_length},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "TTS gateway request body is invalid"}


def test_ops_endpoint_also_gated(temp_substrate, monkeypatch):
    """/ops/provider-ratio exposes dispatch metadata; gated."""
    client = _client_with_token(temp_substrate, "op_secret", monkeypatch)
    resp = client.get("/ops/provider-ratio")
    assert resp.status_code == 401
    resp = client.get(
        "/ops/provider-ratio",
        headers={"Authorization": "Bearer op_secret"},
    )
    assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────
# 5. CORS preflight bypass
# ─────────────────────────────────────────────────────────────────────


def test_options_preflight_passes_without_auth(temp_substrate, monkeypatch):
    """OPTIONS preflights must NOT require the bearer — browsers
    handle CORS preflights automatically before sending the
    Authorization header, so blocking them at auth would prevent the
    actual request from ever firing.

    With CORS enabled, OPTIONS goes through CORSMiddleware (200/204).
    With CORS disabled (e.g. this test's ``cors_origins=[]`` setup),
    OPTIONS falls through to FastAPI's router which returns 405 since
    no OPTIONS route is registered. Either status proves the auth
    middleware did NOT 401 — that's what matters."""
    client = _client_with_token(temp_substrate, "op_secret", monkeypatch)
    resp = client.options(
        "/investigations",
        headers={
            "Origin": "https://app.antiek.ai",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code != 401
    # auth middleware bypassed for OPTIONS regardless of the routing-
    # layer answer
    assert resp.status_code in (200, 204, 405)


# ─────────────────────────────────────────────────────────────────────
# 6. Cloudflare Access email path (H4.5)
# ─────────────────────────────────────────────────────────────────────


def test_cf_access_email_match_passes(temp_substrate, monkeypatch):
    """When ANTIEK_OPERATOR_EMAIL is set and the request carries a
    matching ``Cf-Access-Authenticated-User-Email`` header, the
    request passes without needing a bearer."""
    client = _client_with_token(
        temp_substrate, None, monkeypatch, email="op@antiek.ai",
    )
    resp = client.get(
        "/investigations",
        headers={"Cf-Access-Authenticated-User-Email": "op@antiek.ai"},
    )
    assert resp.status_code == 200


def test_cf_access_email_case_insensitive(temp_substrate, monkeypatch):
    """Email comparison is case-insensitive — Cloudflare may send
    the header in any case."""
    client = _client_with_token(
        temp_substrate, None, monkeypatch, email="op@antiek.ai",
    )
    resp = client.get(
        "/investigations",
        headers={"Cf-Access-Authenticated-User-Email": "OP@ANTIEK.AI"},
    )
    assert resp.status_code == 200


def test_cf_access_email_mismatch_rejected(temp_substrate, monkeypatch):
    """Wrong email in the header → 401."""
    client = _client_with_token(
        temp_substrate, None, monkeypatch, email="op@antiek.ai",
    )
    resp = client.get(
        "/investigations",
        headers={"Cf-Access-Authenticated-User-Email": "intruder@example.com"},
    )
    assert resp.status_code == 401


def test_cf_access_email_missing_rejected_when_email_required(
    temp_substrate, monkeypatch,
):
    """No header + email gate configured → 401."""
    client = _client_with_token(
        temp_substrate, None, monkeypatch, email="op@antiek.ai",
    )
    resp = client.get("/investigations")
    assert resp.status_code == 401


def test_both_paths_either_suffices_email(temp_substrate, monkeypatch):
    """Both env vars set → email path passes without needing bearer."""
    client = _client_with_token(
        temp_substrate, "op_secret", monkeypatch, email="op@antiek.ai",
    )
    resp = client.get(
        "/investigations",
        headers={"Cf-Access-Authenticated-User-Email": "op@antiek.ai"},
    )
    assert resp.status_code == 200


def test_both_paths_either_suffices_bearer(temp_substrate, monkeypatch):
    """Both env vars set → bearer path passes without needing email."""
    client = _client_with_token(
        temp_substrate, "op_secret", monkeypatch, email="op@antiek.ai",
    )
    resp = client.get(
        "/investigations", headers={"Authorization": "Bearer op_secret"},
    )
    assert resp.status_code == 200


def test_both_paths_neither_supplied_rejected(temp_substrate, monkeypatch):
    """Both env vars set + request supplies neither → 401."""
    client = _client_with_token(
        temp_substrate, "op_secret", monkeypatch, email="op@antiek.ai",
    )
    resp = client.get("/investigations")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "operator_auth_required"


# ─────────────────────────────────────────────────────────────────────
# 7. Cloudflare Access Service Token path (machine callers, H4.5)
# ─────────────────────────────────────────────────────────────────────


def test_service_token_pair_match_passes(temp_substrate, monkeypatch):
    """A matching client ID and secret authenticate a machine caller."""
    client = _client_with_token(
        temp_substrate, None, monkeypatch,
        service_token_client_id="ab12cd.access",
        service_token_client_secret="service-secret",
    )
    resp = client.get(
        "/investigations",
        headers={
            "Cf-Access-Client-Id": "ab12cd.access",
            "Cf-Access-Client-Secret": "service-secret",
        },
    )
    assert resp.status_code == 200


def test_service_token_client_id_case_insensitive(temp_substrate, monkeypatch):
    """Client Id comparison is case-insensitive — Cloudflare's header
    casing may vary on the wire even if the value is canonically
    lowercase."""
    client = _client_with_token(
        temp_substrate, None, monkeypatch,
        service_token_client_id="ab12cd.access",
        service_token_client_secret="service-secret",
    )
    resp = client.get(
        "/investigations",
        headers={
            "Cf-Access-Client-Id": "AB12CD.ACCESS",
            "Cf-Access-Client-Secret": "service-secret",
        },
    )
    assert resp.status_code == 200


def test_service_token_client_id_alone_rejected(temp_substrate, monkeypatch):
    client = _client_with_token(
        temp_substrate, None, monkeypatch,
        service_token_client_id="ab12cd.access",
        service_token_client_secret="service-secret",
    )
    resp = client.get(
        "/investigations",
        headers={"Cf-Access-Client-Id": "ab12cd.access"},
    )
    assert resp.status_code == 401


def test_service_token_wrong_secret_rejected(temp_substrate, monkeypatch):
    client = _client_with_token(
        temp_substrate, None, monkeypatch,
        service_token_client_id="ab12cd.access",
        service_token_client_secret="service-secret",
    )
    resp = client.get(
        "/investigations",
        headers={
            "Cf-Access-Client-Id": "ab12cd.access",
            "Cf-Access-Client-Secret": "wrong-secret",
        },
    )
    assert resp.status_code == 401


def test_service_token_client_id_mismatch_rejected(temp_substrate, monkeypatch):
    """Wrong Client Id → 401. Distinguishes the operator's machine
    token from any future service tokens added to the same Access
    application."""
    client = _client_with_token(
        temp_substrate, None, monkeypatch,
        service_token_client_id="ab12cd.access",
        service_token_client_secret="service-secret",
    )
    resp = client.get(
        "/investigations",
        headers={
            "Cf-Access-Client-Id": "ffffff.access",
            "Cf-Access-Client-Secret": "service-secret",
        },
    )
    assert resp.status_code == 401


def test_service_token_three_paths_active_email_passes(temp_substrate, monkeypatch):
    """All three env vars set → any single path matches."""
    client = _client_with_token(
        temp_substrate, "op_secret", monkeypatch,
        email="op@antiek.ai",
        service_token_client_id="ab12cd.access",
        service_token_client_secret="service-secret",
    )
    resp = client.get(
        "/investigations",
        headers={"Cf-Access-Authenticated-User-Email": "op@antiek.ai"},
    )
    assert resp.status_code == 200


def test_service_token_three_paths_active_service_token_passes(
    temp_substrate, monkeypatch,
):
    client = _client_with_token(
        temp_substrate, "op_secret", monkeypatch,
        email="op@antiek.ai",
        service_token_client_id="ab12cd.access",
        service_token_client_secret="service-secret",
    )
    resp = client.get(
        "/investigations",
        headers={
            "Cf-Access-Client-Id": "ab12cd.access",
            "Cf-Access-Client-Secret": "service-secret",
        },
    )
    assert resp.status_code == 200


def test_service_token_three_paths_active_bearer_passes(
    temp_substrate, monkeypatch,
):
    client = _client_with_token(
        temp_substrate, "op_secret", monkeypatch,
        email="op@antiek.ai",
        service_token_client_id="ab12cd.access",
        service_token_client_secret="service-secret",
    )
    resp = client.get(
        "/investigations", headers={"Authorization": "Bearer op_secret"},
    )
    assert resp.status_code == 200


def test_service_token_alone_no_other_env_works(temp_substrate, monkeypatch):
    """Service Token can be the SOLE auth path — bearer + email
    unset, service-token-client-id set. Useful for deployments that
    only ever serve machine callers."""
    client = _client_with_token(
        temp_substrate, None, monkeypatch,
        service_token_client_id="ab12cd.access",
        service_token_client_secret="service-secret",
    )
    # No Cf-Access-* and no Authorization → 401
    resp = client.get("/investigations")
    assert resp.status_code == 401
    # With the complete service-token proof → 200
    resp = client.get(
        "/investigations",
        headers={
            "Cf-Access-Client-Id": "ab12cd.access",
            "Cf-Access-Client-Secret": "service-secret",
        },
    )
    assert resp.status_code == 200
