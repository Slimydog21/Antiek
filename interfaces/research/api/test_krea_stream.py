"""SPR-05 — anti-per-frame-billing ceiling for the now-default living scene.

SPR-02 returned NO-GO on a near-real-time *generative* stream
(``docs/ams-v2/stream-spike.md``): doc-derived ceiling ~0.25 gen fps
(~4 s/image per the spike's 2026-05 doc snapshot) vs the ≥10 gen-fps
"near-real-time" bar, and a poll-driven pseudo-stream at that rate is
15 submits/min, exhausting the 50-unit daily cap in ~3.3 minutes (the
spike priced that at ~$0.60/min from its era's per-image rate; at the
corrected 2026-06-12 docs.krea.ai price of $0.007/request it is
~$0.105/min — the NO-GO is latency- and cap-bound, unchanged). So
SPR-05 ships PERIODIC mood-gated Krea stills over a 60fps procedural
floor, riding the EXISTING periodic ``/krea/scene`` path — NOT a stream.

This module is NOT a duplicate of ``tests/test_krea_routes.py`` (SPR-02),
which enumerates the per-route failure modes. This file LOCKS THREE
SPR-05-specific guarantees the living scene depends on, so a later sprint
that regresses them re-fails LOUDLY:

  (a) DISABLED-WITH-ZERO-UPSTREAM — every disabled posture (no-key /
      KREA_KILL_SWITCH=1 / over-budget past KREA_DAILY_UNIT_CAP) returns
      the typed 503 DisabledResponse ``{enabled:false, isFallback:true,
      reason:...}`` and makes ZERO upstream calls. (The living floor stays
      painted off these, never blank — the browser pixel-diff proof of
      that lives in the scene agent's ``e2e/scene-living.spec.ts``; here we
      prove the SERVER never bills/calls upstream while disabled.)

  (b) RUNAWAY-RE-REQUEST IS CAPPED, NOT UNBOUNDED — a per-frame re-request
      loop (the failure mode where a bug fetches Krea on the clock instead
      of only on mood change) is bounded two ways: identical scene-state
      hits the WARM CACHE (1 upstream submit, the rest free hits), and
      DISTINCT scene-state is bounded by the per-process RATE LIMIT
      (≤ KREA_RATE_LIMIT_MAX real submits / 60s). The measured ceiling is
      recorded below in units/min and fetches-per-120-ticks.

  (c) NO STREAMING ROUTE WAS ADDED — the ``/krea`` namespace exposes
      EXACTLY ``POST /krea/generate``, ``GET /krea/jobs/{job_id}``,
      ``GET /krea/scene`` and nothing matching a streaming shape
      (``/krea/stream``, ``/krea/sse``, a ``/krea`` websocket). SPR-05 adds
      no SSE/WebSocket/EventSource frame channel (RULE-1: none exists on
      origin/main, and the NO-GO verdict forbids one). NOTE: the wider app
      DOES have pre-existing non-krea streaming routes (``/ws/events``,
      ``/research/sessions/{id}/stream``); the assertion is scoped to the
      ``/krea`` namespace so it stays both true and precise.

──────────────────────────────────────────────────────────────────────
MEASURED CADENCE CEILING (derivation, rigor #5 — every number sourced):
──────────────────────────────────────────────────────────────────────
  * Per-process RATE LIMIT (krea_routes ``_DEFAULT_RATE_LIMIT_MAX`` = 6 /
    ``_DEFAULT_RATE_LIMIT_WINDOW_S`` = 60 s) ⇒ ceiling ≤ 6 real upstream
    submits / minute = ≤ 6 billable units / minute.
  * 6 units/min × $0.007/request (flux-1-dev, docs.krea.ai 2026-06-12;
    drawn from the prepaid API balance — there is NO API free tier) =
    ~$0.042/min upper bound — and that is only ever reached on a runaway
    of DISTINCT scene-states; real usage fetches only on mood change.
  * Procedural floor = 60 fps ⇒ 120 ticks = 2 s. A runaway loop fetching
    the SAME scene-state every frame for 120 ticks makes exactly
    **1 upstream submit** (the warm cache absorbs the other 119) — proven
    by test (b). That is the anti-per-frame-billing invariant: fetch rate
    is decoupled from frame rate.
  * Daily cap (``_DEFAULT_DAILY_UNIT_CAP`` = 50 ≈ $0.35/day at
    $0.007/request) is the hard ceiling regardless of cadence — proven by
    test (a)'s over-budget case.

Self-verify (from the worktree, or /Users/slimydog/Desktop/Antiek):
  ./.venv/bin/python -m pytest tests/test_krea_routes.py \
      interfaces/research/api/test_krea_stream.py -q
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.routing import WebSocketRoute

from interfaces.research.api.app import create_app

# ── Fixtures / helpers (mirror tests/test_krea_routes.py conventions) ────


@pytest.fixture(autouse=True)
def _clean_krea_env(monkeypatch):
    """Default to the NO-KEY, kill-switch-OFF posture for every test;
    individual tests opt into a key / kill-switch / budget overrides.
    Mirrors the SPR-02 suite so budget never bleeds across tests."""
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
    # register_wrestling=False keeps the test app lean (no dispatch import),
    # exactly as the SPR-02 suite does.
    return create_app(register_wrestling=False)


def _client_with_transport(app, handler) -> httpx.Client:
    """Inject an httpx.Client backed by a MockTransport so the Krea routes
    use it instead of a real network client. NO network is ever touched.
    Returns the client so the test can close it."""
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.krea.ai")
    app.state.krea_http_client = client
    return client


def _krea_paths(app) -> set[str]:
    return {
        getattr(r, "path", "")
        for r in app.routes
        if getattr(r, "path", "").startswith("/krea")
    }


# ── (a) Every disabled posture → typed 503 + ZERO upstream call ──────────
#
# The living scene leans on EVERY one of these resolving to the typed
# fallback with NO upstream call: a disabled posture must never bill and
# never even reach the network. (That the floor keeps PAINTING on these is
# the scene agent's browser pixel-diff; here we lock the SERVER half.)


def test_disabled_no_key_scene_503_zero_upstream():
    """No key (the sandbox default) → 503 no_key, scene_key carried, and
    the upstream handler is NEVER invoked (it would raise if it were)."""
    app = _app()
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise AssertionError("upstream called while no-key (must not happen)")

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.get(
            "/krea/scene",
            params={"mood": "calm", "day_night": "day", "season": "summer"},
        )
        assert r.status_code == 503
        body = r.json()
        assert body["enabled"] is False
        assert body["isFallback"] is True
        assert body["reason"] == "no_key"
        assert body["scene_key"] == "calm|day|summer"
        assert calls["n"] == 0  # zero upstream calls past the gate
    finally:
        client.close()


def test_disabled_kill_switch_scene_503_zero_upstream(monkeypatch):
    """KREA_KILL_SWITCH=1 forces fallback EVEN WITH a real key — the
    operator panic lever. The /krea/scene path must short-circuit before
    any upstream call."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    monkeypatch.setenv("KREA_KILL_SWITCH", "1")
    app = _app()
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise AssertionError("upstream called while kill-switch on")

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        r = tc.get("/krea/scene")
        assert r.status_code == 503
        body = r.json()
        assert body["enabled"] is False
        assert body["isFallback"] is True
        assert body["reason"] == "kill_switch"
        assert calls["n"] == 0
    finally:
        client.close()


