"""Krea image-generation proxy (Mountain Shell SPR-02).

The secure broker between the browser and Krea. THREE things make this
module mandatory rather than a convenience:

  1. SECRET CONTAINMENT (INV-2). Krea authenticates with a long-lived
     ``Authorization: Bearer $KREA_API_TOKEN`` ONLY — per the public docs
     there is NO ephemeral / scoped client token a browser could safely
     hold. So the key MUST live server-side; the browser talks to
     ``/krea/*`` here and never sees the token (``grep -rn KREA_API_TOKEN
     apps/reading/src`` returns zero).
  2. BUDGET + KILL-SWITCH. Krea bills per generation (Flux ~$0.04/image,
     video ~$0.20/sec). A client-direct caller could run the bill to the
     moon; the server-side daily compute-unit cap + per-process rate limit
     + ``KREA_KILL_SWITCH`` flag bound spend and give the operator a single
     panic lever. Over budget / killed → the FALLBACK signal, never an
     upstream call.
  3. CACHE. Identical scene-state (mood / day-night / season) must not be
     re-billed; an in-memory TTL cache de-dupes generations.

Even if a scoped client token existed (it does not, per docs), (2) + (3)
alone justify the proxy. The cost paid is one extra network hop of
latency; the benefit is no leaked secret + bounded spend + de-billed
repeats.

GRACEFUL ABSENCE. There is NO ``KREA_API_TOKEN`` in the sandbox / CI.
Every endpoint here MUST function without it: it returns a clean, typed
"disabled" response (HTTP 503 with ``{"enabled": false, "reason": ...}``),
NEVER a 500, NEVER a crash, NEVER a hang. The fallback path is the DEFAULT
under test, not an afterthought. This mirrors the graceful-absence idiom
in ``substrate/dispatch/providers/bootstrap.py`` (``_maybe_deepseek`` ->
``None`` when the key is absent) and reuses the outbound-httpx idiom from
``substrate/dispatch/providers/openai_compat.py`` (injectable client,
``time.monotonic`` timing, separate ``TimeoutException`` / ``RequestError``
handling, status check before ``.json()``, body preview on error).

────────────────────────────────────────────────────────────────────────
HONESTY — the Krea wire shape below is DOC-DERIVED, NOT LIVE-VERIFIED.
────────────────────────────────────────────────────────────────────────
No live call was made (no key in sandbox). The exact request/response
shapes this module codes against, recorded so a maintainer can re-verify
when a real key arrives:

  Submit a generation (async job pattern):
    POST {BASE}/generate/image
    Headers: Authorization: Bearer <token>, Content-Type: application/json
    Body:    {"model": "flux", "prompt": "...", "width": W, "height": H}
    -> 200 {"job_id": "job_abc123", "status": "queued"}

  Poll a job:
    GET {BASE}/jobs/{job_id}
    Headers: Authorization: Bearer <token>
    -> 200 {"job_id": "...", "status": "completed",
            "output": {"image_url": "https://..."}}
       status in {"queued","processing","completed","failed"}.

BASE defaults to ``https://api.krea.ai`` and is overridable via
``ANTIEK_KREA_BASE_URL`` (mirrors the ``ANTIEK_DEEPSEEK_BASE_URL``
override convention). If the live schema differs, ONLY the small
``_submit_generation`` / ``_poll_job`` adapters below change — the budget,
cache, and disabled-signal contract the frontend consumes is stable.

This module touches NO DuckDB and NO db_lock — the single-writer invariant
is untouched (the cache is a process-local dict).
"""

from __future__ import annotations

import os
import threading
import time
from datetime import date
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ── Constants: defaults are DOC-DERIVED and CONSERVATIVE ────────────────

# Krea base URL. Doc-derived (api.krea.ai); override for proxying / a
# host change via ANTIEK_KREA_BASE_URL — mirrors the
# ANTIEK_DEEPSEEK_BASE_URL / ANTIEK_HERMES_BASE_URL convention in
# substrate/dispatch/providers/bootstrap.py.
_DEFAULT_BASE_URL = "https://api.krea.ai"

