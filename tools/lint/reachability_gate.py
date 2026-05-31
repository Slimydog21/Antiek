#!/usr/bin/env python3
"""Reachability gate — flag reading-surface code that nothing can reach.

SPR-01 anti-purgatory keystone. The prior foundation died of a "stale-base
stranding/purgatory" failure: code that was authored, tested, and merged, then
never wired into a surface anyone could navigate to — dead weight that read as
"shipped" but reached no user. This gate makes the *static* half of that
failure mechanical, so a NEW stranding reds the build the moment it lands
rather than being discovered months later.

It flags two stranded shapes inside ``apps/reading/src/``:

  (a) AUGMENTATION modules under
      ``apps/reading/src/reading-physics/augmentations/`` with ZERO importers
      anywhere in ``apps/reading/src/``. An augmentation is a *declaration*
      (PR-1) consumed by the reader surface (e.g. MasterMdViewer.tsx) or, at
      minimum, exercised by a test. A module no source file imports at all
      is unreachable: it contributes to no surface and is covered by no test.

  (b) INTERFACE ROUTES — the ``<Route path="…">`` declarations in the central
      route registry (``apps/reading/src/App.tsx``) — whose static path has NO
      inbound navigation reference (``<Link to="…">`` / ``to="…"`` /
      ``href="…"`` / ``navigate("…")``) anywhere in ``apps/reading/src/``. A
      route nothing links to and nothing programmatically navigates to is a
      page you can only reach by typing the URL — the route-level form of
      purgatory.

Both findings are GRANDFATHERED through a dated, shrink-only baseline
(``tools/lints/baselines/reachability.json``) so the gate reds ONLY on code
that becomes unreachable AFTER this lands — never on the legitimately-dormant
set that exists TODAY. See the fairness note below.

The scan is scoped to the reading surface (``apps/reading/src/``) — the
augmentation + route checks above are the entire milestone. The SPR-01
seed-and-catch contract test mints an isolated reading-surface tree (its own
``apps/reading/src/`` with a ``.ts`` augmentation and an ``App.tsx``), seeds a
module nothing imports / a route nothing links to, and asserts the real gate
reds, then greens once it is wired in. The gate stays on the augmentation +
route surface and never enumerates the hundreds of legitimately-CLI-invoked
``.py`` scripts elsewhere in the repo.

Design (rigor #1 — honesty about scope):
  This is a NEW sibling to ``tools/lint/reading_physics_check.py`` rather than
  an extension of it. That guard is TS-augmentation-*boundary*-scoped
  (PR-1…PR-8: what an augmentation may import / store / mutate); it does not
  and should not own *route* reachability, which lives at the App.tsx routing
  layer outside the augmentation surface. One gate, one concern. This gate
  REUSES the augmentation-directory definition and the honest-scan posture of
  reading_physics_check.py, and REUSES the baseline machinery in
  ``tools/lints/baseline.py`` verbatim (it does not reinvent serialization).

────────────────────────────────────────────────────────────────────────────
WHAT THIS GATE CANNOT CATCH (intellectual honesty — mirrors
reading_physics_check.py's CANNOT-catch list; rigor #1)
────────────────────────────────────────────────────────────────────────────
A static text/AST scan is NOT airtight. This gate claims ONLY what its scan
literally matches; the rest is owned by code review.

  - **Dynamic import** — ``await import(someVar)`` / ``require(x)`` where the
    target module string is computed at runtime: there is no literal specifier
    to match, so a module reached ONLY through a computed import reads as
    unreachable here. Out of reach → review-owned.
  - **Computed / variable route navigation** — ``navigate(somePath)`` /
    ``to={pathVar}`` where the destination is a variable or template
    expression, and route paths assembled from constants. The scan matches a
    string literal that ``startsWith("/")``; a route reached only through a
    computed path reads as unreachable here. Out of reach → review-owned.
    The scan DOES see config-object nav — a ``to``/``path``/``route`` key with
    a string-literal destination, the shape most of this codebase's navigation
    is registered in (the SceneChrome scene registry, workflowTaxonomy, the
    CommandPalette facets, Map/index) — so those routes are correctly counted
    reachable rather than baselined. What survives in the baseline is the
    genuinely-uncatchable residue: a route whose destination is a *variable* or
    *template expression* at every reference site (e.g. assembled from a
    constant, or only reached via a programmatic redirect with a computed
    target). Grandfathering THOSE is the honest move — not pretending the scan
    saw a literal it never did.
  - **Shared-util / barrel indirection** — a module re-exported through an
    ``index.ts`` barrel and consumed transitively. The importer scan resolves
    the *direct* relative specifier; it does not chase a re-export chain. Out
    of reach → review-owned.
  - **"Imported only by its own test"** — the milestone's rule is literally
    "ZERO importers anywhere in apps/reading/src/", and a test file IS a source
    file under that tree, so a module imported solely by its own test counts as
    reachable HERE. Whether a *tested-but-never-surface-wired* augmentation has
    actually shipped to the production reader is a product judgment (the PR-7
    anti-purgatory question), which reading_physics_check.py keeps ADVISORY /
    review-owned. This gate deliberately inherits that line: it gates the
    falsifiable "zero importers" floor and leaves "did it reach the real
    surface" to review.

Everything in the FINDING shapes above has a concrete literal signature the
scan matches (a relative import specifier resolving to the module; a route
path string; an inbound nav literal). Nothing else is claimed as mechanically
enforced.

────────────────────────────────────────────────────────────────────────────
FAIRNESS — why a HARD gate is defensible here (fairness #2)
────────────────────────────────────────────────────────────────────────────
Steelman for keeping this advisory: a hard reachability gate reds on
legitimately-dormant code — a feature behind a flag, a route not yet linked,
scaffolding landed ahead of its wiring — and that churn trains the reflexive
``--write-baseline`` muscle that defeats the gate.

Rebuttal, baked into the design: the dated SHRINK-ONLY baseline grandfathers
everything unreachable TODAY. The gate therefore reds ONLY on code that
becomes unreachable AFTER this lands — i.e. a NEW stranding. Landing
scaffolding ahead of its wiring in the same PR that adds the gate is already
grandfathered; landing it AFTER is exactly the failure this gate exists to
catch, and the fix is to add the one link/importer that makes it reachable —
not to re-baseline. The baseline can only shrink (operator refreshes when a
stranding is fixed), so the grandfathered set is a debt that pays down, never
a hiding place that grows.

Exit 0 = clean (every current finding is grandfathered); exit 1 = a NEW
unreachable module/route, printed as ``path:line: message``.

Usage::

    python tools/lint/reachability_gate.py                 # enforce
    python tools/lint/reachability_gate.py --write-baseline # re-capture (operator)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Repo-root resolution mirrors tools/lint/boundary_check.py:28 exactly: this
# file is at <repo>/tools/lint/reachability_gate.py.
_REPO = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO / "apps" / "reading" / "src"
_PHYSICS_DIR = _SRC / "reading-physics"
_AUG_DIR = _PHYSICS_DIR / "augmentations"
_APP_TSX = _SRC / "App.tsx"

_BASELINE = _REPO / "tools" / "lints" / "baselines" / "reachability.json"
_LINT_NAME = "reachability_gate"

# Source-file extensions we treat as TS/TSX modules.
_TS_EXTS = (".ts", ".tsx")

# CI invokes us as a script (`python tools/lint/reachability_gate.py`, per
# .github/workflows/ci.yml), which does NOT put the repo root on sys.path —
# so the `tools.lints.baseline` package import below would fail. Add the repo
# root to sys.path (idempotently) so both script-mode and `-m tools.lint…`
# invocation resolve the shared baseline machinery. We REUSE that machinery
# (diligence #4) rather than reinventing serialization.
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.lints.baseline import (  # noqa: E402  (after sys.path bootstrap)
    ViolationKey,
    compute_keys,
    filter_to_new_only,
    find_stale_baseline_entries,
    load_baseline,
    write_baseline,
)

# ── Augmentation-module identification ──────────────────────────────────────
#
# Mirrors reading_physics_check.py's notion of an "augmentation module": a
# top-level ``.ts`` under augmentations/ that is real source — NOT a test, NOT
# the authoring ``_template.ts``, NOT a ``.d.ts`` declaration, NOT a non-source
# file (README.md). The ``marginalia/`` subdirectory holds composed-augmentation
# source too; we scan the directory recursively for source modules but exclude
# tests/templates the same way.


def _is_augmentation_module(p: Path) -> bool:
    if not p.is_file() or p.suffix != ".ts":
        return False
    name = p.name
    if name.startswith("_"):  # _template.ts and any future scaffolding helper
        return False
    if name.endswith(".d.ts"):
        return False
    # Tests (.test.ts) and composition tests (.compose.test.ts) are not
    # augmentations; they are the things that IMPORT augmentations.
    if ".test." in name or ".compose." in name:
        return False
    return True


def _augmentation_modules() -> list[Path]:
    if not _AUG_DIR.exists():
        return []
    return sorted(p for p in _AUG_DIR.rglob("*") if _is_augmentation_module(p))


# ── Import-specifier extraction ─────────────────────────────────────────────
#
# Match the specifier of a static `import … from "X"`, a side-effect
# `import "X"`, an `export … from "X"` re-export, and a `require("X")`. We
# capture the literal string only; a dynamic `import(expr)` with a non-literal
# argument has no specifier and is intentionally NOT matched (CANNOT-catch
# list above — review-owned).
_IMPORT_RE = re.compile(
    r"""
    (?:from|import|require)      # from / import / require keyword
    \s*\(?\s*                    # optional ( for require()/import()
    ["']([^"']+)["']             # the quoted specifier
    """,
    re.VERBOSE,
)


def _iter_src_modules() -> list[Path]:
    """Every TS/TSX source file under apps/reading/src/ (the universe of
    possible importers / nav-reference holders). Skips node_modules just in
    case a vendored copy ever lands under src/."""
    if not _SRC.exists():
        return []
    out: list[Path] = []
    for p in _SRC.rglob("*"):
        if not p.is_file() or p.suffix not in _TS_EXTS:
            continue
        if "node_modules" in p.parts:
            continue
        out.append(p)
    return sorted(out)


def _imports_module(importer: Path, importer_text: str, target: Path) -> bool:
    """True iff ``importer`` has a RELATIVE import specifier that resolves to
    ``target`` (with or without its .ts extension; with or without an
    /index suffix). Only relative specifiers can name an in-tree module."""
    target_resolved = target.resolve()
    target_noext = target.with_suffix("").resolve()
    for spec in _IMPORT_RE.findall(importer_text):
        if not spec.startswith("."):
            continue  # bare specifiers name packages, never an in-tree module
        try:
            resolved = (importer.parent / spec).resolve()
        except OSError:
            continue
        if resolved == target_resolved or resolved == target_noext:
            return True
        # TS allows importing a directory's index; if the spec resolves to the
        # module's parent dir AND the module is that dir's index, count it.
        if target.stem == "index" and resolved == target.parent.resolve():
            return True
    return False


def find_unreachable_augmentations() -> list[tuple[Path, int, str, str]]:
    """Augmentation modules with ZERO importers anywhere in apps/reading/src/.

    Returns (path, line, col-as-0, finding-text) tuples. ``line`` is 1 — the
    finding is about the whole module's lack of an importer, not a specific
    line; line 1 is the file's identity and keeps the ``path:line:`` output
    shape and the baseline key stable.
    """
    modules = _augmentation_modules()
    if not modules:
        return []
    # Pre-read every candidate importer once (avoid O(modules × files) reads).
    src_files = _iter_src_modules()
    texts: dict[Path, str] = {}
    for f in src_files:
        try:
            texts[f] = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            texts[f] = ""

    findings: list[tuple[Path, int, str, str]] = []
    for mod in modules:
        mod_resolved = mod.resolve()
        has_importer = False
        for f in src_files:
            if f.resolve() == mod_resolved:
                continue  # a module doesn't import itself
            if _imports_module(f, texts[f], mod):
                has_importer = True
                break
        if not has_importer:
            rel = mod.relative_to(_REPO).as_posix()
            findings.append(
                (
                    mod,
                    1,
                    "augmentation:no-importer",
                    f"{rel}:1: reachability — augmentation module has ZERO "
                    f"importers anywhere in apps/reading/src/. A reading "
                    f"augmentation is consumed by the reader surface (e.g. "
                    f"MasterMdViewer.tsx) or at minimum a test; a module nothing "
                    f"imports reaches no surface and is covered by no test "
                    f"(stranded). Wire it in (import it where it is enacted) or "
                    f"remove it. Dynamic/computed imports are review-owned (see "
                    f"reachability_gate.py docstring).",
                )
            )
    return findings


# ── Route reachability ──────────────────────────────────────────────────────
#
# Routes are declared centrally as `<Route path="…" …>` in App.tsx. A route is
# reachable if its STATIC path prefix (everything up to the first :param) has an
# inbound nav literal — `<Link to="…">`, a `to="…"`/`href="…"` prop, or a
# `navigate("…")` / `<Navigate to="…">` — anywhere in apps/reading/src/ that
# isn't the `<Route …>` declaration itself.

_ROUTE_DEF_RE = re.compile(r'<Route\s+path="([^"]+)"')
# Inbound nav references, in three forms this codebase actually uses:
#   1. JSX props        — `to="…"` / `href="…"` (optionally brace-wrapped)
#   2. programmatic      — `navigate("…")`
#   3. CONFIG-OBJECT key — `to: "…"` / `path: "…"` / `route: "…"`
# Most navigation here is registered via config tables (the SceneChrome scene
# registry, workflowTaxonomy, CommandPalette facets, Map/index) whose keys are
# `to`/`path`/`route` followed by a COLON, not a JSX `=` — so form 3 is what
# makes the scan see the real navigation graph instead of false-flagging ~43%
# of routes. The colon-form is distinguished from the `<Route path="…">`
# DECLARATION (which uses `path=` with EQUALS); the declaration line is skipped
# separately in `_collect_nav_references` so a route can't 'reach' itself.
# Captures the destination string in one of the three groups.
_NAV_REF_RE = re.compile(
    r"""
    (?:to|href)\s*=\s*\{?\s*["'`]([^"'`]+)["'`]   # to="…" / href="…" / to={"…"}
    |                                              # …or…
    navigate\(\s*["'`]([^"'`]+)["'`]               # navigate("…")
    |                                              # …or…
    (?<![A-Za-z0-9_])(?:to|path|route)\s*:\s*["'`]([^"'`]+)["'`]  # config key (left word-boundary: open_route:/cache_path: must NOT match)
    """,
    re.VERBOSE,
)


def _static_prefix(route_path: str) -> str | None:
    """The static prefix of a route path: everything up to the first :param.
    ``"/read/meta-reading/:assetId"`` → ``"/read/meta-reading"``;
    ``"/inv/:investigationId"`` → ``"/inv"``; ``"/"`` → ``"/"``. The wildcard
    catch-all ``"*"`` is not a navigable destination — return None to skip it.
    """
    if route_path == "*":
        return None
    segs = route_path.split("/")
    kept: list[str] = []
    for s in segs:
        if s.startswith(":"):
            break
        kept.append(s)
    prefix = "/".join(kept)
    if prefix == "":
        return "/"
    return prefix


def _route_definitions() -> list[tuple[int, str]]:
    """(lineno, static-prefix) for each <Route path="…"> in App.tsx, deduped to
    the FIRST line each distinct static prefix is declared (a baseline key is
    one-per-prefix; multiple routes sharing a prefix — e.g. ``/write`` and
    ``/write/:id`` — are one reachability fact)."""
    if not _APP_TSX.exists():
        return []
    seen: dict[str, int] = {}
    for lineno, line in enumerate(_APP_TSX.read_text(encoding="utf-8").splitlines(), 1):
        for m in _ROUTE_DEF_RE.finditer(line):
            prefix = _static_prefix(m.group(1))
            if prefix is None:
                continue
            if prefix not in seen:
                seen[prefix] = lineno
    return sorted(seen.items(), key=lambda kv: kv[1])


def _collect_nav_references() -> set[str]:
    """Every inbound nav destination literal under apps/reading/src/, expanded
    to include each destination's own static prefix so a link to a deep path
    (``/skill-rules/abc``) marks the parent route prefix (``/skill-rules``)
    reachable. Excludes the literal ``<Route path=…>`` declaration lines so a
    route does not 'reach' itself."""
    refs: set[str] = set()
    for f in _iter_src_modules():
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            if _ROUTE_DEF_RE.search(line):
                continue  # the route declaration is not an inbound reference
            for m in _NAV_REF_RE.finditer(line):
                # group(1): to=/href=  group(2): navigate(  group(3): config key
                dest = m.group(1) or m.group(2) or m.group(3)
                if not dest or not dest.startswith("/"):
                    continue
                refs.add(dest)
                prefix = _static_prefix(dest)
                if prefix:
                    refs.add(prefix)
    return refs


def find_unreachable_routes() -> list[tuple[Path, int, str, str]]:
    """Route prefixes declared in App.tsx with NO inbound nav reference.

    Returns (App.tsx-path, lineno, kind, finding-text) tuples — lineno is the
    line of the route's first declaration so the finding points at the route.
    """
    routes = _route_definitions()
    if not routes:
        return []
    refs = _collect_nav_references()
    findings: list[tuple[Path, int, str, str]] = []
    for prefix, lineno in routes:
        # A route is reachable if its prefix is referenced directly, OR a
        # referenced destination sits under it (a link into a child path).
        reachable = prefix in refs or any(
            ref == prefix or ref.startswith(prefix.rstrip("/") + "/") for ref in refs
        )
        if not reachable:
            rel = _APP_TSX.relative_to(_REPO).as_posix()
            findings.append(
                (
                    _APP_TSX,
                    lineno,
                    f"route:no-inbound-link:{prefix}",
                    f"{rel}:{lineno}: reachability — route '{prefix}' has NO "
                    f"inbound <Link>/to=/href=/navigate() reference anywhere in "
                    f"apps/reading/src/. A route nothing links to and nothing "
                    f"navigates to is reachable only by typing the URL "
                    f"(stranded). Add a link/navigation to it, or remove the "
                    f"route. Computed/variable navigation is review-owned (see "
                    f"reachability_gate.py docstring).",
                )
            )
    return findings


# ── Findings → baseline keys ────────────────────────────────────────────────
#
# A finding's identity for baseline purposes is (path, line, col, kind). For
# augmentation findings the kind is constant ("augmentation:no-importer") so
# renaming/moving a module changes the path and is correctly treated as a NEW
# fact. For route findings the kind embeds the route prefix so a route's
# identity survives the App.tsx line shifting (lines move constantly); the line
# is recorded for the human-facing pointer but the prefix-in-kind is what makes
# the key stable across unrelated edits to App.tsx.


def _finding_to_key(finding: tuple[Path, int, str, str]) -> ViolationKey:
    path, line, kind, _ = finding
    return ViolationKey(
        path=path.relative_to(_REPO).as_posix(),
        line=line,
        col=0,
        kind=kind,
    )


def find_all() -> list[tuple[Path, int, str, str]]:
    """All reachability findings on the reading surface: zero-importer
    augmentations + routes with no inbound link."""
    return find_unreachable_augmentations() + find_unreachable_routes()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reachability_gate",
        description=(
            "Flag stranded reading-surface code: zero-importer augmentations "
            "and routes with no inbound link. Shrink-only baseline."
        ),
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help=(
            "Re-capture the current findings into the baseline JSON "
            "(operator-only). The baseline is shrink-only: use this to "
            "grandfather today's set or to refresh after a stranding is fixed "
            "(which removes its entry); never to silence a NEW stranding."
        ),
    )
    args = parser.parse_args(argv)

    findings = find_all()
    keys = compute_keys(findings, _finding_to_key)

    if args.write_baseline:
        write_baseline(_BASELINE, lint=_LINT_NAME, violations=keys)
        print(f"wrote {len(keys)} finding(s) to {_BASELINE.relative_to(_REPO)}")
        return 0

    # Enforce mode. With no baseline yet, every finding is NEW (the gate is
    # honest about being un-grandfathered rather than silently passing).
    try:
        baseline = load_baseline(_BASELINE)
    except FileNotFoundError:
        baseline = None

    if baseline is None:
        new_keys = keys
    else:
        new_keys = filter_to_new_only(keys, baseline)

    # Map NEW keys back to their human-facing finding text (path:line: message).
    key_to_text = {_finding_to_key(f): f[3] for f in findings}
    for k in new_keys:
        print(key_to_text[k])

    rc = 1 if new_keys else 0

    # Surface stale baseline entries (a stranding that got fixed) so the
    # operator can shrink the baseline — informational, does not flip exit code
    # on its own beyond what NEW findings already did.
    if baseline is not None:
        stale = find_stale_baseline_entries(keys, baseline)
        if stale:
            print(
                f"\n{len(stale)} stale baseline entr"
                f"{'y' if len(stale) == 1 else 'ies'} (now reachable — the "
                f"baseline can shrink; re-run with --write-baseline):",
                file=sys.stderr,
            )
            for k in stale:
                print(f"  - {k.path}:{k.line} {k.kind}", file=sys.stderr)

    if new_keys:
        print(
            f"\n{len(new_keys)} NEW unreachable finding(s) since baseline "
            f"({_BASELINE.name}). See reachability_gate.py docstring for the "
            f"fairness/CANNOT-catch policy.",
            file=sys.stderr,
        )

    return rc


if __name__ == "__main__":
    sys.exit(main())
