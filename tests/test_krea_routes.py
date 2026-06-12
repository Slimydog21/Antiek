"""Tests for the Krea proxy (Mountain Shell SPR-02; live-fixed SPR-01
of antiek-living-caliber, 2026-06-12).

EVERY failure mode is enumerated + asserted to end in the typed 503
fallback signal — never a crash, hang, 500, or leaked key (rigor #3):

  - no key                -> 503 enabled:false reason:no_key
  - kill-switch on        -> 503 reason:kill_switch (even WITH a key)
  - over daily budget     -> 503 reason:over_daily_budget, NO upstream call
  - rate limited          -> 503 reason:rate_limited
  - invalid key (401)     -> 503 reason:upstream_error
  - upstream 429/queue    -> 503 reason:upstream_error
  - empty prepaid balance -> 503 reason:no_api_balance (402, submit OR poll)
  - latency / timeout     -> 503 reason:upstream_timeout
  - offline / network err -> 503 reason:upstream_error
  - partial/garbage JSON  -> 503 reason:upstream_bad_response (billed if 2xx)
  - completed, no urls    -> 503 reason:upstream_bad_response
  - job failed            -> 503 reason:job_failed (error message sanitized)
  - job cancelled         -> 503 reason:job_cancelled (short-circuit)
  - scene cache hit       -> 200, NO second upstream call (no re-bill)

HONESTY (rigor #1): every Krea-shaped fixture below is a TRANSCRIPTION of
a docs.krea.ai page (each carries a citation comment naming it), NOT an
observation of the live API — no live call has ever been made from this
codebase. Live verification is SPR-09's capped smoke. httpx is mocked via
httpx.MockTransport injected onto app.state.krea_http_client. NO network
is touched and NO real KREA_API_TOKEN is required (the absent-key path is
the default under test). The poll loop is exercised with a mock clock
(_FakeClock below) — no real sleeps.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

import interfaces.research.api.krea_routes as kr
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
        "ANTIEK_KREA_MODEL_PATH",
        "KREA_DAILY_UNIT_CAP",
        "KREA_RATE_LIMIT_MAX",
        "KREA_CACHE_TTL_S",
        "KREA_POLL_BUDGET_S",
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


# The submit path the live API serves (docs.krea.ai flux-1-dev reference,
# 2026-06-12): the model is vendor-prefixed IN THE URL; no model body key.
_SUBMIT_PATH = "/generate/image/bfl/flux-1-dev"


def _submit_ok_body() -> dict:
    """Transcription of the docs.krea.ai flux-1-dev submit worked example
    (2026-06-12): {"job_id", "status": "queued", "created_at"}. ASSUMPTION
    (docs ambiguity, rigor #1): submit responses do NOT carry a `result`
    at submit time — the worked example has none, so these fixtures omit
    it; if SPR-09's live smoke observes one, update fixtures + adapter."""
    return {
        "job_id": "job_abc",
        "status": "queued",
        "created_at": "2026-06-12T00:00:00Z",
    }


def _completed_body(job_id: str, url: str) -> dict:
    """Transcription of the docs.krea.ai jobs reference (2026-06-12):
    completed jobs carry result.urls — an ARRAY OF URI STRINGS (the
    adapter takes [0]); result may also carry style_id (ignored)."""
    return {
        "job_id": job_id,
        "status": "completed",
        "result": {"urls": [url], "style_id": "style_fixture"},
    }


class _FakeClock:
    """Mock clock for the poll loop (M4 / rigor #3: NO real sleeps in
    tests). Installed via the krea_routes ``_monotonic``/``_sleep`` module
    seam: ``sleep(dt)`` advances the virtual clock, ``monotonic()`` reads
    it, and every sleep is recorded so a test can assert the documented
    2.5s cadence (docs.krea.ai poll guidance: every 2–5s)."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, dt: float) -> None:
        self.sleeps.append(dt)
        self.now += dt


def _install_clock(monkeypatch) -> _FakeClock:
    clock = _FakeClock()
    monkeypatch.setattr(kr, "_monotonic", clock.monotonic)
    monkeypatch.setattr(kr, "_sleep", clock.sleep)
    return clock


# ── Milestone 1: routes registered + no-key disabled (never 500) ────────


def test_routes_registered_and_health_unaffected():
    app = _app()
    tc = TestClient(app)
    # /health stays green regardless of Krea.
    h = tc.get("/health")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"
    # The Krea routes exist (no 404 for the path itself).
    # Starlette ≥1.3 adds `_IncludedRouter` wrapper entries to ``app.routes``
    # (alongside the flattened path-bearing routes) that carry no ``.path``;
    # guard so the assertion checks real routes, not the wrappers.
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
        # Model-in-path (docs.krea.ai flux-1-dev reference, 2026-06-12).
        assert request.url.path == _SUBMIT_PATH
        assert request.headers["Authorization"] == "Bearer test-token-not-real"
        # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
        return httpx.Response(200, json=_submit_ok_body())

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


def test_submit_targets_model_in_path_with_exact_body_keys(monkeypatch):
    """M1: the mock transport receives POST /generate/image/bfl/flux-1-dev
    (model vendor-prefixed IN THE PATH) with body keys EXACTLY
    {prompt, width, height} — no model key in the body. Both facts
    transcribed from the docs.krea.ai flux-1-dev reference (2026-06-12)."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content.decode("utf-8"))
        # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
        return httpx.Response(200, json=_submit_ok_body())

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.post("/krea/generate", json={
            "prompt": "a mountain", "width": 1024, "height": 1024,
        })
        assert r.status_code == 200
        assert seen["method"] == "POST"
        assert seen["path"] == _SUBMIT_PATH
        assert set(seen["body"].keys()) == {"prompt", "width", "height"}
        assert seen["body"]["prompt"] == "a mountain"
        assert seen["body"]["width"] == 1024
        assert seen["body"]["height"] == 1024
    finally:
        client.close()


def test_submit_model_path_env_override(monkeypatch):
    """M1: ANTIEK_KREA_MODEL_PATH (read at call time, like the other
    knobs) swaps the model segment of the submit URL — the knob that
    covers future model moves (docs.krea.ai lists other models at other
    paths, e.g. krea/krea-2/medium, 2026-06-12)."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    monkeypatch.setenv("ANTIEK_KREA_MODEL_PATH", "test-vendor/test-model")
    app = _app()
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        # Submit worked example shape (docs.krea.ai flux-1-dev, 2026-06-12);
        # the response shape is model-independent per the jobs reference.
        return httpx.Response(200, json=_submit_ok_body())

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.post("/krea/generate", json={"prompt": "x"})
        assert r.status_code == 200
        assert seen["path"] == "/generate/image/test-vendor/test-model"
    finally:
        client.close()


def test_key_present_scene_happy_path_caches(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()
    calls = {"submit": 0, "poll": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _SUBMIT_PATH:
            calls["submit"] += 1
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json={
                "job_id": "j1", "status": "queued",
                "created_at": "2026-06-12T00:00:00Z",
            })
        if request.url.path.startswith("/jobs/"):
            calls["poll"] += 1
            # Completed-job shape: result.urls array of URI strings
            # (docs.krea.ai jobs reference, 2026-06-12).
            return httpx.Response(200, json=_completed_body(
                "j1", "https://img/x.png",
            ))
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
        if request.url.path == _SUBMIT_PATH:
            submits["n"] += 1
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json={
                "job_id": "j", "status": "queued",
                "created_at": "2026-06-12T00:00:00Z",
            })
        # Completed-job result.urls shape (docs.krea.ai jobs, 2026-06-12).
        return httpx.Response(200, json=_completed_body("j", "https://img/a.png"))

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
        # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
        return httpx.Response(200, json=_submit_ok_body())

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
        # M6: a NON-2xx submit was refused upstream — Krea started no job,
        # so the local daily count must NOT increment.
        assert app.state.krea_budget.units_today() == 0
    finally:
        client.close()


@pytest.mark.parametrize("via", ["submit", "poll"])
def test_402_empty_prepaid_balance_yields_no_api_balance(monkeypatch, via):
    """M3: HTTP 402 = Krea's prepaid API balance (separate from any
    subscription; $5 minimum top-up) is empty — answered as
    402 {"message": ...} per docs.krea.ai (2026-06-12). Mapped to the
    ADDITIVE no_api_balance reason (not generic upstream_error) on BOTH
    the submit and the mid-poll legs (rigor #3). Billing: a 402-refused
    submit records NO unit; a 2xx-accepted submit followed by a 402 poll
    keeps its one unit (M6 — the submit was accepted)."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()
    # 402 body transcribed from docs.krea.ai (2026-06-12): {"message": ...}.
    balance_msg = {"message": "API balance empty - top up at krea.ai"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _SUBMIT_PATH:
            if via == "submit":
                return httpx.Response(402, json=balance_msg)
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json=_submit_ok_body())
        return httpx.Response(402, json=balance_msg)

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.get("/krea/scene", params={"mood": "calm", "day_night": "day",
                                          "season": "summer"})
        assert r.status_code == 503
        body = r.json()
        assert body["reason"] == "no_api_balance"
        # Sanitized-preview discipline: no upstream prose in the body.
        assert "top up" not in r.text
        expected_units = 0 if via == "submit" else 1
        assert app.state.krea_budget.units_today() == expected_units
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


def test_upstream_garbage_json_returns_fallback_and_still_bills(monkeypatch):
    """M6 (the billing-accounting hole, closed): a 200 whose body is
    garbage means Krea ACCEPTED the submit and may have started a billable
    job — the daily count must increment (recorded pre-parse) AND the
    caller still gets the typed upstream_bad_response fallback."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        # 200 but the body is not JSON — NOT a docs shape; this fixture
        # models the live API drifting from docs.krea.ai (the exact gap
        # this module's honesty banner warns about).
        return httpx.Response(200, text="<html>not json</html>")

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.post("/krea/generate", json={"prompt": "x"})
        assert r.status_code == 503
        assert r.json()["reason"] == "upstream_bad_response"
        # The 2xx submit was accepted upstream → unit recorded BEFORE the
        # parse failed (bill-on-submit-accept; overcount is the safe
        # direction for a runaway guard).
        assert app.state.krea_budget.units_today() == 1
    finally:
        client.close()


def test_upstream_missing_job_id_returns_fallback(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        # Valid JSON object but no job_id (partial / unexpected shape —
        # NOT a docs shape; models drift from the docs.krea.ai worked
        # example, which always carries job_id).
        return httpx.Response(200, json={"status": "queued"})

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.post("/krea/generate", json={"prompt": "x"})
        assert r.status_code == 503
        assert r.json()["reason"] == "upstream_bad_response"
        # M6: 2xx accepted → billed despite the half-shape.
        assert app.state.krea_budget.units_today() == 1
    finally:
        client.close()


def test_scene_job_failed_returns_fallback_message_sanitized(monkeypatch):
    """M2: failed jobs carry error: {code, message} (docs.krea.ai jobs
    reference, 2026-06-12) → typed 503 job_failed, and the upstream
    MESSAGE text never appears in the response body (sanitized-preview
    discipline)."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()
    leak_marker = "GPU pool exploded at 03:14 leak-marker"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _SUBMIT_PATH:
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json=_submit_ok_body())
        # Failed-job shape (docs.krea.ai jobs reference, 2026-06-12):
        # error carries a machine code + a human message.
        return httpx.Response(200, json={
            "job_id": "job_abc", "status": "failed",
            "error": {"code": "generation_failed", "message": leak_marker},
        })

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.get("/krea/scene")
        assert r.status_code == 503
        assert r.json()["reason"] == "job_failed"
        # The upstream error message must NOT leak into the 503 body.
        assert leak_marker not in r.text
    finally:
        client.close()


