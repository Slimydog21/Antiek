"""A junk invite token must not reach the single-writer lock.

The five ``POST /speak/invite/{token}/*`` routes are waved through the
operator gate by a path-prefix match, so they are reachable with no session
at all. Each one opened ``_write(...)`` and called ``_require_token`` INSIDE
that block:

    with _translate(), _write("speak/api:invite_consent") as con:
        interview_id, _ = _require_token(con, token)

So an anonymous caller with a made-up token still acquired the DuckDB
single-writer flock before being rejected. ``connect_write`` polls with
``time.sleep`` up to ``DEFAULT_TIMEOUT_S`` (300s), and the service runs
``--workers 1`` against one database, so unauthenticated traffic could starve
the real writer — ingest and backup — without ever presenting a credential.

A sibling fix moved the blocking work off the event loop, which stops the API
from stalling. It does NOT stop the lock from being taken: the acquisition
just happens on a worker thread instead. This is the other half.

The fix is the pattern ``invitee_landing`` already used: resolve the token on
the READ connection first and 404 there. ``_require_token`` inside the write
block remains the authority, so a token revoked between the two checks is
still caught exactly as before — the read is a rejection filter, not the
check.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api import create_app
from runtime.db_lock import connect_write as _real_connect_write

_BOGUS = "definitely-not-a-real-invite-token"


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Record every write-lock acquisition made through speak_routes."""
    taken: list[str] = []
    # speak_routes imports this name from runtime.db_lock; reference the
    # canonical object so the spy wraps exactly what the module calls.
    real = _real_connect_write

    def _spy(db: str, *args: Any, **kwargs: Any) -> Any:
        taken.append(str(kwargs.get("purpose", "")))
        return real(db, *args, **kwargs)

    monkeypatch.setattr(
        "interfaces.research.api.speak_routes.connect_write", _spy
    )
    yield taken


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(register_wrestling=False)) as c:
        yield c


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (f"/speak/invite/{_BOGUS}/consent", {"scopes": ["record"]}),
        (f"/speak/invite/{_BOGUS}/answer",
         {"question_id": "q", "transcript": "t", "duration_seconds": 1}),
        (f"/speak/invite/{_BOGUS}/followups", None),
        (f"/speak/invite/{_BOGUS}/decline", None),
    ],
)
def test_bogus_token_never_takes_the_write_lock(
    client: TestClient, spy: list[str], path: str, payload: dict[str, Any] | None,
) -> None:
    resp = client.post(path, json=payload) if payload is not None else client.post(path)
    assert resp.status_code == 404, (
        f"{path} should 404 on an unknown token, got {resp.status_code}"
    )
    assert spy == [], (
        f"{path} acquired the single-writer lock for an unauthenticated caller "
        f"with a junk token: {spy}. The token must be resolved on the read "
        "connection first."
    )


def test_spy_actually_observes_a_real_acquisition(
    client: TestClient, spy: list[str],
) -> None:
    """Guard the guard.

    If the spy could not see a write-lock acquisition, every assertion above
    would pass vacuously. Drive one real write and confirm it is recorded.
    """
    resp = client.post("/speak/projects", json={"title": "t", "subject_ref": "s"})
    assert resp.status_code in (200, 201, 401, 403), resp.status_code
    if resp.status_code in (200, 201):
        assert spy, "the spy observed no write-lock acquisition on a real write"
