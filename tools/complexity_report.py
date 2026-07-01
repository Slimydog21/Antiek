"""complexity_report.py — Ousterhout deep/shallow module ranking (AOD SPR-01).

The measuring instrument for the *Antiek × Ousterhout* deep-modules run. It
reads John Ousterhout's *A Philosophy of Software Design* (Ch. 4) as a metric
and turns it on ``substrate/``: for every module it computes an **interface
surface** proxy and an **implementation depth** proxy, forms the deep/shallow
**ratio = interface ÷ depth**, weights it by recent git churn, and ranks the
modules that are *shallow AND hot*. The output ``reports/complexity/ranking.json``
is the keystone SPR-02..07 consume.

    A DEEP module (Ousterhout's ideal): a small interface over a powerful
    implementation → LOW ratio.  A SHALLOW module (the offender): an interface
    nearly as wide as its implementation → HIGH ratio.

This is deliberately NOT radon's cyclomatic complexity. A generic complexity
number would rank ``substrate/dedup.py`` (720 deep lines behind a handful of
public functions) as a top offender, which is exactly backwards under
Ousterhout. The branch-point count is kept as an *input column* (the "generic
complexity" signal) so calibration can confirm the *ratio* — not raw
branch count — is what ranks.

Read-only: pure ``ast.parse`` + one ``git log`` pass. It imports no substrate
module (substrate has import-time side effects and host-only constraints) and
changes no substrate behavior.

------------------------------------------------------------------------------
METRIC DEFINITION (verbatim — downstream sprints depend on this)
------------------------------------------------------------------------------

interface_surface = public_symbols + param_count
  public_symbols = module-level def/async def/class  +  each class's public
                   methods  +  any name listed in __all__ that is a bare
                   constant (0-param symbol).
  param_count    = sum of parameters across public callables (module funcs,
                   public methods, and each class's explicit __init__), where
                   *args and **kwargs each count 1 and self/cls are excluded.

depth = statements + branch_points
  statements    = every ast.stmt node in the module and all function/method
                  bodies, MINUS docstrings (a bare str Expr that opens a
                  module/func/class body). Comments are not in the AST.
  branch_points = If, For, AsyncFor, While, Try, TryStar, each ExceptHandler,
                  IfExp (ternary), Match + each case, each BoolOp contributes
                  (len(values) - 1), and each comprehension `if` clause.

ratio      = interface_surface / max(depth, 1)     (LOW = deep, HIGH = shallow)
rank_score = ratio * log1p(churn_commit_count)     (shallow AND hot floats up)

------------------------------------------------------------------------------
AST EDGE-CASE DECISIONS (rigor #3 — enumerated before counting, each defended)
------------------------------------------------------------------------------

* ``__all__``            — authoritative when present (incl. augmented/conditional
                           forms: the union of every string literal ever assigned
                           to __all__ is taken, so `__all__ += [...]` is honored).
                           Overrides the leading-underscore heuristic.
* leading underscore     — private when no __all__; excluded from public_symbols.
* ``__init__``           — its params ARE the constructor interface a caller must
                           learn, so they count toward param_count; __init__ is
                           NOT itself a public symbol (the class already is).
* other dunders          — protocol methods (__eq__, __enter__, ...) are excluded
                           from both symbol and param counts: they are conformance,
                           not the direct interface a caller reads.
* ``@property``          — one symbol, ZERO params (a caller sees an attribute,
                           not a call). Setter/deleter of the same name add nothing.
* ``@overload``          — a name is counted once; params are read from the real
                           implementation (or the first stub if impl absent).
* nested classes         — a public nested class counts as one symbol; we do not
                           recurse into its methods (bounds the surface; a nested
                           class is usually an internal detail).
* dataclass / model      — fields are NOT counted as params. milestone-1 counts
   fields                  "parameters across public *callables*"; a synthesized
                           __init__ is not an explicit AST def, so there is no
                           callable to read. A class = 1 symbol; only an EXPLICIT
                           __init__ contributes params. (This is also what keeps
                           the deep anchors deep: dedup/results carry several
                           frozen dataclasses but their bodies dominate depth.)
* enum members           — class-level assignments, not methods → not counted as
                           symbols (KeyType/Confidence stay 1 symbol each).
* module-level constants  — NOT interface surface unless named in __all__ (the
                           milestone-1 definition is def/class + public methods).
* ``TYPE_CHECKING`` imports — imports are never interface; ignored throughout.
* re-export module       — body is imports + __all__ with no module-level def/class
                           → kind="reexport": its surface is real but it is a
                           known-acceptable shallow pattern, tagged so it does not
                           crowd the genuine-offender head.
* ``__init__.py``        — kind="package_init" (same rationale as reexport).
* syntax error           — recorded with kind="parse_error" and zeroed metrics;
                           the run continues (a broken module never crashes the
                           report — the error is defined out of existence).

Matches the tools/lints house shape: schema_version, generated_at, deterministic
sort (indent=2, sort_keys=True, trailing newline). CLI mirrors tools/lints.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "SCHEMA_VERSION",
    "ModuleMetrics",
    "analyze_source",
    "interface_surface",
    "implementation_depth",
    "git_churn",
    "build_report",
    "main",
]

SCHEMA_VERSION = 1

# Default churn window. ~500 commits ≈ the last few weeks of the compounding-loop
# cadence on this repo — long enough to be a stable "recently hot" signal, short
# enough that year-old activity does not dominate. A number without an origin is
# an anti-pattern (rigor #1): this one is a choice, stated, not a discovered truth.
DEFAULT_CHURN_WINDOW = 500

# Interface-surface weights (the "class-cohesion" refinement — SPR-01 milestone-4).
# The spec's default surface = (public symbols) + (params) counts every method as
# a full independent abstraction. That mis-ranks a *cohesive value type* — e.g.
# substrate/results.py (a Result monad: ~16 one-line methods on Ok/Err) — as
# shallow, when Ousterhout would call it deep: a class is ONE abstraction and its
# methods are a vocabulary the caller learns in that context, not N separate
# things to discover. So a public method costs less to learn than a top-level
# name, and a parameter is a sub-unit of a single callable's signature (half a
# learning unit), not a whole abstraction. These weights are a *choice*, stated
# here, and validated by milestone-4 calibration + an independent second sample —
# not discovered truth. A free-function god-module (all top-level, W=1.0) stays
# shallow; only cohesive classes get the discount, which is the Ousterhout-correct
# distinction. Set W_METHOD=W_PARAM=1.0 to recover the spec's flat default.
W_TOP_SYMBOL = 1.0
W_METHOD = 0.5
W_PARAM = 0.5

# Master fence prefixes (relative to the substrate root). Modules owned by an
# in-flight spec's run must never be *refactored* by a downstream AOD sprint —
# they may be *reported*. Sourced from the master spec fence table; unioned at
# run time with substrate/ paths cited in the globbed spec index.html files.
MASTER_FENCE_PREFIXES: tuple[str, ...] = (
    "research_bridge/",
    "write/",
    "edit/",
    "speak/",
    "flywheel/",
    "cross_graph/",
    "coordination/",
    "loop_3/",
    "anti_gaming/",
    "dispatch/",
    "marketplace/",
    "billing/",
    "legal/",
    "ad/",
    "ads/",
    "multi_user/",
    "federation/",
    "graph_per_user/",
    "collective_graph/",
    "public_graph/",
)

# Branch-point node types counted once each (the "generic complexity" column).
_BRANCH_ONCE: tuple[type[ast.AST], ...] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.ExceptHandler,
    ast.IfExp,
    ast.Match,
    ast.match_case,
)
# ast.TryStar exists on 3.11+; add it defensively so except* counts as a branch.
if hasattr(ast, "TryStar"):
    _BRANCH_ONCE = (*_BRANCH_ONCE, ast.TryStar)

_DUNDER_INTERFACE_KEEP = frozenset({"__init__"})  # constructor params count; name itself not a symbol


@dataclass(frozen=True)
class ModuleMetrics:
    """One module's row in the ranking. Frozen + fully ordered by construction
    so the report file diffs cleanly across runs."""

    module: str
    kind: str  # normal | reexport | package_init | parse_error
    top_symbols: int
    method_symbols: int
    public_symbols: int
    param_count: int
    interface_surface: float
    flat_interface_surface: int
    statements: int
    branch_points: int
    depth: int
    ratio: float
    flat_ratio: float
    churn: int
    rank_score: float
    fenced: bool
    parse_error: str | None = None


# --------------------------------------------------------------------------- #
# Interface surface (numerator)                                               #
# --------------------------------------------------------------------------- #


def _decorator_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for dec in getattr(node, "decorator_list", []) or []:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _count_params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Parameters a caller must learn. self/cls excluded; *args and **kwargs
    each count 1; positional-only, positional, and keyword-only count equally."""
    a = fn.args
    named = [*a.posonlyargs, *a.args, *a.kwonlyargs]
    count = sum(1 for arg in named if arg.arg not in ("self", "cls"))
    if a.vararg is not None:
        count += 1
    if a.kwarg is not None:
        count += 1
    return count


