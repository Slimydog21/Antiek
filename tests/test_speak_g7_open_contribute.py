"""G7 open contribution — stranger self-serve mint for will_be_public only."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-g7-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "acquisition.voice.adapter.default_embedding_provider",
        lambda: StubEmbedding(),
    )
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def test_open_contribute_gated_without_g7(client, monkeypatch):
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", raising=False)
    pub = client.post(
        "/speak/projects",
        json={
            "title": "Theo Bakery",
            "subject_ref": "Uncle Theo",
            "publish_intent": "will_be_public",
        },
    ).json()
    r = client.post(f"/speak/projects/{pub['project_id']}/open-contribute")
    assert r.status_code == 403
    assert "G7" in r.json()["detail"] or "ecosystem" in r.json()["detail"].lower()


def test_open_contribute_mints_token_for_public_when_g7(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    pub = client.post(
        "/speak/projects",
        json={
            "title": "Theo Bakery",
            "subject_ref": "Uncle Theo",
            "publish_intent": "will_be_public",
        },
    ).json()
    pid = pub["project_id"]
    r = client.post(f"/speak/projects/{pid}/open-contribute")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["honesty"]["open_contribution"] == "live_g7_will_be_public_only"
    assert body["honesty"]["private_projects"] == "invite_only_unchanged"
    assert body["token"]
    assert body["invite_path"] == f"/speak/invite/{body['token']}"
    # Door resolves unauth
    land = client.get(body["invite_path"])
    assert land.status_code == 200
    # Opportunities honesty flips to live
    opps = client.get("/speak/opportunities").json()
    assert opps["honesty"]["open_contribution_without_invite"] == "live"


def test_open_contribute_refuses_private_even_with_g7(client, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    priv = client.post(
        "/speak/projects",
        json={
            "title": "Dad private",
            "publish_intent": "private_never_published",
        },
    ).json()
    r = client.post(f"/speak/projects/{priv['project_id']}/open-contribute")
    assert r.status_code == 403
    detail = r.json()["detail"].lower()
    assert "private" in detail or "invite-only" in detail


def test_open_contribute_unauth_when_operator_auth_on(client, monkeypatch):
    """Stranger browse must mint without operator token once G7 is on."""
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    pub = client.post(
        "/speak/projects",
        json={"title": "Public", "publish_intent": "will_be_public"},
    ).json()
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "secret-operator-token")
    r = client.post(f"/speak/projects/{pub['project_id']}/open-contribute")
    assert r.status_code == 201, r.text
    # Private mutate still blocked
    blocked = client.post("/speak/projects", json={"title": "Nope"})
    assert blocked.status_code in (401, 403)


def test_open_contribute_is_rate_limited(client, monkeypatch):
    """The one anonymous write door onto the single-writer DB is bounded.

    Regression: this endpoint is waved through the operator-auth middleware by
    a bare POST path-shape match, takes ``connect_write`` on the DuckDB the
    whole service shares under ``--workers 1``, and had no throttle of any
    kind — while ``GET /speak/feed`` publishes the ``project_id`` an anonymous
    caller needs to reach it. Unbounded writes there starve every other
    writer, including the nightly backup and the corpus ingest.
    """
    from interfaces.research.api.auth import reset_auth_throttles
    from interfaces.research.api.speak_routes import (
        _OPEN_CONTRIBUTE_GLOBAL_LIMIT,
        _OPEN_CONTRIBUTE_PER_IP_LIMIT,
    )

    reset_auth_throttles()
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    pub = client.post(
        "/speak/projects",
        json={
            "title": "Theo Bakery",
            "subject_ref": "Uncle Theo",
            "publish_intent": "will_be_public",
        },
    ).json()
    path = f"/speak/projects/{pub['project_id']}/open-contribute"

    # Pin the PER-IP bucket. Deliberately NOT min(per_ip, global): the first
    # version of this test used the min, which is the per-IP limit, sent
    # per_ip + 3 requests, and therefore never reached the global bucket at
    # all. Mutation-proved vacuous — it passed with the global limit set to
    # 100000 AND with the global bucket deleted outright, while its name
    # claimed the door was rate limited. test_global_bucket_is_pinned below
    # covers the other half; neither test alone certifies the pair.
    codes = [
        client.post(path).status_code
        for _ in range(_OPEN_CONTRIBUTE_PER_IP_LIMIT + 3)
    ]
    n = _OPEN_CONTRIBUTE_PER_IP_LIMIT
    assert codes[:n] == [201] * n, f"first {n} should mint: {codes}"
    assert codes[n:] == [429] * 3, f"the rest must be throttled: {codes}"

    reset_auth_throttles()
    assert client.post(path).status_code == 201, "window reset must re-open the door"


def test_global_bucket_is_pinned_independently_of_the_per_ip_bucket(
    client, monkeypatch
):
    """The global bucket must be load-bearing, and provably so.

    The per-IP test cannot see this bucket: it stops at PER_IP_LIMIT + 3
    requests, far under GLOBAL_LIMIT. To reach it, every request must come
    from a DIFFERENT client IP so the per-IP gate never fires.

    TestClient pins ``request.client.host`` to a constant and ignores
    X-Forwarded-For, so varying a header does not work — an earlier version of
    this test did exactly that and stayed vacuous, passing with the global
    bucket deleted because the per-IP gate was silently supplying the 429s.
    Patch the ``_client_ip`` that speak_routes actually calls instead.
    """
    import itertools

    from interfaces.research.api import speak_routes
    from interfaces.research.api.auth import reset_auth_throttles
    from interfaces.research.api.speak_routes import (
        _OPEN_CONTRIBUTE_GLOBAL_LIMIT,
        _OPEN_CONTRIBUTE_PER_IP_LIMIT,
    )

    assert _OPEN_CONTRIBUTE_PER_IP_LIMIT < _OPEN_CONTRIBUTE_GLOBAL_LIMIT, (
        "this test assumes per-IP is the tighter bucket; if that inverts, "
        "spreading across IPs stops isolating the global one"
    )

    counter = itertools.count()
    monkeypatch.setattr(
        speak_routes, "_client_ip", lambda _request: f"10.0.0.{next(counter)}"
    )

    reset_auth_throttles()
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    pub = client.post(
        "/speak/projects",
        json={
            "title": "Theo Bakery",
            "subject_ref": "Uncle Theo",
            "publish_intent": "will_be_public",
        },
    ).json()
    path = f"/speak/projects/{pub['project_id']}/open-contribute"

    codes = [
        client.post(path).status_code
        for _ in range(_OPEN_CONTRIBUTE_GLOBAL_LIMIT + 5)
    ]
    minted = codes.count(201)
    throttled = codes.count(429)

    # Every request had a unique IP, so the per-IP bucket can never fire.
    # Any 429 here came from the global bucket or from nothing.
    assert throttled == 5, (
        f"expected exactly 5 requests past the global limit to be refused; "
        f"got {minted} minted / {throttled} throttled against a global limit "
        f"of {_OPEN_CONTRIBUTE_GLOBAL_LIMIT}. Deleting the global bucket must "
        "fail this test."
    )
    assert minted == _OPEN_CONTRIBUTE_GLOBAL_LIMIT, (
        f"{minted} minted against a global limit of "
        f"{_OPEN_CONTRIBUTE_GLOBAL_LIMIT}"
    )


def test_one_ip_cannot_exhaust_the_global_budget(client, monkeypatch):
    """Pins the ORDER of the two gates, which neither other test can see.

    ``_throttled`` records a hit on every call, so checking global first let a
    single caller burn global budget with requests its own per-IP limit was
    about to reject: one IP sending GLOBAL_LIMIT requests mints only
    PER_IP_LIMIT but consumes the whole global window, denying every other
    caller. That made the throttle a cheaper denial lever than the unbounded
    endpoint it replaced.

    Both other tests in this file pass under either ordering — verified by
    mutation — so without this one the order is unpinned.
    """
    from interfaces.research.api.auth import _throttle, reset_auth_throttles
    from interfaces.research.api.speak_routes import (
        _OPEN_CONTRIBUTE_GLOBAL_LIMIT,
        _OPEN_CONTRIBUTE_PER_IP_LIMIT,
    )

    reset_auth_throttles()
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "1")
    pub = client.post(
        "/speak/projects",
        json={
            "title": "Theo Bakery",
            "subject_ref": "Uncle Theo",
            "publish_intent": "will_be_public",
        },
    ).json()
    path = f"/speak/projects/{pub['project_id']}/open-contribute"

    # TestClient pins request.client.host to a constant, so every one of these
    # is the SAME caller — which is exactly the scenario under test.
    for _ in range(_OPEN_CONTRIBUTE_GLOBAL_LIMIT + 5):
        client.post(path)

    consumed = len(_throttle.get("speak:open-contribute:global", []))
    assert consumed <= _OPEN_CONTRIBUTE_PER_IP_LIMIT, (
        f"one IP consumed {consumed} of {_OPEN_CONTRIBUTE_GLOBAL_LIMIT} global "
        "slots; the per-IP gate must reject first so a single caller cannot "
        "deny the endpoint to everyone else"
    )