def test_disabled_over_budget_scene_503_zero_further_upstream(monkeypatch):
    """Push past KREA_DAILY_UNIT_CAP: the first scene-state spends the one
    unit; the next DISTINCT scene-state trips over_daily_budget and makes
    NO further upstream call. This is the hard daily ceiling (50 units ≈
    $0.35/day at flux-1-dev's $0.007/request, docs.krea.ai 2026-06-12)
    that bounds the living scene regardless of cadence."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    monkeypatch.setenv("KREA_DAILY_UNIT_CAP", "1")  # cap at one image/day
    app = _app()
    submits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        # Submit path is model-in-path (docs.krea.ai flux-1-dev reference,
        # 2026-06-12): /generate/image/{model_path}.
        if request.url.path.startswith("/generate/image/"):
            submits["n"] += 1
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json={
                "job_id": "j", "status": "queued",
                "created_at": "2026-06-12T00:00:00Z",
            })
        # Completed-job shape: result.urls array of URI strings
        # (docs.krea.ai jobs reference, 2026-06-12).
        return httpx.Response(200, json={
            "job_id": "j", "status": "completed",
            "result": {"urls": ["https://img/a.png"]},
        })

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        # First DISTINCT scene-state consumes the single daily unit.
        r1 = tc.get("/krea/scene", params={"mood": "calm", "day_night": "day",
                                           "season": "summer"})
        assert r1.status_code == 200
        assert submits["n"] == 1
        # Second DISTINCT scene-state is over budget → typed fallback, and
        # NO further upstream submit (the cap blocks before the call).
        r2 = tc.get("/krea/scene", params={"mood": "stormy", "day_night": "night",
                                           "season": "winter"})
        assert r2.status_code == 503
        body = r2.json()
        assert body["enabled"] is False
        assert body["isFallback"] is True
        assert body["reason"] == "over_daily_budget"
        assert body["scene_key"] == "stormy|night|winter"
        assert submits["n"] == 1  # unchanged — no upstream call past the cap
    finally:
        client.close()


# ── (b) Runaway per-frame re-request is CAPPED, not unbounded ────────────
#
# THE anti-per-frame-billing proof. If a future bug fetches Krea on the
# clock instead of only on mood change, the SERVER caps the bleed two ways.


def test_runaway_identical_scene_state_caps_at_one_submit_over_120_ticks(
    monkeypatch,
):
    """A runaway loop that re-requests the SAME scene-state once per frame
    for 120 ticks (= 2 s at the 60fps floor) makes EXACTLY ONE upstream
    submit; the warm cache absorbs the other 119. Fetch rate is decoupled
    from frame rate — the core anti-per-frame-billing invariant."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    monkeypatch.setenv("KREA_DAILY_UNIT_CAP", "1000")  # don't trip the cap
    monkeypatch.setenv("KREA_RATE_LIMIT_MAX", "1000")   # don't trip the rate
    app = _app()
    submits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        # Model-in-path submit (docs.krea.ai flux-1-dev, 2026-06-12).
        if request.url.path.startswith("/generate/image/"):
            submits["n"] += 1
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json={
                "job_id": "j", "status": "queued",
                "created_at": "2026-06-12T00:00:00Z",
            })
        # Completed result.urls shape (docs.krea.ai jobs, 2026-06-12).
        return httpx.Response(200, json={
            "job_id": "j", "status": "completed",
            "result": {"urls": ["https://img/same.png"]},
        })

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        TICKS = 120  # 2 s at the 60fps procedural floor
        params = {"mood": "calm", "day_night": "day", "season": "summer"}
        statuses = []
        for _ in range(TICKS):
            statuses.append(tc.get("/krea/scene", params=params).status_code)
        # Every request succeeded from the warm cache after the first.
        assert all(s == 200 for s in statuses)
        # ONE upstream submit across 120 identical-state ticks.
        assert submits["n"] == 1, (
            f"per-frame re-request of an identical scene-state billed "
            f"{submits['n']} units over {TICKS} ticks; expected 1 "
            f"(cache must de-dupe) — anti-per-frame-billing REGRESSED"
        )
    finally:
        client.close()


