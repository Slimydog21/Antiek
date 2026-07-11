#!/usr/bin/env python3
"""Reachability gate (Python surface) — flag backend code that nothing reaches.

Sibling of ``tools/lint/reachability_gate.py``. That gate makes the *static*
half of the "build the module, never wire it" failure mechanical on the
READING surface (``apps/reading/src/`` — TS augmentations + App.tsx routes).
This gate applies the SAME idea to the surface where the money-safety failures
actually landed: the Python backend.

Three P0/money-safety lanes shipped a correct-looking, green-CI module that is
**never reachable from the production path** — the exact stub-theater kernel
that drove the 348-PR runaway:

  * #712 research vertical — ``complete_spawn`` / ``complete_session_research``
    exported, 0 non-test callers → every product merge 400s.
  * #710 spend guard — AST-snapshot test green, 0 product enforcement.
  * #739→#742 exec authority — ``execute_authorized_call`` +
    ``create_multimedia_execution_router``: 21 tests green, HMAC receipts
    correct, yet 0 non-test callers and the router is never ``include_router``'d,
    so the paid Krea path still fires on api-key-presence alone.

All three are Python/backend — outside the reading-surface gate's scan. This
gate closes the class with three mechanical, AST-based checks (A + B target the
enforcement-export / route-surface holes above; C mechanizes the broader
doctrine-completeness-audit class — a whole substrate library built and tested
but wired into no product loop).

Design note (mirrors the TS gate's rigor #1 — one gate, one surface): this is a
NEW sibling, not an edit to ``reachability_gate.py``. That gate owns the reading
surface; this one owns the backend surface. Both REUSE the shrink-only dated
baseline machinery in ``tools/lints/baseline.py`` VERBATIM (no re-invented
serialization).

────────────────────────────────────────────────────────────────────────────
THE THREE CHECKS
────────────────────────────────────────────────────────────────────────────

**Check A — unmounted API routers.** In ``interfaces/**/api/*_routes.py``, a
"router product" is either (a) a module-level ``name = APIRouter(...)``
assignment or (b) a *factory function* that builds one (return annotation
``APIRouter``, or a body that ``return``\\s an ``APIRouter(...)`` call). A
product is MOUNTED iff its identifier appears inside some ``include_router(...)``
call anywhere in the non-test product tree. Mount resolution is MODULE-AWARE
(not a global bare-name match): a product ``P`` in module ``M`` is mounted only
if ``M`` itself ``include_router``\\s the local ``P`` (the same-file
``register_*_routes`` pattern), OR some module ``N`` ``include_router``\\s a
local name whose import resolves to ``P`` in ``M`` — directly (``from .m_routes
import p_router; include_router(p_router)``, ``as``-alias included) OR through a
CONFIRMED module-level package-``__init__`` re-export barrel (``api/__init__.py``
has a top-level ``from .m_routes import router`` and the app mounts
``from x.api import router``), followed up to ``_REEXPORT_MAX_DEPTH`` hops. This
closes the collision where one mounted ``router`` would mask every other file's
unmounted ``router``.

FAIL-SAFE DESIGN CHOICE (Check A): a mount credit is granted ONLY when a real,
module-level re-export edge is present in the barrel. If resolution cannot
confirm one — the name is not actually re-exported, the import is
function-scoped/conditional, it is a star/``__all__``-driven/dynamic re-export,
or the chain exceeds the depth cap — the credit is NOT granted and the router
stays FLAGGED. Check A thus errs toward a FALSE POSITIVE (over-flagging an
actually-mounted router reached by an exotic re-export — the operator grandfathers
it into the baseline) and NEVER toward a FALSE NEGATIVE (crediting an unmounted
router, which would silently reopen the very hole this gate exists to catch).
For an informational-first gate that is the safe bias. A product no
``include_router`` ever consumes is a route surface no mounted app exposes.
Catches #742's ``create_multimedia_execution_router`` and the #712
completion-route absence class.

**Check B — exported-but-uncalled enforcement symbols.** For every
``substrate/**`` module, each name in its ``__all__`` that (i) is a callable
DEFINED in that module (``def`` / ``async def``) and (ii) matches the
enforcement lexicon (below), and (iii) has ZERO references in a genuine
REACHABILITY position anywhere in the non-test product tree, is flagged. A
reference is a CALL (``name(...)``), a callback/dispatch pass (``register(name)``
— the bare name loaded as a value), or an attribute access (``mod.name``) — it
is NOT a bare ``import``: importing a symbol without ever invoking it does not
put it on the production path, so ``from x import execute_authorized_call`` with
no call still reads as uncalled. A USE of an ``as``-alias credits the ORIGINAL
symbol (``from x import execute_authorized_call as run; run()`` clears
``execute_authorized_call``), so a genuinely-called-through-an-alias export is
not falsely flagged; an aliased import that is never used still credits nothing.
A symbol only ever exercised by tests reads as uncalled. Catches
``execute_authorized_call`` / ``complete_spawn``.

The enforcement lexicon (tunable — ``_ENFORCEMENT_LEXICON`` below): the symbol
name and its module path are split into ``[a-z0-9]+`` word tokens, and a
candidate is in scope iff SOME token *starts with* a lexicon entry —
``enforce · authority/authoriz · execut · gate · guard · complete``. Token-prefix
(not raw substring) matching is deliberate: ``guarded``→``guard``,
``execute``→``execut``, ``authorized``→``authoriz`` all match, while
``aggregate`` / ``delegate`` / ``propagate`` (which merely *contain* ``gate``)
do NOT — a substring match would false-flag every ``…gate`` word. Rationale:
a pure-data helper exported for future use is not the target; a claimed
*enforcement / authority / execution / gate / guard / completion* seam with no
caller is exactly the money-safety hole. Narrowing to the lexicon keeps the
gate from flagging every dormant data export in ``substrate/``.

**Check C — unimported substrate packages.** Where Check B asks "is this ONE
exported enforcement symbol called", Check C asks the doctrine-audit's coarser
question: "does ANY product-loop code import this whole package at all". For
every package DIRECTORY under ``substrate/`` (any depth) whose ``__init__.py``
exposes a PUBLIC API — a non-empty literal ``__all__`` OR at least one public
(non-underscore) top-level ``def`` / ``async def`` / ``class`` defined in the
``__init__`` itself — the whole non-test product tree is searched for ANY file
OUTSIDE that package's own directory that imports it: ``from substrate.<pkg>[...]
import ...``, ``import substrate.<pkg>[...]``, ``from substrate import <pkg>`` (the
child package named directly), or a RELATIVE import in a sibling package
(``from ..<pkg> import ...``) that resolves to a module under the package's
directory. A package that ZERO such non-test importers reach is a
"built-but-unwired" library: it exists, its own tests pass, yet no product-loop
code imports it — the platform's #1 gate ("wiring is the constraint") made
mechanical, and the doctrine-completeness-audit's class distinct from Check B's
per-export ``export:uncalled:*`` class. Finding kind ``package:unimported:<pkg>``
(``<pkg>`` the substrate-relative dotted path, e.g. ``multimedia`` or
``dispatch.providers``) — identity-distinct from Check B so baseline keys never
collide — anchored at ``substrate/<pkg>/__init__.py:1``.

FAIL-SAFE DESIGN CHOICE (Check C) = FLAG-and-baseline. Unlike Checks A/B (which
red on a NEW stranding), Check C is a BACKLOG detector: it surfaces EVERY
unimported public-API package, and the shrink-only dated baseline grandfathers
today's intentionally-dormant set. The scan does NOT try to guess "intentional"
— it flags all; the operator baselines the known-dormant ones (each
grandfathered entry is a wiring debt that pays down as packages get wired and
their baseline entries shrink). Two scoping rules keep the flag honest:

  * PUBLIC-API GATE (scope discipline) — a package whose ``__init__`` declares an
    EMPTY ``__all__``, or exposes no ``__all__`` and no public top-level
    def/class at all (a pure-private helper, or a bare re-export barrel with
    neither ``__all__`` nor a public def/class), is SKIPPED: only a package that
    advertises a public surface is a wiring target. ``substrate/__init__.py`` (the
    root) is never itself a target.
  * PARENT-BARREL DECISION — an import THROUGH the root barrel does NOT credit a
    child. ``substrate/__init__.py`` is EXCLUDED from the importer set, so a child
    it re-exports is not thereby counted as wired; otherwise a single
    ``from .child import *`` in the root barrel would mask every package and gut
    the check. A DIRECT relative import BY a sibling package (``substrate/a``
    doing ``from ..b import x``) DOES count as wiring ``b`` — that is a genuine
    cross-package consumer, not an aggregation barrel. Whether that consumer is
    itself reached from the product loop is the transitive/cycle question Check C
    deliberately does not chase (see CANNOT-catch).

All three checks are GRANDFATHERED through the dated, shrink-only baseline
``tools/lints/baselines/reachability_py.json`` so the gate reds ONLY on code
that becomes unreachable AFTER this lands — never on today's legitimately
dormant set. Exit 0 = clean (every current finding grandfathered); exit 1 = a
NEW unmounted router / uncalled enforcement export / unimported substrate
package, printed ``path:line:``.

────────────────────────────────────────────────────────────────────────────
WHAT THIS GATE CANNOT CATCH (intellectual honesty — mirrors the TS gate's
CANNOT-catch list; rigor #1). Claims ONLY what its AST scan literally matches.
────────────────────────────────────────────────────────────────────────────

  - **Dynamic import / reflection** — ``importlib.import_module(name)``,
    ``getattr(mod, "execute_authorized_call")()``, ``globals()[fn]()``: the
    target is a runtime string with no ``Name`` node, so a symbol reached ONLY
    that way reads as unreferenced here. Out of reach → review-owned.
  - **String-built router registration** — a router mounted by assembling the
    ``include_router`` call (or the router itself) from strings / a registry
    table iterated at runtime. The scan matches an ``include_router(...)`` call
    with the router's *identifier* literally in its args; a router mounted only
    through a computed handle reads as unmounted. Out of reach → review-owned.
  - **DI containers / framework auto-wiring** — a router or callable resolved
    by a dependency-injection container (``Depends``, a provider registry, an
    entry-point plugin loader) has no literal call site the scan sees. Out of
    reach → review-owned.
  - **Register-fn defined but never called** — a ``register_*_routes(app)`` that
    DOES ``include_router(r)`` inside its body makes ``r`` read as MOUNTED here
    even if nothing ever calls ``register_*_routes``. The scan gates the
    falsifiable "is there an ``include_router`` that names this router, resolved
    to its defining module, at all" floor; whether the enclosing register fn is
    itself reached from the app factory is a call-graph question left to review
    (the same advisory line the TS gate draws at "imported only by its own test").
  - **Module-object mount form (Check A)** — ``import m_routes; m_routes.router``
    passed to ``include_router`` mounts via a module OBJECT, not a name imported
    FROM the defining module, so the resolver does not tie it to the product and
    reads it as unmounted (an over-flag, not a false negative). The dominant
    patterns (``from .m_routes import router``, same-file mount, and confirmed
    module-level ``__init__`` re-export barrels) resolve correctly.
  - **Only module-level unconditional re-exports are trusted (Check A)** — the
    barrel resolver follows ONLY a top-level, unconditional ``from .sub import P``
    in an ``__init__``, up to ``_REEXPORT_MAX_DEPTH`` hops. A re-export that is
    function-scoped, nested in an ``if``/``try`` (conditional), a
    ``from .sub import *`` star, or ``__all__``-driven/dynamic is NOT trusted as a
    re-export edge, so it does NOT credit a mount — the router stays FLAGGED
    (fail-safe over-flag). A genuinely-mounted router reached only through such an
    exotic re-export is thus over-flagged and grandfathered into the baseline,
    never silently credited. This is the deliberate false-positive-over-
    false-negative bias stated in the Check A description above.
  - **Registry-stored / string-dispatched callable (Check B)** — a name stored in
    a dict/registry and later dispatched by string (``TABLE["exec"] = the_fn`` …
    ``TABLE[key]()``) counts as REFERENCED via the bare-name load at store time
    even though no literal call site names it; conversely a purely
    string-keyed dispatch with no name/attribute load is uncatchable. Import is
    NOT counted as a reference (that is the #739-742 evasion this closes), but
    this store-then-dispatch residual is → review-owned.
  - **Name-collision masking (Check B)** — if an *unrelated* symbol of the same
    name is referenced elsewhere in the tree, the scan counts the target as
    referenced and will not flag it (a false negative, never a false positive).
    Distinctive enforcement names (``execute_authorized_call``) don't collide;
    generic ones (``complete``) can. Likewise an ``as``-alias whose local name
    equals an unrelated used local over-credits the aliased original (also a
    false negative). Under-detection → review-owned.
  - **Fixed-then-reintroduced at the same ``path:line:kind``** — if a stranding
    is fixed (so the operator could shrink its baseline entry) but the entry is
    NOT shrunk, and later the SAME stranding returns at the identical
    ``path:line:kind``, it matches the still-present baseline key and reads as
    grandfathered rather than NEW. Mitigation: while the finding is fixed the
    gate prints its baseline entry as STALE (``find_stale_baseline_entries``,
    surfaced every run) — the standing signal to shrink; and the shrink-only
    ``--write-baseline`` enforcement (below) means a genuinely-new key at a
    fresh location cannot be baselined away without the loud ``--force-baseline``.
    Detecting reintroduction at a byte-identical location is review-owned.
  - **Exported classes / constants** — Check B flags only ``def`` / ``async def``
    callables (the enforcement-seam shape). A class exported in ``__all__`` and
    never instantiated is not claimed here.
  - **Dynamic / importlib package load (Check C)** — a package pulled in only via
    ``importlib.import_module("substrate.x")``, a plugin / entry-point registry,
    or a settings-driven module string has no literal ``import`` node naming it,
    so it reads as unimported (an over-flag → grandfathered into the baseline).
    Out of reach → review-owned.
  - **CLI / entry-point-only package (Check C)** — a package wired ONLY as a
    console-script ``[project.scripts]`` target in ``pyproject.toml`` (never
    imported from any ``.py``) has no in-tree importer the AST scan sees, so it
    over-flags. Grandfather it into the baseline. Review-owned.
  - **Transitive parent-barrel re-export (Check C)** — a package reached ONLY
    because the root ``substrate/__init__.py`` re-exports its symbols and product
    code imports them ``from substrate`` is deliberately NOT credited: the root
    barrel is excluded as an importer (the PARENT-BARREL DECISION above), so such
    a package over-flags and is baselined. Tracing symbol-level re-export chains
    through the barrel is out of scope — the direct ``from substrate.<pkg>`` /
    ``from substrate import <pkg>`` forms are what the scan credits.
  - **Mutually-importing dormant cluster (Check C)** — two (or more) substrate
    packages that import each other but that NO product code reaches read as
    WIRED (each imports the other), a false negative. Import-cycle liveness is a
    call-graph question left to review — the same advisory line Check A draws at
    "register fn defined but never called".
  - **Re-export-only package with no ``__all__`` (Check C)** — a package whose
    ``__init__`` only does ``from .sub import X`` with neither an ``__all__`` nor
    a public top-level def/class is treated as declaring NO public surface and is
    SKIPPED (its intended public API is unknowable from the AST). Under-scoped by
    design (the PUBLIC-API GATE) — not a false-negative claim.

Everything in the FINDING shapes has a concrete literal signature the AST
matches (a module-level ``APIRouter`` assignment / a factory returning one; an
``include_router`` arg whose import resolves — directly or through a bounded
package-``__init__`` re-export chain — to the defining module; an ``__all__``
string + a same-named ``def``; a ``Name`` load / attribute reference, or a used
``as``-alias crediting its original — never a bare unused import; a
``substrate/<pkg>/__init__.py`` with a non-empty ``__all__`` or a public
top-level def/class, and the absence anywhere in the non-test tree of an
``import substrate.<pkg>`` / ``from substrate.<pkg>`` / ``from substrate import
<pkg>`` / resolving relative import that names it). Nothing else is mechanically
enforced.

────────────────────────────────────────────────────────────────────────────
FAIRNESS — why a (future) HARD gate is defensible (fairness #2)
────────────────────────────────────────────────────────────────────────────
Steelman for staying advisory forever: a hard reachability gate reds on
legitimately-dormant code — a seam landed ahead of its wiring — and that churn
trains the reflexive ``--write-baseline`` muscle that defeats the gate.

Rebuttal, baked into the design: the dated SHRINK-ONLY baseline grandfathers
everything unreachable TODAY. The gate reds ONLY on a NEW stranding — a router
built after this lands and never mounted, an enforcement export added and never
called. The fix is the one line that wires it (an ``include_router`` / a call
site), NOT a re-baseline. Shrink-only is ENFORCED, not just documented:
``--write-baseline`` REFUSES (non-zero) to write a set containing any key not
already grandfathered — so a dev cannot silence a new stranding in one command.
The only way to add a key is the explicit, loud ``--force-baseline`` (initial
mint, or an operator deliberately grandfathering a new dormant set with a
documented reason). The baseline can only shrink under normal use (operator
refreshes when a stranding is fixed), so the grandfathered set is a debt that
pays down.

Per CLAUDE.md's test-integrity floor, this gate is INFORMATIONAL-FIRST: it
prints ``path:line`` findings and surfaces ``::warning::`` on nonzero, and does
NOT red the build until a written flip-to-blocking condition lands in
``docs/decisions/``. Never flip silently.

Usage::

    python -m tools.lint.reachability_gate_py                        # enforce, no baseline
    python -m tools.lint.reachability_gate_py --baseline <file>      # enforce vs baseline
    python -m tools.lint.reachability_gate_py --write-baseline <f>   # shrink-only re-capture
    python -m tools.lint.reachability_gate_py --write-baseline <f> --force-baseline  # loud add
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

# Repo-root resolution mirrors reachability_gate.py:133 exactly: this file is at
# <repo>/tools/lint/reachability_gate_py.py.
_REPO = Path(__file__).resolve().parent.parent.parent
_INTERFACES = _REPO / "interfaces"
_SUBSTRATE = _REPO / "substrate"

_DEFAULT_BASELINE = _REPO / "tools" / "lints" / "baselines" / "reachability_py.json"
_LINT_NAME = "reachability_gate_py"

# Directories never part of the product tree we scan for references / mounts.
_EXCLUDE_DIR_PARTS = frozenset(
    {".venv", "venv", "node_modules", ".git", "__pycache__", ".mypy_cache", ".ruff_cache"}
)

# Enforcement lexicon (tunable). A candidate __all__ symbol is in scope for
# Check B only if some word token of the symbol name OR its module path STARTS
# WITH one of these (case-insensitive). Token-prefix (not raw substring) so
# ``guarded``→``guard`` matches but ``aggregate`` does not match ``gate``. See
# the module docstring for rationale.
_ENFORCEMENT_LEXICON = (
    "enforce",
    "authority",
    "authoriz",
    "execut",
    "gate",
    "guard",
    "complete",
)

# CI invokes us as `python -m tools.lint.reachability_gate_py`; in script mode
# the repo root is not on sys.path, so `import tools.lints.baseline` would fail.
# Add the repo root idempotently so both invocations resolve the shared baseline
# machinery — which we REUSE (diligence #4) rather than reinvent.
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

# A finding: (path, line, kind, human-facing text).
Finding = tuple[Path, int, str, str]


# ── Test / product-tree classification ──────────────────────────────────────
def _is_test_path(p: Path) -> bool:
    """True for test files, which are EXCLUDED from the reference/mount scan.
    A symbol only tests exercise must read as uncalled — that is the point."""
    if "tests" in p.parts:
        return True
    name = p.name
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def _is_excluded(p: Path) -> bool:
    return any(part in _EXCLUDE_DIR_PARTS for part in p.parts)


def _product_py_files() -> list[Path]:
    """Every non-test, non-vendored .py file under the repo — the universe of
    possible mount sites (Check A) and reference sites (Check B)."""
    out: list[Path] = []
    for p in _REPO.rglob("*.py"):
        if _is_excluded(p) or _is_test_path(p):
            continue
        out.append(p)
    return sorted(out)


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return None


# ── Per-file precomputed indexes (parse each product file ONCE) ─────────────
def _reachability_reference_names(tree: ast.Module) -> set[str]:
    """The symbol names this module reaches in a GENUINE REACHABILITY position —
    i.e. actually invoked/passed as a value, NOT merely imported.

    An ``import``/``from … import`` alone is deliberately NOT counted: importing
    ``execute_authorized_call`` without ever calling it does not put it on the
    production path, and treating the import as a caller is exactly the
    #739-742 evasion. A reference is a ``Name`` LOAD — a direct call
    ``execute_authorized_call(...)`` (callee is a Name load), a callback / dispatch
    pass ``register(execute_authorized_call)`` (Name loaded as an argument), or any
    other read of the bare name — or an ``Attribute`` access
    ``mod.execute_authorized_call``. A ``def``/``class`` declaration is a name
    string on the node, not a Name load, so a module that defines-but-never-uses
    its own export contributes nothing.

    ALIAS CREDIT: ``from m import execute_authorized_call as run`` binds the local
    name ``run``; a subsequent USE of ``run`` (``run(payload)``) credits the
    ORIGINAL symbol ``execute_authorized_call`` — the finding is keyed on the
    original, so a genuinely-called-through-an-alias export must not read as
    uncalled. Crucially the credit fires only when the LOCAL alias is USED: an
    aliased import that is never used still credits nothing (fix #2 preserved).
    An ``as``-alias whose local name collides with an unrelated used local can
    over-credit (a false negative, never a false positive) — documented in the
    CANNOT-catch list."""
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
    # Alias credit: local alias name -> original imported symbol.
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
    credited = set(used)
    for local in used:
        original = aliases.get(local)
        if original is not None:
            credited.add(original)
    return credited


def _include_router_arg_names(tree: ast.Module) -> set[str]:
    """The LOCAL identifiers appearing inside an ``include_router(...)`` call in
    this module. ``app.include_router(multimedia_router)`` → {multimedia_router};
    ``app.include_router(make_thread_router())`` → {make_thread_router}. These
    are the local names THIS module mounts; mount resolution (``_is_mounted``)
    then ties each local name back to the module it was imported FROM, so a
    router product is mounted only when ITS module's product is the one mounted —
    never when an unrelated same-spelled ``router`` elsewhere is."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        is_include = (isinstance(fn, ast.Attribute) and fn.attr == "include_router") or (
            isinstance(fn, ast.Name) and fn.id == "include_router"
        )
        if not is_include:
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
                elif isinstance(sub, ast.Attribute):
                    names.add(sub.attr)
    return names


