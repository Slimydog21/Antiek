#!/usr/bin/env python3
"""Read-surface reachability probe — Antiek Convergence SPR-04 (M5).

The SPR-01 runner's other probes boot the Python ``create_app()`` factory and
assert a backend OUTCOME. The Read surface is a Vite/React SPA under
``apps/reading/`` — there is no Python factory to boot, and a full headless
browser render of the production bundle is not available in this CI env (no
Playwright server, no chromium download on the box; see the CAVEAT below).
So this probe asserts the most pragmatic OUTCOME the environment supports
WITHOUT degrading to "the component file exists":

  it parses the SPA's actual ROUTE TABLE + SHELL MOUNT + the live reading
  variant out of source, and asserts the canonical reading shell is WIRED
  the way a user reaches it:

    1. ``apps/reading/src/App.tsx`` registers a route whose ``path`` is the
       canonical ``/read/:documentId`` AND whose ``element`` is the
       ``BookReader`` component (``modes/Reading``). A route that 404'd or
       pointed at a different element would FAIL this — it is the SPA analogue
       of the backend probe's "route resolves to the real entrypoint".
    2. ``apps/reading/src/AppShell.tsx`` MOUNTS the canonical Werner reading
       shell — both ``<WernerIceCursorShell />`` and ``<PenguinMascot />`` —
       so the shell floats over every route (not merely imported, but rendered
       in the shell's JSX). An imported-but-never-mounted shell is the exact
       "dormancy" / "brick no one can pick up" failure this gate exists to kill.
    3. ``apps/reading/src/werner/iceFishingFlags.ts`` makes ICE-FISHING the
       LIVE variant: ``wernerIceFishingCursor`` defaults to ON (it is only off
       when ``VITE_WERNER_ICE_FISHING === "0"``). This is the SPR-04 convergence
       outcome: #54's ice-fishing is the canonical Werner shell, not a
       cursor-pursuit fork that removed it.

Why this is an OUTCOME and not a file-presence check (rigor #3):
  - It does NOT assert ``os.path.exists(...)`` on any component.
  - It asserts the route's ``path``+``element`` BINDING, the shell's JSX
    MOUNT, and the flag's DEFAULT POLARITY. Delete the ``<Route
    path="/read/:documentId" .../>`` line, or the ``<WernerIceCursorShell />``
    mount, or flip the flag default, and this probe goes RED — which is the
    teeth demonstrated in the SPR-04 handoff (momentary-removal → RED →
    restore → GREEN).
  - The DEEPER render outcome (BookReader actually renders Attribution +
    TocPanel + the float-menu without a TypeError) is asserted by the vitest
    suite ``apps/reading/src/modes/Reading/Reading.test.tsx`` (27 tests),
    which runs under ``npm test`` / the build's typecheck. This probe is the
    BLOCKING route/mount/variant assertion that complements that render test
    inside the SPR-01 gate.

CAVEAT (rigor #1, honest downgrade): this is the SOURCE-ROUTE-TABLE form of
the probe, not a built-bundle headless render. A full-render probe would boot
the emitted ``dist/`` SPA in a headless browser, navigate to ``/read/<id>``,
and assert the reading column + Attribution paint — catching a route that is
present in source but tree-shaken out of the bundle, or a render that throws
at runtime. What would unblock it: a Playwright/chromium harness available in
CI (``apps/reading`` already declares ``@playwright/test`` and an ``e2e``
script; the chromium binary is not installed on this box). Until then the
render-throw failure mode is covered by ``Reading.test.tsx`` (jsdom render),
and tree-shaking of a top-level ``<Route>`` is not a real risk (it is
unconditionally referenced from the router). The source-route assertion below
is the strongest BLOCKING form this environment supports.
"""

from __future__ import annotations

import os
import re

from tools.reachability.probe_runner import ProbeResult

# Repo root = three levels up from this file (probes/ -> reachability/ -> tools/ -> root).
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_APP_TSX = os.path.join(_REPO_ROOT, "apps", "reading", "src", "App.tsx")
_APPSHELL_TSX = os.path.join(_REPO_ROOT, "apps", "reading", "src", "AppShell.tsx")
_ICE_FLAGS_TS = os.path.join(
    _REPO_ROOT, "apps", "reading", "src", "werner", "iceFishingFlags.ts"
)