def test_runaway_distinct_scene_states_bounded_by_rate_limit(monkeypatch):
    """A runaway loop that re-requests DISTINCT scene-states (so the cache
    never helps) is bounded by the per-process RATE LIMIT. With
    KREA_RATE_LIMIT_MAX=6 / 60s, the upstream submit count over a burst of
    20 distinct states stays at the cap (6) — the rest return rate_limited
    fallback. This is the units/min ceiling: ≤ 6 units/min ≈ $0.042/min at
    flux-1-dev's $0.007/request (docs.krea.ai, 2026-06-12), well inside
    the SPR-02 envelope (the rejected pseudo-stream burned 15 units/min —
    ~$0.60/min at the spike's 2026-05 per-image snapshot)."""
    monkeypatch.setenv("KREA_API_TOKEN", "test-token")
    monkeypatch.setenv("KREA_RATE_LIMIT_MAX", "6")     # the default ceiling
    monkeypatch.setenv("KREA_DAILY_UNIT_CAP", "1000")  # rate, not budget, gates
    app = _app()
    submits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        # Model-in-path submit (docs.krea.ai flux-1-dev, 2026-06-12).
        if request.url.path.startswith("/generate/image/"):
            submits["n"] += 1
            # Submit worked example (docs.krea.ai flux-1-dev, 2026-06-12).
            return httpx.Response(200, json={
                "job_id": "j", "status": "queued",
                "created_at": "2026-06-12T00:00:00Z",
            })
        # Completed result.urls shape (docs.krea.ai jobs, 2026-06-12).
        return httpx.Response(200, json={
            "job_id": "j", "status": "completed",
            "result": {"urls": ["https://img/x.png"]},
        })

    client = _client_with_transport(app, handler)
    try:
        tc = TestClient(app)
        BURST = 20  # 20 distinct scene-states hammered with no cache help
        reasons = []
        for i in range(BURST):
            # Each iteration is a DISTINCT scene-state (unique mood) so the
            # cache never absorbs it — the rate limit is the only governor.
            r = tc.get("/krea/scene", params={"mood": f"mood{i}",
                                              "day_night": "day",
                                              "season": "summer"})
            if r.status_code == 503:
                reasons.append(r.json()["reason"])
        # Upstream submits never exceed the rate-limit ceiling within the
        # 60s window — a runaway is CAPPED, not unbounded.
        assert submits["n"] <= 6, (
            f"distinct-state runaway billed {submits['n']} units; the "
            f"rate limit (6/60s) must cap it"
        )
        # And the excess requests were typed rate_limited fallbacks (no bill).
        assert "rate_limited" in reasons
    finally:
        client.close()