# Outbound request timeout (seconds). Krea's Flux model lands ~4s/image
# per the docs; the async submit returns a job_id fast, and we poll. We
# keep the per-HTTP-call timeout short so a hung connection never deadlocks
# the request handler. 15s comfortably covers a slow submit/poll round
# while staying well under any reasonable browser patience. Matches the
# spirit of openai_compat._DEFAULT_TIMEOUT_S (which is 120s for long
# synthesis — image submit/poll is far quicker, so we use a tighter bound).
_DEFAULT_TIMEOUT_S = 15.0

# How long to poll a submitted job before giving up and falling back.
# Doc-derived: Flux ~4s/image; under queueing it can take longer. We poll
# up to ~12s total (well past the ~4s nominal, short enough that the
# request handler returns promptly and the frontend can show the
# deterministic placeholder while a later refresh may hit the warm cache).
_POLL_BUDGET_S = 12.0
_POLL_INTERVAL_S = 0.75

# ── Budget knobs. EVERY number carries its derivation (rigor #5). ───────
#
# Krea pricing (doc-derived): Flux ~$0.04/image. The free tier is
# ~100 compute units/day; we treat ONE image generation as ONE compute
# unit for the cap (conservative — a unit can't cost less than an image).
#
# DAILY CAP. Default 50 units/day.
#   Derivation: 50 images x ~$0.04/image = ~$2.00/day worst case (~$60/mo).
#   That is HALF the free tier's ~100 units/day, so the default stays
#   inside the free allotment with headroom for the cache to absorb
#   repeats. Conservative on purpose: the operator raises it via
#   KREA_DAILY_UNIT_CAP once real demand + a paid plan justify it. A
#   living background that refreshes a few scene-states per session, with
#   the cache de-duping identical states, sits far under 50/day.
_DEFAULT_DAILY_UNIT_CAP = 50

# PER-PROCESS RATE LIMIT. Default 6 submissions / 60s window.
#   Derivation: Flux ~4s/image, so a single client genuinely needs at most
#   ~1 new generation every few seconds; 6/min is generous for one operator
#   driving one living background yet still caps a runaway loop (a bug that
#   re-requests every frame) at 6 bills/min instead of hundreds. This is a
#   coarse per-PROCESS limit (not per-IP) — single-operator workstation
#   posture (CLAUDE.md invariant 5); a per-tenant limit lands with
#   multi-user (Sprint 22+).
_DEFAULT_RATE_LIMIT_MAX = 6
_DEFAULT_RATE_LIMIT_WINDOW_S = 60.0

# CACHE TTL. Default 3600s (1 hour).
#   Derivation: a scene-state (mood/day-night/season) is stable for long
#   stretches — "afternoon / clear / summer" does not change minute to
#   minute. A 1-hour TTL means at most ~24 generations/day PER DISTINCT
#   scene-state even if every state is requested hourly, which combined
#   with the daily cap keeps spend bounded. Long enough to de-bill a
#   reading session's repeats; short enough that a day/season rollover
#   eventually refreshes the art.
_DEFAULT_CACHE_TTL_S = 3600.0

# CACHE BOUND. Hard cap on distinct cached entries so the in-memory dict
# can't grow without limit. The scene-state key space is small (a handful
# of moods x day-night x seasons ~= dozens), so 256 is comfortably above
# the real cardinality while bounding memory if a caller passes
# free-form prompts.
_CACHE_MAX_ENTRIES = 256

# Reasons surfaced in the disabled/fallback body. Stable strings the
# frontend may switch on (it primarily switches on enabled=false, but a
# precise reason aids debugging + honest UI copy).
_REASON_NO_KEY = "no_key"
_REASON_KILL_SWITCH = "kill_switch"
_REASON_OVER_BUDGET = "over_daily_budget"
_REASON_RATE_LIMITED = "rate_limited"
_REASON_UPSTREAM_ERROR = "upstream_error"
_REASON_UPSTREAM_TIMEOUT = "upstream_timeout"
_REASON_UPSTREAM_BAD_RESPONSE = "upstream_bad_response"
_REASON_JOB_FAILED = "job_failed"
_REASON_JOB_TIMEOUT = "job_timeout"


