#!/usr/bin/env python3
"""Capped, secret-safe Krea first-contact smoke (ALC SPR-02).

Runs the entire first-contact procedure from infrastructure/runbooks/krea.md
against a chosen base URL (local dev 8000 / prod via the on-box operator
bearer):

  0. ``GET /health``        — transport baseline (auth-open path).
  1. ``GET /krea/scene``    — pretty-prints the 200 (SceneArt) or 503
                              (DisabledResponse) shape, with the matching
                              row of the reason-string decision table.
  2. The IDENTICAL call again — asserts ``cached: true`` on a second 200,
                              the de-bill proof (an identical scene-state
                              must never be re-billed).
  3. A reminder to close the loop at the Krea dashboard (the API-balance
     decrement is the ground truth this script cannot see).

SECRET-SAFE BY CONSTRUCTION (proven by tests/test_krea_smoke.py, not by
inspection):

  - It NEVER reads ``KREA_API_TOKEN``. The server holds the Krea secret;
    this script only talks to the proxy (``/krea/scene``). There is no
    code path that could print the token because no code path holds it.
  - The only secret it handles is ``ANTIEK_OPERATOR_TOKEN`` (the prod
    operator bearer, auth path 4 in interfaces/research/api/app.py). It
    is attached to the Authorization header and registered with the
    output scrubber — every printed line is scrubbed of its value, and
    the script never prints the value of ANY environment variable.
  - ``image_url`` is printed with its query string STRIPPED (a signed
    CDN URL can carry token-like query params; they never reach stdout).

CAPPED BY CONSTRUCTION: in ``--serve`` mode (spawn a local API server
first), ``KREA_DAILY_UNIT_CAP=3`` is forced into the server subprocess's
environment unless the operator explicitly set the cap already (or passed
``--cap``). Against an already-running server the cap is server-side; the
runbook's invocations start that server with the same cap.

STDLIB-ONLY on purpose: runs on the prod box (and anywhere) with no venv
beyond the interpreter. Mirrors tools/auth_probe.py's staged-probe shape.

Exit codes:
    0 — live art verified: fresh 200 + identical repeat answered
        ``cached: true`` (or both calls were warm-cache hits).
    3 — typed fallback (503) reached: the proxy is healthy but generation
        is disabled — read the decision-table row printed above.
    1 — assertion failure: the repeat was NOT cached (re-bill bug), or a
        response shape was malformed.
    2 — transport / usage error: base unreachable, 401 (operator auth),
        bad flags.

Usage::

    python tools/krea_smoke.py                       # local, 127.0.0.1:8000
    python tools/krea_smoke.py --serve               # spawn a capped local server first
    python tools/krea_smoke.py --base-url https://api.antiek.ai   # on-box prod (export ANTIEK_OPERATOR_TOKEN first)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_USER_AGENT = "antiek-krea-smoke/1.0 (+https://antiek.ai)"
_DEFAULT_BASE = "http://127.0.0.1:8000"
_SMOKE_CAP = "3"  # forced into --serve subprocess env unless overridden

# ── Reason-string decision table ─────────────────────────────────────────
# MUST match the post-SPR-01 vocabulary in
# interfaces/research/api/krea_routes.py (_REASON_* constants) exactly.
# The vocabulary is additive-only; if a reason arrives that is not here,
# the script says so honestly instead of guessing.
DECISION_TABLE: dict[str, tuple[str, str]] = {
    "no_key": (
        "KREA_API_TOKEN is not set (or blank) in the server's environment.",
        "Wire the token (runbook section 3) and restart the server; for a"
        " fresh account, mint one first (section 1).",
    ),
    "kill_switch": (
        "KREA_KILL_SWITCH is on — the operator panic lever forces fallback"
        " for every generation, key-independent.",
        "If this is intentional, nothing to do. To resume: remove (or"
        " comment out) the appended KREA_KILL_SWITCH line from the"
        " secrets file (/etc/antiek/secrets.env on prod) and restart"
        " (runbook section 6).",
    ),
    "over_daily_budget": (
        "The server-side daily unit cap (KREA_DAILY_UNIT_CAP) is spent for"
        " today. No upstream call was made.",
        "Expected during a capped smoke after 3 fresh generations. Wait for"
        " the date rollover, or raise the cap deliberately (runbook"
        " section 7 prices the consequence).",
    ),
    "rate_limited": (
        "Too many submits in the per-process 60s window"
        " (KREA_RATE_LIMIT_MAX). No upstream call was made.",
        "Wait a minute and retry. If a UI loop caused this, that loop is"
        " the bug — the limiter just contained it.",
    ),
    "upstream_error": (
        "Krea answered a non-2xx (401 invalid key / 429 / 5xx) or the"
        " network failed (DNS, refused, offline).",
        "Check the server logs (journalctl -u antiek) for the status code."
        " 401 → the token is wrong or revoked: rotate (runbook section 5).",
    ),
    "upstream_timeout": (
        "One HTTP round-trip to Krea exceeded the 15s client timeout.",
        "Usually transient — retry. Persistent timeouts: check Krea status"
        " / your egress before touching config.",
    ),
    "upstream_bad_response": (
        "Krea answered, but the body did not match the documented schema"
        " (garbage JSON, missing job_id, completed job without URLs).",
        "Schema drift candidate — re-check docs.krea.ai against the"
        " adapter seam in krea_routes.py before retrying hard.",
    ),
    "job_failed": (
        "The generation job reached the terminal 'failed' state upstream."
        " Krea does not bill failed jobs.",
        "Retry once; persistent failures with a stable error_code →"
        " check the model path (ANTIEK_KREA_MODEL_PATH) and prompt bounds.",
    ),
    "job_timeout": (
        "The job did not reach a terminal state within the poll budget"
        " (KREA_POLL_BUDGET_S, default 30s). The submit WAS billed"
        " locally (bill-on-submit-accept).",
        "A later refresh may find it done. If it recurs, raise"
        " KREA_POLL_BUDGET_S or expect queue latency at busy hours.",
    ),
    "job_cancelled": (
        "The job reached the terminal 'cancelled' state upstream."
        " Krea does not bill cancelled jobs.",
        "Unusual from this path (nothing here cancels jobs) — check the"
        " Krea dashboard for who/what cancelled it.",
    ),
    "no_api_balance": (
        "Krea answered HTTP 402: the PREPAID API balance is empty. This"
        " balance is SEPARATE from any web subscription's compute units.",
        "Top up at https://www.krea.ai/app/api ($5 minimum) — runbook"
        " section 2. A plan/subscription does NOT fix a 402.",
    ),
}


# ── Output scrubbing (defense-in-depth; the tests prove the outcome) ────


class _Scrubber:
    """Every printed line passes through here. Any registered secret value
    is replaced before it can reach stdout. The primary defense is that
    secrets are never formatted into messages at all; this is the belt to
    that suspender."""

    def __init__(self) -> None:
        self._secrets: list[str] = []

    def register(self, value: str) -> None:
        v = value.strip()
        if v:
            self._secrets.append(v)

    def clean(self, text: str) -> str:
        for s in self._secrets:
            if s in text:
                text = text.replace(s, "[scrubbed]")
        return text


_SCRUBBER = _Scrubber()


def say(text: str = "") -> None:
    print(_SCRUBBER.clean(text))


def strip_query(url: str) -> str:
    """Drop the query string + fragment before printing an image URL —
    signed CDN URLs carry token-like params that must not hit stdout."""
    parts = urllib.parse.urlsplit(url)
    bare = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    if parts.query or parts.fragment:
        return bare + " [query string stripped — may carry signed params]"
    return bare


# ── Capped subprocess env (--serve) ─────────────────────────────────────


def build_server_env(parent: dict[str, str]) -> dict[str, str]:
    """Environment for the --serve server subprocess: the parent env
    passed through untouched (the server needs its own secrets, which this
    script never reads), with KREA_DAILY_UNIT_CAP forced to 3 UNLESS the
    operator explicitly set it already (an explicit cap is an explicit
    decision — respect it)."""
    env = dict(parent)
    if not env.get("KREA_DAILY_UNIT_CAP", "").strip():
        env["KREA_DAILY_UNIT_CAP"] = _SMOKE_CAP
    return env


# ── HTTP (stdlib only) ──────────────────────────────────────────────────


def _get(
    url: str, *, bearer: str | None, timeout: float
) -> tuple[int, dict[str, Any] | None]:
    """GET ``url`` → (status, parsed-json-or-None). 4xx/5xx are returned,
    not raised — the 503 fallback body is a first-class result here."""
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read()
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read()
    try:
        data = json.loads(body.decode("utf-8", "replace")) if body else None
        if not isinstance(data, dict):
            data = None
    except ValueError:
        data = None
    return status, data


# ── Pretty-printers ─────────────────────────────────────────────────────


def _print_decision_row(reason: str) -> None:
    row = DECISION_TABLE.get(reason)
    if row is None:
        say(f"  → UNKNOWN reason {reason!r} — not in the post-SPR-01")
        say("    vocabulary this script knows. The server may be newer than")
        say("    this script: re-read krea_routes.py's _REASON_* constants.")
        return
    meaning, next_step = row
    say(f"  → meaning: {meaning}")
    say(f"  → next:    {next_step}")


def _print_scene_200(data: dict[str, Any], call_no: int) -> None:
    cached = bool(data.get("cached"))
    billing = (
        "warm cache — NOT billed"
        if cached
        else "fresh generation — billed 1 unit at submit"
    )
    say(f"HTTP 200 — SceneArt (call {call_no})")
    say(f"  enabled:    {data.get('enabled')}")
    say(f"  cached:     {str(cached).lower()}   ({billing})")
    say(f"  scene_key:  {data.get('scene_key')}")
    url = data.get("image_url")
    if isinstance(url, str):
        say(f"  image_url:  {strip_query(url)}")
    else:
        # Never print a non-str value: a dict/list could embed a signed
        # URL string and bypass strip_query. Type name only.
        say(f"  image_url:  <unexpected type: {type(url).__name__} — not printed>")


def _print_scene_503(data: dict[str, Any], call_no: int) -> str:
    reason = str(data.get("reason", ""))
    say(f"HTTP 503 — DisabledResponse (call {call_no}; typed fallback —")
    say("           the proxy is healthy, generation is disabled)")
    say(f"  enabled:    {data.get('enabled')}")
    say(f"  isFallback: {data.get('isFallback')}")
    say(f"  reason:     {reason}")
    say(f"  scene_key:  {data.get('scene_key')}")
    _print_decision_row(reason)
    return reason


def _format_table() -> str:
    lines = ["reason-string decision table (post-SPR-01 vocabulary):", ""]
    for reason, (meaning, next_step) in DECISION_TABLE.items():
        lines.append(f"  {reason}")
        lines.append(f"      meaning: {meaning}")
        lines.append(f"      next:    {next_step}")
    return "\n".join(lines)


# ── The smoke proper ────────────────────────────────────────────────────


def run_smoke(
    base: str,
    *,
    mood: str,
    day_night: str,
    season: str,
    timeout: float,
) -> int:
    bearer = os.environ.get("ANTIEK_OPERATOR_TOKEN", "").strip() or None
    if bearer:
        _SCRUBBER.register(bearer)
        say("operator bearer: attached from ANTIEK_OPERATOR_TOKEN (value not printed)")
    else:
        say("operator bearer: not set — anonymous (fine for local dev; prod will 401)")

    # Stage 0 — transport baseline (auth-open path).
    health_url = f"{base}/health"
    try:
        status, _ = _get(health_url, bearer=None, timeout=timeout)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        say(f"stage 0  GET /health → UNREACHABLE ({e.__class__.__name__})")
        say("  → the API server is not reachable at this base URL. Start it")
        say("    (or fix --base-url) before reading anything Krea-specific.")
        return 2
    say(f"stage 0  GET /health → HTTP {status}")
    if status != 200:
        say("  → /health is auth-open by design; a non-200 here is a server")
        say("    problem, not a Krea problem. Fix that first.")
        return 2

    # Stage 1 + 2 — the identical scene call, twice.
    qs = urllib.parse.urlencode(
        {"mood": mood, "day_night": day_night, "season": season}
    )
    scene_url = f"{base}/krea/scene?{qs}"
    say(f"stage 1  GET /krea/scene?{qs}")
    results: list[tuple[int, dict[str, Any] | None]] = []
    for call_no in (1, 2):
        try:
            status, data = _get(scene_url, bearer=bearer, timeout=timeout)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            say(f"  call {call_no} → UNREACHABLE ({e.__class__.__name__})")
            return 2
        results.append((status, data))
        if status == 401:
            say(f"  call {call_no} → HTTP 401 — operator auth required.")
            say("  → export ANTIEK_OPERATOR_TOKEN from the secrets file first")
            say("    (runbook section 4 has the no-echo one-liner).")
            return 2
        if data is None:
            say(f"  call {call_no} → HTTP {status} with a non-JSON body —")
            say("    malformed for this endpoint; check the server logs.")
            return 1
        if status == 200:
            _print_scene_200(data, call_no)
        elif status == 503:
            _print_scene_503(data, call_no)
        else:
            say(f"  call {call_no} → unexpected HTTP {status}; /krea/scene")
            say("    answers only 200 or 503 by contract (krea_routes.py).")
            return 1
        if call_no == 1:
            say("stage 2  repeating the IDENTICAL call (de-bill proof:")
            say("         an identical scene-state must come from cache)")

    rc = _verdict(results)
    _dashboard_reminder(results)
    return rc


def _verdict(results: list[tuple[int, dict[str, Any] | None]]) -> int:
    (s1, d1), (s2, d2) = results
    if s1 == 200 and s2 == 200:
        c1 = bool((d1 or {}).get("cached"))
        c2 = bool((d2 or {}).get("cached"))
        if not c2:
            say("VERDICT: FAIL — the identical repeat was NOT served from")
            say("  cache (cached: false twice). That is a re-bill bug; do not")
            say("  proceed to higher volume. (KREA_CACHE_TTL_S misconfigured?)")
            return 1
        if c1:
            say("VERDICT: PASS — both calls were warm-cache hits (an earlier")
            say("  run generated this scene-state). Nothing was billed.")
        else:
            say("VERDICT: PASS — live art verified: one fresh generation,")
            say("  identical repeat answered cached: true (de-bill proven).")
        return 0
    if s1 == 503 and s2 == 503:
        say("VERDICT: FALLBACK — the proxy is healthy and answered the typed")
        say("  503 twice; generation is disabled for the reason above. This")
        say("  is the EXPECTED state before a token/balance is wired.")
        return 3
    say("VERDICT: FAIL — the two identical calls answered different shapes")
    say(f"  (HTTP {s1} then HTTP {s2}). Transient flip mid-smoke; rerun. If")
    say("  it persists, read the server logs.")
    return 1


def _dashboard_reminder(results: list[tuple[int, dict[str, Any] | None]]) -> None:
    fresh = sum(
        1
        for s, d in results
        if s == 200 and d is not None and not d.get("cached")
    )
    say()
    say("REMINDER — close the loop at the Krea dashboard:")
    say("  open https://www.krea.ai/app/api and confirm the prepaid API")
    say(f"  balance moved by exactly {fresh} unit(s) — at the default model")
    say("  (bfl/flux-1-dev) that is $0.007 per fresh generation. The")
    say("  dashboard decrement is the ground truth this script cannot see;")
    say("  a mismatch means the billing model drifted — stop and record it.")


# ── --serve: spawn a capped local server, then smoke it ─────────────────


def _serve_and_smoke(args: argparse.Namespace) -> int:
    env = build_server_env(dict(os.environ))
    if args.cap is not None:
        env["KREA_DAILY_UNIT_CAP"] = str(args.cap)
        say(f"forcing KREA_DAILY_UNIT_CAP={args.cap} into the server"
            " subprocess env (--cap).")
    elif os.environ.get("KREA_DAILY_UNIT_CAP", "").strip():
        say("KREA_DAILY_UNIT_CAP already set in the environment — respecting")
        say("  the operator's override (value not printed).")
    else:
        say(f"forcing KREA_DAILY_UNIT_CAP={_SMOKE_CAP} into the server"
            " subprocess env (capped smoke).")
    port = args.serve_port
    base = f"http://127.0.0.1:{port}"
    cmd = [
        sys.executable, "-m", "uvicorn",
        "interfaces.research.api.app:app",
        "--host", "127.0.0.1", "--port", str(port), "--workers", "1",
    ]
    say(f"spawning local server on {base} (logs suppressed to keep this")
    say("  transcript token-free; run uvicorn yourself if you need them)")
    proc = subprocess.Popen(
        cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        deadline = time.monotonic() + args.serve_wait_s
        ready = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                say("server subprocess exited before becoming healthy —")
                say("  is another writer holding the DuckDB lock (a running")
                say("  `antiek` service)? --serve is for a dev box.")
                return 2
            try:
                status, _ = _get(f"{base}/health", bearer=None, timeout=2.0)
                if status == 200:
                    ready = True
                    break
            except (urllib.error.URLError, OSError, TimeoutError):
                pass
            time.sleep(0.5)
        if not ready:
            say(f"server did not answer /health within {args.serve_wait_s:.0f}s")
            return 2
        return run_smoke(
            base,
            mood=args.mood,
            day_night=args.day_night,
            season=args.season,
            timeout=args.timeout,
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


# ── CLI ─────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="krea_smoke",
        description=(
            "Capped, secret-safe Krea first-contact smoke. Talks ONLY to the"
            " Antiek proxy (/krea/scene) — it never reads the Krea token and"
            " never prints any environment value. See"
            " infrastructure/runbooks/krea.md."
        ),
        epilog=_format_table(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--base-url", default=_DEFAULT_BASE,
        help=f"API base (default {_DEFAULT_BASE}; prod: https://api.antiek.ai)",
    )
    p.add_argument("--mood", default="calm", help="scene mood axis (default calm)")
    p.add_argument(
        "--day-night", default="day", help="scene day/night axis (default day)"
    )
    p.add_argument(
        "--season", default="summer", help="scene season axis (default summer)"
    )
    p.add_argument(
        "--timeout", type=float, default=60.0,
        help="per-request timeout seconds (default 60 — /krea/scene blocks"
        " through the server's poll budget, default 30s, before answering)",
    )
    p.add_argument(
        "--serve", action="store_true",
        help="spawn a local API server first, with KREA_DAILY_UNIT_CAP=3"
        " forced into its environment unless already set (or --cap given)",
    )
    p.add_argument(
        "--serve-port", type=int, default=8000,
        help="port for the --serve server (default 8000)",
    )
    p.add_argument(
        "--serve-wait-s", type=float, default=180.0,
        help="seconds to wait for the --serve server's /health (default 180)",
    )
    p.add_argument(
        "--cap", type=int, default=None,
        help="explicit KREA_DAILY_UNIT_CAP for the --serve subprocess"
        " (overrides the forced 3)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    base = args.base_url.rstrip("/")
    parts = urllib.parse.urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        say(f"invalid --base-url {base!r}: need http(s)://host[:port]")
        return 2
    if args.serve:
        return _serve_and_smoke(args)
    return run_smoke(
        base,
        mood=args.mood,
        day_night=args.day_night,
        season=args.season,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
