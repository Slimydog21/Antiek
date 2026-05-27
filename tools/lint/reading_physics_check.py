#!/usr/bin/env python3
"""Augmentation-boundary lint — enforce the Physics of Reading invariants
(PR-1 / PR-2 / PR-3 / PR-6 / PR-8) on every reading augmentation.

PR-8 is enforced by a POSITIVE import-allowlist (the canon's §7 pattern 6
"the single check that makes PR-8 true"): every external import in an
augmentation module must resolve to the allowlisted set — the facet API barrel,
the substrate read API, React, and (when a real augmentation needs them)
design-token/Lemon primitives. The negative patterns below (PR-1/2/3/6) catch
specific smells; the allowlist catches *everything else* an augmentation reaches
for, which is what proves the augmentation was authorable from the contract
alone.

THE KEYSTONE OF SPR-03. The Physics of Reading
(``docs/philosophy/physics-of-reading.md``) makes Antiek's reading
augmentations composable by having each *declare* contributions into named
facets the surface combines (the CodeMirror pattern). PR-2 — "substrate-owned
data, no side store" — is the invariant the operator chose to make **binding
like DuckDB single-writer**: an augmentation's data lives in the substrate,
visible to every other augmentation, never in a private store. Without
enforcement that is merely aspirational; across many future *agent-authored*
augmentations (SPR-08) a code reviewer will miss a smuggled store. This guard
makes the boundary mechanical: an augmentation that keeps a private store,
mutates the surface, imports a sibling augmentation, imports a substrate
WRITE path, or imports anything outside the PR-8 allowlist fails the build.

This is modeled on ``tools/lint/boundary_check.py`` (the substrate/dispatch
vendor-SDK lint): same repo-root resolution, same ``path:line: message``
output, same exit-code contract (0 clean / 1 violation). It scans the
augmentations directory the Physics slice established
(``apps/reading/src/reading-physics/augmentations/``) plus the facet modules
(``.../facets/``); both are "augmentation surface" the boundary covers.

────────────────────────────────────────────────────────────────────────────
ADVISORY vs BLOCKING (rollout discipline + canon ratification)
────────────────────────────────────────────────────────────────────────────
Per the standing CI discipline (informational-then-blocking) AND the canon's
own §7 instruction, the guard's blocking-ness is gated TWO ways:

  1. The canon front-matter ``status:`` — the guard reads
     ``docs/philosophy/physics-of-reading.md``'s YAML front-matter. While it
     reads ``status: draft`` the guard is **advisory** (warn, exit 0) no matter
     what it finds, because PR-1…PR-8 are not yet binding canon. It only
     **blocks** (exit 1 on a violation) once an operator sets
     ``status: ratified``.
  2. ``--enforce`` — even once ratified, the first CI PR runs the guard
     advisory (no flag) so the team sees findings on the real tree without a
     surprise red gate; a follow-up PR adds ``--enforce`` to flip it blocking.

So: blocking requires BOTH ``status: ratified`` AND ``--enforce``. Either alone
keeps the guard advisory. This is the honest, reversible rollout the canon §7
and ``docs/decisions/ci-informational-gates.md`` prescribe.

────────────────────────────────────────────────────────────────────────────
WHAT THIS GUARD CANNOT CATCH (intellectual honesty — rigor #1)
────────────────────────────────────────────────────────────────────────────
A static text/line scan is NOT airtight, and this docstring refuses to pretend
otherwise. The following evasions are out of reach and are owned by code review
(see ``docs/philosophy/physics-of-reading.md`` §9 open questions 1 and 1b):

  - **Dynamic import** — ``await import(someVar)`` / ``require(x)`` where the
    target is computed at runtime: there is no literal module string to match.
    (This is also the one blind spot of the PR-8 import-allowlist below: it
    gates every *static* import specifier, but a computed dynamic import has no
    specifier to resolve, so a dynamic pull of a non-allowlisted module is
    review-owned.)
  - **Indirection through a shared util** — an augmentation that calls a
    pure-looking helper which itself holds a module-level mutable singleton or
    writes ``localStorage``. The guard scans the augmentation file, not its
    transitive call graph; a store hidden one hop away in ``../../lib/foo`` is
    invisible here.
  - **Module-level mutable singleton** — ``let cache = new Map()`` at module
    scope used as a store of record. It uses no banned identifier, so nothing
    matches. (A reviewer asks "is this reconstructible from the substrate?")
  - **Write through React context / a prop callback** — an augmentation handed
    a setter and calling it to persist. No banned token appears.
  - **PR-6 §7-pattern-5b: substrate-verdict recompute** — re-implementing a
    servability verdict / rubric score / attribution share locally instead of
    reading the substrate's. This is *arbitrary arithmetic* with no import or
    call signature to match; it is **not statically detectable** and is
    explicitly advisory / review-owned (canon §7 5b, §9 OQ 1b). The IMPORT half
    of PR-6 (importing a substrate write path) IS caught — that has a signature.
  - **PR-7 anti-purgatory** — "did this ship into the production surface, not a
    prototype reader?" is partly a product judgment. The guard emits an
    advisory grep for ``*Prototype*``/``*Playground*`` reader imports; it never
    blocks on PR-7 (canon §7, §9 OQ 1).

Everything in ``BLOCKING PATTERNS`` below has a concrete literal signature a
scan can match, and the ``PR-8 IMPORT ALLOWLIST`` below is a concrete static
check (resolve every import specifier; fail anything outside the allowed set).
Nothing else is claimed as mechanically enforced — in particular PR-6's 5b
recompute and PR-7 above remain advisory / review-owned, because neither has any
import or call signature to gate.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Repo-root resolution mirrors boundary_check.py: this file is at
# <repo>/tools/lint/reading_physics_check.py.
_REPO = Path(__file__).resolve().parent.parent.parent
_PHYSICS_DIR = _REPO / "apps" / "reading" / "src" / "reading-physics"
_AUG_DIR = _PHYSICS_DIR / "augmentations"
_FACET_DIR = _PHYSICS_DIR / "facets"
_CANON = _REPO / "docs" / "philosophy" / "physics-of-reading.md"
# The substrate read API the canon names (apps/reading/src/lib/api.ts). An
# augmentation receives it via ctx.substrate, so a direct import is NOT expected
# (the real augmentations don't import it) — but the canon allows it, so the
# allowlist resolves a relative specifier pointing here as ALLOWED.
_SUBSTRATE_READ_API = _REPO / "apps" / "reading" / "src" / "lib" / "api"

# The augmentations directory itself, expressed as the import substring an
# augmentation-to-augmentation import would contain (PR-3, pattern 3).
_AUG_IMPORT_MARKER = "augmentations/"

# ── PR-8 positive import-allowlist ─────────────────────────────────────────
#
# Canon §7 pattern 6 ("the single check that makes PR-8 true"): an augmentation
# module's external imports must be a subset of
#   { the facet API barrel, the substrate read API, React,
#     the design-token/Lemon primitives, pure util modules }.
# Anything outside the allowlist fails (PR-8). This is the POSITIVE complement
# of the negative PR-1/2/3/6 patterns: PR-3 forbids a *sibling augmentation*
# import; the allowlist additionally forbids ANY non-allowlisted module (e.g.
# `lodash`, `chart.js`, `date-fns`), which is what proves the augmentation was
# authorable from the contract alone.
#
# Bare (non-relative) specifiers permitted by exact name or by a "<pkg>/…"
# prefix. Derived from canon §7 pattern 6 AND from what the REAL shipped
# augmentations need: servability.ts and ip-holder.ts import ONLY `../types`
# (a relative facet-barrel import resolved below), so the bare set is held to
# the canon-named members and NOT widened speculatively.
_ALLOWED_BARE_EXACT = {
    "react",  # React (types only) — canon §7 pattern 6.
    "react/jsx-runtime",
}
# A canon-named member is included as an exact/prefix entry the moment a REAL
# augmentation imports it; the design-token/Lemon primitives (canon §7) are NOT
# yet imported by any shipped augmentation, so they are intentionally left OUT
# of the active set (no speculative pre-allow). When servability.ts / ip-holder.ts
# (or a future real augmentation) imports e.g. `@/lemon` or a design-token
# module, add its exact name / prefix here and note it in the decision doc.


def _is_relative(spec: str) -> bool:
    return spec.startswith(".")


def _resolves_into_physics(py: Path, spec: str) -> bool:
    """True iff a RELATIVE ``spec`` from module ``py`` resolves to a path inside
    the reading-physics tree (the facet API barrel: types / facet / facets/* /
    registry, or another physics module). PR-3 separately rejects a *sibling
    augmentation* resolution; the allowlist treats every other in-physics
    resolution (types, facet, registry, facets/*) as the facet API — allowed."""
    if not _is_relative(spec):
        return False
    try:
        resolved = (py.parent / spec).resolve()
        physics = _PHYSICS_DIR.resolve()
    except OSError:
        return False
    return physics == resolved.parent or physics in resolved.parents


def _resolves_to_substrate_read_api(py: Path, spec: str) -> bool:
    """True iff a RELATIVE ``spec`` resolves to the canon-named substrate read
    API module (apps/reading/src/lib/api)."""
    if not _is_relative(spec):
        return False
    try:
        return (py.parent / spec).resolve() == _SUBSTRATE_READ_API.resolve()
    except OSError:
        return False


def _is_allowed_import(py: Path, spec: str) -> bool:
    """PR-8 allowlist membership for one import specifier in module ``py``."""
    # Bare specifiers: exact match or "<allowed>/…" subpath.
    if not _is_relative(spec):
        if spec in _ALLOWED_BARE_EXACT:
            return True
        return any(spec.startswith(p + "/") for p in _ALLOWED_BARE_EXACT)
    # Relative specifiers: the facet API barrel / another physics module, OR the
    # substrate read API. (A sibling-augmentation relative import resolves into
    # physics and so passes the allowlist here — PR-3 is the check that rejects
    # it; the two checks are complementary and both run.)
    return _resolves_into_physics(py, spec) or _resolves_to_substrate_read_api(py, spec)


# ── Front-matter status (advisory while draft) ────────────────────────────


def canon_status() -> str:
    """Read the canon's YAML front-matter ``status:`` (``draft`` | ``ratified``).
    Defaults to ``draft`` (advisory) when the canon or the key is missing — the
    safe default is never to block against canon we can't confirm is ratified."""
    try:
        text = _CANON.read_text(encoding="utf-8")
    except OSError:
        return "draft"
    # Front-matter is a leading --- … --- block.
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return "draft"
    status = re.search(r"^status:\s*(\S+)", m.group(1), re.MULTILINE)
    return status.group(1).strip() if status else "draft"


# ── Comment stripping (so a banned token in a comment/README isn't a hit) ──


def _strip_comments(src: str) -> list[tuple[int, str]]:
    """Return (1-based line number, code-only line) pairs, with ``//`` line
    comments and ``/* … */`` block comments blanked out. A coarse but adequate
    stripper: it does not parse strings, so a banned token inside a string
    literal would still match — which is the conservative direction (a guard
    that over-reports a string is safer than one that under-reports a store).
    The escape-comment check runs against the RAW line, so ``// PR-2 escape:``
    still suppresses correctly."""
    out: list[tuple[int, str]] = []
    in_block = False
    for i, raw in enumerate(src.splitlines(), start=1):
        line = raw
        if in_block:
            end = line.find("*/")
            if end == -1:
                out.append((i, ""))
                continue
            line = line[end + 2 :]
            in_block = False
        # Remove inline /* … */ runs that open and close on one line.
        line = re.sub(r"/\*.*?\*/", "", line)
        # Open block comment with no close on this line.
        open_block = line.find("/*")
        if open_block != -1:
            line = line[:open_block]
            in_block = True
        # Line comment.
        slash = line.find("//")
        if slash != -1:
            line = line[:slash]
        out.append((i, line))
    return out


# ── BLOCKING PATTERNS — each has a concrete literal signature ──────────────
#
# (group, compiled regex, human message). Each maps to a canon invariant. The
# regexes match the CODE-ONLY line (comments stripped). A line carrying a
# ``// PR-2 escape:`` comment (checked against the raw line) is exempt from the
# PR-2 persistence patterns only (the bounded view-only/ephemeral cache).

# PR-2 — non-substrate persistence. Importing or referencing a store.
_PERSISTENCE = re.compile(
    r"\b(localStorage|sessionStorage|indexedDB|window\.localStorage)\b"
)
# A persistence/store CLIENT import (a SQL/KV/state-store library, an idb
# wrapper, a generic "Store"/"persist" import). Conservative allowlist by name.
_STORE_IMPORT = re.compile(
    r"""import\s+.*\bfrom\s+["']"""
    r"""([^"']*\b(?:localforage|idb|dexie|zustand|jotai|redux|"""
    r"""@?\w*store\w*|persist|pouchdb|lowdb)\b[^"']*)["']""",
    re.IGNORECASE,
)
# A non-substrate network fetch used as a store-of-record (fetch/axios/XHR).
_NETWORK = re.compile(r"\b(fetch|axios|XMLHttpRequest)\s*\(")

# PR-1 — DOM / sibling mutation. The augmentation acts on the DOM.
_DOM_MUTATION = re.compile(
    r"""(\.innerHTML\s*=|\.outerHTML\s*=|\.appendChild\s*\(|"""
    r"""\.insertBefore\s*\(|\.removeChild\s*\(|\.replaceChild\s*\(|"""
    r"""\.classList\.(?:add|remove|toggle)\s*\(|"""
    r"""document\.(?:querySelector|getElementById|getElementsBy\w+)\s*\(|"""
    r"""createPortal\s*\()"""
)

# PR-4 / PR-5 — pixel anchoring. The augmentation measures geometry.
_PIXEL = re.compile(
    r"""\b(getBoundingClientRect|offsetTop|offsetLeft|offsetWidth|"""
    r"""offsetHeight|scrollTop|window\.innerWidth|window\.innerHeight|"""
    r"""matchMedia)\b"""
)

# PR-6 — substrate WRITE path import (the detectable half; 5b recompute is not).
# A db_lock / event-append / POST-mutation client import. Conservative.
_WRITE_PATH = re.compile(
    r"""import\s+.*\bfrom\s+["']([^"']*\b(?:db_lock|event_log|eventLog|"""
    r"""append_event|appendEvent|writeEvent|mutation|dispatch/write)\b[^"']*)["']""",
    re.IGNORECASE,
)


def _is_sibling_augmentation_import(py: Path, target: str) -> bool:
    """True iff ``target`` (an import specifier in module ``py``) resolves to a
    DIFFERENT module inside the augmentations directory. Self-imports, the facet
    API (types.ts / facet.ts / facets/*), and the substrate read API are fine —
    only importing a SIBLING augmentation breaks PR-3. Handles relative
    specifiers (``./x``, ``../augmentations/x``) by resolving against the
    importing file's directory; non-relative specifiers fall back to the
    ``augmentations/`` path marker."""
    if target.startswith("."):
        # Resolve the relative specifier against the importing file's directory.
        resolved = (py.parent / target).resolve()
        try:
            inside_aug = _AUG_DIR.resolve() in resolved.parents or resolved.parent == _AUG_DIR.resolve()
        except OSError:
            inside_aug = False
        if not inside_aug:
            return False
        # Same module (any extension) is a self-import — allowed.
        return resolved.stem != py.stem
    # Non-relative: only an explicit augmentations/ path counts.
    return _AUG_IMPORT_MARKER in target


def _is_augmentation_module(py: Path) -> bool:
    name = py.name
    if name == "README.md":
        return False
    if re.search(r"\.(test|spec|stories)\.tsx?$", name):
        return False
    return name.endswith(".ts") or name.endswith(".tsx")


def _is_in_augmentations(py: Path) -> bool:
    """True iff ``py`` lives under the augmentations directory (where the PR-8
    import-allowlist applies). Facet modules under ``.../facets/`` are covered by
    the negative PR-1/2/3/6 patterns but NOT by the augmentation allowlist —
    facets legitimately import more (the combine machinery)."""
    try:
        aug = _AUG_DIR.resolve()
        return aug == py.resolve().parent or aug in py.resolve().parents
    except OSError:
        return False


def _scan_file(py: Path) -> list[str]:
    rel = py.relative_to(_REPO)
    try:
        raw = py.read_text(encoding="utf-8")
    except OSError:
        return []
    raw_lines = raw.splitlines()
    is_aug = _is_in_augmentations(py)
    violations: list[str] = []
    for lineno, code in _strip_comments(raw):
        if not code.strip():
            continue
        raw_line = raw_lines[lineno - 1] if lineno - 1 < len(raw_lines) else ""
        has_escape = "// PR-2 escape:" in raw_line

        # PR-2 — persistence (escape-comment exempt).
        if not has_escape:
            if _PERSISTENCE.search(code):
                violations.append(
                    f"{rel}:{lineno}: PR-2 — writes/reads a non-substrate store "
                    f"(localStorage/sessionStorage/indexedDB). Augmentation data "
                    f"lives in the substrate. (// PR-2 escape: exempts a bounded "
                    f"view-only cache.)"
                )
            elif _STORE_IMPORT.search(code):
                m = _STORE_IMPORT.search(code)
                violations.append(
                    f"{rel}:{lineno}: PR-2 — imports a persistence/store client "
                    f"'{m.group(1)}'. Use the substrate read API. (// PR-2 escape:)"
                )
            elif _NETWORK.search(code):
                violations.append(
                    f"{rel}:{lineno}: PR-2 — calls fetch/axios/XHR directly. An "
                    f"augmentation reads the substrate via ctx.substrate, not a "
                    f"non-substrate origin. (// PR-2 escape: for a known-safe read.)"
                )

        # PR-1 — DOM / sibling mutation (no escape; an augmentation never acts).
        if _DOM_MUTATION.search(code):
            violations.append(
                f"{rel}:{lineno}: PR-1 — mutates the DOM directly. An augmentation "
                f"DECLARES into a facet; the surface enacts."
            )

        # PR-4/PR-5 — pixel anchoring.
        if _PIXEL.search(code):
            violations.append(
                f"{rel}:{lineno}: PR-4/PR-5 — reads pixel geometry to position "
                f"itself. Anchors are semantic; the layout-map resolves pixels."
            )

        # PR-6 — substrate write-path import (detectable half).
        wm = _WRITE_PATH.search(code)
        if wm:
            violations.append(
                f"{rel}:{lineno}: PR-6 — imports a substrate WRITE path "
                f"'{wm.group(1)}'. The physics reads; it never writes the substrate."
            )

        # PR-3 — augmentation-to-augmentation import. An import whose path
        # RESOLVES into the augmentations directory, from a DIFFERENT
        # augmentation module. Two shapes: an absolute-ish path containing
        # "augmentations/", OR a relative "./sibling" / "../augmentations/x"
        # that resolves (relative to THIS file's directory) into _AUG_DIR.
        im = re.search(r"""\bfrom\s+["']([^"']+)["']""", code)
        if im and _is_sibling_augmentation_import(py, im.group(1)):
            violations.append(
                f"{rel}:{lineno}: PR-3 — imports another augmentation "
                f"('{im.group(1)}'). Augmentations couple ONLY through named "
                f"facets, never by importing a sibling."
            )

        # PR-8 — positive import-allowlist (augmentation modules only; canon §7
        # pattern 6 "the single check that makes PR-8 true"). Every import
        # specifier — `… from "x"` AND a side-effect `import "x"` — must resolve
        # to the allowed set { facet API barrel, substrate read API, React,
        # design-token/Lemon primitives }. Anything else fails: an augmentation
        # reaching for `lodash`/`chart.js`/`date-fns`/etc. was NOT authorable
        # from the contract alone. (Dynamic `import(expr)` has no literal
        # specifier and stays review-owned, per the CANNOT-catch list.)
        if is_aug:
            spec_m = im or re.search(r"""\bimport\s+["']([^"']+)["']""", code)
            if spec_m:
                spec = spec_m.group(1)
                if not _is_allowed_import(py, spec):
                    violations.append(
                        f"{rel}:{lineno}: PR-8 — imports '{spec}', which is "
                        f"outside the augmentation allowlist (facet API barrel, "
                        f"substrate read API, React, design-token/Lemon "
                        f"primitives). An augmentation must be authorable from "
                        f"the facet contract alone (canon §7 pattern 6)."
                    )

    return violations


def _advisory_prototype_grep() -> list[str]:
    """PR-7 anti-purgatory — ADVISORY only (never blocks). Grep for an
    augmentation importing a *Prototype*/*Playground* reader. Reported as a
    warning regardless of enforce/ratified state, per canon §7."""
    warnings: list[str] = []
    if not _AUG_DIR.exists():
        return warnings
    pat = re.compile(r"""import\s+.*\bfrom\s+["'][^"']*(Prototype|Playground)[^"']*["']""")
    for py in sorted(_AUG_DIR.rglob("*")):
        if not py.is_file() or not _is_augmentation_module(py):
            continue
        for lineno, code in _strip_comments(py.read_text(encoding="utf-8")):
            if pat.search(code):
                warnings.append(
                    f"{py.relative_to(_REPO)}:{lineno}: PR-7 (advisory) — imports a "
                    f"Prototype/Playground reader. Augmentations ship into the "
                    f"production surface (review-owned; not blocking)."
                )
    return warnings


def find_violations() -> list[str]:
    out: list[str] = []
    for base in (_AUG_DIR, _FACET_DIR):
        if not base.exists():
            continue
        for py in sorted(base.rglob("*")):
            if py.is_file() and _is_augmentation_module(py):
                out.extend(_scan_file(py))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Block (exit 1) on a violation. Without it the guard is advisory "
        "(warn, exit 0). Blocking ALSO requires the canon front-matter to read "
        "status: ratified.",
    )
    args = parser.parse_args(argv)

    status = canon_status()
    violations = find_violations()
    warnings = _advisory_prototype_grep()

    # PR-7 advisory grep — always informational.
    for w in warnings:
        print(f"  [advisory] {w}")

    # Blocking requires BOTH a ratified canon AND --enforce.
    blocking = args.enforce and status == "ratified"

    if violations:
        header = (
            "Augmentation-boundary violations (BLOCKING):"
            if blocking
            else "Augmentation-boundary findings (ADVISORY — not blocking):"
        )
        print(header)
        for line in violations:
            print(f"  {line}")
        print(
            "\nThe Physics of Reading invariants (docs/philosophy/"
            "physics-of-reading.md §1, §7) require: an augmentation DECLARES "
            "into named facets (PR-1), keeps no side store (PR-2), imports no "
            "sibling augmentation (PR-3), and never writes the substrate (PR-6)."
        )
        if not blocking:
            reason = (
                f"canon status is '{status}' (not 'ratified')"
                if status != "ratified"
                else "--enforce not set (first-PR advisory rollout)"
            )
            print(f"Advisory because {reason}; exiting 0. See §7 rollout.")
            return 0
        return 1

    print(
        f"OK: no augmentation-boundary violations "
        f"(canon status: {status}; mode: {'blocking' if blocking else 'advisory'})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