# ── Request / response models ───────────────────────────────────────────


class GenerateRequest(BaseModel):
    """POST /krea/generate body. ``prompt`` is the only required field;
    the rest carry doc-derived defaults. The browser never sends a key —
    it sends a prompt and the server attaches the bearer token."""

    prompt: str = Field(..., min_length=1, max_length=2000)
    # Doc-derived Flux default; the model id is a per-call argument, not a
    # pinned secret (mirrors how the dispatch tier supplies model ids).
    model: str = Field(default="flux", max_length=64)
    width: int = Field(default=1024, ge=64, le=2048)
    height: int = Field(default=1024, ge=64, le=2048)


class GenerateResponse(BaseModel):
    """200 from POST /krea/generate when enabled + under budget. Returns
    the upstream ``job_id`` for the client to poll via GET /krea/jobs/{id}.
    """

    enabled: bool = True
    job_id: str
    status: str  # doc-derived: "queued" | "processing" | "completed" | ...


class JobResponse(BaseModel):
    """200 from GET /krea/jobs/{id}. Mirrors the doc-derived poll shape."""

    enabled: bool = True
    job_id: str
    status: str
    image_url: Optional[str] = None


class SceneArt(BaseModel):
    """The art payload SPR-04 consumes from GET /krea/scene (the happy
    path). ``image_url`` is the generated background; ``cached`` tells the
    surface whether this came from the warm cache (no bill) vs a fresh
    generation."""

    enabled: bool = True
    isFallback: bool = False
    image_url: str
    scene_key: str
    cached: bool = False


class DisabledResponse(BaseModel):
    """The typed FALLBACK signal — returned (HTTP 503) for EVERY failure
    mode: no key, kill-switch, over-budget, rate-limited, upstream error /
    timeout / bad-json, job failed / timed out. NEVER a 500. The frontend
    treats any 503 here as ``isFallback: true`` and renders the
    deterministic placeholder. ``reason`` is a stable machine string;
    ``scene_key`` (when known) lets the surface keep its deterministic
    placeholder keyed to the same scene-state."""

    enabled: bool = False
    isFallback: bool = True
    reason: str
    scene_key: Optional[str] = None


# ── Budget + rate state (process-local; NOT DuckDB) ─────────────────────