def _resolve_from_module(importer: Path, module: str | None, level: int) -> str | None:
    """Resolve a ``from <module> import …`` target to the repo-relative posix
    path of the defining .py (or its package ``__init__.py``), or None if it does
    not resolve to an in-repo module. Handles absolute (``level==0``) and
    relative (``level>=1``) forms — the two shapes the router mounts use."""
    if level == 0:
        if not module:
            return None
        base = _REPO
        parts = module.split(".")
    else:
        base = importer.parent
        for _ in range(level - 1):
            base = base.parent
        parts = module.split(".") if module else []
    target = base
    for part in parts:
        target = target / part
    candidates = []
    if parts:
        candidates.append(target.with_name(target.name + ".py"))
        candidates.append(target / "__init__.py")
    else:
        candidates.append(base / "__init__.py")
    for cand in candidates:
        try:
            if cand.exists():
                return cand.resolve().relative_to(_REPO).as_posix()
        except (OSError, ValueError):
            continue
    return None


def _importfrom_edges(
    importer: Path, nodes: list[ast.ImportFrom]
) -> dict[str, set[tuple[str, str]]]:
    """local-name → {(defining-module-relpath, original-name)} for the given
    ``from … import …`` nodes. Shared by ``_import_map`` (all scopes) and
    ``_reexport_map`` (module scope only)."""
    out: dict[str, set[tuple[str, str]]] = {}
    for node in nodes:
        target = _resolve_from_module(importer, node.module, node.level)
        if target is None:
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            local = alias.asname or alias.name
            out.setdefault(local, set()).add((target, alias.name))
    return out


