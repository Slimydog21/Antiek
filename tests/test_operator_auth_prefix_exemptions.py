"""The operator-auth middleware's PREFIX exemptions must not reach protected paths.

`_operator_auth_middleware` lets four shapes through without operator auth:

  * `/internal/agent-work/…`  — only when the Authorization scheme is
    `AntiekBridge`; the bridge validates its own credential downstream
  * `/speak/invite/…`         — the invite token IS the credential
  * `POST /speak/projects/{id}/open-contribute` (exactly 4 slashes)
  * a handful of exact paths in `_OPERATOR_AUTH_OPEN_PATHS`

Three of those are `startswith` checks, which is the classic shape for an auth
bypass: if the middleware and the router ever disagree about what a path IS,
a request can satisfy the exemption while routing somewhere protected. They
agree today — both read `scope["path"]` — so traversal attempts either fail the
prefix (401) or fail to route (404), never both.

Nothing pinned that. This does, so a future change to path handling — a
normalising middleware, a proxy rewrite, a router upgrade — cannot quietly turn
a prefix exemption into an open door.
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

# A path that MUST require operator auth; the probes below try to reach it.
PROTECTED = "/ops/provider-ratio"

ESCAPE_ATTEMPTS = [
    "/speak/invite/../ops/provider-ratio",
    "/speak/invite/%2e%2e/ops/provider-ratio",
    "/speak/invite/%252e%252e/ops/provider-ratio",
    "/speak/invite/;/../ops/provider-ratio",
    "/speak/invite/./../ops/provider-ratio",
    "/internal/agent-work/../ops/provider-ratio",
    "/internal/agent-work/%2e%2e/ops/provider-ratio",
    "/speak/projects/x/../../ops/provider-ratio",
]


@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.mkdtemp()
    events = os.path.join(tmp, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmp, "g.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    # A token is SET so the gate is live; no request below presents it.
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "pinned-test-token")
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    from interfaces.research.api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def test_the_protected_path_is_actually_protected(client):
    """Positive control. Without it, every assertion below is vacuous — a
    misconfigured fixture that 404s everything would 'pass' the bypass tests."""
    r = client.get(PROTECTED)
    assert r.status_code in (401, 403), (
        f"{PROTECTED} answered {r.status_code} unauthenticated; the probes "
        f"below can no longer prove anything"
    )


@pytest.mark.parametrize("path", ESCAPE_ATTEMPTS)
def test_prefix_exemption_cannot_reach_a_protected_endpoint(client, path):
    r = client.get(path)
    assert r.status_code != 200, (
        f"{path} reached {PROTECTED} WITHOUT operator auth — a prefix "
        f"exemption in _operator_auth_middleware became an open door"
    )
    assert r.status_code in (401, 403, 404, 405), (
        f"{path} answered an unexpected {r.status_code}; expected the prefix "
        f"check to reject it (401/403) or the router not to match it (404/405)"
    )


def test_agent_work_needs_the_bridge_scheme(client):
    """The /internal/agent-work/ exemption is conditional on the scheme.

    A bare request must still meet the operator gate; only `AntiekBridge`
    is waved through to the router, where the bridge validates its own
    credential.
    """
    r = client.get("/internal/agent-work/lease")
    assert r.status_code != 200, (
        "/internal/agent-work/ answered 200 with no Authorization at all"
    )
