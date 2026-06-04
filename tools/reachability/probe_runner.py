#!/usr/bin/env python3
"""Reachability-probe runner — Antiek Convergence SPR-01 (keystone).

Antiek's flagship feature (the compounding flywheel) shipped DEAD in prod:
``interfaces/research/api/cascade_routes.py`` builds ``HostLocalRunner(...)``
with ``retrieval_substrate`` left at its default ``None``, so
``runtime/research_runner/host_local.py`` early-returns the reuse step, no
``knowledge.reused`` event is emitted, and ``/health`` reports
``knowledge_reuse_count=0`` on live prod. It shipped because EVERY gate in
the build verifies a *brick* (a unit test, a contract test, a mocked
harness — the compounding benchmark even *injects* the substrate prod never
injects, ``compounding/benchmark/harness.py:344``) and NOTHING verifies a
feature is REACHABLE FROM THE REAL PRODUCT.

This runner is the missing gate. Each probe:

  * boots the app through the PRODUCTION ``create_app()`` factory — the same
    factory ``interfaces/research/api/app.py`` exposes to uvicorn — with NO
    provider keys, NO ``retrieval_substrate=`` injection, NO stubbed
    providers (that injection is the exact blind spot the benchmark has and
    is forbidden here — see ``README.md`` "the fixture-injection
    anti-pattern");
  * drives ONE feature through its real route(s);
  * asserts an OBSERVABLE OUTCOME (e.g. ``knowledge_reuse_count > 0``),
    never the presence of a parameter or a mocked dependency.

Exit code 0 iff every probe's outcome holds; exit 1 if any probe is
BLOCKED. The known-red valve (``known_red.json``) lets a probe that is
INTENTIONALLY red during a fix window (e.g. the flywheel probe during
SPR-01 -> SPR-02) merge WITHOUT faking green and WITHOUT the red being
ignored forever: the entry carries a linked issue + a hard expiry, and an
EXPIRED entry fails the run (the valve self-closes).

Structure mirrors ``tools/prod_parity/check.py`` (pure-enough functions +
argparse + ``__main__``) so a maintainer who knows one knows the other.

Usage::

    python -m tools.reachability.probe_runner            # run all probes
    python -m tools.reachability.probe_runner --only flywheel
    python -m tools.reachability.probe_runner --list

Exit codes:
    0 — every probe REACHABLE (or BLOCKED-but-within an unexpired known-red
        window).
    1 — at least one probe BLOCKED outside any known-red window, OR a
        known-red entry has EXPIRED (the valve closed and the probe is
        still red).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib
import json
import os
import pkgutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# Ensure the package root is importable when invoked as a bare script
# (``python tools/reachability/probe_runner.py``) as well as a module
# (``python -m tools.reachability.probe_runner``). Mirrors the sys.path
# bootstrap in interfaces/research/api/app.py.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

# Default per-probe wall-clock ceiling. SOURCE: the flywheel probe drives a
# plan->approve->launch of a single demo-loop research and reads the event
# log; that completes in ~2 s in-process on dev hardware (measured during
# SPR-01 M1). 30 s is ~15x headroom for the shared CI runner (CLAUDE.md /
# ci.yml note the runner is ~1.66x-2x slower than dev hardware) so a slow
# feature reds as a finding (timeout), not a flake. Override per probe via
# the descriptor's ``timeout_s``.
DEFAULT_PROBE_TIMEOUT_S = 30.0

_KNOWN_RED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "known_red.json")
_PROBES_PKG = "tools.reachability.probes"


# ---------------------------------------------------------------------------
# Probe descriptor + result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProbeResult:
    """The outcome of running one probe.

    ``ok`` is the feature-outcome verdict (True == REACHABLE). ``reason`` is
    the human-readable BLOCKED reason when ``ok`` is False (empty when ok).
    ``failure_mode`` distinguishes the *class* of failure so a BLOCKED probe
    is not ambiguous between "the app could not boot" and "the feature is
    dead" — the two require different fixes:

      * ``"reachable"``  — outcome held (ok=True).
      * ``"feature_dead"`` — app booted, route responded, but the asserted
        OUTCOME did not hold (the flywheel probe's RED today: launch
        succeeds, ``knowledge_reuse_count`` stays 0).
      * ``"boot_fail"`` — ``create_app()`` raised; nothing downstream ran.
      * ``"route_404"`` — a driven route 404'd (entrypoint moved/renamed).
      * ``"timeout"`` — the probe exceeded its wall-clock ceiling (a slow
        feature is a FINDING, not a pass).
      * ``"error"``    — the probe raised an unexpected exception.
    """

    ok: bool
    reason: str = ""
    failure_mode: str = "reachable"


@dataclass(frozen=True)
class Probe:
    """A per-feature reachability descriptor.

    ``id``       — the ``--only`` selector + the known_red.json key.
    ``feature``  — human name printed in ``[REACHABLE]`` / ``[BLOCKED]``.
    ``run``      — a zero-arg callable that boots the app via the PRODUCTION
                   ``create_app()`` factory, drives the feature, and returns
                   a ``ProbeResult``. It MUST NOT inject ``retrieval_substrate``,
                   stub providers, or otherwise pre-wire a dependency prod
                   does not wire — that is the blind spot this gate exists to
                   catch (README "the fixture-injection anti-pattern").
    ``timeout_s``— per-probe wall-clock ceiling (default
                   ``DEFAULT_PROBE_TIMEOUT_S``).
    ``headline`` — when True, this probe is the TOP-LINE (headline) probe:
                   it sorts FIRST in ``--list`` and in a full run, ahead of
                   every non-headline probe (which keep their id-ascending
                   order). SPR-08's ``usability_keystone`` is the headline —
                   it is the conjunction of the other legs into one journey,
                   so a maintainer reading the gate sees the "is the product
                   usable end-to-end" verdict first, before the per-brick
                   probes. A clean small field, NOT an id-prefix hack (an id
                   like ``aaa_keystone`` would corrupt the ``--only`` selector
                   and the ``known_red.json`` key; this keeps the id honest).
    """

    id: str
    feature: str
    run: Callable[[], ProbeResult]
    timeout_s: float = DEFAULT_PROBE_TIMEOUT_S
    headline: bool = False


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_probes() -> list[Probe]:
    """Import every module under ``tools/reachability/probes/`` and collect
    its module-level ``PROBE`` attribute (a ``Probe``). A module without a
    ``PROBE`` is skipped (helpers are allowed). Sorted HEADLINE-first, then by
    id, for stable output: a probe flagged ``headline=True`` sorts ahead of
    every non-headline probe (the others keep their id-ascending order), so the
    end-to-end "is the product usable" verdict (SPR-08 ``usability_keystone``)
    surfaces as the top line in ``--list`` and in a full run — without an
    id-prefix hack that would corrupt the ``--only`` selector / known_red key.

    Discovery is anchored to THIS file's directory, NOT to the already-imported
    ``tools.reachability.probes`` package's ``__path__``. Reason (verified
    SPR-01): ``tools`` is a NAMESPACE package and, with an editable install
    (``pip install -e``) of a sibling Antiek checkout on ``sys.path``, the
    name ``tools.reachability`` can resolve to the OTHER checkout (which has
    no ``probes/`` subdir) when invoked as ``python -m`` — the ``-m``
    bootstrap binds the namespace before this module's own sys.path insert
    runs, so the probes silently vanish. Iterating the directory next to this
    file is invariant under that ambiguity. We still ``importlib.import_module``
    by the dotted name (so the probe modules' own absolute imports work); the
    sys.path insert at module top guarantees that dotted name resolves to
    this same tree.
    """
    probes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probes")

    found: list[Probe] = []
    for mod_info in pkgutil.iter_modules([probes_dir]):
        if mod_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{_PROBES_PKG}.{mod_info.name}")
        probe = getattr(module, "PROBE", None)
        if isinstance(probe, Probe):
            found.append(probe)
    # Headline-first (not headline → sorts after), then id-ascending within
    # each group. ``not p.headline`` is False (0) for the headline probe, so it
    # sorts before the non-headline probes (True == 1); ``p.id`` breaks ties.
    return sorted(found, key=lambda p: (not p.headline, p.id))


# ---------------------------------------------------------------------------
# Known-red valve
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnownRed:
    """One entry from ``known_red.json``: a probe that is INTENTIONALLY red
    during a fix window. ``until_issue_link`` is the tracking issue that
    closes the window; ``until_date`` (YYYY-MM-DD, UTC) is the hard expiry
    after which the valve self-closes and the red fails the run again."""

    probe_id: str
    until_issue_link: str
    until_date: str

    def is_expired(self, today: _dt.date | None = None) -> bool:
        today = today or _dt.datetime.now(_dt.UTC).date()
        try:
            expiry = _dt.date.fromisoformat(self.until_date)
        except ValueError:
            # A malformed date is treated as EXPIRED — fail closed, never
            # leave the valve open on an unparseable expiry.
            return True
        return today > expiry


def load_known_red(path: str = _KNOWN_RED_PATH) -> dict[str, KnownRed]:
    """Parse ``known_red.json`` into ``{probe_id: KnownRed}``. A missing
    file is an empty manifest (no valves open) — the gate is strict by
    default. The file shape is::

        {"probes": [{"probe_id": "...", "until_issue_link": "...",
                     "until_date": "YYYY-MM-DD"}]}
    """
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out: dict[str, KnownRed] = {}
    for row in data.get("probes", []):
        kr = KnownRed(
            probe_id=row["probe_id"],
            until_issue_link=row["until_issue_link"],
            until_date=row["until_date"],
        )
        out[kr.probe_id] = kr
    return out


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _run_one(probe: Probe) -> ProbeResult:
    """Run a single probe under its wall-clock ceiling. A probe that raises
    is mapped to a BLOCKED ``error`` result (never propagated — one broken
    probe must not crash the whole run). The timeout uses a SIGALRM-free
    thread join so it works on any platform and inside pytest.

    ENV ISOLATION (SPR-01 sharpen, defect #2). Probes mutate ``os.environ``
    in place (per README "isolate your writes": each probe sets
    ``ANTIEK_DUCKDB_PATH`` / ``ANTIEK_RESEARCH_EVENTS_DIR`` to per-PID temp
    paths and restores them in its own ``finally``). But that probe-local
    ``finally`` does NOT run when the probe TIMES OUT: the work happens in a
    daemon thread we ``join(timeout=...)`` and then ABANDON while it is still
    alive, so its ``finally`` (env restore + temp-dir rmtree) never executes
    on this turn. The leaked env would then leak into the NEXT probe, which
    could boot against a stale temp DB path. The runner is the only layer
    that can guarantee restoration regardless of thread/timeout state, so it
    snapshots ``os.environ`` HERE, before the probe runs, and restores it
    after the join UNCONDITIONALLY (success, crash, OR timeout). This is
    belt-and-braces over the probe's own ``finally``, not a replacement for
    it — a well-behaved probe still cleans up its own temp dir on the normal
    path; this only backstops the timeout path the probe cannot reach.
    One probe ships today so the leak cannot bite yet, but README instructs
    every future probe to use the same in-place mutate pattern, so we harden
    the shared runner now."""
    import threading

    box: list[ProbeResult] = []
    # Snapshot env BEFORE the probe runs (full copy: a probe may also mutate
    # keys we don't enumerate). Restored in the ``finally`` below.
    _env_snapshot = dict(os.environ)

    def _target() -> None:
        try:
            box.append(probe.run())
        except Exception as exc:  # noqa: BLE001 — a probe crash is a finding
            box.append(
                ProbeResult(
                    ok=False,
                    reason=f"probe raised {type(exc).__name__}: {exc}",
                    failure_mode="error",
                )
            )

    try:
        t = threading.Thread(target=_target, name=f"probe-{probe.id}", daemon=True)
        t.start()
        t.join(timeout=probe.timeout_s)
        if t.is_alive():
            # The probe thread is daemon, so it is abandoned to the process
            # exit; the verdict is a hard BLOCKED (a slow feature is a
            # finding). Its in-probe ``finally`` will NOT have run — the env
            # restore below is what keeps the leak from reaching the next
            # probe.
            return ProbeResult(
                ok=False,
                reason=f"exceeded {probe.timeout_s:.0f}s wall-clock ceiling",
                failure_mode="timeout",
            )
        if not box:  # pragma: no cover — defensive: thread finished, no result
            return ProbeResult(
                ok=False, reason="probe produced no result", failure_mode="error"
            )
        return box[0]
    finally:
        # Restore os.environ to its pre-probe state REGARDLESS of how the
        # probe exited (normal / crashed / timed-out-and-abandoned). On the
        # normal path the probe already restored its own keys, so this is a
        # no-op; on the timeout path it is the only restore that runs.
        # NOTE: if a probe timed out, its daemon thread is still alive and
        # could race a write to os.environ after this restore. That is
        # inherent to abandoning a thread we cannot kill; the timeout is
        # already a hard BLOCKED finding (the run will not be trusted), and a
        # timing-out probe is a defect to fix, not a state to recover into.
        # The common, non-pathological case (next probe after a clean
        # timeout) is correctly isolated.
        os.environ.clear()
        os.environ.update(_env_snapshot)


def run_probes(
    probes: Sequence[Probe],
    known_red: dict[str, KnownRed],
    *,
    today: _dt.date | None = None,
    out=None,
) -> int:
    """Run ``probes``, print one line each, return the process exit code.

    Pure-enough to call from tests: pass an explicit ``probes`` list, a
    ``known_red`` map, and a fixed ``today`` for deterministic expiry
    checks. ``out`` defaults to ``sys.stdout``.

    Exit policy:
      * Any probe REACHABLE -> contributes 0.
      * A BLOCKED probe with an UNEXPIRED known-red entry -> reported as
        ``[BLOCKED (known-red, expires ...)]`` but contributes 0 (the
        intentional fix-window valve).
      * A BLOCKED probe with NO known-red entry, or an EXPIRED one ->
        contributes 1 (fails the run). An expired entry additionally prints
        an explicit "valve EXPIRED" line so the silent-permanent failure
        mode cannot happen.
    """
    out = out or sys.stdout
    exit_code = 0
    for probe in probes:
        result = _run_one(probe)
        if result.ok:
            print(f"[REACHABLE] {probe.feature}", file=out)
            continue
        kr = known_red.get(probe.id)
        base = f"[BLOCKED] {probe.feature}: {result.reason} ({result.failure_mode})"
        if kr is None:
            print(base, file=out)
            exit_code = 1
        elif kr.is_expired(today):
            print(
                f"[BLOCKED] {probe.feature}: {result.reason} ({result.failure_mode}) "
                f"— known-red window EXPIRED on {kr.until_date} "
                f"(issue: {kr.until_issue_link}); the valve has CLOSED and this "
                f"red now fails the run.",
                file=out,
            )
            exit_code = 1
        else:
            print(
                f"[BLOCKED (known-red, expires {kr.until_date})] {probe.feature}: "
                f"{result.reason} ({result.failure_mode}) — intentionally red until "
                f"{kr.until_issue_link} lands. NOT failing the run (escape valve).",
                file=out,
            )
    return exit_code


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.reachability.probe_runner",
        description=(
            "Run per-feature reachability probes that boot the app via the "
            "production create_app() factory and assert observable outcomes. "
            "Exit 1 on any BLOCKED probe outside an unexpired known-red window."
        ),
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Run only the probe with this id (e.g. --only flywheel).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List discovered probe ids + features and exit 0.",
    )
    args = parser.parse_args(argv)

    probes = discover_probes()
    if args.only:
        probes = [p for p in probes if p.id == args.only]
        if not probes:
            print(
                f"reachability: no probe with id {args.only!r} "
                f"(discovered: {[p.id for p in discover_probes()]})",
                file=sys.stderr,
            )
            return 2

    if args.list:
        for p in probes:
            print(f"{p.id}\t{p.feature}")
        return 0

    if not probes:
        print(
            "reachability: no probes discovered under tools/reachability/probes/",
            file=sys.stderr,
        )
        return 2

    known_red = load_known_red()
    return run_probes(probes, known_red)


if __name__ == "__main__":
    # ``python -m tools.reachability.probe_runner`` runs THIS file as the
    # module named ``__main__``. The probe modules, however, ``from
    # tools.reachability.probe_runner import Probe`` — a SECOND, distinct
    # module object — so ``__main__.Probe`` and
    # ``tools.reachability.probe_runner.Probe`` are different classes and
    # discovery's ``isinstance(probe, Probe)`` would be False, silently
    # finding zero probes (verified SPR-01). Delegate to the CANONICAL module
    # so every ``Probe`` identity is the same one the probes import against.
    # (sys.path was already primed with the package root at module top.)
    from tools.reachability.probe_runner import main as _canonical_main

    raise SystemExit(_canonical_main())