class _BudgetState:
    """Process-local budget + rate counters. Thread-safe (the FastAPI
    handlers may run on a threadpool). Reset daily by date rollover. This
    is deliberately in-memory: it touches NO DuckDB and NO db_lock, so the
    single-writer invariant (CLAUDE.md invariant 1) is untouched. A
    server restart resets the day's tally — acceptable for a spend GUARD
    (it only ever lets LESS through after a restart within the same day if
    the OS clock is stable; the cap is a ceiling, not an accounting
    ledger). Real billing accounting is explicitly out of scope (SPR-02
    OOS: 'real billing dashboards')."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = date.today()
        self._units_today = 0
        self._recent_submits: list[float] = []  # monotonic timestamps

    def _roll_day_locked(self) -> None:
        today = date.today()
        if today != self._day:
            self._day = today
            self._units_today = 0
            self._recent_submits = []

    def daily_cap(self) -> int:
        # Env override read at call time so the operator can tune without a
        # restart; falls back to the conservative default. Mirrors the
        # env-override pattern used across bootstrap.py.
        raw = os.environ.get("KREA_DAILY_UNIT_CAP", "").strip()
        if raw:
            try:
                v = int(raw)
                if v >= 0:
                    return v
            except ValueError:
                pass
        return _DEFAULT_DAILY_UNIT_CAP

    def _rate_max(self) -> int:
        raw = os.environ.get("KREA_RATE_LIMIT_MAX", "").strip()
        if raw:
            try:
                v = int(raw)
                if v >= 0:
                    return v
            except ValueError:
                pass
        return _DEFAULT_RATE_LIMIT_MAX

    def over_daily_budget(self) -> bool:
        with self._lock:
            self._roll_day_locked()
            return self._units_today >= self.daily_cap()

    def rate_limited(self) -> bool:
        now = time.monotonic()
        window = _DEFAULT_RATE_LIMIT_WINDOW_S
        with self._lock:
            self._recent_submits = [
                t for t in self._recent_submits if now - t < window
            ]
            return len(self._recent_submits) >= self._rate_max()

    def record_submit(self, units: int = 1) -> None:
        """Charge the budget AFTER deciding to call upstream. Called only
        on a real (non-cached) submission so cache hits never bill."""
        with self._lock:
            self._roll_day_locked()
            self._units_today += units
            self._recent_submits.append(time.monotonic())

    def units_today(self) -> int:
        with self._lock:
            self._roll_day_locked()
            return self._units_today

    def reset(self) -> None:
        """Test hook — clear all counters."""
        with self._lock:
            self._day = date.today()
            self._units_today = 0
            self._recent_submits = []


class _SceneCache:
    """In-memory TTL cache keyed by scene-state. Bounded + thread-safe.
    A cache hit returns the prior generation's image_url so an identical
    scene is NEVER re-billed (rigor / milestone 3). Touches NO DuckDB."""

    def __init__(self, ttl_s: float = _DEFAULT_CACHE_TTL_S,
                 max_entries: int = _CACHE_MAX_ENTRIES) -> None:
        self._lock = threading.Lock()
        self._ttl_s = ttl_s
        self._max_entries = max_entries
        # key -> (expires_at_monotonic, image_url)
        self._store: dict[str, tuple[float, str]] = {}

    def _ttl(self) -> float:
        raw = os.environ.get("KREA_CACHE_TTL_S", "").strip()
        if raw:
            try:
                v = float(raw)
                if v > 0:
                    return v
            except ValueError:
                pass
        return self._ttl_s

    def get(self, key: str) -> Optional[str]:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, url = entry
            if now >= expires_at:
                # Expired — evict + miss so a stale day/season refreshes.
                self._store.pop(key, None)
                return None
            return url

    def put(self, key: str, url: str) -> None:
        now = time.monotonic()
        with self._lock:
            # Bound the dict: when full, evict the soonest-to-expire entry.
            if key not in self._store and len(self._store) >= self._max_entries:
                oldest = min(self._store.items(), key=lambda kv: kv[1][0])[0]
                self._store.pop(oldest, None)
            self._store[key] = (now + self._ttl(), url)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# ── Pure helpers ────────────────────────────────────────────────────────


def _base_url() -> str:
    return os.environ.get("ANTIEK_KREA_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _api_token() -> Optional[str]:
    """Graceful-absence read of the Krea token (mirrors bootstrap.py's
    ``if not os.environ.get(...): return None``). Returns None when the
    token is unset OR blank — the disabled path, not an error."""
    tok = os.environ.get("KREA_API_TOKEN", "").strip()
    return tok or None


def _kill_switch_on() -> bool:
    """``KREA_KILL_SWITCH`` is the operator panic lever. Any of the truthy
    strings flips it; default off. When on, EVERY generation falls back
    regardless of key (a deliberate, key-independent override)."""
    return os.environ.get("KREA_KILL_SWITCH", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def scene_key(mood: str, day_night: str, season: str) -> str:
    """The cache + placeholder key. DETERMINISTIC + normalized so
    "Afternoon" and "afternoon" hit the same cache entry and SPR-04's
    deterministic placeholder is stable across runs. The same key string
    is what the frontend hook derives for its offline placeholder, so the
    server cache key and the client placeholder key never disagree."""
    def _norm(s: str) -> str:
        return "".join(ch for ch in s.strip().lower() if ch.isalnum()) or "any"
    return f"{_norm(mood)}|{_norm(day_night)}|{_norm(season)}"


def _scene_prompt(mood: str, day_night: str, season: str) -> str:
    """Build the generation prompt from scene-state. Kept here (server
    side) so the browser never crafts prompts and the prompt is one
    auditable place. SPR-04 owns the actual visual; this is only the
    art-request text."""
    return (
        f"A serene mountain landscape, {day_night.strip().lower()}, "
        f"{season.strip().lower()} season, {mood.strip().lower()} mood, "
        "soft painterly illustration, wide aspect, calm reading backdrop"
    )


# ── Upstream adapters (doc-derived; the ONLY part that changes if the ───
#    live Krea schema differs from the docs) ────────────────────────────


def _ensure_client(client: Optional[httpx.Client]) -> tuple[httpx.Client, bool]:
    """Return (client, owns). Accept an injected client for tests
    (httpx.MockTransport) — same injectable-client idiom as
    openai_compat.OpenAICompatProvider. When None, build a short-timeout
    client we own + close."""
    if client is not None:
        return client, False
    return httpx.Client(timeout=_DEFAULT_TIMEOUT_S), True


class _UpstreamError(Exception):
    """Internal: any upstream problem. Carries a stable ``reason`` that
    becomes the DisabledResponse.reason. Never escapes as a 500 — the
    handlers map it to the typed 503 fallback."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


