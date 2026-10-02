"""Find PRs blocked on an ORPHANED CI run — cancelled, with nothing replacing it.

A cancelled workflow run never re-reports. If nothing supersedes it, the PR's
required checks sit at ``cancelled`` forever: auto-merge will not fire, the
branch is not DIRTY, and no failure is shown. The PR is simply dead, quietly,
until a human notices and re-runs it.

This is not hypothetical. Measured on 2026-09-21: of 54 completed ``ci.yml``
runs, 42 were cancelled — 20 legitimately superseded by a newer push, and 22
orphaned. Nineteen open PRs were blocked that way at once, each with 2-8 dead
required checks, all cancelled inside one 43-minute window. Main also carries
two commits from an earlier occurrence, ``ci: re-trigger checks after
out-of-band cancellation`` and ``ci: re-trigger after cancel loop quieted``.

WHY THIS ONLY REPORTS
---------------------
It does not re-run anything. Under ``concurrency: cancel-in-progress`` a re-run
CANCELS the attempt it just started, so an automated re-runner that triggers on
"cancelled" feeds itself: cancel -> rerun -> cancel. That loop was observed
first-hand. Re-running is a human decision, one run at a time, verifying
``run_attempt`` actually incremented — ``gh run rerun`` exits 0 for requests it
does not fulfil.

Exit codes: ``0`` no orphans, ``1`` orphans found (the loud channel for a
scheduled probe), ``2`` the scan could not be trusted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass

# A required-context set this small means the ruleset read failed. Reporting
# "no orphans" off a truncated set would be a clean bill of health over nothing.
_MIN_REQUIRED = 4


def _gh(*args: str) -> str:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    return proc.stdout


@dataclass(frozen=True)
class Orphan:
    number: int
    dead: tuple[str, ...]
    updated_at: str
    title: str


def required_contexts() -> set[str]:
    out: set[str] = set()
    for rid in _gh("api", "repos/:owner/:repo/rulesets", "--jq", ".[].id").split():
        out |= {
            line.strip()
            for line in _gh(
                "api",
                f"repos/:owner/:repo/rulesets/{rid}",
                "--jq",
                '.rules[]?|select(.type=="required_status_checks")'
                "|.parameters.required_status_checks[].context",
            ).splitlines()
            if line.strip()
        }
    return out


def find_orphans(limit: int, required: set[str]) -> list[Orphan]:
    prs = json.loads(
        _gh(
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "number,headRefOid,updatedAt,title",
        )
        or "[]"
    )
    found: list[Orphan] = []
    for pr in prs:
        sha = pr["headRefOid"]
        checks = json.loads(
            _gh(
                "api",
                f"repos/:owner/:repo/commits/{sha}/check-runs?per_page=100",
                "--jq",
                "[.check_runs[]|{name,conclusion,status}]",
            )
            or "[]"
        )
        state = {c["name"]: (c.get("conclusion") or c.get("status")) for c in checks}
        dead = tuple(sorted(c for c in required if state.get(c) == "cancelled"))
        if not dead:
            continue
        runs = json.loads(
            _gh(
                "api",
                f"repos/:owner/:repo/actions/runs?head_sha={sha}&per_page=20",
                "--jq",
                '[.workflow_runs[]|select(.path|test("ci.yml"))|{status}]',
            )
            or "[]"
        )
        # Something in flight will replace those checks: superseded, not orphaned.
        if any(r["status"] != "completed" for r in runs):
            continue
        found.append(Orphan(pr["number"], dead, pr["updatedAt"], pr["title"]))
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--json", action="store_true", help="emit the verdict as JSON")
    args = ap.parse_args(argv)

    required = required_contexts()
    if len(required) < _MIN_REQUIRED:
        print(
            f"UNTRUSTED: read only {len(required)} required contexts "
            f"(expected >= {_MIN_REQUIRED}); refusing to report a clean scan "
            f"over a failed ruleset read",
            file=sys.stderr,
        )
        return 2

    orphans = find_orphans(args.limit, required)
    if args.json:
        print(
            json.dumps(
                {
                    "required_contexts": sorted(required),
                    "orphans": [
                        {
                            "number": o.number,
                            "dead": list(o.dead),
                            "updated_at": o.updated_at,
                            "title": o.title,
                        }
                        for o in orphans
                    ],
                },
                indent=2,
            )
        )
    elif not orphans:
        print(f"CLEAN: no PR is blocked on an orphaned run ({len(required)} required contexts)")
    else:
        print(f"ORPHANED: {len(orphans)} PR(s) blocked on a cancelled run nothing replaced")
        for o in sorted(orphans, key=lambda x: x.number):
            print(
                f"  #{o.number}  {len(o.dead)} dead required check(s)  "
                f"{o.updated_at[:16]}  {o.title[:60]}"
            )
        print()
        print("  Re-run each ONCE by hand and verify run_attempt incremented.")
        print("  Do NOT automate this: rerun cancels the attempt it starts.")
    return 1 if orphans else 0


if __name__ == "__main__":
    raise SystemExit(main())