def test_scene_cancelled_job_short_circuits_to_job_cancelled(monkeypatch):
    """M3: "cancelled" is TERMINAL in the 9-state lifecycle (docs.krea.ai,
    2026-06-12) → typed 503 with the ADDITIVE job_cancelled reason after
    EXACTLY ONE poll — the remaining poll budget is not burned (zero
    sleeps on the mock clock)."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    clock = _install_clock(monkeypatch)
    app = _app()
    polls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _SUBMIT_PATH:
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json=_submit_ok_body())
        polls["n"] += 1
        # Cancelled terminal state (docs.krea.ai jobs reference,
        # 2026-06-12). ASSUMPTION (rigor #1): the docs do not show a
        # cancelled job carrying result or error, so this fixture has
        # neither.
        return httpx.Response(200, json={"job_id": "job_abc",
                                         "status": "cancelled"})

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.get("/krea/scene", params={"mood": "calm", "day_night": "day",
                                          "season": "summer"})
        assert r.status_code == 503
        body = r.json()
        assert body["reason"] == "job_cancelled"
        assert body["scene_key"] == "calm|day|summer"
        assert polls["n"] == 1  # short-circuit: one poll, no re-poll
        assert clock.sleeps == []  # no poll budget burned waiting
    finally:
        client.close()


def test_scene_processing_then_completed_loops_and_caches(monkeypatch):
    """The poll loop's CONTINUE branch: upstream walks the documented
    non-terminal states (queued → sampling → processing; all members of
    the docs.krea.ai 9-state lifecycle, 2026-06-12) before "completed".
    Exercises the loop body + the cache write on completion. Mock clock —
    no real sleeps (M4)."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    _install_clock(monkeypatch)
    app = _app()
    state = {"polls": 0}
    # Non-terminal walk transcribed from the docs.krea.ai job lifecycle
    # (2026-06-12); the loop must poll THROUGH each of these.
    walk = ["queued", "sampling", "processing"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _SUBMIT_PATH:
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json={
                "job_id": "jp", "status": "queued",
                "created_at": "2026-06-12T00:00:00Z",
            })
        if request.url.path.startswith("/jobs/"):
            state["polls"] += 1
            if state["polls"] <= len(walk):
                # Non-terminal job states from the docs.krea.ai 9-state
                # lifecycle (2026-06-12) — see `walk` above.
                return httpx.Response(200, json={
                    "job_id": "jp", "status": walk[state["polls"] - 1],
                })
            # Completed result.urls shape (docs.krea.ai jobs, 2026-06-12).
            return httpx.Response(200, json=_completed_body(
                "jp", "https://img/p.png",
            ))
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
        assert state["polls"] == 4  # 3 non-terminal + the completed poll
        # The completion was cached: a second identical request is a hit
        # with NO further polling.
        polls_before = state["polls"]
        r2 = tc.get("/krea/scene", params=params)
        assert r2.json()["cached"] is True
        assert state["polls"] == polls_before  # cache served it, no re-poll
    finally:
        client.close()