def _submit_generation(
    token: str,
    req: GenerateRequest,
    *,
    client: Optional[httpx.Client] = None,
) -> tuple[str, str]:
    """POST {BASE}/generate/image → (job_id, status). DOC-DERIVED shape.
    Reuses the openai_compat httpx idiom: monotonic timing, separate
    Timeout/RequestError handling, status check before .json(), tolerant
    of partial/garbage JSON. Raises _UpstreamError (never a bare crash)."""
    http, owns = _ensure_client(client)
    url = f"{_base_url()}/generate/image"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "model": req.model,
        "prompt": req.prompt,
        "width": req.width,
        "height": req.height,
    }
    try:
        try:
            resp = http.post(url, json=body, headers=headers)
        except httpx.TimeoutException as e:  # latency / timeout failure mode
            raise _UpstreamError(_REASON_UPSTREAM_TIMEOUT, str(e)) from e
        except httpx.RequestError as e:  # offline / DNS / connection refused
            raise _UpstreamError(_REASON_UPSTREAM_ERROR, str(e)) from e
        # 401 (invalid key), 429 (rate-limited upstream / queue), 5xx —
        # ALL collapse to the fallback signal. We do not retry here; the
        # frontend simply shows the placeholder and a later refresh may
        # succeed (and hit the warm cache).
        if resp.status_code != 200:
            preview = (resp.text or "")[:300]
            raise _UpstreamError(
                _REASON_UPSTREAM_ERROR,
                f"HTTP {resp.status_code} — {preview}",
            )
        try:
            data: Any = resp.json()
        except ValueError as e:  # partial / garbage JSON failure mode
            raise _UpstreamError(_REASON_UPSTREAM_BAD_RESPONSE, str(e)) from e
        if not isinstance(data, dict):
            raise _UpstreamError(
                _REASON_UPSTREAM_BAD_RESPONSE, f"non-object body: {type(data)}",
            )
        job_id = data.get("job_id")
        status = data.get("status") or "queued"
        if not isinstance(job_id, str) or not job_id:
            raise _UpstreamError(
                _REASON_UPSTREAM_BAD_RESPONSE, f"missing job_id: {str(data)[:200]}",
            )
        return job_id, str(status)
    finally:
        if owns:
            http.close()


