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
gate closes the class with three mechanical, AST-based checks.

Design note (mirrors the TS gate's rigor #1 — one gate, one surface): this is a
NEW sibling, not an edit to ``reachability_gate.py``. That gate owns the reading
surface; this one owns the backend surface. Both REUSE the shrink-only dated
baseline machinery in ``tools/lints/baseline.py`` VERBATIM (no re-invented
serialization).

────────────────────────────────────────────────────────────────────────────
THE THREE CHECKS
────────────────────────────────────────────────────────────────────────────

**Check A — unmounted API routers.** In ``interfaces/**/api/*.py``, excluding
``__init__.py`` and obvious test files, a
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
For a hard gate with a shrink-only baseline, that is the safe bias. A product no
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

**Check C — uncalled router-registration wrappers.** A module-level
``register_*_routes`` function in an API routes module that contains an
``include_router`` call must itself be called by non-test product code. Calls
are resolved back to the defining module through direct imports, aliases, and
the same bounded trusted re-export chain as Check A. This catches the subtler
dead surface where a router looks mounted inside its own wrapper, but the real
app factory never invokes that wrapper.

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

All three checks are GRANDFATHERED through the dated, shrink-only baseline
``tools/lints/baselines/reachability_py.json`` so the gate reds ONLY on code
that becomes unreachable AFTER this lands — never on today's legitimately
dormant set. Exit 0 = clean (every current finding grandfathered); exit 1 = a
NEW unmounted router / uncalled registration wrapper / uncalled enforcement
export, printed ``path:line:``.

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
  - **Dynamic register-wrapper dispatch** — ordinary ``register_*_routes(app)``
    wrappers that contain ``include_router`` are checked module-awarely and must
    themselves be called by non-test product code. A wrapper invoked only via
    reflection, a string registry, or a DI container has no statically resolvable
    call and is conservatively flagged; that dynamic wiring is review-owned.
  - **Reachable-code model** — the scanner roots live module-scope code, direct
    ``@app`` route handlers, the designated production ASGI factory
    (``interfaces/research/api/app.py:create_app``), and route handlers whose
    router is mounted. Other FastAPI-looking factories are reachable only if
    product-reachable code calls them; an unreferenced sidecar ``create_app`` does
    NOT root its body. The scanner then follows explicit local and
    ``from … import …`` call edges, returned nested callback bodies, and methods
    on classes instantiated by reachable code. Bodies of arbitrary uncalled
    helpers do NOT count, regardless of name or ``__all__`` membership; methods
    on exported but uninstantiated classes likewise do not count. It deliberately
    ignores bodies under static-dead branches (``if False:``, ``if 0:``,
    ``if None:``, statically resolvable ``if TYPE_CHECKING:``, and
    ``if __name__ == "__main__":``). It does not prove full Python call
    reachability; ambiguous dynamic wiring remains review-owned and should be
    made explicit if it is product-critical.
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

Everything in the FINDING shapes has a concrete literal signature the AST
matches (a module-level ``APIRouter`` assignment / a factory returning one; an
``include_router`` arg whose import resolves — directly or through a bounded
package-``__init__`` re-export chain — to the defining module; an ``__all__``
string + a same-named ``def``; a ``Name`` load / attribute reference, or a used
``as``-alias crediting its original — never a bare unused import). Nothing else
is mechanically enforced.

────────────────────────────────────────────────────────────────────────────
FAIRNESS — why a HARD gate is defensible (fairness #2)
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

This gate is a hard CI blocker in ``.github/workflows/ci.yml``. It prints
``path:line`` findings and exits non-zero on any NEW non-grandfathered
stranding. Do not swallow its exit code in CI; the shrink-only baseline is the
fairness mechanism.

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
from dataclasses import dataclass
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
_DEAD_BRANCH_SENTINELS = (False, 0, None)
_TYPE_CHECKING_MODULES = frozenset({"typing", "typing_extensions"})


@dataclass(frozen=True)
class _DeadBranchGuards:
    type_checking_names: frozenset[str] = frozenset()
    type_checking_modules: frozenset[str] = frozenset()


_EMPTY_DEAD_BRANCH_GUARDS = _DeadBranchGuards()


def _dead_branch_guards(statements: list[ast.stmt]) -> _DeadBranchGuards:
    """Statically-known names that make an ``if`` body non-product code.

    This intentionally recognizes only ordinary typing imports. A project-local
    variable named ``TYPE_CHECKING`` or a runtime feature flag is not enough to
    discard a branch.
    """
    type_checking_names: set[str] = set()
    type_checking_modules: set[str] = set()
    for stmt in statements:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                root = alias.name.split(".", 1)[0]
                if root in _TYPE_CHECKING_MODULES:
                    type_checking_modules.add(alias.asname or root)
        elif isinstance(stmt, ast.ImportFrom) and stmt.module in _TYPE_CHECKING_MODULES:
            for alias in stmt.names:
                if alias.name == "TYPE_CHECKING":
                    type_checking_names.add(alias.asname or alias.name)
    return _DeadBranchGuards(
        type_checking_names=frozenset(type_checking_names),
        type_checking_modules=frozenset(type_checking_modules),
    )


def _merge_dead_branch_guards(
    left: _DeadBranchGuards, right: _DeadBranchGuards
) -> _DeadBranchGuards:
    return _DeadBranchGuards(
        type_checking_names=left.type_checking_names | right.type_checking_names,
        type_checking_modules=left.type_checking_modules | right.type_checking_modules,
    )


def _is_type_checking_guard(node: ast.expr, guards: _DeadBranchGuards) -> bool:
    if isinstance(node, ast.Name):
        return node.id in guards.type_checking_names
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "TYPE_CHECKING"
        and isinstance(node.value, ast.Name)
        and node.value.id in guards.type_checking_modules
    )


def _is_dunder_name(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "__name__"


def _is_main_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == "__main__"


def _is_main_guard(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.Eq)
        and len(node.comparators) == 1
        and (
            (_is_dunder_name(node.left) and _is_main_literal(node.comparators[0]))
            or (_is_main_literal(node.left) and _is_dunder_name(node.comparators[0]))
        )
    )


def _is_static_dead_test(
    node: ast.expr, guards: _DeadBranchGuards = _EMPTY_DEAD_BRANCH_GUARDS
) -> bool:
    return (
        (isinstance(node, ast.Constant) and node.value in _DEAD_BRANCH_SENTINELS)
        or _is_type_checking_guard(node, guards)
        or _is_main_guard(node)
    )


def _reachable_statement_nodes(
    statements: list[ast.stmt],
    *,
    route_bases: frozenset[str] = frozenset(),
    reachable_nested_functions: frozenset[str] = frozenset(),
    dead_guards: _DeadBranchGuards = _EMPTY_DEAD_BRANCH_GUARDS,
) -> list[ast.AST]:
    """Nodes reachable inside already-reachable statements.

    This walker is intentionally body-scoped: nested function/class/lambda
    bodies are definitions, not execution. Static-dead ``if`` bodies are also
    ignored, with ``else`` still inspected because it is the reachable branch.
    """
    out: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        out.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in reachable_nested_functions or any(
                (base := _route_decorator_base(dec)) is not None and base in route_bases
                for dec in node.decorator_list
            ):
                for child in node.body:
                    visit(child)
            return
        if isinstance(node, (ast.ClassDef, ast.Lambda)):
            return
        if isinstance(node, ast.If) and _is_static_dead_test(node.test, dead_guards):
            for child in node.orelse:
                visit(child)
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    for stmt in statements:
        visit(stmt)
    return out


def _module_level_reachable_nodes(tree: ast.Module) -> list[ast.AST]:
    """Reachable nodes that are not nested inside a function/class body."""
    return [
        tree,
        *_reachable_statement_nodes(
            tree.body, dead_guards=_dead_branch_guards(tree.body)
        ),
    ]


_DEFAULT_ROUTE_BASES = frozenset({"app"})


def _returned_local_function_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    dead_guards: _DeadBranchGuards = _EMPTY_DEAD_BRANCH_GUARDS,
) -> frozenset[str]:
    """Nested functions returned by an already-reachable factory.

    This is deliberately narrower than "all nested helpers": a callback body is
    reachable when the reachable factory returns that local function object.
    """
    local_functions = {
        stmt.name
        for stmt in node.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    returned: set[str] = set()

    def visit(stmt: ast.stmt) -> None:
        if isinstance(stmt, ast.If) and _is_static_dead_test(stmt.test, dead_guards):
            for child in stmt.orelse:
                visit(child)
            return
        if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Name):
            if stmt.value.id in local_functions:
                returned.add(stmt.value.id)
            return
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        for child in ast.iter_child_nodes(stmt):
            if isinstance(child, ast.stmt):
                visit(child)

    for stmt in node.body:
        visit(stmt)
    return frozenset(returned)


def _function_body_nodes(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    route_bases: frozenset[str] = _DEFAULT_ROUTE_BASES,
    dead_guards: _DeadBranchGuards = _EMPTY_DEAD_BRANCH_GUARDS,
) -> list[ast.AST]:
    """Nodes in an already-proven-reachable function body."""
    body_guards = _dead_branch_guards(list(node.body))
    return [
        node,
        *_reachable_statement_nodes(
            list(node.body),
            route_bases=route_bases,
            reachable_nested_functions=_returned_local_function_names(
                node, dead_guards
            ),
            dead_guards=_merge_dead_branch_guards(dead_guards, body_guards),
        ),
    ]


def _reachable_function_nodes(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Module-level functions whose definitions are not under static-dead code."""
    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    dead_guards = _dead_branch_guards(tree.body)

    def visit_stmt(node: ast.stmt) -> None:
        if isinstance(node, ast.If) and _is_static_dead_test(node.test, dead_guards):
            for child in node.orelse:
                if isinstance(child, ast.stmt):
                    visit_stmt(child)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
            return
        if isinstance(node, ast.ClassDef):
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                visit_stmt(child)

    for stmt in tree.body:
        visit_stmt(stmt)
    return out


def _reachable_class_nodes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    """Module-level classes whose definitions are not under static-dead code."""
    out: dict[str, ast.ClassDef] = {}
    dead_guards = _dead_branch_guards(tree.body)

    def visit_stmt(node: ast.stmt) -> None:
        if isinstance(node, ast.If) and _is_static_dead_test(node.test, dead_guards):
            for child in node.orelse:
                if isinstance(child, ast.stmt):
                    visit_stmt(child)
            return
        if isinstance(node, ast.ClassDef):
            out[node.name] = node
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                visit_stmt(child)

    for stmt in tree.body:
        visit_stmt(stmt)
    return out


_APP_FACTORY_NAMES = frozenset(
    {"create_app", "make_app", "build_app", "get_app", "app_factory"}
)
_DESIGNATED_APP_FACTORY_ROOTS = frozenset(
    {("interfaces/research/api/app.py", "create_app")}
)


@dataclass(frozen=True)
class _Reachability:
    nodes: list[ast.AST]
    functions: frozenset[str]
    classes: frozenset[str]


def _is_fastapi_annotation(node: ast.expr | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id == "FastAPI"
    if isinstance(node, ast.Attribute):
        return node.attr == "FastAPI"
    if isinstance(node, ast.Subscript):
        return _is_fastapi_annotation(node.value) or _is_fastapi_annotation(node.slice)
    if isinstance(node, ast.BinOp):
        return _is_fastapi_annotation(node.left) or _is_fastapi_annotation(node.right)
    return False


def _returns_fastapi_call(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(sub, ast.Return)
        and isinstance(sub.value, ast.Call)
        and (
            (isinstance(sub.value.func, ast.Name) and sub.value.func.id == "FastAPI")
            or (
                isinstance(sub.value.func, ast.Attribute)
                and sub.value.func.attr == "FastAPI"
            )
        )
        for sub in ast.walk(node)
    )


def _is_app_factory(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when a function has the FastAPI factory shape.

    Shape alone is not a root. It is used only to validate narrow, designated
    product entrypoints; all other factories must be reached by ordinary product
    call edges.
    """
    return (
        node.name in _APP_FACTORY_NAMES
        or _is_fastapi_annotation(node.returns)
        or _returns_fastapi_call(node)
    )


def _reachability_reference_names(nodes: list[ast.AST]) -> set[str]:
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
    for node in nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
    # Alias credit: local alias name -> original imported symbol.
    aliases: dict[str, str] = {}
    for node in nodes:
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


def _include_router_arg_names(nodes: list[ast.AST]) -> set[str]:
    """The LOCAL identifiers appearing inside an ``include_router(...)`` call in
    this module. ``app.include_router(multimedia_router)`` → {multimedia_router};
    ``app.include_router(make_thread_router())`` → {make_thread_router}. These
    are the local names THIS module mounts; mount resolution (``_is_mounted``)
    then ties each local name back to the module it was imported FROM, so a
    router product is mounted only when ITS module's product is the one mounted —
    never when an unrelated same-spelled ``router`` elsewhere is."""
    names: set[str] = set()

    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        is_include = (
            isinstance(fn, ast.Attribute) and fn.attr == "include_router"
        ) or (isinstance(fn, ast.Name) and fn.id == "include_router")
        if not is_include:
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
                elif isinstance(sub, ast.Attribute):
                    names.add(sub.attr)
    return names


def _called_local_names(nodes: list[ast.AST]) -> set[str]:
    """Local identifiers used as call targets in this module."""
    called: set[str] = set()
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    return called


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


def _import_map(importer: Path, nodes: list[ast.AST]) -> dict[str, set[tuple[str, str]]]:
    """local-name → {(defining-module-relpath, original-name)} for EVERY
    ``from … import …`` in this module (walked — so the function-local imports
    ``create_app`` uses at the MOUNT SITE are included). This ties a mounted
    local name back to the module it was imported from, closing the global
    bare-name collision. It is used only for the mount-SITE binding; the trusted
    re-export CHAIN uses ``_reexport_map`` (module-level only) so a
    function-scoped or conditional import cannot fabricate a re-export edge."""
    return _importfrom_edges(
        importer, [n for n in nodes if isinstance(n, ast.ImportFrom)]
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
    """``interfaces/**/api/*.py`` — the scope Check A draws router products
    from. Includes ``*_routes.py``, direct ``app`` route modules, and
    ``register_*_routes`` wrapper modules while excluding package barrels and
    tests."""
    if not _INTERFACES.exists():
        return []
    out: list[Path] = []
    for p in _INTERFACES.rglob("api/*.py"):
        if _is_excluded(p) or _is_test_path(p):
            continue
        if p.name == "__init__.py" or p.parent.name != "api":
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


_ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "websocket"}


def _route_decorator_base(dec: ast.expr) -> str | None:
    call = dec if isinstance(dec, ast.Call) else None
    target = call.func if call is not None else dec
    if not (
        isinstance(target, ast.Attribute)
        and target.attr in _ROUTE_METHODS
        and isinstance(target.value, ast.Name)
    ):
        return None
    return target.value.id


def _has_direct_app_route(tree: ast.Module) -> bool:
    """True when a module declares direct FastAPI app routes via ``@app.get`` /
    ``@app.post`` etc. These modules are already self-mounted app surfaces, not
    router products requiring ``include_router`` credit."""
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if _route_decorator_base(dec) == "app":
                return True
    return False


def _direct_app_route_handlers(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(_route_decorator_base(dec) == "app" for dec in node.decorator_list):
            names.add(node.name)
    return names


def _router_route_handlers(tree: ast.Module, router_names: set[str]) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(_route_decorator_base(dec) in router_names for dec in node.decorator_list):
            names.add(node.name)
    return names


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


def _reexport_targets(
    origin_rel: str,
    origin_name: str,
    reexport_map: dict[str, dict[str, set[tuple[str, str]]]],
    depth: int = _REEXPORT_MAX_DEPTH,
    seen: frozenset[tuple[str, str]] = frozenset(),
) -> set[tuple[str, str]]:
    """Confirmed module-level re-export targets for a call-site binding.

    Includes the original binding plus every target reached through the same
    fail-safe barrel edges Check A trusts for router mounts.
    """
    out = {(origin_rel, origin_name)}
    if depth <= 0 or (origin_rel, origin_name) in seen:
        return out
    seen = seen | {(origin_rel, origin_name)}
    for next_rel, next_name in reexport_map.get(origin_rel, {}).get(origin_name, ()):
        out |= _reexport_targets(
            next_rel, next_name, reexport_map, depth - 1, seen
        )
    return out


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
    # Same-module include_router is only a product mount when it is in reachable
    # module-scope code. A mount hidden inside an uncalled register_*_routes
    # wrapper is validated by Check C and must not credit Check A by itself.
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
    """Router products in ``interfaces/**/api/*.py`` that no module mounts
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


def _registration_wrappers(tree: ast.Module) -> list[tuple[str, int]]:
    """Module-level register wrappers that own at least one router mount."""
    wrappers: list[tuple[str, int]] = []
    for node in _reachable_function_nodes(tree).values():
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not (node.name.startswith("register_") and node.name.endswith("_routes")):
            continue
        if any(
            isinstance(call, ast.Call)
            and (
                (isinstance(call.func, ast.Attribute) and call.func.attr == "include_router")
                or (isinstance(call.func, ast.Name) and call.func.id == "include_router")
            )
            for call in _function_body_nodes(
                node, dead_guards=_dead_branch_guards(tree.body)
            )
        ):
            wrappers.append((node.name, node.lineno))
    return wrappers


def _wrapper_is_called(
    defining_rel: str,
    wrapper: str,
    called_local: dict[str, set[str]],
    import_map: dict[str, dict[str, set[tuple[str, str]]]],
    reexport_map: dict[str, dict[str, set[tuple[str, str]]]],
) -> bool:
    """Resolve a call target back to its defining registration wrapper."""
    for caller_rel, names in called_local.items():
        if caller_rel == defining_rel:
            # A same-module call is reachable. Recursive registration wrappers
            # are not a supported pattern and remain review-owned.
            if wrapper in names:
                return True
            continue
        for local in names:
            for origin_rel, origin_name in import_map.get(caller_rel, {}).get(local, ()):
                if _resolves_to(
                    origin_rel,
                    origin_name,
                    defining_rel,
                    wrapper,
                    reexport_map,
                ):
                    return True
    return False


def find_uncalled_registration_wrappers(
    trees: dict[Path, ast.Module],
    called_local: dict[str, set[str]],
    import_map: dict[str, dict[str, set[tuple[str, str]]]],
    reexport_map: dict[str, dict[str, set[tuple[str, str]]]],
) -> list[Finding]:
    """Router-owning register wrappers no product module ever calls."""
    findings: list[Finding] = []
    for path in _routes_files():
        tree = trees.get(path)
        if tree is None:
            continue
        rel = path.relative_to(_REPO).as_posix()
        for name, line in _registration_wrappers(tree):
            if _wrapper_is_called(rel, name, called_local, import_map, reexport_map):
                continue
            findings.append(
                (
                    path,
                    line,
                    f"router:registration-uncalled:{name}",
                    f"{rel}:{line}: reachability — registration wrapper '{name}' "
                    f"contains include_router() but is called by zero non-test "
                    f"product modules. Its router is locally assembled but absent "
                    f"from the running app. Call it from the app factory or remove "
                    f"the dormant surface.",
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


def _function_local_mounted_router_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    dead_guards: _DeadBranchGuards = _EMPTY_DEAD_BRANCH_GUARDS,
) -> set[str]:
    """Router locals mounted directly by this already-reachable function body."""
    shallow_body = _reachable_statement_nodes(
        list(node.body), route_bases=frozenset(), dead_guards=dead_guards
    )
    return _include_router_arg_names(shallow_body)


def _function_local_apirouter_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    dead_guards: _DeadBranchGuards = _EMPTY_DEAD_BRANCH_GUARDS,
) -> set[str]:
    """APIRouter locals built inside a reachable mounted router factory."""
    names: set[str] = set()
    shallow_body = _reachable_statement_nodes(
        list(node.body), route_bases=frozenset(), dead_guards=dead_guards
    )
    for stmt in shallow_body:
        if isinstance(stmt, ast.Assign) and _is_apirouter_call(stmt.value):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and _is_apirouter_call(stmt.value)
        ):
            names.add(stmt.target.id)
    return names


def _reachable_nodes_for_functions(
    tree: ast.Module,
    function_names: set[str],
    class_names: set[str] | frozenset[str] = frozenset(),
    *,
    route_bases: frozenset[str] = _DEFAULT_ROUTE_BASES,
    mounted_router_products: frozenset[str] = frozenset(),
) -> list[ast.AST]:
    functions = _reachable_function_nodes(tree)
    module_dead_guards = _dead_branch_guards(tree.body)
    nodes = _module_level_reachable_nodes(tree)
    for name in sorted(function_names):
        fn = functions.get(name)
        if fn is not None:
            function_dead_guards = _merge_dead_branch_guards(
                module_dead_guards, _dead_branch_guards(list(fn.body))
            )
            function_route_bases = set(route_bases)
            function_route_bases.update(
                _function_local_mounted_router_names(fn, function_dead_guards)
            )
            if name in mounted_router_products:
                function_route_bases.update(
                    _function_local_apirouter_names(fn, function_dead_guards)
                )
            nodes.extend(
                _function_body_nodes(
                    fn,
                    route_bases=frozenset(function_route_bases),
                    dead_guards=module_dead_guards,
                )
            )
    for class_name in sorted(class_names):
        cls = _reachable_class_nodes(tree).get(class_name)
        if cls is None:
            continue
        nodes.append(cls)
        for stmt in cls.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nodes.extend(_function_body_nodes(stmt, dead_guards=module_dead_guards))
    return nodes


def _initial_reachable_functions(rel: str, tree: ast.Module) -> set[str]:
    functions = _reachable_function_nodes(tree)
    roots = {
        name
        for name, node in functions.items()
        if (rel, name) in _DESIGNATED_APP_FACTORY_ROOTS and _is_app_factory(node)
    }
    roots |= _direct_app_route_handlers(tree)
    return roots


def _expand_reachable_functions(
    trees_by_rel: dict[str, ast.Module],
    paths_by_rel: dict[str, Path],
    reachable_functions: dict[str, set[str]],
    reachable_classes: dict[str, set[str]],
    *,
    route_bases_by_rel: dict[str, frozenset[str]] | None = None,
    mounted_router_products_by_rel: dict[str, frozenset[str]] | None = None,
) -> None:
    """Mutate reachable functions/classes to a fixed point over call edges."""
    reexport_map = {
        rel: _reexport_map(paths_by_rel[rel], tree)
        for rel, tree in trees_by_rel.items()
    }
    changed = True
    while changed:
        changed = False
        for rel, tree in trees_by_rel.items():
            nodes = _reachable_nodes_for_functions(
                tree,
                reachable_functions[rel],
                reachable_classes[rel],
                route_bases=(
                    route_bases_by_rel or {}
                ).get(rel, _DEFAULT_ROUTE_BASES),
                mounted_router_products=(
                    mounted_router_products_by_rel or {}
                ).get(rel, frozenset()),
            )
            called = _called_local_names(nodes)
            local_functions = _reachable_function_nodes(tree)
            local_classes = _reachable_class_nodes(tree)
            for name in called:
                if name in local_functions and name not in reachable_functions[rel]:
                    reachable_functions[rel].add(name)
                    changed = True
                if name in local_classes and name not in reachable_classes[rel]:
                    reachable_classes[rel].add(name)
                    changed = True

            imports = _import_map(paths_by_rel[rel], nodes)
            for local in called:
                for origin_rel, origin_name in imports.get(local, ()):
                    for target_rel, target_name in _reexport_targets(
                        origin_rel, origin_name, reexport_map
                    ):
                        target_tree = trees_by_rel.get(target_rel)
                        if target_tree is None:
                            continue
                        target_functions = _reachable_function_nodes(target_tree)
                        target_classes = _reachable_class_nodes(target_tree)
                        if (
                            target_name in target_functions
                            and target_name not in reachable_functions[target_rel]
                        ):
                            reachable_functions[target_rel].add(target_name)
                            changed = True
                        if (
                            target_name in target_classes
                            and target_name not in reachable_classes[target_rel]
                        ):
                            reachable_classes[target_rel].add(target_name)
                            changed = True


def _mounted_router_names_by_rel(
    trees_by_rel: dict[str, ast.Module],
    include_local: dict[str, set[str]],
    import_map: dict[str, dict[str, set[tuple[str, str]]]],
    reexport_map: dict[str, dict[str, set[tuple[str, str]]]],
) -> dict[str, set[str]]:
    mounted: dict[str, set[str]] = {}
    for path in _routes_files():
        rel = path.relative_to(_REPO).as_posix()
        tree = trees_by_rel.get(rel)
        if tree is None:
            continue
        for name, _line in _router_products(path, tree):
            if _is_mounted(rel, name, include_local, import_map, reexport_map):
                mounted.setdefault(rel, set()).add(name)
    return mounted


def _build_reachability(
    trees: dict[Path, ast.Module],
) -> dict[str, _Reachability]:
    trees_by_rel = {path.relative_to(_REPO).as_posix(): tree for path, tree in trees.items()}
    paths_by_rel = {path.relative_to(_REPO).as_posix(): path for path in trees}
    reachable_functions = {
        rel: _initial_reachable_functions(rel, tree)
        for rel, tree in trees_by_rel.items()
    }
    reachable_classes = {rel: set[str]() for rel in trees_by_rel}

    _expand_reachable_functions(
        trees_by_rel, paths_by_rel, reachable_functions, reachable_classes
    )

    include_local = {
        rel: _include_router_arg_names(
            _reachable_nodes_for_functions(
                tree, reachable_functions[rel], reachable_classes[rel]
            )
        )
        for rel, tree in trees_by_rel.items()
    }
    import_map = {
        rel: _import_map(
            paths_by_rel[rel],
            _reachable_nodes_for_functions(
                tree, reachable_functions[rel], reachable_classes[rel]
            ),
        )
        for rel, tree in trees_by_rel.items()
    }
    reexport_map = {
        rel: _reexport_map(paths_by_rel[rel], tree) for rel, tree in trees_by_rel.items()
    }

    mounted_router_names = _mounted_router_names_by_rel(
        trees_by_rel, include_local, import_map, reexport_map
    )
    mounted_route_bases_by_rel = {
        rel: frozenset(_DEFAULT_ROUTE_BASES | router_names)
        for rel, router_names in mounted_router_names.items()
    }
    mounted_router_products_by_rel = {
        rel: frozenset(router_names) for rel, router_names in mounted_router_names.items()
    }
    for rel, router_names in mounted_router_names.items():
        route_handlers = _router_route_handlers(trees_by_rel[rel], router_names)
        before = set(reachable_functions[rel])
        reachable_functions[rel].update(route_handlers)
        if reachable_functions[rel] != before:
            _expand_reachable_functions(
                trees_by_rel,
                paths_by_rel,
                reachable_functions,
                reachable_classes,
                route_bases_by_rel=mounted_route_bases_by_rel,
                mounted_router_products_by_rel=mounted_router_products_by_rel,
            )

    _expand_reachable_functions(
        trees_by_rel,
        paths_by_rel,
        reachable_functions,
        reachable_classes,
        route_bases_by_rel=mounted_route_bases_by_rel,
        mounted_router_products_by_rel=mounted_router_products_by_rel,
    )

    return {
        rel: _Reachability(
            nodes=_reachable_nodes_for_functions(
                tree,
                reachable_functions[rel],
                reachable_classes[rel],
                route_bases=mounted_route_bases_by_rel.get(rel, _DEFAULT_ROUTE_BASES),
                mounted_router_products=mounted_router_products_by_rel.get(
                    rel, frozenset()
                ),
            ),
            functions=frozenset(reachable_functions[rel]),
            classes=frozenset(reachable_classes[rel]),
        )
        for rel, tree in trees_by_rel.items()
    }


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
    """All router, registration-wrapper, and enforcement reachability findings."""
    product_files = _product_py_files()
    trees: dict[Path, ast.Module] = {}
    called_local: dict[str, set[str]] = {}
    import_map: dict[str, dict[str, set[tuple[str, str]]]] = {}
    reexport_map: dict[str, dict[str, set[tuple[str, str]]]] = {}
    referenced: set[str] = set()
    for f in product_files:
        tree = _parse(f)
        if tree is None:
            continue
        trees[f] = tree
    reachability = _build_reachability(trees)

    for f, tree in trees.items():
        rel = f.relative_to(_REPO).as_posix()
        nodes = reachability[rel].nodes
        called_local[rel] = _called_local_names(nodes)
        import_map[rel] = _import_map(f, nodes)
        reexport_map[rel] = _reexport_map(f, tree)
        referenced |= _reachability_reference_names(nodes)

    include_local: dict[str, set[str]] = {}
    for f in trees:
        rel = f.relative_to(_REPO).as_posix()
        include_local[rel] = _include_router_arg_names(reachability[rel].nodes)
    routers = find_unmounted_routers(trees, include_local, import_map, reexport_map)
    wrappers = find_uncalled_registration_wrappers(
        trees, called_local, import_map, reexport_map
    )
    exports = find_uncalled_enforcement_exports(trees, referenced)
    return routers + wrappers + exports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reachability_gate_py",
        description=(
            "Flag stranded backend code: unmounted routers, uncalled route "
            "registration wrappers, and uncalled enforcement exports. "
            "Hard-blocking with a shrink-only baseline."
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
            f"fairness/CANNOT-catch policy. This is a hard CI gate; do not "
            f"swallow this exit code.",
            file=sys.stderr,
        )

    return rc


if __name__ == "__main__":
    sys.exit(main())
