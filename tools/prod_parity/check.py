#!/usr/bin/env python3
"""Prod-parity assertion — SPR-07 (antiek-foundation-v2),
extended SPR-11 (antiek-flywheel-foundation).

Fetch ``/health`` from a live Antiek API and assert three things:

  (a) the SHA the running process reports (``build_sha``) equals the
      expected ref (default: ``git rev-parse origin/main``),
  (b) the live provider registry (``registered_providers``) is non-empty,
      and
  (c) the research-DEPTH flywheel is ALIVE (``flywheel_ready`` is true) —
      i.e. the retrieval substrate opens and >= 1 ``knowledge.reused``
      event is observable on the box. This is the SPR-11 extension: a
      deployed-but-dead flywheel ("it compounds in dev, not on prod") now
      reds the deploy assert, not just a stale SHA or empty registry.

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
  * INFORMATIONAL — a scheduled / workflow_dispatch CI job in
    ``.github/workflows/prod_parity.yml``. It probes prod against the tip
    of ``origin/main`` and reports drift, but it CANNOT be a required
    PR-blocking gate: it structurally needs the *live prod URL*, which is
    only meaningful AFTER a deploy completes (a PR has no deployed SHA to
    compare against), and that external endpoint can be down for reasons
    unrelated to code. So it is marked ``continue-on-error`` and never
    blocks a PR.

REJECTED ALTERNATIVE — "trust the deploy pipeline." Empirically false
here: the stale-SPA drift already shipped undetected, so a ~10-line
assertion comparing deployed-SHA to ``main`` is exactly the control the
pipeline lacked. Trust is not a control.

Exit codes:
    0 — build_sha == expected_sha AND len(registered_providers) > 0 AND
        the flywheel is live (``flywheel_ready`` true).
    1 — a parity failure (SHA mismatch and/or empty provider registry
        and/or a dead flywheel), with a message naming which condition
        failed.
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
    """The real assertion logic. Returns a list of failure messages —
    empty list means in-parity (the check passes).

    Asserts THREE things (SPR-11 added the third):
      (a) deployed ``build_sha`` == ``expected_sha``,
      (b) ``registered_providers`` is non-empty, and
      (c) the flywheel is live (``flywheel_ready`` true).
    """
    failures: list[str] = []
    build_sha = health.get("build_sha", "")
    providers = health.get("registered_providers", [])
    # ``flywheel_ready`` is the SPR-11 /health field. Absent (an older
    # build that predates the field) reads as falsy here — which is the
    # safe red: we cannot prove the flywheel is live, so we do not pass it.
    flywheel_ready = health.get("flywheel_ready", False)
    reuse_count = health.get("knowledge_reuse_count", 0)
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
    if not flywheel_ready:
        failures.append(
            "dead flywheel: flywheel_ready is false/absent "
            f"(knowledge_reuse_count={reuse_count!r}) — the retrieval "
            "substrate did not open or zero knowledge.reused events are "
            "observable. Compounding is NOT live on this box (it may "
            "compound in dev but not on prod — the exact failure SPR-11 "
            "guards)."
        )
    return failures


def run(url: str, expected_sha: str) -> int:
    """Fetch + assert; return the process exit code. Pure-enough to call
    from tests (they pass a fake ``url`` or monkeypatch ``fetch_health``)."""
    try:
        health = fetch_health(url)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"prod-parity: could not reach {url}/health: {exc}", file=sys.stderr)
        return 2
    failures = assert_parity(health, expected_sha)
    if failures:
        for msg in failures:
            print(f"prod-parity: FAIL — {msg}", file=sys.stderr)
        return 1
    print(
        f"prod-parity: OK — build_sha {expected_sha} matches main, "
        f"{len(health.get('registered_providers', []))} providers registered, "
        f"and the flywheel is live "
        f"(knowledge_reuse_count={health.get('knowledge_reuse_count', 0)})",
    )
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
    args = parser.parse_args(argv)

    expected = args.expected_sha
    if expected is None:
        try:
            expected = default_expected_sha()
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            print(f"prod-parity: could not compute expected SHA: {exc}", file=sys.stderr)
            return 2

    return run(args.url, expected)


if __name__ == "__main__":
    raise SystemExit(main())
