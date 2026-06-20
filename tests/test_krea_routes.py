"""Tests for the Krea proxy (Mountain Shell SPR-02).

EVERY failure mode is enumerated + asserted to end in the typed 503
fallback signal — never a crash, hang, 500, or leaked key (rigor #3):

  - no key                -> 503 enabled:false reason:no_key
  - kill-switch on        -> 503 reason:kill_switch (even WITH a key)
  - over daily budget     -> 503 reason:over_daily_budget, NO upstream call
  - rate limited          -> 503 reason:rate_limited
  - invalid key (401)     -> 503 reason:upstream_error
  - upstream 429/queue    -> 503 reason:upstream_error
  - latency / timeout     -> 503 reason:upstream_timeout
  - offline / network err -> 503 reason:upstream_error
  - partial/garbage JSON  -> 503 reason:upstream_bad_response
  - job failed            -> 503 reason:job_failed
  - scene cache hit       -> 200, NO second upstream call (no re-bill)

The upstream Krea wire is doc-derived; httpx is mocked via
httpx.MockTransport injected onto app.state.krea_http_client. NO network
is touched and NO real KREA_API_TOKEN is required (the absent-key path is
the default under test).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app

# ── Fixtures / helpers ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_krea_env(monkeypatch):
    """Default to the NO-KEY, kill-switch-OFF posture for every test;
    individual tests opt into a key / kill-switch / budget overrides."""
    for var in (
        "KREA_API_TOKEN",
        "KREA_KILL_SWITCH",
        "ANTIEK_KREA_BASE_URL",
        "KREA_DAILY_UNIT_CAP",
        "KREA_RATE_LIMIT_MAX",
        "KREA_CACHE_TTL_S",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


def _app():
    # register_wrestling=False keeps the test app lean (no dispatch import).
    return create_app(register_wrestling=False)


def _client_with_transport(app, handler) -> httpx.Client:
    """Build an httpx.Client backed by a MockTransport running ``handler``
    and inject it onto the app so the Krea routes use it instead of a real
    network client. Returns the client so the test can close it."""
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.krea.ai")
    app.state.krea_http_client = client
    return client


# ── Milestone 1: routes registered + no-key disabled (never 500) ────────


def test_routes_registered_and_health_unaffected():
    app = _app()
    tc = TestClient(app)
    # /health stays green regardless of Krea.
    h = tc.get("/health")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"
    # The Krea routes exist (no 404 for the path itself). Tolerate route types
    # without ``.path`` — a newer FastAPI registers an ``_IncludedRouter`` in
    # ``app.routes`` that has no ``.path``; the krea APIRoutes still carry it, so
    # the assertions below are unaffected. (Pre-existing origin/main test bug
    # surfaced by CI; fixed here to unblock the gate, not caused by this PR.)
    paths = {r.path for r in app.routes if hasattr(r, "path")}  # type: ignore[attr-defined]
    assert "/krea/generate" in paths
    assert "/krea/jobs/{job_id}" in paths
    assert "/krea/scene" in paths


def test_no_key_generate_returns_typed_disabled_503():
    app = _app()
    tc = TestClient(app)
    r = tc.post("/krea/generate", json={"prompt": "a mountain"})
    assert r.status_code == 503
    body = r.json()
    assert body["enabled"] is False
    assert body["isFallback"] is True
    assert body["reason"] == "no_key"


def test_no_key_scene_returns_typed_disabled_503_with_scene_key():
    app = _app()
    tc = TestClient(app)
    r = tc.get("/krea/scene", params={"mood": "calm", "day_night": "day",
                                      "season": "summer"})
    assert r.status_code == 503
    body = r.json()
    assert body["enabled"] is False
    assert body["isFallback"] is True
    assert body["reason"] == "no_key"
    # scene_key carried so the surface keeps a deterministic placeholder.
    assert body["scene_key"] == "calm|day|summer"


def test_no_key_job_returns_typed_disabled_503():
    app = _app()
    tc = TestClient(app)
    r = tc.get("/krea/jobs/job_xyz")
    assert r.status_code == 503
    assert r.json()["reason"] == "no_key"


# ── Milestone 1: key-present happy path (httpx mocked) ───────────────────


def test_key_present_generate_returns_job_id(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token-not-real")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/generate/image"
        assert request.headers["Authorization"] == "Bearer test-token-not-real"
        return httpx.Response(200, json={"job_id": "job_abc", "status": "queued"})

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.post("/krea/generate", json={"prompt": "a mountain"})
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True
        assert body["job_id"] == "job_abc"
        assert body["status"] == "queued"
    finally:
        client.close()


def test_key_present_scene_happy_path_caches(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()
    calls = {"submit": 0, "poll": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/generate/image":
            calls["submit"] += 1
            return httpx.Response(200, json={"job_id": "j1", "status": "queued"})
        if request.url.path.startswith("/jobs/"):
            calls["poll"] += 1
            return httpx.Response(200, json={
                "job_id": "j1", "status": "completed",
                "output": {"image_url": "https://img/x.png"},
            })
        return httpx.Response(404)

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r1 = tc.get("/krea/scene", params={"mood": "calm", "day_night": "day",
                                           "season": "summer"})
        assert r1.status_code == 200
        b1 = r1.json()
        assert b1["enabled"] is True
        assert b1["isFallback"] is False
        assert b1["image_url"] == "https://img/x.png"
        assert b1["scene_key"] == "calm|day|summer"
        assert b1["cached"] is False
        assert calls["submit"] == 1

        # Milestone 3: a SECOND identical request is a cache hit — no
        # second upstream submit (no re-bill).
        r2 = tc.get("/krea/scene", params={"mood": "calm", "day_night": "day",
                                           "season": "summer"})
        assert r2.status_code == 200
        b2 = r2.json()
        assert b2["cached"] is True
        assert b2["image_url"] == "https://img/x.png"
        assert calls["submit"] == 1  # unchanged — cache served it
    finally:
        client.close()


# ── Milestone 2: kill-switch + budget cap ────────────────────────────────


def test_kill_switch_forces_fallback_even_with_key(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    monkeypatch.setenv("KREA_KILL_SWITCH", "1")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:  # must never run
        raise AssertionError("upstream called while kill-switch on")

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        for path, kw in (
            ("/krea/generate", {"json": {"prompt": "x"}}),
            ("/krea/scene", {}),
        ):
            r = (tc.post(path, **kw) if path.endswith("generate")
                 else tc.get(path, **kw))
            assert r.status_code == 503
            assert r.json()["reason"] == "kill_switch"
        rj = tc.get("/krea/jobs/j1")
        assert rj.status_code == 503
        assert rj.json()["reason"] == "kill_switch"
    finally:
        client.close()


def test_over_daily_budget_returns_fallback_no_upstream_call(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    monkeypatch.setenv("KREA_DAILY_UNIT_CAP", "1")  # cap at one image/day
    app = _app()
    submits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/generate/image":
            submits["n"] += 1
            return httpx.Response(200, json={"job_id": "j", "status": "queued"})
        return httpx.Response(200, json={
            "job_id": "j", "status": "completed",
            "output": {"image_url": "https://img/a.png"},
        })

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        # First generate consumes the only unit.
        r1 = tc.post("/krea/generate", json={"prompt": "one"})
        assert r1.status_code == 200
        assert submits["n"] == 1
        # Second generate is over budget → fallback, and crucially NO
        # second upstream submit (the cap blocks before the call).
        r2 = tc.post("/krea/generate", json={"prompt": "two"})
        assert r2.status_code == 503
        assert r2.json()["reason"] == "over_daily_budget"
        assert submits["n"] == 1  # unchanged — no upstream call past the cap
    finally:
        client.close()


def test_rate_limit_returns_fallback(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    monkeypatch.setenv("KREA_RATE_LIMIT_MAX", "1")
    monkeypatch.setenv("KREA_DAILY_UNIT_CAP", "100")  # don't trip budget first
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"job_id": "j", "status": "queued"})

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r1 = tc.post("/krea/generate", json={"prompt": "one"})
        assert r1.status_code == 200
        r2 = tc.post("/krea/generate", json={"prompt": "two"})
        assert r2.status_code == 503
        assert r2.json()["reason"] == "rate_limited"
    finally:
        client.close()


# ── Milestone 1/3: upstream failure modes all collapse to fallback ──────


@pytest.mark.parametrize("status_code,expected_reason", [
    (401, "upstream_error"),   # invalid key
    (429, "upstream_error"),   # rate-limited / queue upstream
    (500, "upstream_error"),   # server error
    (503, "upstream_error"),   # upstream unavailable
])
def test_upstream_http_error_returns_fallback(monkeypatch, status_code,
                                              expected_reason):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="boom")

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.post("/krea/generate", json={"prompt": "x"})
        assert r.status_code == 503
        assert r.json()["reason"] == expected_reason
    finally:
        client.close()


def test_upstream_timeout_returns_fallback(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow", request=request)

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.post("/krea/generate", json={"prompt": "x"})
        assert r.status_code == 503
        assert r.json()["reason"] == "upstream_timeout"
    finally:
        client.close()


def test_upstream_network_error_offline_returns_fallback(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.post("/krea/generate", json={"prompt": "x"})
        assert r.status_code == 503
        assert r.json()["reason"] == "upstream_error"
    finally:
        client.close()


def test_upstream_garbage_json_returns_fallback(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        # 200 but the body is not JSON.
        return httpx.Response(200, text="<html>not json</html>")

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.post("/krea/generate", json={"prompt": "x"})
        assert r.status_code == 503
        assert r.json()["reason"] == "upstream_bad_response"
    finally:
        client.close()


def test_upstream_missing_job_id_returns_fallback(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        # Valid JSON object but no job_id (partial / unexpected shape).
        return httpx.Response(200, json={"status": "queued"})

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.post("/krea/generate", json={"prompt": "x"})
        assert r.status_code == 503
        assert r.json()["reason"] == "upstream_bad_response"
    finally:
        client.close()


def test_scene_job_failed_returns_fallback(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/generate/image":
            return httpx.Response(200, json={"job_id": "j", "status": "queued"})
        return httpx.Response(200, json={"job_id": "j", "status": "failed"})

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.get("/krea/scene")
        assert r.status_code == 503
        assert r.json()["reason"] == "job_failed"
    finally:
        client.close()


def test_scene_processing_then_completed_loops_and_caches(monkeypatch):
    """The poll loop's CONTINUE branch: upstream reports "processing" a few
    times before "completed". Exercises the loop body (the only code that
    runs time.sleep) + the cache write on completion. _POLL_INTERVAL_S is
    monkeypatched tiny so the test doesn't actually wait."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    import interfaces.research.api.krea_routes as kr
    monkeypatch.setattr(kr, "_POLL_INTERVAL_S", 0.001)
    app = _app()
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/generate/image":
            return httpx.Response(200, json={"job_id": "jp", "status": "queued"})
        if request.url.path.startswith("/jobs/"):
            state["polls"] += 1
            if state["polls"] < 3:
                return httpx.Response(200, json={
                    "job_id": "jp", "status": "processing",
                })
            return httpx.Response(200, json={
                "job_id": "jp", "status": "completed",
                "output": {"image_url": "https://img/p.png"},
            })
        return httpx.Response(404)

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        params = {"mood": "calm", "day_night": "night", "season": "winter"}
        r = tc.get("/krea/scene", params=params)
        assert r.status_code == 200
        b = r.json()
        assert b["image_url"] == "https://img/p.png"
        assert b["cached"] is False
        assert state["polls"] >= 3  # looped through "processing" first
        # The completion was cached: a second identical request is a hit
        # with NO further polling.
        polls_before = state["polls"]
        r2 = tc.get("/krea/scene", params=params)
        assert r2.json()["cached"] is True
        assert state["polls"] == polls_before  # cache served it, no re-poll
    finally:
        client.close()


