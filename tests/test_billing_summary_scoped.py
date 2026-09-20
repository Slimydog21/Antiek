"""Billing summary must be scoped to the authenticated caller.

`GET /billing/summary/{user_id}/{period}` took `user_id` as a path parameter
and passed it straight to `aggregate_period` with no authorization check, so
any authenticated caller could read any other identity's spend by editing the
URL — including the operator's.

This is a live IDOR rather than a theoretical one, because more than one
identity authenticating is a SUPPORTED configuration:
`operator_allowlist_from_env` parses a comma-separated list, and each
allowlisted email gets its own `request.state.user_id` from its session
cookie. `substrate/multi_user/auth.py` is a real multi-user model in which
`__operator__` is the operator's own sentinel.

The frontend made it concrete: `AISidecar.tsx:120` hardcoded
`/billing/summary/__operator__/${period}`, so every signed-in user's sidecar
asked for the operator's aggregate, and the endpoint served it.

`me` now resolves server-side to the caller, so a client never needs to know
or transmit its own id. The operator keeps cross-user read — the billing
dashboard is an operator surface. With auth disabled the caller IS
`__operator__`, the same fallback the rest of the API uses, so local dev is
unchanged.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.auth.magic_link import mint_session_cookie

_EMAIL = "owner@example.test"
_PERIOD = "2026-09"


@pytest.fixture
def enforced(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    tmp = tempfile.mkdtemp(prefix="billing-scope-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmp, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmp, "events"))
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _EMAIL)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "test-secret-not-real")
    with TestClient(create_app(register_wrestling=False)) as client:
        yield client


def _as(client: TestClient, user_id: str) -> None:
    client.cookies.set(
        "ANTIEK_SESSION", mint_session_cookie(user_id=user_id, email=_EMAIL)
    )


def test_caller_can_read_its_own_summary(enforced: TestClient) -> None:
    _as(enforced, "alice")
    assert enforced.get(f"/billing/summary/me/{_PERIOD}").status_code == 200


def test_caller_cannot_read_another_identity(enforced: TestClient) -> None:
    _as(enforced, "alice")
    resp = enforced.get(f"/billing/summary/bob/{_PERIOD}")
    assert resp.status_code == 403, (
        f"alice read bob's billing summary: HTTP {resp.status_code}. "
        "user_id is a path parameter and must be bound to the caller."
    )


def test_caller_cannot_read_the_operator_aggregate(enforced: TestClient) -> None:
    """The exact request AISidecar used to make for every signed-in user."""
    _as(enforced, "alice")
    assert enforced.get(f"/billing/summary/__operator__/{_PERIOD}").status_code == 403


def test_operator_keeps_cross_user_read(enforced: TestClient) -> None:
    """The billing dashboard is an operator surface; do not break it."""
    _as(enforced, "__operator__")
    assert enforced.get(f"/billing/summary/bob/{_PERIOD}").status_code == 200


def test_frontend_no_longer_hardcodes_the_operator_sentinel() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "apps" / "reading" / "src" / "components" / "AISidecar.tsx"
    ).read_text(encoding="utf-8")
    assert "/billing/summary/me/" in src
    assert "billing/summary/__operator__" not in src