def _extract_all_names(tree: ast.Module) -> set[str] | None:
    """Union of every string literal ever assigned to a module-level __all__
    (handles __all__ = [...], __all__ += [...], and conditional reassignment).
    Returns None if __all__ is not defined."""
    found = False
    names: set[str] = set()

    def harvest(value: ast.AST) -> None:
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            for elt in value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    names.add(elt.value)

    for node in tree.body:
        targets: list[ast.AST] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AugAssign) or isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            found = True
            if value is not None:
                harvest(value)
    return names if found else None


def _is_public(name: str, all_names: set[str] | None) -> bool:
    if all_names is not None:
        return name in all_names
    return not name.startswith("_")


def _tally_callables(
    funcs: list[ast.FunctionDef | ast.AsyncFunctionDef],
) -> tuple[int, int]:
    """(symbols, params) for a list of already-public callables at one scope.
    A name is ONE symbol however many defs it has (@overload stubs + impl, or
    @property getter + setter/deleter all collapse to one). Params come from the
    concrete implementation (the def without @overload/@property/setter/deleter);
    a @property name contributes 0 params (a caller sees an attribute)."""
    by_name: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    order: list[str] = []
    for fn in funcs:
        if fn.name not in by_name:
            by_name[fn.name] = []
            order.append(fn.name)
        by_name[fn.name].append(fn)

    params = 0
    for name in order:
        defs = by_name[name]
        is_property = any("property" in _decorator_names(fn) for fn in defs)
        if is_property:
            continue  # 0 params — an attribute from the caller's view
        impl = None
        for fn in defs:
            decs = _decorator_names(fn)
            if not ({"overload", "setter", "deleter"} & decs):
                impl = fn
        params += _count_params(impl if impl is not None else defs[0])
    return len(order), params