# The canonical Read route binding. Matches:
#   <Route path="/read/:documentId" element={<BookReader />} />
# Tolerant of attribute order + whitespace, but PINS both the path AND that the
# element is BookReader — a route that pointed elsewhere would not match.
_READ_ROUTE_RE = re.compile(
    r'<Route\b[^>]*\bpath\s*=\s*"(?:/read/:documentId)"[^>]*\belement\s*=\s*\{\s*<\s*BookReader\b'
)
# Tolerate the reverse attribute order (element before path) too.
_READ_ROUTE_RE_ALT = re.compile(
    r'<Route\b[^>]*\belement\s*=\s*\{\s*<\s*BookReader\b[^>]*\bpath\s*=\s*"(?:/read/:documentId)"'
)
# BookReader must be the default import of modes/Reading (the canonical reader).
_BOOKREADER_IMPORT_RE = re.compile(
    r'import\s+BookReader\s+from\s+"\./modes/Reading"'
)

# The canonical Werner reading shell must be MOUNTED in AppShell's JSX (not just
# imported). Both the floating mascot and the ice-cursor shell.
_PENGUIN_MOUNT_RE = re.compile(r"<\s*PenguinMascot\s*/?\s*>")
_ICESHELL_MOUNT_RE = re.compile(r"<\s*WernerIceCursorShell\s*/?\s*>")

# Ice-fishing is the LIVE variant: the flag defaults ON (only off when the env
# var is exactly "0"). A fork that hard-disabled ice-fishing (e.g. `= false`)
# would fail this.
_ICE_DEFAULT_ON_RE = re.compile(
    r"wernerIceFishingCursor\s*=\s*\n?\s*import\.meta\.env\.VITE_WERNER_ICE_FISHING\s*!==\s*\"0\""
)


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _probe() -> ProbeResult:
    app = _read(_APP_TSX)
    if app is None:
        return ProbeResult(
            ok=False,
            reason=f"App.tsx not found at {_APP_TSX} — the SPA route table moved",
            failure_mode="route_404",
        )
    shell = _read(_APPSHELL_TSX)
    if shell is None:
        return ProbeResult(
            ok=False,
            reason=f"AppShell.tsx not found at {_APPSHELL_TSX} — the reading shell moved",
            failure_mode="route_404",
        )
    flags = _read(_ICE_FLAGS_TS)
    if flags is None:
        return ProbeResult(
            ok=False,
            reason=f"iceFishingFlags.ts not found at {_ICE_FLAGS_TS}",
            failure_mode="route_404",
        )

    # 1. canonical /read/:documentId route bound to BookReader.
    route_ok = bool(_READ_ROUTE_RE.search(app) or _READ_ROUTE_RE_ALT.search(app))
    if not route_ok:
        return ProbeResult(
            ok=False,
            reason=(
                'no <Route path="/read/:documentId" element={<BookReader …}> in '
                "App.tsx — the canonical reader route is unmounted (a user cannot "
                "navigate to a book)"
            ),
            failure_mode="feature_dead",
        )
    if not _BOOKREADER_IMPORT_RE.search(app):
        return ProbeResult(
            ok=False,
            reason=(
                'BookReader is no longer the default import of "./modes/Reading" '
                "in App.tsx — the /read route may resolve to a different reader"
            ),
            failure_mode="feature_dead",
        )

    # 2. the canonical Werner reading shell is MOUNTED in AppShell's JSX.
    if not _PENGUIN_MOUNT_RE.search(shell):
        return ProbeResult(
            ok=False,
            reason=(
                "<PenguinMascot /> is not mounted in AppShell.tsx — the canonical "
                "reading-shell mascot is imported-but-dormant (no surface renders it)"
            ),
            failure_mode="feature_dead",
        )
    if not _ICESHELL_MOUNT_RE.search(shell):
        return ProbeResult(
            ok=False,
            reason=(
                "<WernerIceCursorShell /> is not mounted in AppShell.tsx — the "
                "canonical ice-fishing shell is unmounted (#54's shell is dormant)"
            ),
            failure_mode="feature_dead",
        )

    # 3. ice-fishing is the LIVE variant (flag defaults ON).
    if not _ICE_DEFAULT_ON_RE.search(flags):
        return ProbeResult(
            ok=False,
            reason=(
                "wernerIceFishingCursor no longer defaults ON in iceFishingFlags.ts "
                "— ice-fishing is not the live Werner variant (a cursor-pursuit fork "
                "may have superseded #54's canonical ice-fishing shell)"
            ),
            failure_mode="feature_dead",
        )

    return ProbeResult(ok=True, failure_mode="reachable")


from tools.reachability.probe_runner import Probe  # noqa: E402

PROBE = Probe(
    id="read",
    feature="read surface (canonical /read/:documentId route + mounted ice-fishing Werner shell)",
    run=_probe,
)
