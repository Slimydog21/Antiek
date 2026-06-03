#!/usr/bin/env python3
"""Combined convergence sweep — Antiek Convergence SPR-07 (M3).

The convergence-owner's ONE command. The Antiek parallel-sprint loop recurs into
two failure classes, and each has a guard:

  * FORKS — two impls of one substrate concern. Guard: the SPR-07 uniqueness
    registry (``tools/lint/uniqueness_registry.run_all``).
  * DEAD-IN-PROD FEATURES — a feature unreachable from the real product. Guard:
    the SPR-01 reachability probe runner (``tools/reachability/probe_runner``).

This sweep runs BOTH and prints ONE combined report, so the convergence-owner
(see ``docs/decisions/convergence-owner.md``) asks "is anything forked, and is
anything dead-in-prod?" in a single invocation after a wave.

It does NOT re-implement either guard — it IMPORTS and calls the REAL ones:

  * ``uniqueness_registry.run_all()`` for the uniqueness half (the SAME engine
    the CI anti-fork meta-check runs);
  * ``probe_runner.discover_probes()`` + ``run_probes()`` + ``load_known_red()``
    for the reachability half (the SAME runner the CI ``reachability`` job
    runs — booting the app through the production ``create_app()`` factory).

AGGREGATION, NOT SHORT-CIRCUIT (SPR-07 rigor #3). A fork AND a dead probe must
BOTH appear in one run — the sweep never returns early on the first failure. It
returns non-zero iff EITHER half fails, so a green exit means BOTH halves are
green.

CI POSTURE (SPR-07 M3 decision). This sweep is primarily the OPERATOR / runbook
entrypoint. Its two halves are ALREADY enforced in CI separately and at full
strength — the uniqueness registry as a blocking step in the ``pytest`` job, the
reachability runner as the dedicated app-booting ``reachability`` job. Adding the
sweep as a THIRD CI step would duplicate the reachability job's app boot (the
expensive part) for no extra coverage. So the sweep is NOT wired as its own CI
step; the CI enforcement is uniqueness-step + reachability-job, and the sweep is
the human's single-command convenience over both. (Documented in the runbook.)

Usage::

    python -m tools.reachability.sweep        # run both halves, one report
    python -m tools.reachability.sweep --only-uniqueness
    python -m tools.reachability.sweep --only-reachability

Exit codes:
    0 — every concern UNIQUE AND every probe REACHABLE (or BLOCKED-but-within an
        unexpired known-red window).
    1 — at least one concern FORKED, OR at least one probe BLOCKED outside a
        known-red window / an EXPIRED known-red entry. BOTH halves are always
        evaluated and reported before the exit.
"""

from __future__ import annotations

import argparse
import io
import os
import sys

# Make the package root importable when invoked as a bare script
# (``python tools/reachability/sweep.py``) as well as a module. Mirrors the
# bootstrap in tools/reachability/probe_runner.py.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from tools.lint.uniqueness_registry import run_all as _uniqueness_run_all  # noqa: E402
from tools.reachability.probe_runner import (  # noqa: E402
    discover_probes,
    load_known_red,
    run_probes,
)


def _run_uniqueness() -> tuple[int, list[str]]:
    """The uniqueness half — the SAME registry the CI anti-fork meta-check runs.
    Returns ``(exit_code, report_lines)`` ([UNIQUE]/[FORK] lines)."""
    return _uniqueness_run_all()


def _run_reachability() -> tuple[int, list[str]]:
    """The reachability half — the REAL SPR-01 runner (boots the app via the
    production create_app() factory). We call ``run_probes`` with an in-memory
    buffer so its [REACHABLE]/[BLOCKED] lines fold into the one combined report
    rather than printing out of order. Returns ``(exit_code, report_lines)``.

    A discovery failure (zero probes — the namespace-package ambiguity SPR-01
    documents, or a deleted probes/ dir) is a FAILURE here, not a vacuous pass:
    a sweep that silently runs zero probes would be the false-green the whole
    reachability gate exists to forbid."""
    probes = discover_probes()
    if not probes:
        return 1, [
            "[BLOCKED] reachability: NO probes discovered under "
            "tools/reachability/probes/ — the reachability half cannot run "
            "(a zero-probe sweep is a false green, not a pass)."
        ]
    known_red = load_known_red()
    buf = io.StringIO()
    code = run_probes(probes, known_red, out=buf)
    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    return code, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.reachability.sweep",
        description=(
            "Combined convergence sweep: run the SPR-07 uniqueness registry "
            "(anti-fork) AND the SPR-01 reachability probe runner "
            "(anti-dead-in-prod), aggregate both (no short-circuit), and exit "
            "non-zero iff EITHER fails. The convergence-owner's one command."
        ),
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--only-uniqueness",
        action="store_true",
        help="run ONLY the uniqueness (anti-fork) half",
    )
    g.add_argument(
        "--only-reachability",
        action="store_true",
        help="run ONLY the reachability (anti-dead-in-prod) half",
    )
    args = parser.parse_args(argv)

    exit_code = 0
    uniq_lines: list[str] = []
    reach_lines: list[str] = []

    # ALWAYS evaluate both halves (unless explicitly scoped) BEFORE deciding the
    # exit code — aggregate, never short-circuit. A fork and a dead probe must
    # both be reported in one run.
    if not args.only_reachability:
        uc, uniq_lines = _run_uniqueness()
        exit_code |= 1 if uc else 0
    if not args.only_uniqueness:
        rc, reach_lines = _run_reachability()
        exit_code |= 1 if rc else 0

    print("=== Antiek Convergence sweep (SPR-07) ===")
    if uniq_lines:
        print("\n-- uniqueness (anti-fork) --")
        for ln in uniq_lines:
            print(ln)
    if reach_lines:
        print("\n-- reachability (anti-dead-in-prod) --")
        for ln in reach_lines:
            print(ln)

    print()
    if exit_code:
        print(
            "FAIL: a registered concern FORKED and/or a feature is "
            "DEAD-IN-PROD. Converge forks and wire dead features per "
            "docs/decisions/convergence-owner.md before declaring the wave "
            "merged."
        )
    else:
        print(
            "OK: every registered concern is UNIQUE and every probed feature "
            "is REACHABLE from the production factory."
        )
    return 1 if exit_code else 0


if __name__ == "__main__":
    sys.exit(main())
