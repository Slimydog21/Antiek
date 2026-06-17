#!/usr/bin/env python3
"""Bot-aware PostHog capture verifier (Antiek — APH SPR-02).

WHY THIS EXISTS — read before "diagnosing" PostHog:
  posthog-js bot-filters automated browsers. Playwright (headless AND headed)
  sets navigator.webdriver / headless fingerprints, so posthog classifies the
  session "likely bot" and SUPPRESSES ALL capture: zero POSTs to /i/v0/e/. At
  the network layer this is indistinguishable from "analytics is broken" — and
  during this integration it caused a multi-turn misdiagnosis (a fix, PR #74,
  was shipped chasing a phantom). Real human visitors are NOT filtered.
  THEREFORE: this verifier NEVER concludes "broken" from whether a browser
  emitted /i/v0/e/. Its authority is the PostHog events API (server-side ground
  truth): it EMITS a uniquely-tagged sentinel event, then POLLS the API until
  that exact event appears. See docs/decisions/posthog-bot-filter.md.

Modes:
  --emit     POST a sentinel capture to the ingest endpoint (uses the phc_
             project token). Prints the generated verify_run_id.
  --assert   Poll the events API (uses the phx_ personal key) for a sentinel
             with a given --run-id, until found or --timeout seconds elapse.
  (default: --emit then --assert on the just-emitted run-id = a full check.)

Credentials (env; never hardcode, never print):
  POSTHOG_PROJECT_TOKEN      phc_… (client/ingest token; for --emit)
  POSTHOG_PERSONAL_API_KEY   phx_… (personal API key; for --assert)
  POSTHOG_PROJECT_ID         default 193061
  POSTHOG_HOST               default https://eu.posthog.com      (API)
  POSTHOG_INGEST_HOST        default https://eu.i.posthog.com     (capture)

Exit: 0 = capture CONFIRMED server-side; non-zero = could-not-confirm/error.
A non-zero from --assert means "not seen within the timeout" (check token /
quota / ingest) — it does NOT mean a browser bot-filter problem.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

SENTINEL_EVENT = "aph_verify_capture"
BANNER = (
    "[verify_capture] NOTE: automated browsers are bot-filtered by posthog "
    "(opt_out_useragent_filter); zero /i/v0/e/ from a headless/headed probe is "
    "EXPECTED, not a defect. The server-side events-API assertion below is the "
    "source of truth. See docs/decisions/posthog-bot-filter.md."
)


def _env(name: str, default: str | None = None, *, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        sys.exit(f"[verify_capture] missing required env var {name}")
    return val or ""


def emit(run_id: str) -> None:
    """Emit one sentinel capture via the ingest endpoint (phc_ token)."""
    token = _env("POSTHOG_PROJECT_TOKEN", required=True)
    ingest = _env("POSTHOG_INGEST_HOST", "https://eu.i.posthog.com").rstrip("/")
    payload = {
        "api_key": token,
        "event": SENTINEL_EVENT,
        "distinct_id": f"aph-verify-{run_id}",
        "properties": {
            "verify_run_id": run_id,
            "$lib": "aph-verify-capture",
            # No substrate content — this is a synthetic verification event.
            "note": "APH SPR-02 server-side capture verifier sentinel",
        },
    }
    req = urllib.request.Request(
        f"{ingest}/i/v0/e/",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode()
        status = resp.status
    # Fail loud if the ingest did not accept the event — otherwise a rejected
    # emit would surface only later as a misattributed assert timeout.
    if status not in (200, 202):
        sys.exit(f"[verify_capture] ingest REJECTED the sentinel (HTTP {status}: {body[:120]}) — "
                 f"capture cannot be verified; check the phc_ project token / host.")
    print(f"[verify_capture] emitted sentinel run_id={run_id} (ingest status {status}: {body[:80]})")


def assert_seen(run_id: str, timeout: int) -> bool:
    """Poll the events API for the sentinel; True iff the EXACT run_id is found.

    Endpoint choice (evidence-based, 2026-06-04): the events list endpoint is on
    PostHog's deprecation track, and the HogQL `/query/` endpoint is the
    nominally-preferred successor. BUT HogQL reads ClickHouse, which has materially
    higher ingest lag — a freshly-emitted sentinel was NOT visible via HogQL within
    90s, while the events list surfaces it in ~seconds. For REAL-TIME sentinel
    verification, propagation latency dominates: the events list is the fitter tool.
    We match on the exact `verify_run_id` property (not event name), so volume /
    ordering within the filtered, last-emitted-first set is not a correctness risk
    for a sentinel emitted seconds earlier. Reconsider if PostHog removes the events
    list or gives HogQL a low-lag/real-time mode. (See SPR-02 handoff.)
    """
    key = _env("POSTHOG_PERSONAL_API_KEY", required=True)
    host = _env("POSTHOG_HOST", "https://eu.posthog.com").rstrip("/")
    pid = _env("POSTHOG_PROJECT_ID", "193061")
    url = f"{host}/api/projects/{pid}/events/?event={SENTINEL_EVENT}&limit=20"
    deadline = time.time() + timeout
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            sys.exit(f"[verify_capture] events API error {e.code}: {e.read().decode()[:120]}")
        for ev in data.get("results", []):
            if (ev.get("properties") or {}).get("verify_run_id") == run_id:
                print(f"[verify_capture] PASS — sentinel run_id={run_id} confirmed "
                      f"server-side (event at {ev.get('timestamp')}, attempt {attempt}).")
                return True
        time.sleep(min(5, max(1, timeout // 12)))
    print(f"[verify_capture] FAIL — sentinel run_id={run_id} not seen within {timeout}s. "
          f"Check the phc_ token / event quota / ingest reachability. This is NOT a "
          f"browser bot-filter issue (that only suppresses client-side capture).")
    return False


def main() -> int:
    print(BANNER, file=sys.stderr)
    ap = argparse.ArgumentParser(description="Bot-aware PostHog capture verifier (APH SPR-02).")
    ap.add_argument("--emit", action="store_true", help="emit a sentinel capture")
    ap.add_argument("--assert", dest="do_assert", action="store_true", help="assert a sentinel is seen server-side")
    ap.add_argument("--run-id", default=None, help="verify_run_id (default: a fresh uuid on --emit)")
    ap.add_argument("--timeout", type=int, default=90, help="seconds to poll the events API (default 90)")
    args = ap.parse_args()

    # Default (neither flag): full check = emit then assert.
    full = not args.emit and not args.do_assert
    run_id = args.run_id or uuid.uuid4().hex[:16]

    if args.emit or full:
        emit(run_id)
        if full:
            # PostHog ingest → queryable has a short lag; give it a moment.
            time.sleep(3)
    if args.do_assert or full:
        if args.do_assert and not args.run_id and not full:
            sys.exit("[verify_capture] --assert requires --run-id (or run without flags for a full emit+assert).")
        ok = assert_seen(run_id, args.timeout)
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