def _import_map(importer: Path, tree: ast.Module) -> dict[str, set[tuple[str, str]]]:
    """local-name → {(defining-module-relpath, original-name)} for EVERY
    ``from … import …`` in this module (walked — so the function-local imports
    ``create_app`` uses at the MOUNT SITE are included). This ties a mounted
    local name back to the module it was imported from, closing the global
    bare-name collision. It is used only for the mount-SITE binding; the trusted
    re-export CHAIN uses ``_reexport_map`` (module-level only) so a
    function-scoped or conditional import cannot fabricate a re-export edge."""
    return _importfrom_edges(
        importer, [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    )


def _reexport_map(importer: Path, tree: ast.Module) -> dict[str, set[tuple[str, str]]]:
    """local-name → {(defining-module-relpath, original-name)} for ONLY the
    MODULE-LEVEL, UNCONDITIONAL ``from … import …`` statements in this module —
    the re-export edges that a ``from package import P`` would actually observe
    at import time. A ``from .sub import P`` nested inside a function, an
    ``if``/``try``, a ``from .sub import *`` star, or an ``__all__``-driven
    dynamic re-export is NOT here (only ``tree.body``-level ImportFrom nodes are
    scanned), so an unconfirmed re-export cannot credit a mount — the router
    stays flagged (fail-safe). This is what biases Check A toward over-flagging,
    never toward crediting a mount that may not exist at runtime."""
    return _importfrom_edges(
        importer, [n for n in tree.body if isinstance(n, ast.ImportFrom)]
    )


# ── Check A — unmounted API routers ─────────────────────────────────────────
def _is_apirouter_call(node: ast.expr | None) -> bool:
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    return (isinstance(fn, ast.Name) and fn.id == "APIRouter") or (
        isinstance(fn, ast.Attribute) and fn.attr == "APIRouter"
    )


def _is_apirouter_annotation(node: ast.expr | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id == "APIRouter"
    if isinstance(node, ast.Attribute):
        return node.attr == "APIRouter"
    # Optional[APIRouter] / APIRouter | None
    if isinstance(node, ast.Subscript):
        return _is_apirouter_annotation(node.value) or _is_apirouter_annotation(node.slice)
    if isinstance(node, ast.BinOp):
        return _is_apirouter_annotation(node.left) or _is_apirouter_annotation(node.right)
    return False


def _routes_files() -> list[Path]:
    """``interfaces/**/api/*_routes.py`` — the scope Check A draws router
    products from (per spec). Excludes tests."""
    if not _INTERFACES.exists():
        return []
    out: list[Path] = []
    for p in _INTERFACES.rglob("*_routes.py"):
        if _is_excluded(p) or _is_test_path(p):
            continue
        if p.parent.name != "api":
            continue
        out.append(p)
    return sorted(out)


def _router_products(path: Path, tree: ast.Module) -> list[tuple[str, int]]:
    """(product-identifier, defn-line) for each router product in ``tree``:
    a module-level ``name = APIRouter(...)`` / annotated assignment, and any
    function whose return annotation is APIRouter or whose body returns an
    ``APIRouter(...)`` call (a factory). Module-level only — a router built
    inside a function body and never returned is a local, not a product."""
    products: list[tuple[str, int]] = []
    for node in tree.body:
        # (a) module-level assignment to an APIRouter(...) call
        if isinstance(node, ast.Assign) and _is_apirouter_call(node.value):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    products.append((tgt.id, node.lineno))
        elif isinstance(node, ast.AnnAssign) and _is_apirouter_call(node.value):
            if isinstance(node.target, ast.Name):
                products.append((node.target.id, node.lineno))
        # (b) factory function: returns an APIRouter (annotation or body return)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_apirouter_annotation(node.returns):
                products.append((node.name, node.lineno))
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and _is_apirouter_call(sub.value):
                    products.append((node.name, node.lineno))
                    break
    return products


_REEXPORT_MAX_DEPTH = 6


def _resolves_to(
    origin_rel: str,
    origin_name: str,
    defining_rel: str,
    product: str,
    reexport_map: dict[str, dict[str, set[tuple[str, str]]]],
    depth: int = _REEXPORT_MAX_DEPTH,
    seen: frozenset[tuple[str, str]] = frozenset(),
) -> bool:
    """True iff the mount-site binding ``(origin_rel, origin_name)`` resolves —
    directly, or THROUGH one-or-more CONFIRMED module-level package re-export
    edges — to the router ``product`` defined in ``defining_rel``.

    The common FastAPI barrel: ``interfaces/x/api/__init__.py`` has a MODULE-LEVEL
    ``from .widget_routes import router`` and the app mounts
    ``from interfaces.x.api import router`` — the app's import resolves to the
    package ``__init__``, so this follows the ``__init__``'s CONFIRMED re-export
    of ``router`` (present in ``reexport_map``) down to ``widget_routes.py``.

    FAIL-SAFE BIAS: the chain hops read ONLY from ``reexport_map`` (module-level,
    unconditional re-exports). If the barrel does NOT actually re-export the name
    at module scope — the name is not re-exported, the import is
    function-scoped/conditional, it is a star/``__all__``-driven re-export, or the
    chain exceeds ``_REEXPORT_MAX_DEPTH`` — no edge is found, the credit is NOT
    granted, and the router stays FLAGGED. Check A therefore errs toward a false
    POSITIVE (over-flag an actually-mounted router reached by an exotic
    re-export, which the operator baselines) rather than a false NEGATIVE
    (crediting an unmounted router, which silently reopens the hole)."""
    if origin_rel == defining_rel and origin_name == product:
        return True
    if depth <= 0 or (origin_rel, origin_name) in seen:
        return False
    seen = seen | {(origin_rel, origin_name)}
    for next_rel, next_name in reexport_map.get(origin_rel, {}).get(origin_name, ()):
        if _resolves_to(
            next_rel, next_name, defining_rel, product, reexport_map, depth - 1, seen
        ):
            return True
    return False


def _is_mounted(
    defining_rel: str,
    product: str,
    include_local: dict[str, set[str]],
    import_map: dict[str, dict[str, set[tuple[str, str]]]],
    reexport_map: dict[str, dict[str, set[tuple[str, str]]]],
) -> bool:
    """True iff router ``product`` defined in module ``defining_rel`` is mounted,
    resolved MODULE-AWARELY (not by global bare-name collision):

      * same-module — ``defining_rel`` itself ``include_router``\\s the local
        name ``product`` (the common ``register_*_routes`` pattern where the
        router is defined and mounted in one file), OR
      * cross-module — some module N ``include_router``\\s a local name L whose
        mount-site binding (``import_map``, any scope) resolves — directly, or
        through a CONFIRMED module-level package re-export chain
        (``reexport_map``) — to ``product`` in ``defining_rel``. Covers both
        ``from .x_routes import x_router; include_router(x_router)`` and the
        barrel ``from .x_routes import router`` (module-level) in
        ``api/__init__.py`` + ``from x.api import router; include_router(router)``.

    A different module defining its own ``router`` and mounting it cannot mount
    THIS module's ``router``: the cross-module arm requires the binding to resolve
    to ``defining_rel`` specifically. An unconfirmed re-export never credits a
    mount (see ``_resolves_to`` — fail-safe toward flagging)."""
    if product in include_local.get(defining_rel, set()):
        return True
    for n_rel, mounted_locals in include_local.items():
        imap = import_map.get(n_rel, {})
        for local in mounted_locals:
            for origin_rel, origin_name in imap.get(local, ()):
                if _resolves_to(
                    origin_rel, origin_name, defining_rel, product, reexport_map
                ):
                    return True
    return False


def find_unmounted_routers(
    trees: dict[Path, ast.Module],
    include_local: dict[str, set[str]],
    import_map: dict[str, dict[str, set[tuple[str, str]]]],
    reexport_map: dict[str, dict[str, set[tuple[str, str]]]],
) -> list[Finding]:
    """Router products in ``interfaces/**/api/*_routes.py`` that no module mounts
    (module-aware — see ``_is_mounted``)."""
    findings: list[Finding] = []
    for path in _routes_files():
        tree = trees.get(path)
        if tree is None:
            continue
        rel = path.relative_to(_REPO).as_posix()
        for name, line in _router_products(path, tree):
            if _is_mounted(rel, name, include_local, import_map, reexport_map):
                continue
            findings.append(
                (
                    path,
                    line,
                    f"router:unmounted:{name}",
                    f"{rel}:{line}: reachability — router product '{name}' is "
                    f"never passed to include_router() anywhere in the non-test "
                    f"tree. A route surface no mounted app exposes is unreachable "
                    f"(stub-theater: built + tested, never wired). Mount it "
                    f"(app.include_router({name}) or via its register_*_routes) "
                    f"or remove it. Dynamic/DI/string-built mounts are "
                    f"review-owned (see reachability_gate_py.py docstring).",
                )
            )
    return findings


# ── Check B — exported-but-uncalled enforcement symbols ─────────────────────
def _dunder_all(tree: ast.Module) -> list[str] | None:
    """The list of string names in a module-level ``__all__ = [...]`` / ``(...)``,
    or None if the module has no literal-list ``__all__``."""
    for node in tree.body:
        value: ast.expr | None = None
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
        ) or (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
        ):
            value = node.value
        if not isinstance(value, (ast.List, ast.Tuple)):
            continue
        out: list[str] = []
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.append(elt.value)
        return out
    return None


def _defined_callables(tree: ast.Module) -> dict[str, int]:
    """Module-level ``def`` / ``async def`` name → defn line (the callable-export
    candidates; classes are intentionally out of scope — see docstring)."""
    out: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node.lineno
    return out


def _in_lexicon(symbol: str, module_rel: str) -> bool:
    tokens = re.findall(r"[a-z0-9]+", f"{symbol} {module_rel}".lower())
    return any(
        tok.startswith(lex) for tok in tokens for lex in _ENFORCEMENT_LEXICON
    )


def find_uncalled_enforcement_exports(
    trees: dict[Path, ast.Module],
    referenced: set[str],
) -> list[Finding]:
    """substrate/** ``__all__`` callables in the enforcement lexicon with ZERO
    references anywhere in the non-test product tree."""
    if not _SUBSTRATE.exists():
        return []
    findings: list[Finding] = []
    for path in sorted(_SUBSTRATE.rglob("*.py")):
        if _is_excluded(path) or _is_test_path(path):
            continue
        tree = trees.get(path)
        if tree is None:
            continue
        exported = _dunder_all(tree)
        if not exported:
            continue
        callables = _defined_callables(tree)
        rel = path.relative_to(_REPO).as_posix()
        for name in exported:
            if name not in callables:
                continue  # not a callable defined here (class / re-export / data)
            if not _in_lexicon(name, rel):
                continue  # outside the enforcement lexicon — not the target
            if name in referenced:
                continue  # referenced somewhere non-test → reachable
            line = callables[name]
            findings.append(
                (
                    path,
                    line,
                    f"export:uncalled:{name}",
                    f"{rel}:{line}: reachability — enforcement export '{name}' is "
                    f"in __all__ but is CALLED by ZERO non-test code anywhere in "
                    f"the tree (a bare import does not count — only an actual "
                    f"call/callback/attribute use). A claimed "
                    f"enforcement/authority/execution seam only tests exercise "
                    f"does not run in production (stub-theater: green tests, "
                    f"unguarded path). Wire it into the product path (call it) or "
                    f"remove it from __all__. Reflection/getattr/registry-dispatch/"
                    f"name-collision cases are review-owned (see "
                    f"reachability_gate_py.py docstring).",
                )
            )
    return findings


# ── Check C — unimported substrate packages ─────────────────────────────────
def _package_has_public_api(tree: ast.Module) -> bool:
    """True iff this package ``__init__`` advertises a PUBLIC surface — the scope
    gate for Check C. Two forms count (mirrors the spec's public-API rule):

      * a NON-EMPTY literal ``__all__`` (the declared export list), OR
      * at least one public (non-underscore) top-level ``def`` / ``async def`` /
        ``class`` DEFINED in the ``__init__`` itself.

    A package with an EMPTY ``__all__``, or with neither an ``__all__`` nor a
    public top-level def/class (a pure-private helper, or a bare re-export barrel
    that only ``from .sub import X`` with no ``__all__``), declares no public
    surface and is SKIPPED — its intended public API is unknowable from the AST,
    and a private helper is not the wiring target. Re-export-only names are
    intentionally NOT treated as a public surface here (documented in the
    CANNOT-catch list)."""
    exported = _dunder_all(tree)
    if exported:  # non-empty list -> declared public surface
        return True
    for node in tree.body:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ) and not node.name.startswith("_"):
            return True
    return False