def _class_public_members(cls: ast.ClassDef) -> tuple[int, int]:
    """(public_method_symbols, param_count) for one class body. __init__ params
    count toward param_count but __init__ is not a symbol; other dunders are
    ignored; @property is 1 symbol / 0 params; @overload names counted once; a
    public nested class is 1 symbol (methods not recursed)."""
    init_params = 0
    methods: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    nested_public_classes = 0
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if name == "__init__":
                init_params += _count_params(node)  # constructor interface, not a symbol
            elif name.startswith("__") and name.endswith("__"):
                continue  # protocol dunder — conformance, not learned interface
            elif name.startswith("_"):
                continue  # private helper
            else:
                methods.append(node)
        elif isinstance(node, ast.ClassDef):
            if _is_public(node.name, None):
                nested_public_classes += 1  # one symbol; internals not recursed
    m_symbols, m_params = _tally_callables(methods)
    return m_symbols + nested_public_classes, m_params + init_params


def interface_surface(tree: ast.Module) -> tuple[int, int, int]:
    """(top_symbols, method_symbols, params) for the whole module.

    top_symbols  = module-level public def/class + __all__-exported bare constants
    method_symbols = public methods across public classes (class-cohesion discount)
    params       = all counted parameters (top-level callables + __init__ + methods)
    The weighted surface is composed by the caller via W_TOP_SYMBOL/W_METHOD/W_PARAM."""
    all_names = _extract_all_names(tree)
    top_funcs = [
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _is_public(n.name, all_names)
    ]
    top_symbols, params = _tally_callables(top_funcs)
    method_symbols = 0

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and _is_public(node.name, all_names):
            top_symbols += 1  # the class itself is a top-level abstraction
            m_syms, m_params = _class_public_members(node)
            method_symbols += m_syms
            params += m_params

    # Names exported via __all__ that are bare constants (not def/class) are real
    # interface a caller imports — count each as a 0-param top-level symbol.
    if all_names is not None:
        defined = {
            n.name
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        top_symbols += sum(1 for name in all_names if name not in defined)

    return top_symbols, method_symbols, params


# --------------------------------------------------------------------------- #
# Implementation depth (denominator)                                          #
# --------------------------------------------------------------------------- #


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """id() of every Expr node that is a docstring (opens a module/func/class
    body with a bare string constant) — excluded from the statement count."""
    doc_ids: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and body:
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                doc_ids.add(id(first))
    return doc_ids


def implementation_depth(tree: ast.Module) -> tuple[int, int]:
    """(statements, branch_points). statements excludes docstrings; branch_points
    is the generic-complexity column (kept separate so it does not rank)."""
    doc_ids = _docstring_nodes(tree)
    statements = 0
    branches = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and id(node) not in doc_ids:
            statements += 1
        if isinstance(node, _BRANCH_ONCE):
            branches += 1
        elif isinstance(node, ast.BoolOp):
            branches += max(len(node.values) - 1, 0)
        elif isinstance(node, ast.comprehension):
            branches += len(node.ifs)
    return statements, branches


# --------------------------------------------------------------------------- #
# Kind classification                                                         #
# --------------------------------------------------------------------------- #


def _classify_kind(path: Path, tree: ast.Module) -> str:
    if path.name == "__init__.py":
        return "package_init"
    has_def = any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for n in tree.body
    )
    if not has_def:
        return "reexport"
    return "normal"