def _poll_job(
    token: str,
    job_id: str,
    *,
    client: Optional[httpx.Client] = None,
) -> JobResponse:
    """GET {BASE}/jobs/{id} → JobResponse. DOC-DERIVED shape. One poll
    (not the loop) — the loop lives in the /krea/scene handler so a single
    poll is independently testable. Raises _UpstreamError on any problem."""
    http, owns = _ensure_client(client)
    url = f"{_base_url()}/jobs/{job_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        try:
            resp = http.get(url, headers=headers)
        except httpx.TimeoutException as e:
            raise _UpstreamError(_REASON_UPSTREAM_TIMEOUT, str(e)) from e
        except httpx.RequestError as e:
            raise _UpstreamError(_REASON_UPSTREAM_ERROR, str(e)) from e
        if resp.status_code != 200:
            preview = (resp.text or "")[:300]
            raise _UpstreamError(
                _REASON_UPSTREAM_ERROR,
                f"HTTP {resp.status_code} — {preview}",
            )
        try:
            data: Any = resp.json()
        except ValueError as e:
            raise _UpstreamError(_REASON_UPSTREAM_BAD_RESPONSE, str(e)) from e
        if not isinstance(data, dict):
            raise _UpstreamError(
                _REASON_UPSTREAM_BAD_RESPONSE, f"non-object body: {type(data)}",
            )
        status = str(data.get("status") or "")
        output = data.get("output")
        image_url = None
        if isinstance(output, dict):
            image_url = output.get("image_url")
        # Some doc variants put the URL at the top level; tolerate both.
        if not image_url:
            image_url = data.get("image_url")
        if image_url is not None and not isinstance(image_url, str):
            image_url = None
        return JobResponse(
            job_id=job_id, status=status or "unknown", image_url=image_url,
        )
    finally:
        if owns:
            http.close()


# ── Route registration ──────────────────────────────────────────────────


