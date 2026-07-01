"""info_hiding.py — Ousterhout information-hiding leak audit (AOD SPR-02).

Ousterhout, Ch. 5: the most important technique for managing complexity is
**information hiding** — a module encapsulates its design decisions so callers
depend only on its interface. The failure mode is **information leakage**: a
piece of a module's internal knowledge escapes and becomes embedded in a caller,
coupling the two so the module can no longer change freely. The code still
*works* — it has just quietly lost the freedom to evolve.

This is a READ-ONLY AST audit. It reports leaks with `path:line` precision; it
fixes nothing (SPR-03/04 close leaks, test-locked). It is DELIBERATELY DISTINCT
from `tools/lint/boundary_check.py`, which forbids concrete vendor-SDK imports
outside `substrate/dispatch/providers/` (the §16 dispatch boundary). That guards
vendor coupling; this guards every module's information-hiding boundary — two
different leak classes.

------------------------------------------------------------------------------
THE THREE LEAK CATEGORIES (milestone 1 — pinned before the walker)
------------------------------------------------------------------------------

L1 — PRIVATE-NAME IMPORT
    A module imports, from another first-party module, a name that is private in
    that module: the imported name (BEFORE any `as` alias) is underscore-prefixed,
    OR the owning module declares `__all__`, defines the name, and did NOT export
    it. The importer now depends on the exporter's internals.
      LEAK:     from substrate.dedup import _select_canonical
      NOT A LEAK (near-miss): from substrate.ip_holders import list_all as _x
                              — the IMPORTED name `list_all` is public; `_x` is
                              only a local alias. L1 keys on alias.name, not asname.
      NOT A LEAK: importing a submodule (from substrate.graph import retrieval_gate
                  where substrate.graph.retrieval_gate is itself a module).
      NOT A LEAK: relative imports (from . import _x) — intra-package co-ownership.

L2 — DEEP ATTRIBUTE REACH-THROUGH
    A caller walks an attribute chain (depth >= 2) rooted at a first-party import
    and passing THROUGH a private (underscore) attribute, depending on the shape
    of an internal representation instead of an interface method.
      LEAK:     dedup._registry._field   /   config._state.value
      NOT A LEAK (near-miss): self._cache.value — root is self (own internals).
      NOT A LEAK: obj.public.attr — no private hop.

L3 — LOGIC RE-IMPLEMENTATION  (candidate-only, behind --include-l3)
    A caller re-derives something a module already exposes. Cannot be detected
    without false positives (two functions may legitimately compute the same
    thing), so it is a CANDIDATE detector, never a verdict: a file OTHER than the
    canonical owner defines a function whose name collides with a known public
    helper (e.g. a local `def identity_key` that should call substrate.dedup's).
    Reported only with --include-l3 and labelled "candidate, needs human read."

Precision over recall (the sprint's bar): a false positive misdirects an SPR-03/04
refactor, which is worse than missing an obscure leak. Every near-miss above is a
fixture in tests/test_info_hiding.py that must NOT flag.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "SCHEMA_VERSION",
    "Leak",
    "ModuleInfo",
    "build_module_index",
    "find_l1_leaks",
    "find_l2_leaks",
    "find_l3_candidates",
    "build_report",
    "main",
]

SCHEMA_VERSION = 1

# First-party top-level packages whose information-hiding boundary we protect. A
# leak must cross a boundary BETWEEN these; stdlib/third-party imports are out of
# scope (that is boundary_check.py's job for vendor SDKs).
FIRST_PARTY_ROOTS: tuple[str, ...] = (
    "substrate",
    "roles",
    "interfaces",
    "acquisition",
    "orchestration",
    "runtime",
    "middleware",
    "processing",
    "compounding",
    "loop_one",
    "antiek_extensions",
)

# L3 canonical-helper registry: public function name -> the module that owns it.
# A definition of the same name in any OTHER module is a re-implementation
# candidate. Seeded narrowly with high-value substrate normalizers/key-builders.
L3_CANONICAL_HELPERS: dict[str, str] = {
    "identity_key": "substrate.dedup",
    "dedup_key": "substrate.dedup",
    "normalize_doi": "substrate.dedup",
    "normalize_isbn": "substrate.dedup",
    "normalize_arxiv_id": "substrate.dedup",
    "normalize_source_id": "substrate.dedup",
    "normalize_content_hash": "substrate.dedup",
    "document_id_basis": "substrate.dedup",
}

_DIR_SKIP = {".venv", "node_modules", "__pycache__", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".hypothesis", "build", "dist"}


@dataclass(frozen=True)
class ModuleInfo:
    dotted: str
    path: str  # repo-relative posix
    has_all: bool
    all_names: frozenset[str]
    public_names: frozenset[str]  # module-level def/class not underscore (or in __all__)
    is_package: bool


@dataclass(frozen=True)
class Leak:
    caller_path: str
    caller_line: int
    target_module: str
    leaked_name: str
    category: str  # L1 | L2 | L3
    detail: str
    target_rank_score: float | None = None
    target_fenced: bool | None = None


# --------------------------------------------------------------------------- #
# Module index                                                                #
# --------------------------------------------------------------------------- #


def _iter_py_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.py"):
        if any(part in _DIR_SKIP for part in p.parts):
            continue
        out.append(p)
    return sorted(out)


def _dotted_name(root: Path, path: Path) -> tuple[str, bool]:
    """(dotted module path, is_package). __init__.py collapses to its package."""
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    return ".".join(parts), is_package


def _extract_all(tree: ast.Module) -> frozenset[str] | None:
    """Union of every string literal assigned to a module-level __all__ (handles
    __all__ = [...] and __all__ += [...]). None if __all__ is absent."""
    found = False
    names: set[str] = set()
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AugAssign) or isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            found = True
            if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
                for elt in value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        names.add(elt.value)
    return frozenset(names) if found else None


def _public_defs(tree: ast.Module, all_names: frozenset[str] | None) -> frozenset[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if all_names is not None:
                if node.name in all_names:
                    names.add(node.name)
            elif not node.name.startswith("_"):
                names.add(node.name)
    return frozenset(names)


def build_module_index(root: Path, files: list[Path]) -> dict[str, ModuleInfo]:
    """dotted module path -> ModuleInfo, for first-party modules only."""
    index: dict[str, ModuleInfo] = {}
    for path in files:
        parts = path.relative_to(root).parts
        if not parts or parts[0] not in FIRST_PARTY_ROOTS:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        dotted, is_pkg = _dotted_name(root, path)
        all_names = _extract_all(tree)
        index[dotted] = ModuleInfo(
            dotted=dotted,
            path=path.relative_to(root).as_posix(),
            has_all=all_names is not None,
            all_names=all_names or frozenset(),
            public_names=_public_defs(tree, all_names),
            is_package=is_pkg,
        )
    return index


# --------------------------------------------------------------------------- #
# Leak detection                                                              #
# --------------------------------------------------------------------------- #


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _defines_private(info: ModuleInfo, name: str) -> str | None:
    """Return a leak sub-reason if `name` is private in `info`, else None."""
    if name.startswith("_") and not _is_dunder(name):
        return "underscore-private name"
    if info.has_all and name not in info.all_names and name in info.public_names:
        return "public name withheld from __all__"
    return None


def find_l1_leaks(
    caller_rel: str, tree: ast.Module, index: dict[str, ModuleInfo]
) -> list[Leak]:
    """L1: absolute first-party ImportFrom of a private name. Relative imports
    (level>0) are treated as intra-package co-ownership and skipped."""
    leaks: list[Leak] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level and node.level > 0:  # relative import — intra-package, skip
            continue
        module = node.module
        if not module or module not in index:
            continue
        target = index[module]
        for alias in node.names:
            name = alias.name  # the IMPORTED name, never the local `as` alias
            if name == "*":
                continue
            if f"{module}.{name}" in index:  # submodule import, not a name import
                continue
            reason = _defines_private(target, name)
            if reason is not None:
                leaks.append(
                    Leak(
                        caller_path=caller_rel,
                        caller_line=node.lineno,
                        target_module=module,
                        leaked_name=name,
                        category="L1",
                        detail=reason,
                    )
                )
    return leaks


def _first_party_import_roots(tree: ast.Module, index: dict[str, ModuleInfo]) -> dict[str, str]:
    """Local-binding-name -> target first-party module, for absolute imports.
    Both `import substrate.x as y` and `from substrate import x` bind a name that,
    when used as an attribute-chain root, points into a first-party module."""
    roots: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FIRST_PARTY_ROOTS:
                    bound = alias.asname or alias.name.split(".")[0]
                    roots[bound] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and not (node.level or 0):
            if node.module.split(".")[0] not in FIRST_PARTY_ROOTS:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                submod = f"{node.module}.{alias.name}"
                roots[bound] = submod if submod in index else node.module
    return roots


def _attr_chain(node: ast.Attribute) -> tuple[ast.expr, list[str]]:
    """Descend a possibly-mixed Attribute/Subscript/Call chain to its root
    expression, returning (root, [attr names outermost..innermost order])."""
    attrs: list[str] = []
    cur: ast.expr = node
    while True:
        if isinstance(cur, ast.Attribute):
            attrs.append(cur.attr)
            cur = cur.value
        elif isinstance(cur, ast.Subscript):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        else:
            break
    attrs.reverse()
    return cur, attrs


def find_l2_leaks(
    caller_rel: str, tree: ast.Module, index: dict[str, ModuleInfo]
) -> list[Leak]:
    """L2: an attribute chain (depth>=2) rooted at a first-party import that
    passes through a private (underscore) attribute. self/cls roots excluded."""
    roots = _first_party_import_roots(tree, index)
    leaks: list[Leak] = []
    seen: set[tuple[int, int]] = set()  # (line, col) of the outermost node

    # Only consider MAXIMAL chains: an Attribute node not itself the .value of a
    # parent Attribute/Subscript/Call. Track consumed sub-nodes.
    consumed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
            val = getattr(node, "value", None) or getattr(node, "func", None)
            if isinstance(val, (ast.Attribute, ast.Subscript, ast.Call)):
                consumed.add(id(val))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or id(node) in consumed:
            continue
        root, attrs = _attr_chain(node)
        if not isinstance(root, ast.Name):
            continue
        if root.id in ("self", "cls"):
            continue
        if root.id not in roots:
            continue
        if len(attrs) < 2:
            continue
        private_hops = [a for a in attrs if a.startswith("_") and not _is_dunder(a)]
        if not private_hops:
            continue
        key = (node.lineno, node.col_offset)
        if key in seen:
            continue
        seen.add(key)
        leaks.append(
            Leak(
                caller_path=caller_rel,
                caller_line=node.lineno,
                target_module=roots[root.id],
                leaked_name=".".join(attrs),
                category="L2",
                detail=f"reaches through private attr '{private_hops[0]}' (chain depth {len(attrs)})",
            )
        )
    return leaks


def find_l3_candidates(
    caller_rel: str, dotted: str, tree: ast.Module
) -> list[Leak]:
    """L3 (candidate-only): this module defines a function whose name collides
    with a canonical helper owned by a DIFFERENT module."""
    leaks: list[Leak] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = L3_CANONICAL_HELPERS.get(node.name)
            if owner and owner != dotted:
                leaks.append(
                    Leak(
                        caller_path=caller_rel,
                        caller_line=node.lineno,
                        target_module=owner,
                        leaked_name=node.name,
                        category="L3",
                        detail=f"defines '{node.name}' — candidate re-implementation of {owner}.{node.name}; needs human read",
                    )
                )
    return leaks


# --------------------------------------------------------------------------- #
# Ranking join + report                                                       #
# --------------------------------------------------------------------------- #


def _load_ranking(path: Path) -> tuple[dict[str, dict[str, Any]], str | None]:
    """module_path -> row, plus the ranking tool_commit (or (None) if absent)."""
    if not path.is_file():
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, None
    by_path = {m["module"]: m for m in data.get("modules", [])}
    return by_path, data.get("tool_commit")


def _target_path_candidates(dotted: str, index: dict[str, ModuleInfo]) -> str | None:
    info = index.get(dotted)
    return info.path if info else None


def build_report(
    *,
    root: Path,
    ranking_path: Path,
    include_l3: bool,
    precision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    files = _iter_py_files(root)
    index = build_module_index(root, files)
    ranking, ranking_sha = _load_ranking(ranking_path)

    all_leaks: list[Leak] = []
    for path in files:
        parts = path.relative_to(root).parts
        if not parts or parts[0] not in FIRST_PARTY_ROOTS:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        rel = path.relative_to(root).as_posix()
        dotted, _ = _dotted_name(root, path)
        all_leaks.extend(find_l1_leaks(rel, tree, index))
        all_leaks.extend(find_l2_leaks(rel, tree, index))
        if include_l3:
            all_leaks.extend(find_l3_candidates(rel, dotted, tree))

    # Join each leak against SPR-01's ranking (via the target module's path).
    joined: list[dict[str, Any]] = []
    for leak in all_leaks:
        row = asdict(leak)
        tpath = _target_path_candidates(leak.target_module, index)
        rank_row = ranking.get(tpath) if tpath else None
        if rank_row is not None:
            row["target_rank_score"] = rank_row.get("rank_score")
            row["target_fenced"] = rank_row.get("fenced")
        joined.append(row)

    def _sort_key(r: dict[str, Any]) -> tuple[float, str, str, int]:
        rs = r.get("target_rank_score")
        return (-(rs if rs is not None else -1.0), r["category"], r["caller_path"], r["caller_line"])

    actionable = sorted(
        (r for r in joined if not r.get("target_fenced")), key=_sort_key
    )
    fenced_targets = sorted(
        (r for r in joined if r.get("target_fenced")), key=_sort_key
    )

    counts = {c: sum(1 for r in joined if r["category"] == c) for c in ("L1", "L2", "L3")}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "tool": "tools/lint/info_hiding.py",
        "ranking_joined": ranking_sha is not None,
        "ranking_tool_commit": ranking_sha,
        "root": str(root),
        "files_scanned": len(files),
        "first_party_modules_indexed": len(index),
        "categories": {
            "L1": "private-name import: from a first-party module, imported name (pre-alias) is underscore-private or withheld from __all__",
            "L2": "deep attribute reach-through: chain depth>=2 rooted at a first-party import, through a private attr; self/cls excluded",
            "L3": "logic re-implementation CANDIDATE (--include-l3): local def collides with a canonical helper owned elsewhere; needs human read",
        },
        "include_l3": include_l3,
        "counts": counts,
        "actionable_count": len(actionable),
        "fenced_count": len(fenced_targets),
        "precision": precision or {
            "status": "pending",
            "note": "milestone-4 hand-verdict lives in leaks.md; re-run with --precision-file to embed the X/N precision here",
        },
        "leaks": actionable,
        "fenced_targets": fenced_targets,
    }


# --------------------------------------------------------------------------- #
# Markdown + CLI                                                              #
# --------------------------------------------------------------------------- #


def render_markdown(report: dict[str, Any], top: int) -> str:
    lines: list[str] = []
    lines.append("# Information-hiding leak audit — Ousterhout Ch. 5 lens")
    lines.append("")
    lines.append(f"- Generated: `{report['generated_at']}`")
    lines.append(f"- Files scanned: **{report['files_scanned']}** · first-party modules indexed: {report['first_party_modules_indexed']}")
    lines.append(f"- SPR-01 ranking joined: {report['ranking_joined']}" + (f" (tool `{str(report['ranking_tool_commit'])[:12]}`)" if report["ranking_joined"] else " — **ran without ranking (graceful degradation)**"))
    lines.append(f"- Counts: L1={report['counts']['L1']} · L2={report['counts']['L2']} · L3={report['counts']['L3']}"
                 + ("" if report["include_l3"] else " (L3 not run — pass --include-l3)"))
    lines.append(f"- Actionable (unfenced target): **{report['actionable_count']}** · fenced targets segregated: {report['fenced_count']}")
    lines.append("")
    lines.append("**Precision over recall** — a false positive misdirects an SPR-03/04 refactor. L3 is candidate-only.")
    lines.append("")
    lines.append(f"## Top {top} actionable leaks (unfenced target, by target rank_score)")
    lines.append("")
    lines.append("| # | caller path:line | leaked name | ← target module | cat | target rank |")
    lines.append("|--:|------------------|-------------|-----------------|:---:|------------:|")
    for i, r in enumerate(report["leaks"][:top], 1):
        rs = r.get("target_rank_score")
        lines.append(
            f"| {i} | `{r['caller_path']}:{r['caller_line']}` | `{r['leaked_name']}` | "
            f"`{r['target_module']}` | {r['category']} | {rs if rs is not None else '—'} |"
        )
    lines.append("")
    lines.append("## Verification (milestone 4 — hand-labeled precision)")
    lines.append("")
    prec = report.get("precision") or {}
    if prec.get("L1_L2_precision"):
        lines.append(f"**L1/L2 precision: {prec['L1_L2_precision']}** · {prec.get('summary', '')}")
        lines.append("")
        lines.append("| caller path:line | ← target | verdict | note |")
        lines.append("|------------------|----------|---------|------|")
        for row in prec.get("table", []):
            lines.append(f"| `{row['caller']}` | `{row['target']}` | {row['verdict']} | {row.get('note', '')} |")
    else:
        lines.append("_pending — open each caller path:line and classify true leak / acceptable / false positive; re-run with `--precision-file`._")
    lines.append("")
    return "\n".join(lines) + "\n"


def _write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="info_hiding",
        description="Read-only audit for information-hiding leaks (L1/L2/L3). A report, not a gate.",
    )
    parser.add_argument("--root", default=".", type=Path, help="tree root to scan (default: cwd)")
    parser.add_argument("--out", default="reports/complexity/leaks.json", type=Path, help="leaks.json path")
    parser.add_argument("--ranking", default="reports/complexity/ranking.json", type=Path, help="SPR-01 ranking to join")
    parser.add_argument("--top", default=30, type=int, help="rows in leaks.md")
    parser.add_argument("--include-l3", action="store_true", help="also emit L3 re-implementation candidates")
    parser.add_argument("--precision-file", type=Path, default=None, help="optional milestone-4 precision verdict JSON to embed")
    parser.add_argument("--format", choices=("json", "md"), default="json", help="stdout format")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"✗ root not found: {root}", file=sys.stderr)
        return 2

    precision: dict[str, Any] | None = None
    if args.precision_file is not None:
        try:
            precision = json.loads(args.precision_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"✗ could not read --precision-file: {exc}", file=sys.stderr)
            return 2

    report = build_report(root=root, ranking_path=args.ranking, include_l3=args.include_l3, precision=precision)
    _write_json(args.out, report)
    md_path = args.out.parent / "leaks.md"
    md_path.write_text(render_markdown(report, args.top), encoding="utf-8")

    if args.format == "md":
        sys.stdout.write(render_markdown(report, args.top))
    else:
        print(
            f"wrote {args.out}: {report['actionable_count']} actionable leaks "
            f"(L1={report['counts']['L1']} L2={report['counts']['L2']} L3={report['counts']['L3']}), "
            f"{report['fenced_count']} fenced. + {md_path}"
        )
    return 0  # a report, never fails the build (SPR-07 is the gate)


if __name__ == "__main__":
    sys.exit(main())
