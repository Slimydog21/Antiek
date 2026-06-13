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

import logging

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
    paths = {r.path for r in app.routes}  # type: ignore[attr-defined]
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


def test_scene_job_failed_returns_fallback_message_sanitized(monkeypatch, caplog):
    """M2 + DEFECT 1: failed jobs carry error: {code, message} (docs.krea.ai
    jobs reference, 2026-06-12) → typed 503 job_failed. The stable machine
    error_code now SURFACES to the operator in BOTH the ring-buffer preview
    AND the WARNING record (so the gate is no longer hollow — before the fix
    the preview was empty because the code was DROPPED, not scrubbed), while
    the upstream MESSAGE prose still never appears in the response body
    (sanitized-preview discipline)."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    app = _app()
    leak_marker = "GPU pool exploded at 03:14 leak-marker"
    error_code = "nsfw_filter"  # a real, non-secret machine failure code

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _SUBMIT_PATH:
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json=_submit_ok_body())
        # Failed-job shape (docs.krea.ai jobs reference, 2026-06-12):
        # error carries a machine code + a human message.
        return httpx.Response(200, json={
            "job_id": "job_abc", "status": "failed",
            "error": {"code": error_code, "message": leak_marker},
        })

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        with caplog.at_level(logging.WARNING, logger="antiek.interfaces.krea"):
            r = tc.get("/krea/scene")
        assert r.status_code == 503
        assert r.json()["reason"] == "job_failed"
        # The upstream error PROSE message must NOT leak into the 503 body.
        assert leak_marker not in r.text
        # DEFECT 1: the stable machine error_code now reaches the operator —
        # in the ring preview AND the WARNING. (This is the core sprint goal:
        # "reach the true reason in one request".)
        preview = app.state.krea_failures.snapshot()["entries"][0]["preview"]
        assert preview == error_code
        recs = [
            rec for rec in caplog.records
            if rec.name == "antiek.interfaces.krea"
            and rec.levelno == logging.WARNING
        ]
        assert len(recs) == 1
        assert error_code in recs[0].getMessage()
        # The body still excludes the preview/detail (the log/response split).
        assert error_code not in r.text
    finally:
        client.close()


def test_scene_job_failed_error_code_with_embedded_token_is_scrubbed(
    monkeypatch, caplog,
):
    """DEFECT 1 + rigor #1: even a job_failed whose error_code embeds a
    credential-shaped token has the token scrubbed on EVERY channel (ring
    preview, /krea/status payload, WARNING, 503 body) — the error_code flows
    through _scrub_secrets like any other detail, so surfacing it never
    becomes a leak vector."""
    monkeypatch.setenv("KREA_API_TOKEN", _FAKE_TOKEN)
    app = _app()
    # A pathological error_code that embeds a bearer-shaped token.
    poisoned_code = f"generation_failed Bearer {_FAKE_TOKEN}"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _SUBMIT_PATH:
            return httpx.Response(200, json=_submit_ok_body())
        return httpx.Response(200, json={
            "job_id": "job_abc", "status": "failed",
            "error": {"code": poisoned_code, "message": "irrelevant"},
        })

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        with caplog.at_level(logging.WARNING, logger="antiek.interfaces.krea"):
            r = tc.get("/krea/scene")
        assert r.status_code == 503
        assert r.json()["reason"] == "job_failed"
        preview = app.state.krea_failures.snapshot()["entries"][0]["preview"]
        assert _FAKE_TOKEN not in preview
        assert "PLANTEDLEAKMARKER" not in preview
        assert "[redacted]" in preview
        status_raw = tc.get("/krea/status").text
        assert _FAKE_TOKEN not in status_raw
        assert "PLANTEDLEAKMARKER" not in status_raw
        for rec in caplog.records:
            assert _FAKE_TOKEN not in rec.getMessage()
            assert "PLANTEDLEAKMARKER" not in rec.getMessage()
        assert _FAKE_TOKEN not in r.text
        assert "PLANTEDLEAKMARKER" not in r.text
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
    # MANUAL MIRROR of apps/reading/src/scene/mood.ts — hand-transcribed,
    # not imported. If mood.ts grows a daypart / day-night / season value,
    # EXTEND these lists or the matrix silently under-covers. Drift here
    # degrades COVERAGE only, never safety: _scene_prompt clamps to
    # _PROMPT_MAX_CHARS, so an over-limit prompt is structurally impossible
    # whatever mood.ts emits (the worst-case assertion below proves the
    # clamp independently of this list).
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


# ═════════════════════════════════════════════════════════════════════════
# SPR-04 (antiek-living-caliber) — FALLBACK OBSERVABILITY
# ═════════════════════════════════════════════════════════════════════════
#
# The typed-503 contract is SACRED: this block OBSERVES the degradation, it
# never redesigns it. It locks M1 (failure ring), M2 (GET /krea/status), and
# M4 (structured WARNING at the single 503-minting boundary).
#
# RIGOR #1 — no-leak by CONSTRUCTION (scrub before storage) + a planted-fake-
# token across EVERY output channel (status payload, ring buffer, caplog,
# 503 bodies). The token is a credential-SHAPED FAKE — no real secret is ever
# used (no live Krea call is ever made).
# RIGOR #3 — EVERY reason that mints a 503 gets a test-trio (ring + WARNING +
# 503 body); the reason matrix below is the single source the sweeps use.

# A planted credential-SHAPED FAKE token (never a real secret). The marker
# PLANTEDLEAKMARKER lets any channel be scanned for zero occurrences.
_FAKE_TOKEN = "sk-PLANTEDLEAKMARKER1234567890abcdefABCDEF"
# A bearer-like string in an UPSTREAM ERROR BODY — the realistic leak vector
# (Krea echoing our auth header back in a 401/500). The scrubber must redact
# it before it reaches the ring / status payload / logs.
_LEAK_BODY = f"upstream rejected: Authorization: Bearer {_FAKE_TOKEN} — denied"

# Every reason that can mint a 503 (rigor #3 — enumeration, not sampling).
_ALL_REASONS = [
    "no_key",
    "kill_switch",
    "over_daily_budget",
    "rate_limited",
    "upstream_error",
    "upstream_timeout",
    "upstream_bad_response",
    "job_failed",
    "job_timeout",
    "job_cancelled",
    "no_api_balance",
]

# DEFECT 4 — leak enumeration, not sampling. Classify EVERY reason by whether
# its 503 mint carries an upstream-derived detail (→ a non-empty, scrubbed
# preview that a planted token could ride) vs carries NONE by design (a gate
# reject / a terminal-state short-circuit → empty preview). The leak sweep
# below asserts scrubbing on EVERY carrier and empty-by-design on the rest, so
# "every reason scrubbed" is enumerated across all 11 reasons.
#
# Carriers whose preview is BUILT FROM the planted leak body under _trip(leak=
# True) — the token must be present-then-scrubbed (→ "[redacted]"):
_LEAK_CARRYING_REASONS = [
    "upstream_error",     # detail = "HTTP 500 — <leak body>"
    "upstream_timeout",   # detail = str(TimeoutException(<leak body>))
    "no_api_balance",     # detail = "HTTP 402 — {...<leak body>...}"
    "job_failed",         # detail = error.code (now surfaced; leak planted in it)
]
# Carrier whose preview is non-empty but does NOT echo the leak body: a JSON
# decode error message ("Expecting value: ...") — token absent trivially, but
# the preview is still a real (scrubbed) detail, so it is a carrier, not empty.
_DETAIL_NO_LEAK_ECHO_REASONS = ["upstream_bad_response"]
# Empty-by-design: gate rejects + terminal-state short-circuits pass NO detail
# to _disabled(), so the preview is "" for these.
_EMPTY_PREVIEW_REASONS = [
    "no_key", "kill_switch", "over_daily_budget", "rate_limited",
    "job_timeout", "job_cancelled",
]

# Sanity: the three buckets partition _ALL_REASONS exactly (no reason missed,
# none double-counted) — this is what makes the sweep an ENUMERATION.
assert set(
    _LEAK_CARRYING_REASONS + _DETAIL_NO_LEAK_ECHO_REASONS + _EMPTY_PREVIEW_REASONS
) == set(_ALL_REASONS)
assert len(
    _LEAK_CARRYING_REASONS + _DETAIL_NO_LEAK_ECHO_REASONS + _EMPTY_PREVIEW_REASONS
) == len(_ALL_REASONS)


def _trip(reason, monkeypatch, *, leak=False):
    """Build an app whose next /krea/scene call mints the given `reason` 503.
    Returns (app, client, call). `leak=True` plants _LEAK_BODY in the upstream
    error body for reasons whose preview comes from upstream prose."""
    if reason != "no_key":
        monkeypatch.setenv("KREA_API_TOKEN", _FAKE_TOKEN)
    if reason == "kill_switch":
        monkeypatch.setenv("KREA_KILL_SWITCH", "1")
    if reason == "over_daily_budget":
        monkeypatch.setenv("KREA_DAILY_UNIT_CAP", "0")
    if reason == "rate_limited":
        monkeypatch.setenv("KREA_RATE_LIMIT_MAX", "0")
        monkeypatch.setenv("KREA_DAILY_UNIT_CAP", "100")
    if reason == "job_timeout":
        _install_clock(monkeypatch)

    app = _app()
    leak_body_text = _LEAK_BODY if leak else "boom"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if reason == "upstream_error":
            return httpx.Response(500, text=leak_body_text)
        if reason == "upstream_timeout":
            # The timeout's str(e) becomes the _UpstreamError.detail (and so
            # the preview) — so leak=True plants the bearer-token there too.
            raise httpx.TimeoutException(leak_body_text, request=request)
        if reason == "no_api_balance":
            return httpx.Response(402, json={"message": leak_body_text})
        if reason == "upstream_bad_response":
            return httpx.Response(200, text=f"<html>{leak_body_text}</html>")
        if path == _SUBMIT_PATH:
            return httpx.Response(200, json={
                "job_id": "j", "status": "queued",
                "created_at": "2026-06-12T00:00:00Z",
            })
        if reason == "job_failed":
            # DEFECT 1: the preview now comes from error.CODE (surfaced to
            # the operator), not error.message. So under leak=True plant the
            # bearer-token in the CODE — that is the channel the fix exposes,
            # and the scrubber must still redact it. error.message stays prose
            # that is dropped entirely.
            failed_code = (
                f"generation_failed {leak_body_text}" if leak
                else "generation_failed"
            )
            return httpx.Response(200, json={
                "job_id": "j", "status": "failed",
                "error": {"code": failed_code, "message": "upstream prose msg"},
            })
        if reason == "job_cancelled":
            return httpx.Response(200, json={"job_id": "j", "status": "cancelled"})
        if reason == "job_timeout":
            return httpx.Response(200, json={"job_id": "j", "status": "processing"})
        return httpx.Response(404)

    client = _client_with_transport(app, handler)

    def call() -> httpx.Response:
        tc = TestClient(app)
        return tc.get("/krea/scene", params={
            "mood": "calm", "day_night": "day", "season": "summer",
        })

    return app, client, call


# ── M1: ring buffer records exactly one entry per minted 503 (every reason) ─


@pytest.mark.parametrize("reason", _ALL_REASONS)
def test_spr04_each_reason_records_exactly_one_ring_entry(reason, monkeypatch):
    """M1 + rigor #3 (enumeration): tripping each reason once appends EXACTLY
    one sanitized ring entry (reason + scene_key match), AND the 503 body
    still carries the typed contract unchanged."""
    app, client, call = _trip(reason, monkeypatch)
    try:
        r = call()
        assert r.status_code == 503
        body = r.json()
        assert body["enabled"] is False
        assert body["isFallback"] is True
        assert body["reason"] == reason
        # DEFECT 3: the SACRED typed-503 contract is exactly these 4 keys for
        # EVERY reason — no preview/detail ever leaks into the body. Proven by
        # an exact key-set assertion across all 11 reasons (not just the 4
        # upstream-prose ones).
        assert set(body) == {"enabled", "isFallback", "reason", "scene_key"}
        snap = app.state.krea_failures.snapshot()
        assert len(snap["entries"]) == 1, snap
        entry = snap["entries"][0]
        assert entry["reason"] == reason
        assert entry["scene_key"] == "calm|day|summer"
        assert entry["timestamp"]
        assert "preview" in entry
        assert snap["failure_counts"][reason] == 1
    finally:
        client.close()


def test_spr04_ring_evicts_oldest_at_51(monkeypatch):
    """M1: the ring holds the LAST 50; the 51st append evicts the 1st (the
    per-reason counter is a TOTAL, not ring-bounded)."""
    monkeypatch.setenv("KREA_API_TOKEN", _FAKE_TOKEN)
    monkeypatch.setenv("KREA_DAILY_UNIT_CAP", "0")  # every call → over_budget
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("over-budget gate must not reach upstream")

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        for i in range(51):
            r = tc.get("/krea/scene", params={
                "mood": f"mood{i}", "day_night": "day", "season": "summer",
            })
            assert r.status_code == 503
        snap = app.state.krea_failures.snapshot()
        assert len(snap["entries"]) == 50
        keys = [e["scene_key"] for e in snap["entries"]]
        assert "mood0|day|summer" not in keys  # evicted
        assert "mood50|day|summer" in keys
        assert snap["failure_counts"]["over_daily_budget"] == 51  # total
    finally:
        client.close()


def test_spr04_scrub_runs_before_storage_on_ring(monkeypatch):
    """M1 + rigor #1: an upstream body embedding a bearer-like token is
    scrubbed BEFORE it enters the ring — the stored preview carries ZERO
    occurrences of the planted token (proof by construction) and is ≤300."""
    app, client, call = _trip("upstream_error", monkeypatch, leak=True)
    try:
        r = call()
        assert r.status_code == 503
        preview = app.state.krea_failures.snapshot()["entries"][0]["preview"]
        assert "PLANTEDLEAKMARKER" not in preview
        assert _FAKE_TOKEN not in preview
        assert "[redacted]" in preview
        assert len(preview) <= 300
    finally:
        client.close()


def test_spr04_unit_scrubber_redacts_every_credential_shape():
    """M1 + rigor #1 (unit): the scrubber redacts each credential SHAPE it
    claims to, leaving no original secret bytes."""
    samples = [
        f"Authorization: Bearer {_FAKE_TOKEN}",
        f"token={_FAKE_TOKEN}",
        'api_key: "abcdef0123456789ABCDEF"',
        'password="hunter2hunter2hunter2"',
        "sk-abcdefghijklmnop0123456789",
    ]
    for s in samples:
        out = kr._scrub_secrets(s)
        assert _FAKE_TOKEN not in out
        assert "abcdef0123456789ABCDEF" not in out
        assert "hunter2hunter2hunter2" not in out
        assert "abcdefghijklmnop0123456789" not in out
        assert "[redacted]" in out


def test_spr04_short_odd_token_redacted_by_exact_match_every_channel(
    monkeypatch, caplog,
):
    """DEFECT 2 + rigor #1: a short / odd-shaped configured token (12 chars,
    NO `sk-` prefix, label-DETACHED) echoed BARE in an upstream preview would
    slip past the 24-char catch-all + the labelled patterns — but the exact
    substring redaction of the configured KREA_API_TOKEN removes it FIRST,
    regardless of shape. Prove it is ABSENT from the ring entry, the
    /krea/status payload, the WARNING, AND the 503 body."""
    short_token = "QZ7kP2mW9xLr"  # 12 chars, no sk- prefix, no label nearby
    assert len(short_token) == 12  # below the 24-char catch-all floor
    bare_in_prose = f"upstream rejected request {short_token} for account"
    # The SHAPE patterns ALONE do NOT catch this bare token (no label, <24
    # chars) — proven directly: with NO token configured the scrubber leaves
    # it intact. ONLY the exact-match on the configured value redacts it,
    # which is the BY-CONSTRUCTION claim DEFECT 2 closes.
    monkeypatch.delenv("KREA_API_TOKEN", raising=False)
    assert short_token in kr._scrub_secrets(bare_in_prose)
    monkeypatch.setenv("KREA_API_TOKEN", short_token)
    assert short_token not in kr._scrub_secrets(bare_in_prose)  # now caught
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        # Upstream echoes the bare token (no "Bearer", no "token=" label) —
        # the detached-echo leak vector the catch-all floor cannot reach.
        return httpx.Response(500, text=bare_in_prose)

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        with caplog.at_level(logging.WARNING, logger="antiek.interfaces.krea"):
            r = tc.post("/krea/generate", json={"prompt": "x"})
        assert r.status_code == 503
        assert r.json()["reason"] == "upstream_error"
        # Ring entry preview.
        preview = app.state.krea_failures.snapshot()["entries"][0]["preview"]
        assert short_token not in preview
        assert "[redacted]" in preview
        # /krea/status payload.
        assert short_token not in tc.get("/krea/status").text
        # WARNING record.
        for rec in caplog.records:
            assert short_token not in rec.getMessage()
        # 503 body (which carries no preview at all, but assert anyway).
        assert short_token not in r.text
    finally:
        client.close()


# ── M4: structured WARNING at the single 503-minting boundary (every reason) ─


@pytest.mark.parametrize("reason", _ALL_REASONS)
def test_spr04_each_reason_emits_exactly_one_warning(reason, monkeypatch, caplog):
    """M4 + rigor #3: each reason emits EXACTLY one WARNING on the
    antiek.interfaces.krea logger with reason + scene_key + preview, and the
    503 body STILL excludes the preview (the log/response split)."""
    app, client, call = _trip(reason, monkeypatch)
    try:
        with caplog.at_level(logging.WARNING, logger="antiek.interfaces.krea"):
            r = call()
        assert r.status_code == 503
        recs = [
            rec for rec in caplog.records
            if rec.name == "antiek.interfaces.krea"
            and rec.levelno == logging.WARNING
        ]
        assert len(recs) == 1, [rec.getMessage() for rec in recs]
        msg = recs[0].getMessage()
        assert f"reason={reason}" in msg
        assert "scene_key=calm|day|summer" in msg
        assert "preview=" in msg
    finally:
        client.close()


@pytest.mark.parametrize("reason", _ALL_REASONS)
def test_spr04_warning_preview_scrubbed_and_body_excludes_preview(
    reason, monkeypatch, caplog,
):
    """M4 + rigor #1 + DEFECT 4 (enumeration, not sampling): for EVERY reason,
    a planted bearer-token appears in NEITHER the log record, the ring preview,
    the /krea/status payload, NOR the 503 body. The preview lives ONLY in the
    log/ring (sanitized); the response never carries it (the log/response
    split). The expectation per reason is bucket-driven (carrier → token
    present-then-redacted; empty-by-design → empty preview)."""
    app, client, call = _trip(reason, monkeypatch, leak=True)
    try:
        with caplog.at_level(logging.WARNING, logger="antiek.interfaces.krea"):
            r = call()
        assert r.status_code == 503
        # No channel ever carries the planted token (log + status payload).
        for rec in caplog.records:
            line = rec.getMessage()
            assert "PLANTEDLEAKMARKER" not in line
            assert _FAKE_TOKEN not in line
        assert "PLANTEDLEAKMARKER" not in tc_status_text(app)
        # 503 body excludes the preview/detail entirely (SACRED contract).
        assert "PLANTEDLEAKMARKER" not in r.text
        assert _FAKE_TOKEN not in r.text
        assert "Bearer" not in r.text
        body = r.json()
        assert body["reason"] == reason
        assert set(body) == {"enabled", "isFallback", "reason", "scene_key"}

        # DEFECT 4: enumerate the preview expectation per bucket.
        preview = app.state.krea_failures.snapshot()["entries"][0]["preview"]
        assert _FAKE_TOKEN not in preview
        assert "PLANTEDLEAKMARKER" not in preview
        if reason in _LEAK_CARRYING_REASONS:
            # The planted token rode the detail in → it must be REDACTED.
            assert "[redacted]" in preview, (reason, preview)
        elif reason in _DETAIL_NO_LEAK_ECHO_REASONS:
            # A real (non-empty) detail that simply does not echo the leak.
            assert preview != ""
        else:
            # Empty-by-design: gate rejects + terminal short-circuits carry
            # NO upstream detail, so the preview is empty.
            assert reason in _EMPTY_PREVIEW_REASONS
            assert preview == "", (reason, preview)
    finally:
        client.close()


def tc_status_text(app) -> str:
    """Read the /krea/status payload text on a fresh TestClient (the app's
    injected mock transport is irrelevant — /krea/status touches no network).
    Used by the leak sweep to assert no token rides the status surface."""
    return TestClient(app).get("/krea/status").text


# ── M2: GET /krea/status — auth, shape, read-only, no token bytes ─────────


def test_spr04_status_401_without_operator_creds(monkeypatch):
    """M2: /krea/status is NOT in the open-paths set, so with operator-auth
    configured it requires operator creds — 401 without them, 200 with the
    operator bearer (mirrors test_operator_bearer_middleware.py)."""
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "op_secret")
    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[],
    )
    tc = TestClient(app)
    r = tc.get("/krea/status")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "operator_auth_required"
    r2 = tc.get("/krea/status", headers={"Authorization": "Bearer op_secret"})
    assert r2.status_code == 200


def test_spr04_status_open_when_auth_disabled():
    """When operator-auth is NOT configured (test/local default), the
    middleware admits everything with a default operator identity, so
    /krea/status answers 200."""
    app = _app()
    tc = TestClient(app)
    assert tc.get("/krea/status").status_code == 200


def test_spr04_status_shape_locked_no_key_posture():
    """M2: the status payload shape is locked; the README mirrors it
    byte-for-byte. NO-KEY posture → key_present strict-bool False, verdict
    no_key, every section present."""
    app = _app()
    tc = TestClient(app)
    body = tc.get("/krea/status").json()
    assert set(body.keys()) == {
        "enabled", "key_present", "kill_switch", "gate_verdict",
        "budget", "rate_window", "cache", "last_success_at",
        "failure_counts", "failures",
    }
    assert body["key_present"] is False
    assert isinstance(body["key_present"], bool)
    assert body["kill_switch"] is False
    assert body["enabled"] is False
    assert body["gate_verdict"] == "no_key"
    assert body["budget"] == {"spent_today": 0, "cap": 50}
    assert set(body["rate_window"].keys()) == {"occupancy", "max", "window_s"}
    assert body["rate_window"]["occupancy"] == 0
    assert set(body["cache"].keys()) == {"entries", "hits", "misses"}
    assert body["last_success_at"] is None
    assert body["failure_counts"] == {}
    assert body["failures"] == []


def test_spr04_status_key_present_is_boolean_no_token_bytes(monkeypatch):
    """M2 + rigor #1: with a planted fake token, key_present is BOOLEAN True
    and NO field carries >8 consecutive chars of the token value."""
    monkeypatch.setenv("KREA_API_TOKEN", _FAKE_TOKEN)
    app = _app()
    tc = TestClient(app)
    r = tc.get("/krea/status")
    body = r.json()
    assert body["key_present"] is True
    assert isinstance(body["key_present"], bool)
    raw = r.text
    assert "PLANTEDLEAKMARKER" not in raw
    for i in range(0, len(_FAKE_TOKEN) - 8):
        window = _FAKE_TOKEN[i:i + 9]
        assert window not in raw, f"token slice leaked into status: {window!r}"


def test_spr04_status_gate_verdict_tracks_kill_switch(monkeypatch):
    """M2: key present + kill-switch on → verdict kill_switch (first gate),
    enabled False even though a key is present."""
    monkeypatch.setenv("KREA_API_TOKEN", _FAKE_TOKEN)
    monkeypatch.setenv("KREA_KILL_SWITCH", "1")
    app = _app()
    body = TestClient(app).get("/krea/status").json()
    assert body["key_present"] is True
    assert body["kill_switch"] is True
    assert body["gate_verdict"] == "kill_switch"
    assert body["enabled"] is False


def test_spr04_status_reflects_failures_and_last_success(monkeypatch):
    """M2: after a live success then a failure, the payload reports the
    failure in the ring + counts AND a non-null last_success_at (preserved
    across the later failure)."""
    monkeypatch.setenv("KREA_API_TOKEN", _FAKE_TOKEN)
    app = _app()
    mode = {"fail": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _SUBMIT_PATH:
            return httpx.Response(200, json={
                "job_id": "j", "status": "queued",
                "created_at": "2026-06-12T00:00:00Z",
            })
        if mode["fail"]:
            return httpx.Response(200, json={"job_id": "j", "status": "failed",
                                             "error": {"code": "x"}})
        return httpx.Response(200, json=_completed_body("j", "https://img/ok.png"))

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r1 = tc.get("/krea/scene", params={"mood": "calm", "day_night": "day",
                                           "season": "summer"})
        assert r1.status_code == 200
        s1 = tc.get("/krea/status").json()
        assert s1["last_success_at"] is not None
        assert s1["failure_counts"] == {}
        mode["fail"] = True
        r2 = tc.get("/krea/scene", params={"mood": "stormy", "day_night": "night",
                                           "season": "winter"})
        assert r2.status_code == 503
        s2 = tc.get("/krea/status").json()
        assert s2["failure_counts"]["job_failed"] == 1
        assert len(s2["failures"]) == 1
        assert s2["last_success_at"] == s1["last_success_at"]  # unchanged
    finally:
        client.close()


def test_spr04_status_is_read_only_counter_equality(monkeypatch):
    """M2 (read-only by COUNTER-EQUALITY, not impression): /krea/status,
    called 25x, perturbs NO budget / rate / cache / failure counter. Seed a
    miss→submit→put then a hit so every counter has moved, then assert
    byte-identical counters across the reads."""
    monkeypatch.setenv("KREA_API_TOKEN", _FAKE_TOKEN)
    app = _app()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _SUBMIT_PATH:
            return httpx.Response(200, json={
                "job_id": "j", "status": "queued",
                "created_at": "2026-06-12T00:00:00Z",
            })
        return httpx.Response(200, json=_completed_body("j", "https://img/ok.png"))

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        params = {"mood": "calm", "day_night": "day", "season": "summer"}
        tc.get("/krea/scene", params=params)  # miss + bill + put
        tc.get("/krea/scene", params=params)  # hit
        before = tc.get("/krea/status").json()
        for _ in range(25):
            tc.get("/krea/status")
        after = tc.get("/krea/status").json()
        assert after["budget"] == before["budget"]
        assert after["rate_window"]["occupancy"] == before["rate_window"]["occupancy"]
        assert after["cache"] == before["cache"]
        assert after["failure_counts"] == before["failure_counts"]
        assert after["failures"] == before["failures"]
    finally:
        client.close()