def _module_dotted(importer: Path, module: str | None, level: int) -> str | None:
    """The dotted module path a ``from <module> import …`` targets, IF it resolves
    to an in-repo module under ``substrate/`` — else None. Reuses
    ``_resolve_from_module`` (which handles both absolute ``level==0`` and
    relative ``level>=1`` forms) to get the defining file, then converts the
    repo-relative path back to a dotted module. ``substrate/x/__init__.py`` ->
    ``substrate.x``; ``substrate/x/sub.py`` -> ``substrate.x.sub``."""
    rel = _resolve_from_module(importer, module, level)
    if rel is None:
        return None
    if rel == "substrate/__init__.py":
        return "substrate"
    if not (rel == "substrate.py" or rel.startswith("substrate/")):
        return None
    if rel.endswith("/__init__.py"):
        rel = rel[: -len("/__init__.py")]
    elif rel.endswith(".py"):
        rel = rel[: -len(".py")]
    return rel.replace("/", ".")


def _imported_substrate_modules(importer: Path, tree: ast.Module) -> set[str]:
    """The set of ``substrate.*`` dotted module paths this file imports — the
    evidence Check C uses to decide a package is WIRED.

    Covers every import shape that literally names a substrate module:

      * ``import substrate.x`` / ``import substrate.x.sub`` (``ast.Import``) — the
        alias's dotted name, taken verbatim when it is ``substrate`` or under it.
      * ``from substrate.x[...] import Y`` (absolute ``ast.ImportFrom``) — the base
        module resolved to its dotted path.
      * ``from substrate import x`` — the base is ``substrate`` and the imported
        NAME ``x`` names the child package directly, so ``substrate.x`` is added
        (this is the one non-``substrate.<pkg>`` shape that still directly names a
        child; symbol re-exports off the root barrel are NOT chased — see the
        parent-barrel decision).
      * ``from ..x import Y`` (relative ``ast.ImportFrom`` in a sibling package) —
        resolved through ``_resolve_from_module`` to its dotted substrate path.

    For each ``from`` import the imported NAMES are also appended as
    ``base + "." + name`` candidates so ``from substrate import x`` and
    ``from substrate.pkg import subpkg`` credit the named child; a candidate that
    matches no real package is harmless (the WIRED check only compares against
    actual package module paths)."""
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "substrate" or alias.name.startswith("substrate."):
                    mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = _module_dotted(importer, node.module, node.level)
            if base is None:
                continue
            mods.add(base)
            for alias in node.names:
                if alias.name != "*":
                    mods.add(f"{base}.{alias.name}")
    return mods


