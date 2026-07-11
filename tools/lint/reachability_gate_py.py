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
gate closes the class with two mechanical, AST-based checks.

Design note (mirrors the TS gate's rigor #1 — one gate, one surface): this is a
NEW sibling, not an edit to ``reachability_gate.py``. That gate owns the reading
surface; this one owns the backend surface. Both REUSE the shrink-only dated
baseline machinery in ``tools/lints/baseline.py`` VERBATIM (no re-invented
serialization).

────────────────────────────────────────────────────────────────────────────
THE TWO CHECKS
────────────────────────────────────────────────────────────────────────────

**Check A — unmounted API routers.** In ``interfaces/**/api/*_routes.py``, a
"router product" is either (a) a module-level ``name = APIRouter(...)``
assignment or (b) a *factory function* that builds one (return annotation
``APIRouter``, or a body that ``return``\\s an ``APIRouter(...)`` call). A
product is MOUNTED iff its identifier appears inside some ``include_router(...)``
call anywhere in the non-test product tree (directly — ``include_router(r)`` —
or via a factory call — ``include_router(make_r())``). A product no
``include_router`` ever consumes is a route surface no mounted app exposes.
Catches #742's ``create_multimedia_execution_router`` and the #712
completion-route absence class.

**Check B — exported-but-uncalled enforcement symbols.** For every
``substrate/**`` module, each name in its ``__all__`` that (i) is a callable
DEFINED in that module (``def`` / ``async def``) and (ii) matches the
enforcement lexicon (below), and (iii) has ZERO references anywhere in the
non-test product tree, is flagged. A reference is an ``import``, a call, an
attribute access, or any bare-name use — so a symbol only ever exercised by
tests reads as uncalled. Catches ``execute_authorized_call`` / ``complete_spawn``.

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

Both checks are GRANDFATHERED through the dated, shrink-only baseline
``tools/lints/baselines/reachability_py.json`` so the gate reds ONLY on code
that becomes unreachable AFTER this lands — never on today's legitimately
dormant set. Exit 0 = clean (every current finding grandfathered); exit 1 = a
NEW unmounted router / uncalled enforcement export, printed ``path:line:``.

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
    falsifiable "is there an ``include_router`` that names this router at all"
    floor; whether the enclosing register fn is itself reached from the app
    factory is a call-graph question left to review (the same advisory line the
    TS gate draws at "imported only by its own test").
  - **Name-collision masking (Check B)** — if an *unrelated* symbol of the same
    name is referenced elsewhere in the tree, the scan counts the target as
    referenced and will not flag it (a false negative, never a false positive).
    Distinctive enforcement names (``execute_authorized_call``) don't collide;
    generic ones (``complete``) can. Under-detection → review-owned.
  - **Exported classes / constants** — Check B flags only ``def`` / ``async def``
    callables (the enforcement-seam shape). A class exported in ``__all__`` and
    never instantiated is not claimed here.

Everything in the FINDING shapes has a concrete literal signature the AST
matches (a module-level ``APIRouter`` assignment / a factory returning one; an
``include_router`` arg naming it; an ``__all__`` string + a same-named ``def``;
a ``Name``/import/attribute reference). Nothing else is mechanically enforced.

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
site), NOT a re-baseline. The baseline can only shrink (operator refreshes when
a stranding is fixed), so the grandfathered set is a debt that pays down.

Per CLAUDE.md's test-integrity floor, this gate is INFORMATIONAL-FIRST: it
prints ``path:line`` findings and surfaces ``::warning::`` on nonzero, and does
NOT red the build until a written flip-to-blocking condition lands in
``docs/decisions/``. Never flip silently.

Usage::

    python -m tools.lint.reachability_gate_py                       # enforce, no baseline
    python -m tools.lint.reachability_gate_py --baseline <file>     # enforce vs baseline
    python -m tools.lint.reachability_gate_py --write-baseline <f>  # re-capture (operator)
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
def _referenced_names(tree: ast.Module) -> set[str]:
    """Every identifier this module REFERENCES (not merely defines): bare-name
    loads, attribute accesses (``mod.execute_authorized_call``), and imported
    names. A ``def foo`` / ``class Foo`` declaration is NOT a reference (its name
    is a FunctionDef.name string, never a Name-load node), so a module that
    defines-but-never-uses its own export contributes nothing here — exactly
    what makes an only-tests-call-it export read as unreferenced."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.name)
                if alias.asname:
                    names.add(alias.asname)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


def _include_router_arg_names(tree: ast.Module) -> set[str]:
    """Every identifier appearing anywhere inside an ``include_router(...)`` call
    in this module. ``app.include_router(multimedia_router)`` → {multimedia_router};
    ``app.include_router(make_thread_router())`` → {make_thread_router}. A router
    product whose identifier lands in this set (in ANY product file) is mounted."""
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


def find_unmounted_routers(
    trees: dict[Path, ast.Module],
    mount_names: set[str],
) -> list[Finding]:
    """Router products in ``interfaces/**/api/*_routes.py`` whose identifier is
    never an argument to any ``include_router(...)`` in the product tree."""
    findings: list[Finding] = []
    for path in _routes_files():
        tree = trees.get(path)
        if tree is None:
            continue
        for name, line in _router_products(path, tree):
            if name in mount_names:
                continue
            rel = path.relative_to(_REPO).as_posix()
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
                    f"in __all__ but has ZERO non-test callers/importers anywhere "
                    f"in the tree. A claimed enforcement/authority/execution seam "
                    f"only tests exercise does not run in production (stub-theater: "
                    f"green tests, unguarded path). Wire it into the product path "
                    f"or remove it from __all__. Reflection/getattr/name-collision "
                    f"cases are review-owned (see reachability_gate_py.py docstring).",
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
    """All Python-surface reachability findings: unmounted routers + uncalled
    enforcement exports."""
    product_files = _product_py_files()
    trees: dict[Path, ast.Module] = {}
    mount_names: set[str] = set()
    referenced: set[str] = set()
    for f in product_files:
        tree = _parse(f)
        if tree is None:
            continue
        trees[f] = tree
        mount_names |= _include_router_arg_names(tree)
        referenced |= _referenced_names(tree)
    routers = find_unmounted_routers(trees, mount_names)
    exports = find_uncalled_enforcement_exports(trees, referenced)
    return routers + exports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reachability_gate_py",
        description=(
            "Flag stranded backend code: unmounted API routers and uncalled "
            "enforcement exports. Informational-first; shrink-only baseline."
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
            "The baseline is shrink-only: use this to grandfather today's set or "
            "to refresh after a stranding is fixed (removing its entry); never "
            "to silence a NEW stranding."
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
        write_baseline(args.write_baseline, lint=_LINT_NAME, violations=keys)
        try:
            shown = args.write_baseline.relative_to(_REPO)
        except ValueError:
            shown = args.write_baseline
        print(f"wrote {len(keys)} finding(s) to {shown}")
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
