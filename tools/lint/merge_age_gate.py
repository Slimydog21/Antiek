#!/usr/bin/env python3
"""Merge-age gate — red if the PR's base is too far behind ``origin/main``.

The invariant (SPR-01, Antiek Flywheel Foundation): the prior foundation died
of **stale-base stranding** — it forked at ``69bcfef``, was lapped by ~+38
commits onto a long-lived integration branch, and never merged to main. This
gate makes that failure mechanically loud. It measures how many commits on
``origin/main`` the PR's base has NOT absorbed and reds once that distance
exceeds a single tunable budget ``N``.

What the distance measures (honesty): on a ``pull_request`` CI run the merge
base is ``git merge-base HEAD origin/main``; the distance is
``git rev-list --count <merge-base>..origin/main`` — i.e. the commits on
``origin/main`` that the PR's base has not yet absorbed. It is NOT the count of
the PR's own commits, and it says nothing about content conflicts; it is purely
"how lapped is your base."

Fairness: ``N`` (= 25) is deliberately generous enough for normal multi-day
parallel work; it is justified against the prior +38 stranding. ``N`` lives in
ONE named constant so the decision doc and the code cannot drift.

Exit-code contract (same shape as ``tools/lint/boundary_check.py``):
  * 0  — base is within budget (distance <= N).
  * 1  — base is over budget (distance > N); rebase required.
  * 2  — ``origin/main`` is unresolvable / git failed. FAIL LOUD — never a
         silent pass (defensibility: no false-negative trap).

Defensibility: if ``origin/main`` cannot be resolved (no remote, fetch failed,
merge-base undeterminable), the gate exits NON-ZERO with an explicit
"cannot determine merge-base" message. A green exit here would re-create the
exact stranding hole this gate exists to close, so the unresolvable path is
treated as a hard error, not a skip.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

# Maximum number of commits the PR's base may be behind ``origin/main`` before
# this gate reds. ONE named constant — changing the budget is a one-line edit,
# and the decision doc cites this same number so doc and code cannot drift.
# Justified at 25 against the prior +38 stranding (SPR-01 decision doc).
MAX_BEHIND: int = 25

# Exit codes (loud, distinct so callers/CI can tell the two failure kinds apart).
_OK = 0
_OVER_BUDGET = 1
_UNRESOLVABLE = 2


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command rooted at the repo. Never raises on non-zero — callers
    inspect ``returncode`` so a git failure can be reported loudly rather than
    swallowed into a misleading exit 0."""
    return subprocess.run(
        ["git", "-C", str(_REPO), *args],
        capture_output=True,
        text=True,
    )


def _fetch_origin_main() -> None:
    """Best-effort defensive fetch of ``origin/main``.

    CI checks out with ``fetch-depth: 0`` so the ref is already present; locally
    it may be stale. We do NOT treat a fetch failure as fatal here — a usable
    ``origin/main`` ref may already exist from a prior fetch — but if the ref is
    genuinely unresolvable that is caught (loudly) by ``compute_distance``.
    """
    _git("fetch", "origin", "main")


def compute_distance() -> tuple[int | None, str]:
    """Return ``(distance, message)``.

    ``distance`` is the number of commits on ``origin/main`` not absorbed by the
    PR's base, or ``None`` if ``origin/main`` / the merge-base cannot be
    resolved (in which case ``message`` explains why and the caller must FAIL
    LOUD — never exit 0).
    """
    # 1. origin/main must resolve to a real commit.
    rev = _git("rev-parse", "--verify", "--quiet", "origin/main")
    if rev.returncode != 0 or not rev.stdout.strip():
        return (
            None,
            "merge_age: cannot determine merge-base — 'origin/main' is "
            "unresolvable (no such ref; is the remote present and fetched?). "
            "Refusing to pass: a stale or missing base is exactly the "
            "stranding this gate guards against. Fetch origin/main and retry.",
        )

    # 2. merge-base(HEAD, origin/main) must resolve.
    mb = _git("merge-base", "HEAD", "origin/main")
    if mb.returncode != 0 or not mb.stdout.strip():
        return (
            None,
            "merge_age: cannot determine merge-base between HEAD and "
            "origin/main (no common ancestor / unrelated histories). "
            "Refusing to pass.",
        )
    merge_base = mb.stdout.strip()

    # 3. distance = commits on origin/main NOT absorbed by the base.
    count = _git("rev-list", "--count", f"{merge_base}..origin/main")
    if count.returncode != 0 or not count.stdout.strip().isdigit():
        return (
            None,
            "merge_age: cannot determine merge-base — 'git rev-list --count' "
            f"failed (rc={count.returncode}): {count.stderr.strip() or '<no stderr>'}. "
            "Refusing to pass.",
        )
    return int(count.stdout.strip()), ""


def main() -> int:
    _fetch_origin_main()
    distance, err = compute_distance()

    if distance is None:
        print(err)
        return _UNRESOLVABLE

    if distance > MAX_BEHIND:
        print(
            f"merge_age: base is {distance} commits behind origin/main "
            f"(limit N={MAX_BEHIND}); run `git rebase origin/main`"
        )
        return _OVER_BUDGET

    print(
        f"OK: base is {distance} commits behind origin/main "
        f"(limit N={MAX_BEHIND})."
    )
    return _OK


if __name__ == "__main__":
    sys.exit(main())