def analyze_source(path: Path, source: str) -> dict[str, Any]:
    """Static AST analysis of one module. Never raises on bad syntax."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {
            "kind": "parse_error",
            "top_symbols": 0,
            "method_symbols": 0,
            "public_symbols": 0,
            "param_count": 0,
            "interface_surface": 0.0,
            "flat_interface_surface": 0,
            "statements": 0,
            "branch_points": 0,
            "depth": 1,
            "parse_error": f"{exc.msg} (line {exc.lineno})",
        }
    top_symbols, method_symbols, params = interface_surface(tree)
    statements, branches = implementation_depth(tree)
    depth = max(statements + branches, 1)  # divide-by-zero defined out of existence
    surface = W_TOP_SYMBOL * top_symbols + W_METHOD * method_symbols + W_PARAM * params
    # Flat (unweighted) surface = the spec's default. Carried alongside the
    # cohesion-discounted score so a reader can see exactly how much the discount
    # moved each module and confirm the weights are not cherry-picked (rigor #1;
    # independent-verifier request).
    flat_surface = top_symbols + method_symbols + params
    return {
        "kind": _classify_kind(path, tree),
        "top_symbols": top_symbols,
        "method_symbols": method_symbols,
        "public_symbols": top_symbols + method_symbols,
        "param_count": params,
        "interface_surface": round(surface, 3),
        "flat_interface_surface": flat_surface,
        "statements": statements,
        "branch_points": branches,
        "depth": depth,
        "parse_error": None,
    }


# --------------------------------------------------------------------------- #
# Churn (git)                                                                 #
# --------------------------------------------------------------------------- #


def git_churn(
    repo: Path, window: int
) -> tuple[dict[str, int], dict[str, Any]]:
    """Map repo-relative posix path → number of commits (within the window) that
    touched it, via a single `git log --name-only` pass. Returns (counts, meta).
    Degrades honestly if git is unavailable or the repo has < window commits."""
    meta: dict[str, Any] = {
        "window_commits": window,
        "method": "single `git log --name-only` pass, one commit = one increment per path (no --follow; renames start fresh)",
        "fallback": False,
        "actual_commits_scanned": 0,
        "note": "",
    }
    counts: dict[str, int] = {}
    try:
        total = int(
            subprocess.run(
                ["git", "-C", str(repo), "rev-list", "--count", "HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as exc:
        meta["fallback"] = True
        meta["note"] = f"git unavailable ({type(exc).__name__}); churn is all-zero, rank_score collapses to 0"
        return counts, meta

    cmd = ["git", "-C", str(repo), "log", "--name-only", "--pretty=format:%H"]
    if total >= window:
        cmd.insert(4, f"-n{window}")
        meta["actual_commits_scanned"] = window
    else:
        meta["fallback"] = True
        meta["actual_commits_scanned"] = total
        meta["note"] = f"repo has {total} < {window} commits; used all-commit churn"

    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        meta["fallback"] = True
        meta["note"] = f"git log failed ({type(exc).__name__}); churn all-zero"
        return counts, meta

    hash_re = re.compile(r"^[0-9a-f]{40}$")
    for line in out.splitlines():
        line = line.strip()
        if not line or hash_re.match(line):
            continue
        counts[line] = counts.get(line, 0) + 1
    return counts, meta


# --------------------------------------------------------------------------- #
# Fence                                                                       #
# --------------------------------------------------------------------------- #


def build_fence(
    root_repo: Path, substrate_root: str, fence_source: str
) -> tuple[list[str], dict[str, Any]]:
    """Return (fence_prefixes, meta). Prefixes are repo-relative posix paths a
    module path is tested against with str.startswith."""
    prefixes: set[str] = {f"{substrate_root}/{p}" for p in MASTER_FENCE_PREFIXES}
    globbed: list[str] = []
    src = (root_repo / fence_source) if not Path(fence_source).is_absolute() else Path(fence_source)
    cite_re = re.compile(r"substrate/[A-Za-z0-9_./\-]+")
    if src.exists():
        for index in sorted(src.glob("*/index.html")):
            globbed.append(str(index.relative_to(root_repo)) if _is_relative(index, root_repo) else str(index))
            try:
                text = index.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for hit in cite_re.findall(text):
                # keep directory prefixes and exact file paths alike
                prefixes.add(hit if hit.endswith("/") else hit)
    meta: dict[str, Any] = {
        "master_prefixes": [f"{substrate_root}/{p}" for p in MASTER_FENCE_PREFIXES],
        "source_glob": f"{fence_source}/*/index.html",
        "index_files_found": globbed,
        "dated": datetime.now(UTC).date().isoformat(),
    }
    return sorted(prefixes), meta


def _is_relative(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_fenced(module_path: str, fence_prefixes: list[str]) -> bool:
    for p in fence_prefixes:
        if module_path == p:
            return True  # exact file citation
        if module_path.startswith(p if p.endswith("/") else p + "/"):
            return True  # directory-prefix fence
    return False


# --------------------------------------------------------------------------- #
# Report assembly                                                             #
# --------------------------------------------------------------------------- #


def _tool_commit(repo: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def build_report(
    *,
    root_repo: Path,
    substrate_root: str,
    window: int,
    fence_source: str,
    top: int,
    calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    substrate_dir = root_repo / substrate_root
    churn_counts, churn_meta = git_churn(root_repo, window)
    fence_prefixes, fence_meta = build_fence(root_repo, substrate_root, fence_source)

    rows: list[ModuleMetrics] = []
    for py in sorted(substrate_dir.rglob("*.py")):
        rel = py.relative_to(root_repo).as_posix()
        source = py.read_text(encoding="utf-8", errors="replace")
        a = analyze_source(py, source)
        depth = int(a["depth"])  # already floored at 1
        surface = float(a["interface_surface"])
        flat_surface = int(a["flat_interface_surface"])
        ratio = surface / depth
        flat_ratio = flat_surface / depth
        churn = churn_counts.get(rel, 0)
        rank_score = ratio * math.log1p(churn)
        rows.append(
            ModuleMetrics(
                module=rel,
                kind=str(a["kind"]),
                top_symbols=int(a["top_symbols"]),
                method_symbols=int(a["method_symbols"]),
                public_symbols=int(a["public_symbols"]),
                param_count=int(a["param_count"]),
                interface_surface=surface,
                flat_interface_surface=flat_surface,
                statements=int(a["statements"]),
                branch_points=int(a["branch_points"]),
                depth=depth,
                ratio=round(ratio, 6),
                flat_ratio=round(flat_ratio, 6),
                churn=churn,
                rank_score=round(rank_score, 6),
                fenced=_is_fenced(rel, fence_prefixes),
                parse_error=a["parse_error"],
            )
        )

    # Deterministic order: rank_score desc, ratio desc, module asc.
    rows.sort(key=lambda m: (-m.rank_score, -m.ratio, m.module))

    # top_unfenced = the list SPR-04 picks a refactor target from: unfenced AND a
    # genuine "normal" module (reexport/package_init/parse_error are not
    # refactorable offenders). Documented in the header so the filter is auditable.
    top_unfenced = [
        asdict(m)
        for m in rows
        if not m.fenced and m.kind == "normal"
    ][:top]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "tool": "tools/complexity_report.py",
        "tool_commit": _tool_commit(root_repo),
        "root": substrate_root,
        "module_count": len(rows),
        "metric": {
            "interface_surface": (
                f"{W_TOP_SYMBOL}*top_symbols + {W_METHOD}*method_symbols + {W_PARAM}*params. "
                "top_symbols = module-level public def/class + __all__-exported constants; "
                "method_symbols = public methods across public classes (class-cohesion discount: "
                "a class is one abstraction, its methods a vocabulary learned in-context); "
                "params = explicit callable + __init__ params (*args/**kwargs=1; self/cls excluded; "
                "@property=0; dataclass/model fields NOT counted). Set W_METHOD=W_PARAM=1.0 for the flat default."
            ),
            "weights": {"W_TOP_SYMBOL": W_TOP_SYMBOL, "W_METHOD": W_METHOD, "W_PARAM": W_PARAM},
            "depth": "non-docstring ast.stmt nodes + branch_points {If,For,AsyncFor,While,Try,TryStar,ExceptHandler,IfExp,Match,case,BoolOp(n-1),comprehension-ifs}",
            "ratio": "interface_surface / max(depth, 1)  — LOW = deep (Ousterhout ideal), HIGH = shallow (offender)",
            "rank_score": "ratio * log1p(churn)  — surfaces shallow AND hot; churn=0 → rank_score=0 (untouched shallow modules are harmless)",
            "not_cyclomatic": "branch_points is an input column only; the ratio ranks, so a deep module (dedup.py) ranks LOW despite high branch count",
        },
        "churn": churn_meta,
        "fence": {
            **fence_meta,
            "top_unfenced_filter": "unfenced AND kind=='normal' (reexport/package_init/parse_error excluded as non-refactorable)",
        },
        "calibration": calibration or {
            "status": "pending",
            "note": "milestone-4 hand-judgment lives in ranking.md; re-run with --calibration-file to embed the X/10 verdict here",
        },
        "modules": [asdict(m) for m in rows],
        "top_unfenced": top_unfenced,
    }


# --------------------------------------------------------------------------- #
# Markdown rendering                                                          #
# --------------------------------------------------------------------------- #


def _rank_of(modules: list[dict[str, Any]], name: str) -> int:
    for i, m in enumerate(modules, 1):
        if m["module"] == name:
            return i
    return -1


def render_markdown(report: dict[str, Any], top: int) -> str:
    modules: list[dict[str, Any]] = report["modules"]
    churn = report["churn"]
    cal = report["calibration"]
    n = len(modules)
    normal = [m for m in modules if m["kind"] == "normal"]
    shells = [m for m in modules if m["kind"] in ("reexport", "package_init")]
    lines: list[str] = []
    lines.append("# Substrate complexity ranking — Ousterhout deep/shallow lens")
    lines.append("")
    lines.append(f"- Generated: `{report['generated_at']}`  ·  tool commit `{str(report['tool_commit'])[:12]}`")
    lines.append(f"- Modules scanned: **{n}** under `{report['root']}/` ({len(normal)} normal · {len(shells)} re-export/package shells)")
    lines.append(
        f"- Churn window: N={churn['window_commits']} "
        f"(scanned {churn['actual_commits_scanned']}"
        f"{', FALLBACK' if churn['fallback'] else ''})  ·  {churn['method']}"
    )
    if churn.get("note"):
        lines.append(f"  - churn note: {churn['note']}")
    lines.append(f"- Fence dated `{report['fence']['dated']}`; index files globbed: {len(report['fence']['index_files_found'])}")
    lines.append("")
    lines.append("**Metric** — `ratio = interface_surface / max(depth,1)` (LOW=deep, HIGH=shallow); "
                 "`rank_score = ratio × log1p(churn)`. Interface surface applies a class-cohesion discount "
                 f"(top-symbol=×{report['metric']['weights']['W_TOP_SYMBOL']}, method=×{report['metric']['weights']['W_METHOD']}, param=×{report['metric']['weights']['W_PARAM']}). "
                 "Branch count is an input column, not the rank. Re-export/package shells are scored separately below.")
    lines.append("")
    lines.append(f"## Top {top} genuine offenders (kind=normal — the shallow-and-hot head)")
    lines.append("")
    lines.append("| # | module | surface | depth | ratio | flat_ratio | churn | rank | fenced |")
    lines.append("|--:|--------|--------:|------:|------:|-----------:|------:|-----:|:------:|")
    for i, m in enumerate(normal[:top], 1):
        lines.append(
            f"| {i} | `{m['module']}` | {m['interface_surface']:g} | {m['depth']} | "
            f"{m['ratio']:.3f} | {m['flat_ratio']:.3f} | {m['churn']} | {m['rank_score']:.3f} | "
            f"{'🔒' if m['fenced'] else ''} |"
        )
    lines.append("")
    lines.append("## Re-export / package shells (scored separately — known-acceptable shallow pattern)")
    lines.append("")
    lines.append(f"{len(shells)} modules whose body is imports + `__all__` (or `__init__.py` aggregation): "
                 "real interface surface, but hides no implementation, so not a refactor target. "
                 "Excluded from `top_unfenced` and from the offender head above.")
    lines.append("")
    lines.append("## top_unfenced head (SPR-04 refactor-target candidates)")
    lines.append("")
    lines.append("_Filter: " + str(report["fence"]["top_unfenced_filter"]) + "_")
    lines.append("")
    tu: list[dict[str, Any]] = report["top_unfenced"]
    if tu:
        lines.append("| # | module | ratio | churn | rank |")
        lines.append("|--:|--------|------:|------:|-----:|")
        for i, m in enumerate(tu[:top], 1):
            lines.append(f"| {i} | `{m['module']}` | {m['ratio']:.3f} | {m['churn']} | {m['rank_score']:.3f} |")
    else:
        lines.append("_(none — every candidate was fenced)_")
    lines.append("")
    lines.append("## Calibration (milestone 4 — proxy vs. hand judgment)")
    lines.append("")
    if isinstance(cal, dict) and cal.get("agreement"):
        lines.append(f"**Agreement: {cal['agreement']}**  ·  {cal.get('summary', '')}")
        lines.append("")
        lines.append("| module | alleged | proxy rank | verdict | note |")
        lines.append("|--------|---------|-----------|---------|------|")
        for row in cal.get("table", []):
            lines.append(
                f"| `{row['module']}` | {row.get('alleged','')} | {row.get('proxy_rank','')} | "
                f"{row.get('verdict','')} | {row.get('note', '')} |"
            )
        if cal.get("anchor_divergences"):
            lines.append("")
            lines.append("**Documented anchor divergences (rigor #1 — not gamed):**")
            for d in cal["anchor_divergences"]:
                lines.append(f"- {d}")
    else:
        lines.append("_pending — see handoff; re-run with `--calibration-file` to embed._")
    lines.append("")
    lines.append("## Full positional index (all modules, by rank_score — greppable)")
    lines.append("")
    lines.append("| rank | module | ratio | churn | rank_score | kind | fenced |")
    lines.append("|-----:|--------|------:|------:|-----------:|------|:------:|")
    for i, m in enumerate(modules, 1):
        lines.append(
            f"| {i} | `{m['module']}` | {m['ratio']:.3f} | {m['churn']} | {m['rank_score']:.3f} | "
            f"{m['kind']} | {'🔒' if m['fenced'] else ''} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def _write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="complexity_report",
        description="Rank substrate modules by Ousterhout deep/shallow ratio × churn.",
    )
    parser.add_argument("--root", default="substrate", help="module root under the repo (default: substrate)")
    parser.add_argument("--repo", default=".", type=Path, help="repo root for churn + fence (default: cwd)")
    parser.add_argument("--out", default="reports/complexity/ranking.json", type=Path, help="ranking.json path")
    parser.add_argument("--top", default=30, type=int, help="rows in ranking.md + top_unfenced length")
    parser.add_argument("--window", default=DEFAULT_CHURN_WINDOW, type=int, help="churn window in commits")
    parser.add_argument("--fence-source", default="specs", help="dir globbed for */index.html fence citations")
    parser.add_argument("--format", choices=("json", "md"), default="json", help="stdout format")
    parser.add_argument("--calibration-file", type=Path, default=None, help="optional calibration JSON to embed")
    parser.add_argument("--check-regression", action="store_true", help="reserved for SPR-07")
    args = parser.parse_args(argv)

    if args.check_regression:
        print("--check-regression: not implemented in SPR-01 (reserved for SPR-07).", file=sys.stderr)
        return 0

    repo = args.repo.resolve()
    substrate_dir = repo / args.root
    if not substrate_dir.is_dir():
        print(f"✗ root not found: {substrate_dir}", file=sys.stderr)
        return 2

    calibration: dict[str, Any] | None = None
    if args.calibration_file is not None:
        try:
            calibration = json.loads(args.calibration_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"✗ could not read --calibration-file: {exc}", file=sys.stderr)
            return 2

    report = build_report(
        root_repo=repo,
        substrate_root=args.root,
        window=args.window,
        fence_source=args.fence_source,
        top=args.top,
        calibration=calibration,
    )

    _write_json(args.out, report)
    md_path = args.out.parent / "ranking.md"
    md_path.write_text(render_markdown(report, args.top), encoding="utf-8")

    if args.format == "md":
        sys.stdout.write(render_markdown(report, args.top))
    else:
        tu = report["top_unfenced"]
        head = tu[0]["module"] if tu else "(none)"
        print(
            f"wrote {args.out} ({report['module_count']} modules) + {md_path}; "
            f"top_unfenced[0] = {head}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