def _substrate_package_inits() -> list[Path]:
    """Every ``substrate/**/__init__.py`` (any depth) EXCEPT the root
    ``substrate/__init__.py``, excluding tests/vendored — the Check C candidate
    packages before the public-API gate is applied."""
    if not _SUBSTRATE.exists():
        return []
    out: list[Path] = []
    for p in _SUBSTRATE.rglob("__init__.py"):
        if _is_excluded(p) or _is_test_path(p):
            continue
        if p.relative_to(_REPO).as_posix() == "substrate/__init__.py":
            continue
        out.append(p)
    return sorted(out)


def find_unimported_substrate_packages(
    trees: dict[Path, ast.Module],
    substrate_imports: dict[str, set[str]],
) -> list[Finding]:
    """substrate/** packages that expose a public API yet are imported by ZERO
    non-test files OUTSIDE the package itself (the built-but-unwired library —
    the doctrine-completeness-audit class). See ``_package_has_public_api`` for
    the public-API scope gate and the module docstring for the fail-safe
    FLAG-and-baseline bias + the parent-barrel decision."""
    findings: list[Finding] = []
    for init_path in _substrate_package_inits():
        tree = trees.get(init_path)
        if tree is None:
            continue
        if not _package_has_public_api(tree):
            continue
        pkg_dir_rel = init_path.parent.relative_to(_REPO).as_posix()  # substrate/x
        pkg_module = pkg_dir_rel.replace("/", ".")  # substrate.x
        pkg_id = pkg_dir_rel[len("substrate/") :].replace("/", ".")  # x
        inside_prefix = pkg_dir_rel + "/"
        wired = False
        for importer_rel, mods in substrate_imports.items():
            # Self-exclusion: an importer inside the package's own directory does
            # not count. Root-barrel exclusion (parent-barrel decision): a child
            # re-exported by substrate/__init__.py is not thereby wired.
            if importer_rel == "substrate/__init__.py":
                continue
            if importer_rel.startswith(inside_prefix):
                continue
            for m in mods:
                if m == pkg_module or m.startswith(pkg_module + "."):
                    wired = True
                    break
            if wired:
                break
        if wired:
            continue
        rel = init_path.relative_to(_REPO).as_posix()
        findings.append(
            (
                init_path,
                1,
                f"package:unimported:{pkg_id}",
                f"{rel}:1: reachability — substrate package '{pkg_id}' exposes a "
                f"public API (__all__ or public top-level def/class) but is "
                f"imported by ZERO non-test files OUTSIDE the package. A built + "
                f"tested library that no product-loop code imports is unreachable "
                f"(the doctrine 'wiring is the constraint' hole). Import it from a "
                f"product path (from substrate.{pkg_id} import ...) or remove it. "
                f"Dynamic/importlib/entry-point/parent-barrel wiring is "
                f"review-owned (see reachability_gate_py.py docstring).",
            )
        )
    return findings


