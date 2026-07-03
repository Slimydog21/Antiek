"""Krea image-generation proxy (Mountain Shell SPR-02).

The secure broker between the browser and Krea. THREE things make this
module mandatory rather than a convenience:

  1. SECRET CONTAINMENT (INV-2). Krea authenticates with a long-lived
     ``Authorization: Bearer $KREA_API_TOKEN`` ONLY — per the public docs
     there is NO ephemeral / scoped client token a browser could safely
     hold. So the key MUST live server-side; the browser talks to
     ``/krea/*`` here and never sees the token (``grep -rn KREA_API_TOKEN
     apps/reading/src`` returns zero).
  2. BUDGET + KILL-SWITCH. Krea bills per generation against a PREPAID
     API balance — separate from any web subscription's compute units,
     $5 minimum top-up, HTTP 402 when empty (docs.krea.ai, 2026-06-12).
     flux-1-dev is $0.007/request; there is NO API free tier. A
     client-direct caller could still drain the balance; the server-side
     daily unit cap + per-process rate limit + ``KREA_KILL_SWITCH`` flag
     bound spend and give the operator a single panic lever. Over budget
     / killed → the FALLBACK signal, never an upstream call.
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
HONESTY — wire shapes are DOCS-CURRENT AS OF 2026-06-12; LIVE
VERIFICATION IS PENDING SPR-09 (the first capped live smoke).
────────────────────────────────────────────────────────────────────────
No live call has ever been made from this codebase (no funded key was
ever present). The shapes below are TRANSCRIPTIONS of docs.krea.ai
(the API launched in its current form 2026-05-27), re-verified against
the docs 2026-06-12 — transcriptions, not observations. Do NOT delete
this banner when tests are green; retire it only after SPR-09 records
live behavior. The shapes this module codes against:

  Submit a generation (async job pattern; the MODEL IS IN THE PATH,
  vendor-prefixed — docs.krea.ai flux-1-dev reference, 2026-06-12):
    POST {BASE}/generate/image/{model_path}    e.g. bfl/flux-1-dev
    Headers: Authorization: Bearer <token>, Content-Type: application/json
    Body:    {"prompt": "...", "width": W, "height": H}
             (NO model key in the body — the model is the URL path;
              other models live at other paths, e.g. krea/krea-2/medium)
    -> 200 {"job_id": "...", "status": "queued", "created_at": ...}
       (the docs' worked example; submit responses do NOT carry a
        result at submit time — assumption noted in fixture comments)
    -> 402 {"message": ...} when the prepaid API balance is empty.

  Poll a job (docs.krea.ai jobs reference, 2026-06-12):
    GET {BASE}/jobs/{job_id}
    Headers: Authorization: Bearer <token>
    -> 200 {"job_id": "...", "status": "...",
            "result": {"urls": ["https://...", ...]}}  on completion
       ``result.urls`` is an ARRAY OF URI STRINGS — take [0]; ``result``
       may also carry ``style_id`` (ignored here). Failed jobs carry
       ``"error": {"code": ..., "message": ...}`` instead.
       status enum (9 states): backlogged | queued | scheduled |
       processing | sampling | intermediate-complete | completed |
       failed | cancelled. TERMINAL: completed / failed / cancelled.
       Krea does NOT bill failed/cancelled jobs (we still count the
       submit locally — see the bill-on-submit divergence comment at
       the recording sites).

BASE defaults to ``https://api.krea.ai`` and is overridable via
``ANTIEK_KREA_BASE_URL`` (mirrors the ``ANTIEK_DEEPSEEK_BASE_URL``
override convention). If the live schema differs, ONLY the small
``_submit_generation`` / ``_poll_job`` adapters below change — the budget,
cache, and disabled-signal contract the frontend consumes is stable.

This module touches NO DuckDB and NO db_lock — the single-writer invariant
is untouched (the cache is a process-local dict).

────────────────────────────────────────────────────────────────────────
SPR-05 POSTURE — PERIODIC ART, NOT A STREAM (SPR-02 returned NO-GO).
────────────────────────────────────────────────────────────────────────
The v2 mountain shell ships a 60fps procedural floor with PERIODIC,
mood-gated Krea stills crossfaded over it — NOT a near-real-time
generative stream. The stream was ruled out in ``docs/ams-v2/stream-spike.md``
(verdict: NO-GO): the doc-derived generative ceiling is ~0.25 gen fps
(~4 s/image per the spike's 2026-05 doc snapshot) against a ≥10 gen-fps
"near-real-time" bar, and a poll-driven pseudo-stream at that rate is
15 submits/min — burning the 50-unit daily cap in ~3.3 minutes. (The
spike priced that at ~$0.60/min from its 2026-05 per-image snapshot; at
the corrected 2026-06-12 price of $0.007/request it is ~$0.105/min —
the NO-GO is unchanged: it is latency- and cap-exhaustion-bound, not
only price-bound.) So:

  - NO streaming route is added here (no SSE / WebSocket / EventSource /
    ``/krea/stream``). The ``/krea`` namespace stays exactly three routes:
    ``POST /krea/generate``, ``GET /krea/jobs/{job_id}``, ``GET /krea/scene``.
  - The now-default living scene rides the EXISTING periodic ``/krea/scene``
    path (submit → poll-to-completion → cache → typed-503 fallback). The
    anti-per-frame-billing guardrails below (``_gate`` order, ``_BudgetState``
    daily cap + rate limit, ``_SceneCache`` warm-cache de-dupe, the typed
    ``DisabledResponse``) are what bound spend for the living background.
  - A streaming route is the NAMED FUTURE-GO task: it lands ONLY if a real
    ``KREA_API_TOKEN`` benchmarks a sub-second model at <500 ms TTFF,
    ≥10 gen fps, ≤~$0.10/min at the cap (the three rows §5 of the spike
    records as "not measured (no key)"). It would attach at the upstream-
    adapter seam (``_submit_generation`` / ``_poll_job`` below — the
    "L411" seam stream-spike.md §1 names) and re-use this same
    budget/cache/typed-503 contract — see ``stream-spike.md`` §4/§5.

``tests/test_krea_routes.py`` (SPR-02) covers the per-route failure modes;
``interfaces/research/api/test_krea_stream.py`` (SPR-05) locks the
anti-per-frame-billing CEILING for the living-scene cadence and asserts
NO streaming route was added.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("antiek.interfaces.krea")

# ── Constants: defaults are DOC-DERIVED and CONSERVATIVE ────────────────

# Krea base URL. Doc-derived (api.krea.ai); override for proxying / a
# host change via ANTIEK_KREA_BASE_URL — mirrors the
# ANTIEK_DEEPSEEK_BASE_URL / ANTIEK_HERMES_BASE_URL convention in
# substrate/dispatch/providers/bootstrap.py.
_DEFAULT_BASE_URL = "https://api.krea.ai"

# Outbound per-HTTP-call timeout (seconds). UNCHANGED at 15s (SPR-01,
# 2026-06-12): this bounds ONE network round-trip (a submit POST or a
# poll GET — both return promptly; job latency is the POLL BUDGET's
# problem, not this one's), so a hung connection never deadlocks the
# request handler. Matches the spirit of openai_compat._DEFAULT_TIMEOUT_S
# (120s for long synthesis — a single submit/poll round-trip is far
# quicker, so we keep the tighter bound).
_DEFAULT_TIMEOUT_S = 15.0

# How long to poll a submitted job before giving up and falling back.
# Default 30s. Source (docs.krea.ai, 2026-06-12): flux-1-dev's latency is
# NOT documented, so we take the nearest documented model — Krea-2 at
# ~10s/generation — and budget 3x for headroom; 30s is also well under
# Krea's documented 3-minute hosted job timeout. Override via
# KREA_POLL_BUDGET_S (read at call time via _poll_budget_s(), like the
# other knobs). On expiry the handler returns the typed job_timeout
# fallback promptly — a later refresh may find the job done.
_POLL_BUDGET_S = 30.0

# Poll cadence. Source (docs.krea.ai, 2026-06-12): the docs say to poll
# job status every 2–5 seconds. 2.5s sits at the bottom of that band so
# a fast job is noticed promptly while staying inside the guidance (the
# shipped 0.75s was below it — out of contract).
_POLL_INTERVAL_S = 2.5

# Default model path for the submit URL. Source (docs.krea.ai flux-1-dev
# reference, 2026-06-12): the model is a vendor-prefixed URL path segment
# (POST {BASE}/generate/image/bfl/flux-1-dev), NOT a body field. Other
# models live at other paths (e.g. krea/krea-2/medium); the
# ANTIEK_KREA_MODEL_PATH env knob (see _model_path) covers future swaps.
_DEFAULT_MODEL_PATH = "bfl/flux-1-dev"

# Poll-loop clock seam. The /krea/scene poll loop reads these module
# aliases (NOT time.monotonic/time.sleep directly) so tests can install a
# mock clock and prove the 2.5s interval + the poll budget are honored
# without any real sleeps (rigor #3). Production behavior is identical:
# these ARE the real clock functions.
_monotonic = time.monotonic
_sleep = time.sleep

# ── Budget knobs. EVERY number carries its derivation (rigor #5). ───────
#
# Krea pricing (docs.krea.ai, 2026-06-12): flux-1-dev is $0.007/request.
# There is NO API free tier — the API draws a separate PREPAID USD
# balance ($5 minimum top-up; distinct from any web subscription's
# compute units; upstream returns HTTP 402 when it is empty, mapped to
# the no_api_balance reason below). We treat ONE image generation as ONE
# budget unit.
#
# DAILY CAP. Default 50 units/day.
#   Derivation: 50 requests x $0.007/request ≈ $0.35/day worst case
#   (~$10.50/mo) against the prepaid balance — i.e. a $5 minimum top-up
#   survives ≥14 maxed-out days. Conservative on purpose: the operator
#   raises it via KREA_DAILY_UNIT_CAP once real demand justifies it. A
#   living background that refreshes a few scene-states per session, with
#   the cache de-duping identical states, sits far under 50/day.
_DEFAULT_DAILY_UNIT_CAP = 50

# PER-PROCESS RATE LIMIT. Default 6 submissions / 60s window.
#   Derivation: generation takes seconds (Krea-2 is documented ~10s;
#   flux-1-dev undocumented), so a single client genuinely needs at most
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
# precise reason aids debugging + honest UI copy). The vocabulary is
# ADDITIVE-ONLY: existing strings are a frozen frontend contract — never
# rename or remove one; new failure modes get NEW strings (mirrored in
# apps/reading/src/api/krea.ts's reason doc + src/krea/README.md).
_REASON_NO_KEY = "no_key"
_REASON_KILL_SWITCH = "kill_switch"
_REASON_OVER_BUDGET = "over_daily_budget"
_REASON_RATE_LIMITED = "rate_limited"
_REASON_UPSTREAM_ERROR = "upstream_error"
_REASON_UPSTREAM_TIMEOUT = "upstream_timeout"
_REASON_UPSTREAM_BAD_RESPONSE = "upstream_bad_response"
_REASON_JOB_FAILED = "job_failed"
_REASON_JOB_TIMEOUT = "job_timeout"
# ADDITIVE 2026-06-12 (SPR-01) — two reasons for live-API states the
# doc-derived adapters could not name (docs.krea.ai, 2026-06-12):
#   job_cancelled  — the job reached the terminal "cancelled" state of
#                    the 9-state lifecycle; polling stops immediately.
#   no_api_balance — upstream HTTP 402: Krea's prepaid API balance
#                    (separate from any subscription) is empty. The
#                    operator's signal to top up, distinct from our own
#                    local over_daily_budget guard.
_REASON_JOB_CANCELLED = "job_cancelled"
_REASON_NO_API_BALANCE = "no_api_balance"
_ALL_DISABLED_REASONS = (
    _REASON_NO_KEY,
    _REASON_KILL_SWITCH,
    _REASON_OVER_BUDGET,
    _REASON_RATE_LIMITED,
    _REASON_UPSTREAM_ERROR,
    _REASON_UPSTREAM_TIMEOUT,
    _REASON_UPSTREAM_BAD_RESPONSE,
    _REASON_JOB_FAILED,
    _REASON_JOB_TIMEOUT,
    _REASON_JOB_CANCELLED,
    _REASON_NO_API_BALANCE,
)
_FAILURE_RING_MAXLEN = 50

# ── Request bounds. Transcribed from the flux-1-dev model reference ─────
# (docs.krea.ai, 2026-06-12). Enforced at the proxy BEFORE any billable
# submit: scene prompts are proxy-built (and clamped in _scene_prompt);
# direct /krea/generate callers get a 422 naming the violated bound
# (FastAPI/Pydantic includes the bound in the validation message).
#   prompt: max 1800 characters (the shipped 2000 admitted requests the
#           API would reject — i.e. invalid-but-billable risk).
#   width/height: 512–2368 px (the shipped 64–2048 was half out of
#           contract on both ends).
_PROMPT_MAX_CHARS = 1800
_DIM_MIN_PX = 512
_DIM_MAX_PX = 2368


# ── Request / response models ───────────────────────────────────────────


class GenerateRequest(BaseModel):
    """POST /krea/generate body. ``prompt`` is the only required field;
    the rest carry defaults inside the flux-1-dev bounds (docs.krea.ai,
    2026-06-12). The browser never sends a key — it sends a prompt and
    the server attaches the bearer token. The MODEL is NOT a body field
    (removed 2026-06-12): per the flux-1-dev reference the model is the
    URL path segment, server-selected via ANTIEK_KREA_MODEL_PATH (see
    _model_path). Unknown body keys from older clients are ignored by
    Pydantic's default config."""

    # flux-1-dev: prompt max 1800 chars (docs.krea.ai, 2026-06-12).
    prompt: str = Field(..., min_length=1, max_length=_PROMPT_MAX_CHARS)
    # flux-1-dev: width/height 512–2368 px (docs.krea.ai, 2026-06-12);
    # the 1024 default sits comfortably inside the band.
    width: int = Field(default=1024, ge=_DIM_MIN_PX, le=_DIM_MAX_PX)
    height: int = Field(default=1024, ge=_DIM_MIN_PX, le=_DIM_MAX_PX)