def test_scene_poll_interval_and_budget_honored_mock_clock(monkeypatch):
    """M4: with the default knobs, a never-completing job is polled every
    _POLL_INTERVAL_S = 2.5s (docs.krea.ai guidance: poll every 2–5s) until
    the 30s budget (3x documented Krea-2 ~10s; flux-1-dev latency
    undocumented) expires → typed job_timeout. Mock clock proves BOTH
    numbers: 13 polls (t = 0, 2.5, …, 30.0) and 12 sleeps of exactly
    2.5s — and the suite never really sleeps."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    clock = _install_clock(monkeypatch)
    app = _app()
    polls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _SUBMIT_PATH:
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json=_submit_ok_body())
        polls["n"] += 1
        # "processing" is non-terminal in the 9-state lifecycle
        # (docs.krea.ai, 2026-06-12) — the job never finishes here, so the
        # poll budget is the only thing that can end the loop.
        return httpx.Response(200, json={"job_id": "job_abc",
                                         "status": "processing"})

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.get("/krea/scene", params={"mood": "stormy",
                                          "day_night": "day",
                                          "season": "autumn"})
        assert r.status_code == 503
        assert r.json()["reason"] == "job_timeout"
        # 30s budget / 2.5s interval: polls at t=0..30 inclusive = 13.
        assert polls["n"] == 13
        assert clock.sleeps == [2.5] * 12
    finally:
        client.close()


def test_scene_poll_budget_env_override(monkeypatch):
    """M4: KREA_POLL_BUDGET_S is read at call time (like the other knobs);
    5s budget / 2.5s interval → polls at t = 0, 2.5, 5.0 = exactly 3, then
    the typed job_timeout fallback."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    monkeypatch.setenv("KREA_POLL_BUDGET_S", "5")
    clock = _install_clock(monkeypatch)
    app = _app()
    polls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _SUBMIT_PATH:
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json=_submit_ok_body())
        polls["n"] += 1
        # Non-terminal state (docs.krea.ai 9-state lifecycle, 2026-06-12).
        return httpx.Response(200, json={"job_id": "job_abc",
                                         "status": "backlogged"})

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.get("/krea/scene")
        assert r.status_code == 503
        assert r.json()["reason"] == "job_timeout"
        assert polls["n"] == 3
        assert clock.sleeps == [2.5] * 2
    finally:
        client.close()


