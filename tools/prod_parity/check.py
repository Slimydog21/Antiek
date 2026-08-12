#!/usr/bin/env python3
"""Prod-parity assertion — SPR-07 (antiek-foundation-v2),
extended SPR-11 (antiek-flywheel-foundation).

Fetch ``/health`` from a live Antiek API and check three things:

  (a) the SHA the running process reports (``build_sha``) equals the
      expected ref (default: ``git rev-parse origin/main``)  — BLOCKING,
  (b) the live provider registry (``registered_providers``) is non-empty
      — BLOCKING, and
  (c) the research-DEPTH flywheel is ALIVE (``flywheel_ready`` is true) —
      i.e. the retrieval substrate opens and >= 1 ``knowledge.reused``
      event is observable on the box. This is the SPR-11 extension and is
      INFORMATIONAL by default (a ``::warning`` that does not fail the run),
      because flywheel liveness is a product-maturity signal gated on a
      corpus + research activity, NOT a property of the code that shipped:
      a correct deploy onto an unfed box cannot make it true. Promote it to
      BLOCKING with ``--require-flywheel`` once a corpus ingest has produced
      >= 1 reuse event on prod (RECONSIDER-IF — see
      ``docs/decisions/prod-parity-flywheel-informational.md``).

This is the cheap parity catch the deploy pipeline lacked. Earlier this
month a stale-SPA drift shipped to ``api.antiek.ai`` and went undetected
for an extended period because *nothing asserted that the deployed commit
equals main's tip*. Eyeballing ``status: ok`` does not compare a SHA — so
this script mechanizes the one comparison a human reliably skips.

WHERE IT RUNS (two surfaces, honestly):

  * BLOCKING — a post-deploy task in
    ``infrastructure/ansible/playbooks/deploy.yml``. At that moment the
    deployed SHA is known (``git_pull.after``) and the URL is live, so a
    non-zero exit *fails the play*. This is the surface that would have
    caught the original drift.
  * OPERATIONAL ALARM — a scheduled / workflow_dispatch CI job in
    ``.github/workflows/prod_parity.yml``. It probes prod against the tip
    of ``origin/main`` and preserves blocking SHA/provider/transport exit
    codes. It is not a required PR gate because it has no ``pull_request``
    trigger: a PR has no deployed SHA to compare against. Flywheel maturity
    alone remains warning-only unless ``--require-flywheel`` is supplied.

REJECTED ALTERNATIVE — "trust the deploy pipeline." Empirically false
here: the stale-SPA drift already shipped undetected, so a ~10-line
assertion comparing deployed-SHA to ``main`` is exactly the control the
pipeline lacked. Trust is not a control.

Exit codes:
    0 — build_sha == expected_sha AND len(registered_providers) > 0 (a dead
        flywheel only warns here unless ``--require-flywheel`` is set).
    1 — a parity failure (SHA mismatch and/or empty provider registry; plus a
        dead flywheel only when ``--require-flywheel`` is set), with a message
        naming which condition failed.
    2 — could not complete the check (network/HTTP error reaching
        ``/health``, or could not compute the expected SHA).

Usage::

    python tools/prod_parity/check.py \
        --url https://api.antiek.ai \
        --expected-sha <the-just-deployed-sha>

When ``--expected-sha`` is omitted it defaults to
``git rev-parse origin/main`` (run ``git fetch`` first for an accurate
comparison against the remote tip).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def fetch_health(url: str, *, timeout: float = 10.0) -> dict:
    """GET ``{url}/health`` and return the parsed JSON body.

    ``url`` may be a bare base URL (``https://api.antiek.ai``) or already
    end in ``/health`` — both are accepted so the caller need not care.
    Raises on any transport/HTTP/JSON error; the CLI maps that to exit 2.
    """
    base = url.rstrip("/")
    health_url = base if base.endswith("/health") else base + "/health"
    # Cloudflare (fronting api.antiek.ai) 403s the default ``Python-urllib/*``
    # User-Agent as a bot, so the parity probe never reached /health — the
    # blocking deploy assert + the scheduled probe both false-red. Send a
    # descriptive UA (verified: default urllib UA → 403, this UA → 200).
    req = urllib.request.Request(
        health_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "antiek-prod-parity/1.0 (+https://antiek.ai)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (own URL)
        return json.loads(resp.read().decode("utf-8"))


def default_expected_sha() -> str:
    """``git rev-parse origin/main`` — the tip of main to compare against."""
    out = subprocess.run(
        ["git", "rev-parse", "origin/main"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if out.returncode != 0:
        raise RuntimeError(
            "git rev-parse origin/main failed (run `git fetch` first?): "
            + out.stderr.strip()
        )
    return out.stdout.strip()


def assert_parity(health: dict, expected_sha: str) -> list[str]:
    """The BLOCKING parity assertions. Returns a list of failure messages —
    empty list means in-parity (the check passes).

    Asserts the two deploy-correctness invariants — the things a code deploy
    is actually responsible for and can always satisfy:
      (a) deployed ``build_sha`` == ``expected_sha``,
      (b) ``registered_providers`` is non-empty.

    The SPR-11 flywheel-liveness check is INTENTIONALLY NOT here — it is a
    product-maturity signal (does compounding happen on this box?) gated on a
    corpus + research activity, not on the code that shipped. It lives in
    ``flywheel_warnings`` and is informational by default; see that function
    and ``docs/decisions/prod-parity-flywheel-informational.md``.
    """
    failures: list[str] = []
    build_sha = health.get("build_sha", "")
    providers = health.get("registered_providers", [])
    if build_sha != expected_sha:
        failures.append(
            f"SHA mismatch: deployed build_sha={build_sha!r} != "
            f"expected_sha={expected_sha!r} (deployed code is not main's tip)"
        )
    if not providers:
        failures.append(
            "empty provider registry: registered_providers is empty "
            "(credential-gated silent-empty mode — the secrets file is "
            "almost certainly unpopulated)"
        )
    return failures


def flywheel_warnings(health: dict) -> list[str]:
    """SPR-11 flywheel-liveness check — INFORMATIONAL by default.

    Returns a list of warning messages (empty == flywheel live). A dead
    flywheel (``flywheel_ready`` false, or the field absent on an older
    build) is a real signal worth surfacing, but it is NOT a deploy defect:
    ``flywheel_ready`` only becomes true once the box has an ingested corpus
    AND >= 1 ``knowledge.reused`` event from real research activity. A clean
    code deploy onto an unfed box (the current prod state — the corpus ingest
    window is an operator-gated deferral) cannot make it true, so hard-failing
    the deploy on it would red-flag every correct deploy.

    Promote this to a BLOCKING failure with ``run(..., require_flywheel=True)``
    / the ``--require-flywheel`` CLI flag. RECONSIDER-IF: once an operator
    corpus ingest has produced >= 1 reuse event on prod, flip the deploy
    playbook to pass ``--require-flywheel`` so a regression to a dead flywheel
    reds again (the original SPR-11 intent, now correctly sequenced after the
    corpus exists). See ``docs/decisions/prod-parity-flywheel-informational.md``.
    """
    flywheel_ready = health.get("flywheel_ready", False)
    reuse_count = health.get("knowledge_reuse_count", 0)
    if flywheel_ready:
        return []
    return [
        "dead flywheel: flywheel_ready is false/absent "
        f"(knowledge_reuse_count={reuse_count!r}) — the retrieval "
        "substrate did not open or zero knowledge.reused events are "
        "observable. Compounding is NOT live on this box (it may "
        "compound in dev but not on prod — the exact failure SPR-11 "
        "guards)."
    ]


def _auth_probe_base_url(cli_url: str) -> str | None:
    env_base = os.environ.get("ANTIEK_API_BASE", "").strip()
    if env_base:
        return env_base.rstrip("/")
    return cli_url.rstrip("/") if cli_url else None


def run_auth_probe(base_url: str, *, origin: str = "https://antiek.ai") -> int:
    from tools.auth_probe import _DEFAULT_PROBE_EMAIL, run_stages

    results = run_stages(base_url, origin, _DEFAULT_PROBE_EMAIL)
    for stage in results:
        print(json.dumps(stage.to_json()))
    if all(s.pass_ for s in results):
        print("prod-parity: auth-probe OK — all stages passed")
        return 0
    print("prod-parity: auth-probe FAIL — one or more stages failed", file=sys.stderr)
    return 1


def run(
    url: str,
    expected_sha: str,
    *,
    auth_probe: bool = False,
    auth_origin: str = "https://antiek.ai",
    require_flywheel: bool = False,
) -> int:
    """Fetch + assert; return the process exit code. Pure-enough to call
    from tests (they pass a fake ``url`` or monkeypatch ``fetch_health``).

    SHA + provider parity always block (exit 1 on failure). Flywheel liveness
    is INFORMATIONAL by default (a ``::warning`` / stderr note, exit unchanged)
    and only blocks when ``require_flywheel`` is set — see ``flywheel_warnings``.
    """
    try:
        health = fetch_health(url)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"prod-parity: could not reach {url}/health: {exc}", file=sys.stderr)
        return 2
    failures = assert_parity(health, expected_sha)
    flywheel = flywheel_warnings(health)
    if require_flywheel:
        # Operator opted in (post-corpus): a dead flywheel is now blocking.
        failures = failures + flywheel
    elif flywheel:
        # Informational: surface it loudly but do NOT fail the deploy.
        for msg in flywheel:
            print(f"::warning title=prod-parity flywheel::{msg}")
            print(f"prod-parity: WARNING (informational) — {msg}", file=sys.stderr)
    if failures:
        for msg in failures:
            print(f"prod-parity: FAIL — {msg}", file=sys.stderr)
        return 1
    flywheel_note = (
        f"flywheel live (knowledge_reuse_count={health.get('knowledge_reuse_count', 0)})"
        if not flywheel
        else "flywheel informational (not yet live — see warning above)"
    )
    print(
        f"prod-parity: OK — build_sha {expected_sha} matches main, "
        f"{len(health.get('registered_providers', []))} providers registered, "
        f"{flywheel_note}",
    )
    if auth_probe or os.environ.get("ANTIEK_API_BASE", "").strip():
        probe_base = _auth_probe_base_url(url)
        if not probe_base:
            print("prod-parity: auth-probe skipped — no base URL", file=sys.stderr)
            return 2
        return run_auth_probe(probe_base, origin=auth_origin)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prod_parity.check",
        description="Assert the live API's deployed SHA == main and providers are live.",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Base URL of the live API (e.g. https://api.antiek.ai). "
        "A trailing /health is optional.",
    )
    parser.add_argument(
        "--expected-sha",
        default=None,
        help="Commit SHA the deployed process should report. "
        "Defaults to `git rev-parse origin/main` when omitted.",
    )
    parser.add_argument(
        "--auth-probe",
        action="store_true",
        help="After parity passes, run tools/auth_probe staged checks.",
    )
    parser.add_argument(
        "--auth-origin",
        default="https://antiek.ai",
        help="Origin for auth-probe CORS stage.",
    )
    parser.add_argument(
        "--require-flywheel",
        action="store_true",
        help="Promote the flywheel-liveness check from informational to "
        "BLOCKING (exit 1 on a dead flywheel). Off by default — flip on "
        "once a corpus ingest has produced >= 1 knowledge.reused event on "
        "prod. See docs/decisions/prod-parity-flywheel-informational.md.",
    )
    args = parser.parse_args(argv)

    expected = args.expected_sha
    if expected is None:
        try:
            expected = default_expected_sha()
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            print(f"prod-parity: could not compute expected SHA: {exc}", file=sys.stderr)
            return 2

    return run(
        args.url,
        expected,
        auth_probe=args.auth_probe,
        auth_origin=args.auth_origin.strip(),
        require_flywheel=args.require_flywheel,
    )


if __name__ == "__main__":
    raise SystemExit(main())