def test_scene_poll_timeout_returns_fallback(monkeypatch):
    """The poll-budget deadline: the job never completes within
    _POLL_BUDGET_S → typed 503 job_timeout fallback (never a hang). Budget
    is monkeypatched to 0 so the deadline trips after the first poll."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    import interfaces.research.api.krea_routes as kr
    monkeypatch.setattr(kr, "_POLL_BUDGET_S", 0.0)
    monkeypatch.setattr(kr, "_POLL_INTERVAL_S", 0.001)
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/generate/image":
            return httpx.Response(200, json={"job_id": "jt", "status": "queued"})
        # Always "processing" — it never finishes, so the deadline decides.
        return httpx.Response(200, json={"job_id": "jt", "status": "processing"})

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.get("/krea/scene", params={"mood": "stormy",
                                          "day_night": "day",
                                          "season": "autumn"})
        assert r.status_code == 503
        assert r.json()["reason"] == "job_timeout"
    finally:
        client.close()


def test_job_poll_endpoint_happy_path(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/jobs/job_abc"
        return httpx.Response(200, json={
            "job_id": "job_abc", "status": "completed",
            "output": {"image_url": "https://img/done.png"},
        })

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.get("/krea/jobs/job_abc")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"
        assert body["image_url"] == "https://img/done.png"
    finally:
        client.close()