# ── Findings → baseline keys ────────────────────────────────────────────────
#
# Identity is (path, line, col=0, kind). The kind embeds the product/symbol name
# so a finding's identity survives unrelated line shifts within its file (the
# name is stable; the line is the human pointer). Renaming or moving the symbol
# changes the kind/path and is correctly treated as a NEW fact.
def _finding_to_key(finding: Finding) -> ViolationKey:
    path, line, kind, _ = finding
    return ViolationKey(
        path=path.relative_to(_REPO).as_posix(),
        line=line,
        col=0,
        kind=kind,
    )


def find_all() -> list[Finding]:
    """All Python-surface reachability findings: unmounted routers (A) + uncalled
    enforcement exports (B) + unimported substrate packages (C)."""
    product_files = _product_py_files()
    trees: dict[Path, ast.Module] = {}
    include_local: dict[str, set[str]] = {}
    import_map: dict[str, dict[str, set[tuple[str, str]]]] = {}
    reexport_map: dict[str, dict[str, set[tuple[str, str]]]] = {}
    substrate_imports: dict[str, set[str]] = {}
    referenced: set[str] = set()
    for f in product_files:
        tree = _parse(f)
        if tree is None:
            continue
        rel = f.relative_to(_REPO).as_posix()
        trees[f] = tree
        include_local[rel] = _include_router_arg_names(tree)
        import_map[rel] = _import_map(f, tree)
        reexport_map[rel] = _reexport_map(f, tree)
        substrate_imports[rel] = _imported_substrate_modules(f, tree)
        referenced |= _reachability_reference_names(tree)
    routers = find_unmounted_routers(trees, include_local, import_map, reexport_map)
    exports = find_uncalled_enforcement_exports(trees, referenced)
    packages = find_unimported_substrate_packages(trees, substrate_imports)
    return routers + exports + packages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reachability_gate_py",
        description=(
            "Flag stranded backend code: unmounted API routers, uncalled "
            "enforcement exports, and unimported substrate packages. "
            "Informational-first; shrink-only baseline."
        ),
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=_DEFAULT_BASELINE,
        help=(
            "Path to the shrink-only dated baseline JSON. Findings present in it "
            "are grandfathered; only NEW findings red the exit code."
        ),
    )
    parser.add_argument(
        "--write-baseline",
        nargs="?",
        const=_DEFAULT_BASELINE,
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Re-capture current findings into the baseline JSON (operator-only). "
            "SHRINK-ONLY: this REFUSES (non-zero) if the current findings contain "
            "any key not already in the existing baseline — you cannot baseline "
            "away a NEW stranding. Use it to grandfather today's set (via "
            "--force-baseline on first mint) or to refresh after a stranding is "
            "fixed (which only REMOVES its entry)."
        ),
    )
    parser.add_argument(
        "--force-baseline",
        action="store_true",
        help=(
            "The explicit, loud escape hatch for the shrink-only refusal: writes "
            "the current findings even when they ADD keys (initial mint, or an "
            "operator deliberately grandfathering a new dormant set with a "
            "documented reason). Mirrors the ALLOW_EMPTY-style override — never "
            "the silent default."
        ),
    )
    args = parser.parse_args(argv)

    findings = find_all()
    # compute_keys' adapter param is contravariant (Callable[[object], …]); our
    # adapter is typed to the concrete Finding tuple, so cast at the boundary.
    keys = compute_keys(
        findings, cast(Callable[[object], ViolationKey], _finding_to_key)
    )

    if args.write_baseline is not None:
        target = args.write_baseline
        try:
            shown = target.relative_to(_REPO)
        except ValueError:
            shown = target
        # Shrink-only enforcement: the written set must be a SUBSET of the
        # existing baseline (removals only). Any current key not already
        # grandfathered is an ADD — refuse unless --force-baseline.
        try:
            existing = {
                (k.path, k.line, k.col, k.kind)
                for k in load_baseline(target).violations
            }
        except FileNotFoundError:
            existing = set()
        added = [k for k in keys if (k.path, k.line, k.col, k.kind) not in existing]
        if added and not args.force_baseline:
            print(
                f"shrink-only: {len(added)} new finding(s) cannot be baselined "
                f"away; wire or remove them, or use --force-baseline with a "
                f"documented reason:",
                file=sys.stderr,
            )
            for k in added:
                print(f"  + {k.path}:{k.line} {k.kind}", file=sys.stderr)
            return 1
        write_baseline(target, lint=_LINT_NAME, violations=keys)
        forced = " (FORCED — new keys added)" if (added and args.force_baseline) else ""
        print(f"wrote {len(keys)} finding(s) to {shown}{forced}")
        return 0

    # Enforce mode. With no baseline file, every finding is NEW (honest about
    # being un-grandfathered rather than silently passing).
    try:
        baseline = load_baseline(args.baseline)
    except FileNotFoundError:
        baseline = None

    new_keys = keys if baseline is None else filter_to_new_only(keys, baseline)

    key_to_text = {_finding_to_key(f): f[3] for f in findings}
    for k in new_keys:
        print(key_to_text[k])

    rc = 1 if new_keys else 0

    # Surface stale baseline entries (a stranding that got fixed) so the operator
    # can shrink the baseline — informational only.
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
            f"\n{len(new_keys)} NEW unreachable Python-surface finding(s) since "
            f"baseline. See reachability_gate_py.py docstring for the "
            f"fairness/CANNOT-catch policy. Informational-first: this does not "
            f"red the build until a flip-to-blocking decision lands.",
            file=sys.stderr,
        )

    return rc


if __name__ == "__main__":
    sys.exit(main())