def test_job_poll_endpoint_happy_path(monkeypatch):
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/jobs/job_abc"
        # Completed-job shape: result.urls array of URI strings, result
        # may carry style_id (docs.krea.ai jobs reference, 2026-06-12).
        return httpx.Response(200, json=_completed_body(
            "job_abc", "https://img/done.png",
        ))

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


# ── Milestone 2 (SPR-01): completed-but-malformed + bounds ──────────────


@pytest.mark.parametrize("result_field", [
    None,                          # completed with NO result at all
    {},                            # result present but no urls
    {"urls": []},                  # urls present but EMPTY
    {"urls": [123]},               # urls present but not URI strings
])
def test_completed_job_missing_urls_is_bad_response_never_none_200(
    monkeypatch, result_field,
):
    """M2: a completed job MUST carry result.urls (array of URI strings —
    docs.krea.ai jobs reference, 2026-06-12). Every malformed variant
    yields the typed upstream_bad_response — never a crash, a None-URL
    200, or an endless re-poll."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    _install_clock(monkeypatch)
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _SUBMIT_PATH:
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json=_submit_ok_body())
        # MALFORMED variant of the completed shape — models the live API
        # drifting from the docs.krea.ai jobs reference (2026-06-12),
        # which always shows result.urls on completion.
        body: dict = {"job_id": "job_abc", "status": "completed"}
        if result_field is not None:
            body["result"] = result_field
        return httpx.Response(200, json=body)

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        # Scene path: bad completed shape → typed fallback.
        r = tc.get("/krea/scene")
        assert r.status_code == 503
        assert r.json()["reason"] == "upstream_bad_response"
        # Direct poll endpoint: same discipline.
        rj = tc.get("/krea/jobs/job_abc")
        assert rj.status_code == 503
        assert rj.json()["reason"] == "upstream_bad_response"
    finally:
        client.close()


@pytest.mark.parametrize("payload,bound_name", [
    # Bounds transcribed from the docs.krea.ai flux-1-dev reference
    # (2026-06-12): prompt max 1800 chars; width/height 512–2368 px.
    ({"prompt": "p" * 1801}, "1800"),
    ({"prompt": "x", "width": 511}, "512"),
    ({"prompt": "x", "width": 2369}, "2368"),
    ({"prompt": "x", "height": 511}, "512"),
    ({"prompt": "x", "height": 2369}, "2368"),
])
def test_generate_out_of_bounds_is_422_naming_the_bound(monkeypatch,
                                                        payload, bound_name):
    """M5: a direct /krea/generate caller outside the documented contract
    gets a 422 NAMING the violated bound, and NO upstream call (nothing
    billable happens for an invalid request)."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("upstream called for an out-of-bounds request")

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.post("/krea/generate", json=payload)
        assert r.status_code == 422
        assert bound_name in r.text  # the 422 names the bound
        assert app.state.krea_budget.units_today() == 0
    finally:
        client.close()