# ── (c) NO streaming route was added under /krea (RULE-1) ────────────────


def test_krea_namespace_is_exactly_three_routes_no_stream():
    """The /krea namespace exposes EXACTLY the three SPR-02 routes and
    nothing matching a streaming shape. SPR-05 (NO-GO) adds no SSE /
    WebSocket / EventSource / /krea/stream endpoint."""
    app = _app()
    krea = _krea_paths(app)
    assert krea == {
        "/krea/generate",
        "/krea/jobs/{job_id}",
        "/krea/scene",
    }, f"unexpected /krea route surface: {sorted(krea)}"

    # No krea path matches any streaming marker.
    streamy = [
        p for p in krea
        if any(tok in p.lower() for tok in (
            "stream", "/sse", "events", "/ws", "subscribe", "poll-stream",
        ))
    ]
    assert streamy == [], f"a /krea streaming route appeared: {streamy}"


def test_no_krea_websocket_route():
    """No WebSocket route lives under /krea. (The app DOES have a
    pre-existing, non-krea ``/ws/events`` websocket — that one is fine and
    out of scope; this asserts SPR-05 added no krea-namespaced WS channel.)"""
    app = _app()
    krea_ws = [
        r.path for r in app.routes
        if isinstance(r, WebSocketRoute) and r.path.startswith("/krea")
    ]
    assert krea_ws == [], f"a /krea websocket route appeared: {krea_ws}"


def test_krea_stream_path_404s_no_handler():
    """A direct probe of the would-be streaming path 404s — there is no
    handler. (Belt-and-suspenders to the route-surface assertion: a route
    accidentally registered under a name that dodged the marker scan would
    still respond here.)"""
    app = _app()
    tc = TestClient(app)
    for path in ("/krea/stream", "/krea/sse", "/krea/scene/stream"):
        r = tc.get(path)
        assert r.status_code == 404, (
            f"{path} unexpectedly handled ({r.status_code}) — a streaming "
            f"route may have been added"
        )