def register_krea_routes(app: FastAPI) -> None:
    """Mount the Krea proxy routes. One call from ``create_app`` (mirrors
    ``register_book_routes``). The budget + cache state is created here so
    each app instance (incl. each TestClient app) gets its own — tests
    don't bleed budget into each other.

    State is exposed on ``app.state.krea_budget`` / ``app.state.krea_cache``
    so a test can reset/clear it deterministically without monkeypatching
    module globals."""

    budget = _BudgetState()
    cache = _SceneCache()
    app.state.krea_budget = budget
    app.state.krea_cache = cache
    # Optional injected httpx client for tests (MockTransport). Production
    # leaves this None → each call builds + closes its own short-timeout
    # client. Set via app.state.krea_http_client in a test.
    app.state.krea_http_client = None

    def _http() -> Optional[httpx.Client]:
        return getattr(app.state, "krea_http_client", None)

    def _disabled(reason: str, scene: Optional[str] = None) -> JSONResponse:
        """Build the typed 503 fallback body. ALWAYS 503, NEVER 500."""
        payload = DisabledResponse(reason=reason, scene_key=scene)
        return JSONResponse(status_code=503, content=payload.model_dump())

    def _gate() -> Optional[str]:
        """Return a fallback reason if generation is NOT permitted right
        now, else None. Order: kill-switch (operator override, key-
        independent) → no-key → over-budget → rate-limited. The first
        gate that trips short-circuits, and NO upstream call is made past
        any tripped gate (rigor #3 + milestone 2 acceptance)."""
        if _kill_switch_on():
            return _REASON_KILL_SWITCH
        if _api_token() is None:
            return _REASON_NO_KEY
        if budget.over_daily_budget():
            return _REASON_OVER_BUDGET
        if budget.rate_limited():
            return _REASON_RATE_LIMITED
        return None

    @app.post("/krea/generate", tags=["krea"])
    def krea_generate(req: GenerateRequest):
        """Submit a generation. Returns 200 {job_id,status} when enabled +
        under budget; otherwise the typed 503 fallback. Charges the budget
        ONLY on a successful upstream submit (a gated request never bills,
        and an upstream failure does not bill a phantom unit).

        SYNC handler ON PURPOSE: it makes a blocking httpx call. Declared
        ``def`` (not ``async def``) so Starlette runs it in the threadpool
        and the blocking I/O never stalls the single-worker event loop
        (CLAUDE.md invariant 1: uvicorn --workers 1)."""
        blocked = _gate()
        if blocked is not None:
            return _disabled(blocked)
        token = _api_token()
        assert token is not None  # _gate() guarantees this
        try:
            job_id, status = _submit_generation(token, req, client=_http())
        except _UpstreamError as e:
            # Every upstream failure mode (timeout / network / 401 / 429 /
            # 5xx / bad-json) ends here → typed fallback, never a 500.
            return _disabled(e.reason)
        budget.record_submit(units=1)
        return JSONResponse(
            status_code=200,
            content=GenerateResponse(job_id=job_id, status=status).model_dump(),
        )

    @app.get("/krea/jobs/{job_id}", tags=["krea"])
    def krea_job(job_id: str):
        """Poll a submitted job. 200 {job_id,status,image_url?} when
        enabled; typed 503 fallback when disabled / on any upstream
        failure. Polling does NOT bill (only the submit does).

        SYNC handler (see krea_generate): blocking httpx in the threadpool,
        never on the event loop."""
        if _kill_switch_on():
            return _disabled(_REASON_KILL_SWITCH)
        token = _api_token()
        if token is None:
            return _disabled(_REASON_NO_KEY)
        try:
            job = _poll_job(token, job_id, client=_http())
        except _UpstreamError as e:
            return _disabled(e.reason)
        return JSONResponse(status_code=200, content=job.model_dump())

    @app.get("/krea/scene", tags=["krea"])
    def krea_scene(
        mood: str = Query(default="calm", max_length=64),
        day_night: str = Query(default="day", max_length=64),
        season: str = Query(default="summer", max_length=64),
    ):
        """The higher-level endpoint SPR-04 consumes. Encapsulates
        prompt-building + cache + budget + submit + poll-to-completion
        behind a single GET keyed by scene-state.

        SYNC handler — CRITICAL. This endpoint runs a blocking poll loop
        (``time.sleep`` up to ``_POLL_BUDGET_S`` = 12s). Declared ``def``
        (not ``async def``) so Starlette runs it in the threadpool; an
        ``async def`` here would block the single-worker event loop for the
        whole poll, stalling /health, the WS tail, and every other request
        (CLAUDE.md invariant 1). The three scene axes are length-bounded
        (Query max_length=64) so a direct caller can't blow up the cache-key
        cardinality or the built prompt (symmetry with GenerateRequest's
        field caps).

        Flow:
          1. Compute the deterministic scene_key.
          2. CACHE HIT → return the cached art (cached=true), NO upstream
             call, NO bill. (A second identical /krea/scene is a hit.)
          3. Gate (kill-switch / no-key / over-budget / rate-limited) →
             typed 503 fallback carrying scene_key (so the surface keeps a
             stable placeholder).
          4. Submit → poll up to _POLL_BUDGET_S → on completion cache +
             return art; on failure/timeout → typed 503 fallback.
        """
        key = scene_key(mood, day_night, season)

        # 2. Cache hit — never re-bill an identical scene-state.
        cached_url = cache.get(key)
        if cached_url is not None:
            return JSONResponse(
                status_code=200,
                content=SceneArt(
                    image_url=cached_url, scene_key=key, cached=True,
                ).model_dump(),
            )

        # 3. Gate. carry scene_key so the placeholder stays keyed.
        blocked = _gate()
        if blocked is not None:
            return _disabled(blocked, scene=key)

        token = _api_token()
        assert token is not None
        gen = GenerateRequest(prompt=_scene_prompt(mood, day_night, season))
        try:
            job_id, _status = _submit_generation(token, gen, client=_http())
        except _UpstreamError as e:
            return _disabled(e.reason, scene=key)
        # Charge the budget for the real submit (cache miss only).
        budget.record_submit(units=1)

        # 4. Poll to completion within the poll budget.
        deadline = time.monotonic() + _POLL_BUDGET_S
        while True:
            try:
                job = _poll_job(token, job_id, client=_http())
            except _UpstreamError as e:
                return _disabled(e.reason, scene=key)
            if job.status == "completed" and job.image_url:
                cache.put(key, job.image_url)
                return JSONResponse(
                    status_code=200,
                    content=SceneArt(
                        image_url=job.image_url, scene_key=key, cached=False,
                    ).model_dump(),
                )
            if job.status == "failed":
                return _disabled(_REASON_JOB_FAILED, scene=key)
            if time.monotonic() >= deadline:
                # Took too long — fall back now; a later refresh may find
                # the job done and (if the surface re-requests) it can warm
                # the cache. We do NOT hang the request.
                return _disabled(_REASON_JOB_TIMEOUT, scene=key)
            time.sleep(_POLL_INTERVAL_S)