@pytest.mark.parametrize("payload", [
    # In-bounds boundary values per the flux-1-dev reference
    # (docs.krea.ai, 2026-06-12): 1800-char prompt; 512 + 2368 px edges.
    {"prompt": "p" * 1800},
    {"prompt": "x", "width": 512, "height": 512},
    {"prompt": "x", "width": 2368, "height": 2368},
])
def test_generate_at_documented_bounds_is_accepted(monkeypatch, payload):
    """M5: the documented boundary values themselves are VALID — the
    proxy's bounds are the contract's, not tighter."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
        return httpx.Response(200, json=_submit_ok_body())

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.post("/krea/generate", json=payload)
        assert r.status_code == 200
        assert r.json()["job_id"] == "job_abc"
    finally:
        client.close()


def test_scene_prompt_within_limit_for_every_mood_matrix_combination():
    """M5: the proxy-built scene prompt stays ≤ 1800 chars (the
    docs.krea.ai flux-1-dev prompt limit, 2026-06-12) for EVERY mood-
    matrix combination the frontend can emit — the matrix is transcribed
    from apps/reading/src/scene/mood.ts (dayparts dawn/day/dusk/night ×
    weather clear/snow → mood = daypart, day_night ∈ {day, night},
    season ∈ {winter, clear}) — AND for the worst case a direct caller
    can reach (three 64-char axes, the Query max_length bound)."""
    dayparts = ["dawn", "day", "dusk", "night"]   # mood.ts DayPart
    day_nights = ["day", "night"]                 # mood.ts sceneStateFromMood
    seasons = ["winter", "clear"]                 # mood.ts weather mapping
    for mood in dayparts:
        for dn in day_nights:
            for season in seasons:
                prompt = kr._scene_prompt(mood, dn, season)
                assert len(prompt) <= kr._PROMPT_MAX_CHARS
                # And it must validate as a GenerateRequest (the scene
                # handler builds exactly this) — never a self-inflicted 422.
                kr.GenerateRequest(prompt=prompt)
    # Worst case beyond the matrix: axes at the Query max_length=64 cap.
    worst = kr._scene_prompt("m" * 64, "d" * 64, "s" * 64)
    assert len(worst) <= kr._PROMPT_MAX_CHARS
    kr.GenerateRequest(prompt=worst)
