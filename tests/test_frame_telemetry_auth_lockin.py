"""AFA-S1 — lock in the auth posture of the money-write frame-telemetry route.

Context (verified 2026-07-02 against ``interfaces/research/api/app.py``): auth
in this codebase is a single global ASGI middleware (``_operator_auth_middleware``),
NOT a per-route ``Depends``. When enforcement is ON (any operator auth env var
set — the production posture), EVERY path except the small
``_OPERATOR_AUTH_OPEN_PATHS`` allowlist and the ``/speak/invite/`` prefix
requires a real credential and gets 401 otherwise. ``/api/ad/frame-telemetry``
is a MONEY-ACCRUING write; it must stay behind that gate.

This file does NOT add a redundant per-route dependency (the middleware already
fails closed — a second gate would be dead weight, not defense). It LOCKS IN the
property so a future refactor cannot silently open the money route: the route is
(a) NOT in the open-paths allowlist, and (b) rejected 401 without a credential
when enforcement is on. If someone later adds the path to the allowlist, these
tests red.

Mirrors ``tests/test_operator_bearer_middleware.py`` (its
``test_post_investigations_requires_bearer`` proves the same gate for a
cost-bearing POST).
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

_ROUTE = "/api/ad/frame-telemetry"


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="afa-authlock-")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmp, "g.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield tmp


def _enforcing_client(monkeypatch):
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "op_secret")
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    from interfaces.research.api.app import create_app

    return TestClient(
        create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    )


def _minimal_v2_batch():
    from substrate.ad_inventory.frame_attention import FRAME_TELEMETRY_SCHEMA_VERSION

    return {
        "window_id": "win:read:lockin01",
        "schema_version": FRAME_TELEMETRY_SCHEMA_VERSION,
        "seconds": [],
    }


def test_route_is_not_in_the_auth_open_paths_allowlist():
    """The money-write route must never be allowlisted-open. Reads the
    middleware's allowlist directly so this fails the instant someone adds the
    path (or a prefix of it) to the exempt set."""
    from interfaces.research.api import app as app_module
    import inspect

    src = inspect.getsource(app_module.create_app)
    # The allowlist literal lives inside create_app. The route must not appear
    # in the exempt set, and the exempt set must not contain an "/api/ad" prefix.
    assert '"/api/ad/frame-telemetry"' not in src, (
        "frame-telemetry must not be added to _OPERATOR_AUTH_OPEN_PATHS — it is "
        "a money-accruing write and must stay behind the operator-auth gate."
    )
    assert '"/api/ad"' not in src, "no /api/ad prefix may be auth-exempt"


def test_frame_telemetry_rejected_without_credential_when_enforcing(
    temp_substrate, monkeypatch,
):
    client = _enforcing_client(monkeypatch)
    resp = client.post(_ROUTE, json=_minimal_v2_batch())  # no Authorization
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "operator_auth_required"


def test_frame_telemetry_reaches_handler_with_credential_when_enforcing(
    temp_substrate, monkeypatch,
):
    """With a valid credential the request passes the gate and reaches the
    handler (202 for the accepted empty batch). Proves the 401 above is the
    auth gate, not an unrelated rejection."""
    client = _enforcing_client(monkeypatch)
    resp = client.post(
        _ROUTE,
        json=_minimal_v2_batch(),
        headers={"Authorization": "Bearer op_secret"},
    )
    assert resp.status_code == 202, resp.text