class GenerateResponse(BaseModel):
    """200 from POST /krea/generate when enabled + under budget. Returns
    the upstream ``job_id`` for the client to poll via GET /krea/jobs/{id}.
    """

    enabled: bool = True
    job_id: str
    # The 9-state job lifecycle (docs.krea.ai, 2026-06-12): backlogged |
    # queued | scheduled | processing | sampling | intermediate-complete |
    # completed | failed | cancelled. A submit answers "queued" in the
    # docs' worked example; kept a free string so a future upstream state
    # never crashes the proxy.
    status: str


class JobResponse(BaseModel):
    """200 from GET /krea/jobs/{id}. Mirrors the docs.krea.ai job shape
    (2026-06-12): ``status`` is the 9-state lifecycle enum (see
    GenerateResponse.status), ``image_url`` is ``result.urls[0]`` on
    completion, and ``error_code`` (ADDITIVE 2026-06-12) is the stable
    machine code from a failed job's ``error`` object. The upstream error
    MESSAGE is parsed but never serialized — sanitized-preview
    discipline: no upstream prose reaches the browser."""

    enabled: bool = True
    job_id: str
    status: str
    image_url: str | None = None
    error_code: str | None = None


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
    timeout / bad-json, job failed / timed out / cancelled, empty prepaid
    API balance (402). NEVER a 500. The frontend
    treats any 503 here as ``isFallback: true`` and renders the
    deterministic placeholder. ``reason`` is a stable machine string;
    ``scene_key`` (when known) lets the surface keep its deterministic
    placeholder keyed to the same scene-state."""

    enabled: bool = False
    isFallback: bool = True
    reason: str
    scene_key: str | None = None


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

    def status_snapshot(self) -> dict[str, Any]:
        """Read-only budget/rate snapshot for GET /krea/status.

        This intentionally avoids _roll_day_locked() and rate_limited(), both
        of which mutate state. It reports the counters as the gates would see
        them now without pruning or resetting during observation.
        """
        now = time.monotonic()
        window = _DEFAULT_RATE_LIMIT_WINDOW_S
        with self._lock:
            in_window = sum(1 for t in self._recent_submits if now - t < window)
            cap = self.daily_cap()
            return {
                "budget": {
                    "spent_today": self._units_today,
                    "cap": cap,
                    "remaining": max(cap - self._units_today, 0),
                },
                "rate_window": {
                    "occupancy": in_window,
                    "max": self._rate_max(),
                    "window_s": window,
                },
            }

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

    def get(self, key: str) -> str | None:
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

    def stats(self) -> dict[str, int]:
        """Read-only cache snapshot for GET /krea/status."""
        with self._lock:
            return {"entries": len(self._store), "max_entries": self._max_entries}


class _FailureRing:
    """Thread-safe bounded ring of fallback reasons.

    Entries store reason classes and upstream status codes only. Raw upstream
    response bodies are deliberately excluded because vendors can echo bearer
    credentials in error text.
    """

    def __init__(self, maxlen: int = _FAILURE_RING_MAXLEN) -> None:
        self._lock = threading.Lock()
        self._entries: deque[dict[str, str | int | None]] = deque(maxlen=maxlen)
        self._counts: dict[str, int] = {}
        self._last_success_at: str | None = None

    def record(
        self,
        reason: str,
        *,
        scene_key: str | None = None,
        upstream_status: int | None = None,
    ) -> None:
        entry: dict[str, str | int | None] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "reason": reason,
            "scene_key": scene_key,
            "upstream_status": upstream_status,
        }
        with self._lock:
            self._entries.append(entry)
            self._counts[reason] = self._counts.get(reason, 0) + 1

    def mark_success(self) -> None:
        with self._lock:
            self._last_success_at = datetime.now(UTC).isoformat()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "entries": [dict(entry) for entry in self._entries],
                "failure_counts": dict(self._counts),
                "last_success_at": self._last_success_at,
            }


# ── Pure helpers ────────────────────────────────────────────────────────


def _base_url() -> str:
    return os.environ.get("ANTIEK_KREA_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _model_path() -> str:
    """The model segment of the submit URL (docs.krea.ai, 2026-06-12:
    POST {BASE}/generate/image/{model_path}; the model is vendor-prefixed
    IN THE PATH, not a body field). Read at call time via
    ANTIEK_KREA_MODEL_PATH — same no-restart-tuning convention as the
    other knobs — defaulting to the flux-1-dev path this module's
    fixtures transcribe. Slashes are trimmed at the edges so an operator
    value like ``/bfl/flux-1-dev/`` still forms a clean URL."""
    raw = os.environ.get("ANTIEK_KREA_MODEL_PATH", "").strip().strip("/")
    return raw or _DEFAULT_MODEL_PATH


def _poll_budget_s() -> float:
    """KREA_POLL_BUDGET_S override, read at call time (mirrors
    _BudgetState.daily_cap's env-override pattern). Falls back to
    _POLL_BUDGET_S = 30s — see the derivation at the constant (3x the
    documented Krea-2 ~10s; well under Krea's 3-minute job timeout)."""
    raw = os.environ.get("KREA_POLL_BUDGET_S", "").strip()
    if raw:
        try:
            v = float(raw)
            if v >= 0:
                return v
        except ValueError:
            pass
    return _POLL_BUDGET_S


def _api_token() -> str | None:
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
    art-request text.

    CLAMPED to the flux-1-dev prompt limit (_PROMPT_MAX_CHARS = 1800,
    docs.krea.ai 2026-06-12) BEFORE the billable submit: the three axes
    are length-bounded upstream (Query max_length=64) so the template
    sits far below the limit (asserted for every mood-matrix combination
    in tests/test_krea_routes.py), but the clamp makes over-limit
    structurally impossible — a proxy-built prompt must never fail its
    own GenerateRequest validation (clamping is safe here precisely
    because the prompt is proxy-built, not caller-supplied)."""
    text = (
        f"A serene mountain landscape, {day_night.strip().lower()}, "
        f"{season.strip().lower()} season, {mood.strip().lower()} mood, "
        "soft painterly illustration, wide aspect, calm reading backdrop"
    )
    return text[:_PROMPT_MAX_CHARS]


# ── Upstream adapters (doc-derived; the ONLY part that changes if the ───
#    live Krea schema differs from the docs) ────────────────────────────


def _ensure_client(client: httpx.Client | None) -> tuple[httpx.Client, bool]:
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

    def __init__(
        self,
        reason: str,
        detail: str = "",
        *,
        upstream_status: int | None = None,
    ) -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail
        self.upstream_status = upstream_status


def _submit_generation(
    token: str,
    req: GenerateRequest,
    *,
    client: httpx.Client | None = None,
    on_2xx: Callable[[], None] | None = None,
) -> tuple[str, str]:
    """POST {BASE}/generate/image/{model_path} → (job_id, status).

    Wire shape transcribed from docs.krea.ai (flux-1-dev reference,
    2026-06-12; live verification pending SPR-09): the model is the URL
    path segment (vendor-prefixed; selected via ANTIEK_KREA_MODEL_PATH),
    the body carries exactly prompt/width/height, and the docs' worked
    example answers {"job_id": ..., "status": "queued", "created_at": ...}.
    Reuses the openai_compat httpx idiom: separate Timeout/RequestError
    handling, status check before .json(), tolerant of partial/garbage
    JSON. Raises _UpstreamError (never a bare crash).

    ``on_2xx`` fires the moment upstream answers ANY 2xx — BEFORE the
    body is parsed. It is the billing-accounting seam (M6): a 2xx means
    Krea ACCEPTED the submit, so the caller's budget unit must be
    recorded even when the body then turns out to be unparseable."""
    http, owns = _ensure_client(client)
    url = f"{_base_url()}/generate/image/{_model_path()}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    # Body per the flux-1-dev schema (docs.krea.ai, 2026-06-12): exactly
    # prompt/width/height. There is NO model key in the body — the model
    # is the URL path segment above.
    body = {
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
        # 402 = the prepaid API balance is empty (docs.krea.ai, 2026-06-12:
        # the API draws a separate prepaid USD balance, $5 minimum top-up;
        # empty → HTTP 402 {"message": ...}). Its own reason so the
        # operator reads "top up" rather than a generic upstream error. A
        # refused submit is NOT billable — no unit is recorded.
        if resp.status_code == 402:
            raise _UpstreamError(
                _REASON_NO_API_BALANCE,
                f"HTTP 402 — {(resp.text or '')[:300]}",
                upstream_status=resp.status_code,
            )
        # 401 (invalid key), 429 (rate-limited upstream / queue), 5xx —
        # ALL collapse to the fallback signal. We do not retry here; the
        # frontend simply shows the placeholder and a later refresh may
        # succeed (and hit the warm cache).
        if not (200 <= resp.status_code < 300):
            preview = (resp.text or "")[:300]
            raise _UpstreamError(
                _REASON_UPSTREAM_ERROR,
                f"HTTP {resp.status_code} — {preview}",
                upstream_status=resp.status_code,
            )
        # ANY 2xx: Krea accepted the submit. Record the budget unit NOW,
        # before parsing (M6) — see the divergence comment at the
        # recording site in krea_generate.
        if on_2xx is not None:
            on_2xx()
        try:
            data: Any = resp.json()
        except ValueError as e:  # partial / garbage JSON failure mode
            raise _UpstreamError(
                _REASON_UPSTREAM_BAD_RESPONSE,
                str(e),
                upstream_status=resp.status_code,
            ) from e
        if not isinstance(data, dict):
            raise _UpstreamError(
                _REASON_UPSTREAM_BAD_RESPONSE,
                f"non-object body: {type(data)}",
                upstream_status=resp.status_code,
            )
        job_id = data.get("job_id")
        status = data.get("status") or "queued"
        if not isinstance(job_id, str) or not job_id:
            raise _UpstreamError(
                _REASON_UPSTREAM_BAD_RESPONSE,
                f"missing job_id: {str(data)[:200]}",
                upstream_status=resp.status_code,
            )
        return job_id, str(status)
    finally:
        if owns:
            http.close()


def _poll_job(
    token: str,
    job_id: str,
    *,
    client: httpx.Client | None = None,
) -> JobResponse:
    """GET {BASE}/jobs/{id} → JobResponse. Shape transcribed from the
    docs.krea.ai jobs reference (2026-06-12; live verification pending
    SPR-09). One poll (not the loop) — the loop lives in the /krea/scene
    handler so a single poll is independently testable. Raises
    _UpstreamError on any problem, including a completed job that is
    missing its result URLs (a half-shape must surface as
    upstream_bad_response, never a None-URL success)."""
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
        # 402 mid-poll: same prepaid-balance signal as on submit
        # (docs.krea.ai, 2026-06-12) — mapped to the same reason so the
        # operator's "top up" signal is consistent wherever it lands.
        if resp.status_code == 402:
            raise _UpstreamError(
                _REASON_NO_API_BALANCE,
                f"HTTP 402 — {(resp.text or '')[:300]}",
                upstream_status=resp.status_code,
            )
        if not (200 <= resp.status_code < 300):
            preview = (resp.text or "")[:300]
            raise _UpstreamError(
                _REASON_UPSTREAM_ERROR,
                f"HTTP {resp.status_code} — {preview}",
                upstream_status=resp.status_code,
            )
        try:
            data: Any = resp.json()
        except ValueError as e:
            raise _UpstreamError(
                _REASON_UPSTREAM_BAD_RESPONSE,
                str(e),
                upstream_status=resp.status_code,
            ) from e
        if not isinstance(data, dict):
            raise _UpstreamError(
                _REASON_UPSTREAM_BAD_RESPONSE,
                f"non-object body: {type(data)}",
                upstream_status=resp.status_code,
            )
        status = str(data.get("status") or "")
        # Failure detail (docs.krea.ai jobs reference, 2026-06-12): failed
        # jobs carry error: {code, message}. The CODE is a stable machine
        # string surfaced additively on JobResponse; the MESSAGE is
        # upstream prose and is deliberately dropped here (sanitized-
        # preview discipline — no upstream text reaches a response body).
        error_code: str | None = None
        err = data.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            if isinstance(code, str) and code:
                error_code = code
        # Completed jobs carry result.urls — an ARRAY OF URI STRINGS; take
        # [0] (docs.krea.ai jobs reference, 2026-06-12). result may also
        # carry style_id (ignored). The legacy doc-derived parse paths (a
        # nested image-url object and a top-level image-url) were REMOVED
        # 2026-06-12: the live API never serves them, and a parser that
        # accepts shapes the API never sends masks the next schema drift.
        image_url: str | None = None
        result = data.get("result")
        if isinstance(result, dict):
            urls = result.get("urls")
            if (isinstance(urls, list) and urls
                    and isinstance(urls[0], str) and urls[0]):
                image_url = urls[0]
        if status == "completed" and image_url is None:
            # A completed job MUST carry result.urls per the docs. Missing
            # → bad-response fallback, never a None-URL 200 (and never an
            # endless re-poll of a job that will not change).
            raise _UpstreamError(
                _REASON_UPSTREAM_BAD_RESPONSE,
                f"completed job missing result.urls: {str(data)[:200]}",
                upstream_status=resp.status_code,
            )
        return JobResponse(
            job_id=job_id, status=status or "unknown", image_url=image_url,
            error_code=error_code,
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
    failures = _FailureRing()
    app.state.krea_budget = budget
    app.state.krea_cache = cache
    app.state.krea_failures = failures
    # Optional injected httpx client for tests (MockTransport). Production
    # leaves this None → each call builds + closes its own short-timeout
    # client. Set via app.state.krea_http_client in a test.
    app.state.krea_http_client = None

    def _http() -> httpx.Client | None:
        return getattr(app.state, "krea_http_client", None)

    state_lock = threading.Lock()
    last_enabled = True

    def _observe_enabled(enabled: bool, reason: str | None = None) -> None:
        """Log once for each enabled->disabled transition, never per request."""
        nonlocal last_enabled
        should_log = False
        with state_lock:
            if enabled:
                last_enabled = True
                return
            if last_enabled:
                should_log = True
            last_enabled = False
        if should_log:
            logger.warning("krea disabled: reason=%s", reason)

    def _disabled(
        reason: str,
        scene: str | None = None,
        upstream_status: int | None = None,
    ) -> JSONResponse:
        """Build the typed 503 fallback body. ALWAYS 503, NEVER 500."""
        failures.record(reason, scene_key=scene, upstream_status=upstream_status)
        _observe_enabled(False, reason)
        payload = DisabledResponse(reason=reason, scene_key=scene)
        return JSONResponse(status_code=503, content=payload.model_dump())

    def _status_payload() -> dict[str, Any]:
        budget_snap = budget.status_snapshot()
        key_present = _api_token() is not None
        kill_switch = _kill_switch_on()
        spent = budget_snap["budget"]["spent_today"]
        cap = budget_snap["budget"]["cap"]
        occupancy = budget_snap["rate_window"]["occupancy"]
        rate_max = budget_snap["rate_window"]["max"]
        if kill_switch:
            verdict = _REASON_KILL_SWITCH
        elif not key_present:
            verdict = _REASON_NO_KEY
        elif spent >= cap:
            verdict = _REASON_OVER_BUDGET
        elif occupancy >= rate_max:
            verdict = _REASON_RATE_LIMITED
        else:
            verdict = None
        enabled = verdict is None
        failure_snap = failures.snapshot()
        return {
            "enabled": enabled,
            "key_present": key_present,
            "kill_switch": kill_switch,
            "gate_verdict": verdict,
            "reasons": list(_ALL_DISABLED_REASONS),
            "budget": budget_snap["budget"],
            "rate_window": budget_snap["rate_window"],
            "cache": cache.stats(),
            "last_success_at": failure_snap["last_success_at"],
            "failure_counts": failure_snap["failure_counts"],
            "failures": failure_snap["entries"],
        }

    def _gate() -> str | None:
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
    def krea_generate(req: GenerateRequest) -> JSONResponse:
        """Submit a generation. Returns 200 {job_id,status} when enabled +
        under budget; otherwise the typed 503 fallback. Charges the budget
        on ANY 2xx submit answer (a gated request never bills; a non-2xx
        refusal never bills; a 2xx with an unparseable body DOES bill —
        see the divergence comment below).

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
            # BILLING-ACCOUNTING (M6, 2026-06-12): the budget unit is
            # recorded by on_2xx the moment Krea answers ANY 2xx — BEFORE
            # the body is parsed — so a 200 with a surprising shape still
            # counts against the daily cap (the shipped code recorded only
            # after a parseable submit, leaving a hole where upstream
            # could bill while the local cap never moved).
            #
            # DELIBERATE DIVERGENCE from Krea's semantics: Krea bills on
            # job COMPLETION and does NOT bill failed/cancelled jobs
            # (docs.krea.ai, 2026-06-12). We count on submit-accept, so
            # this counter OVERCOUNTS on jobs that later fail — the safe
            # direction for a runaway guard (we throttle ourselves before
            # the prepaid balance drains, never the reverse). REVISIT IF
            # the cap starts starving legitimate use under a high upstream
            # failure rate: reconcile against Krea's billing then — do not
            # loosen the record-before-parse ordering.
            job_id, status = _submit_generation(
                token, req, client=_http(),
                on_2xx=lambda: budget.record_submit(units=1),
            )
        except _UpstreamError as e:
            # Every upstream failure mode (timeout / network / 401 / 402 /
            # 429 / 5xx / bad-json) ends here → typed fallback, never a
            # 500. (A 2xx-then-bad-body path has ALREADY recorded its unit
            # via on_2xx by the time the parse error lands here.)
            return _disabled(e.reason, upstream_status=e.upstream_status)
        _observe_enabled(True)
        return JSONResponse(
            status_code=200,
            content=GenerateResponse(job_id=job_id, status=status).model_dump(),
        )

    @app.get("/krea/jobs/{job_id}", tags=["krea"])
    def krea_job(job_id: str) -> JSONResponse:
        """Poll a submitted job. 200 {job_id,status,image_url?,error_code?}
        when enabled; typed 503 fallback when disabled / on any upstream
        failure (incl. 402 → no_api_balance and a completed job missing
        its result URLs → upstream_bad_response). Polling does NOT bill
        (only the submit does).

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
            return _disabled(e.reason, upstream_status=e.upstream_status)
        _observe_enabled(True)
        return JSONResponse(status_code=200, content=job.model_dump())

    @app.get("/krea/scene", tags=["krea"])
    def krea_scene(
        mood: str = Query(default="calm", max_length=64),
        day_night: str = Query(default="day", max_length=64),
        season: str = Query(default="summer", max_length=64),
    ) -> JSONResponse:
        """The higher-level endpoint SPR-04 consumes. Encapsulates
        prompt-building + cache + budget + submit + poll-to-completion
        behind a single GET keyed by scene-state.

        SYNC handler — CRITICAL. This endpoint runs a blocking poll loop
        (sleeps up to the poll budget — KREA_POLL_BUDGET_S, default
        ``_POLL_BUDGET_S`` = 30s). Declared ``def``
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
            _observe_enabled(True)
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
            # Budget unit recorded on ANY 2xx submit, BEFORE parsing —
            # cache miss only (a cache hit returned above, unbilled). Same
            # bill-on-submit-accept divergence as krea_generate: Krea
            # bills on completion (failed/cancelled unbilled); we count
            # the accepted submit — overcounting is the safe direction
            # for a runaway guard. Full rationale + revisit condition at
            # the krea_generate recording site.
            job_id, _status = _submit_generation(
                token, gen, client=_http(),
                on_2xx=lambda: budget.record_submit(units=1),
            )
        except _UpstreamError as e:
            return _disabled(e.reason, scene=key, upstream_status=e.upstream_status)

        # 4. Poll to completion within the poll budget (KREA_POLL_BUDGET_S,
        #    default 30s — derivation at _POLL_BUDGET_S) at the documented
        #    2–5s cadence (_POLL_INTERVAL_S = 2.5). _monotonic/_sleep are
        #    the module clock seam so tests prove this loop with a mock
        #    clock, no real sleeps.
        deadline = _monotonic() + _poll_budget_s()
        while True:
            try:
                job = _poll_job(token, job_id, client=_http())
            except _UpstreamError as e:
                return _disabled(e.reason, scene=key, upstream_status=e.upstream_status)
            # Terminal states per the docs.krea.ai 9-state job lifecycle
            # (2026-06-12): completed / failed / cancelled. Every other
            # state (backlogged / queued / scheduled / processing /
            # sampling / intermediate-complete — and any state a future
            # docs revision adds) keeps polling until the budget expires.
            if job.status == "completed" and job.image_url:
                cache.put(key, job.image_url)
                failures.mark_success()
                _observe_enabled(True)
                return JSONResponse(
                    status_code=200,
                    content=SceneArt(
                        image_url=job.image_url, scene_key=key, cached=False,
                    ).model_dump(),
                )
            if job.status == "failed":
                return _disabled(_REASON_JOB_FAILED, scene=key)
            if job.status == "cancelled":
                # Terminal — short-circuit NOW (M3): burning the remaining
                # poll budget on a job that can never complete would only
                # delay the frontend's placeholder.
                return _disabled(_REASON_JOB_CANCELLED, scene=key)
            if _monotonic() >= deadline:
                # Took too long — fall back now; a later refresh may find
                # the job done and (if the surface re-requests) it can warm
                # the cache. We do NOT hang the request.
                return _disabled(_REASON_JOB_TIMEOUT, scene=key)
            _sleep(_POLL_INTERVAL_S)

    @app.get("/krea/status", tags=["krea"])
    def krea_status() -> JSONResponse:
        """Return the Krea fallback-observability contract, always HTTP 200.

        Stable fields: enabled (bool), key_present (bool only, never token
        bytes), kill_switch (bool), gate_verdict (first active local gate or
        null), reasons (additive reason vocabulary), budget {spent_today, cap,
        remaining}, rate_window {occupancy, max, window_s}, cache {entries,
        max_entries}, last_success_at (ISO timestamp or null), failure_counts
        (reason -> count), failures (bounded newest ring of timestamp, reason,
        scene_key, upstream_status). The route never returns raw upstream
        response bodies and responds 200 in disabled/no-key states.
        """
        payload = _status_payload()
        _observe_enabled(bool(payload["enabled"]), payload["gate_verdict"])
        return JSONResponse(status_code=200, content=payload)
