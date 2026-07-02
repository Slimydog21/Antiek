#!/usr/bin/env python3
"""Retrieval-gate UNIQUENESS lint — exactly ONE definition of each gate symbol.

Antiek Convergence SPR-03 (the convergence GUARD). The §9.0 retrieval gate was
forked across two parallel implementations and reconsolidated into a single
canonical module by #65 (commit ``b27b9df``). #65 collapsed #53's two helpers
into ONE ``non_privileged_chunk_sql_clause`` (the SQL emitter, used by
``search()`` + the VSS substrate) and ONE ``is_chunk_body_withheld`` (the HTTP
withhold predicate, used by ``GET /chunks/{id}``) — both in
``substrate/graph/retrieval_gate.py``.

This check is the never-re-fork guard: if a SECOND ``def`` of either symbol
ever appears anywhere under ``substrate/graph/`` (a future sprint re-introducing
a parallel gate the way #53 did), this reds. It is a STRUCTURAL count of the
DEFINITION sites — it does not look at what the body does.

WHY THIS IS A DISTINCT CHECK FROM ``retrieval_gate_check.py`` (fairness): the two
guards catch DIFFERENT failure modes and neither subsumes the other.

  * ``retrieval_gate_check.py`` (the drift check) forbids a RE-IMPLEMENTATION of
    the gate's LOGIC under a different name — a hand-rolled
    ``NOT IN ('restricted_pending_opt_in')`` SQL literal, a
    ``list(RESTRICTED_CONTENT_CLASSES)`` bind list, a
    ``content_class in RESTRICTED_CONTENT_CLASSES`` HTTP check. That is the
    pre-#53 leak shape: the symbol stays singular but the LOGIC is duplicated
    inline somewhere else.
  * THIS check forbids a SECOND DEFINITION of the canonical symbols themselves —
    a literal ``def non_privileged_chunk_sql_clause`` / ``def
    is_chunk_body_withheld`` appearing twice. That is the pre-#65 fork shape: two
    modules each export a function of the SAME name, callers split across them,
    and the two drift apart silently (the exact fork #65 consolidated). The drift
    check would NOT flag this — both definitions could delegate correctly and
    contain no banned literal — yet the convergence is broken the moment a second
    canonical definition exists for a caller to import the wrong one.

So: the drift check defends "no inline re-impl of the gate logic"; this check
defends "exactly one home for each gate symbol". Keep both.

SCOPE. We scan every ``.py`` under ``substrate/graph/`` (where the canonical
module lives and where a parallel gate would most plausibly be re-introduced)
PLUS ``interfaces/research/api/app.py`` (the HTTP surface that originally carried
the duplicate ``is_chunk_body_withheld`` logic before #65 routed it through the
helper). Test files are EXCLUDED: tests legitimately define same-named local
helpers / fixtures and exercising the gate is not re-forking it.

We count DEFINITIONS via AST (``ast.FunctionDef`` / ``ast.AsyncFunctionDef``
whose ``name`` is a watched symbol) — not text matches — so a docstring mention,
a string literal, or a call site never miscounts. A ``def`` nested inside another
function still counts (a nested re-definition is still a second home a refactor
could hoist); this is intentional fail-closed strictness.

Modeled on ``tools/lint/retrieval_gate_check.py`` + ``tools/lint/register_check.py``:
same ``path:line: message`` output, same exit-code contract (0 = clean,
1 = violations), same AST walk.

Exit 0 = exactly one definition of each watched symbol. Exit 1 = either symbol
has ≠ 1 definition (zero — the canonical home vanished — or two+ — a re-fork);
each definition site is printed as ``path:line``.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

# Ensure the package root is importable when invoked as a BARE SCRIPT
# (``python tools/lint/retrieval_gate_uniqueness.py``, the CI idiom) as well as
# a module. SPR-07: ``main`` now delegates to ``tools.lint.uniqueness_registry``,
# a cross-``tools`` import that needs the repo root on ``sys.path`` in the
# bare-script case (a ``python -m`` invocation already has it). Mirrors the
# bootstrap in tools/reachability/probe_runner.py.
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# The canonical gate symbols #65 consolidated to exactly one definition each.
_WATCHED_SYMBOLS: frozenset[str] = frozenset({
    "non_privileged_chunk_sql_clause",
    "is_chunk_body_withheld",
})

# The canonical home (where each symbol is EXPECTED to live). Used only for the
# clean-run summary line, never to skip scanning — if a symbol ever moves, the
# count still has to be exactly one wherever it lands.
_CANONICAL_HOME = "substrate/graph/retrieval_gate.py"


def _is_test_file(rel: str) -> bool:
    """Tests define same-named local helpers / fixtures legitimately — exclude
    them so exercising the gate is never miscounted as re-defining it. Mirrors
    ``retrieval_gate_check._is_test_file``."""
    parts = Path(rel).parts
    if parts and parts[0] == "tests":
        return True
    stem = Path(rel).name
    return stem.startswith("test_") or stem.endswith("_test.py")


def _scanned_files(root: Path) -> list[Path]:
    """Every ``.py`` under ``substrate/graph/`` plus the HTTP surface
    ``interfaces/research/api/app.py`` — the two places #53/#65's fork lived
    and where a re-fork would most plausibly reappear. Test files are dropped."""
    out: list[Path] = []
    graph_dir = root / "substrate" / "graph"
    if graph_dir.is_dir():
        out.extend(sorted(graph_dir.rglob("*.py")))
    app_py = root / "interfaces" / "research" / "api" / "app.py"
    if app_py.is_file():
        out.append(app_py)
    return [
        py
        for py in out
        if not _is_test_file(py.relative_to(root).as_posix())
    ]


def find_definitions(root: Path = _REPO) -> dict[str, list[str]]:
    """Map each watched symbol -> the ``path:line`` of every ``def`` of it
    found across the scanned files. AST-based: a ``FunctionDef`` /
    ``AsyncFunctionDef`` whose ``name`` is watched, anywhere in the module
    (nested defs included)."""
    found: dict[str, list[str]] = {sym: [] for sym in _WATCHED_SYMBOLS}
    for py in _scanned_files(root):
        rel = py.relative_to(root).as_posix()
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in _WATCHED_SYMBOLS
            ):
                found[node.name].append(f"{rel}:{node.lineno}")
    for sym in found:
        found[sym].sort()
    return found


def find_violations(root: Path = _REPO) -> list[str]:
    """Return ``path:line: message`` for any watched symbol whose definition
    count is not exactly one."""
    out: list[str] = []
    defs = find_definitions(root)
    for sym in sorted(_WATCHED_SYMBOLS):
        sites = defs[sym]
        if len(sites) == 1:
            continue
        if not sites:
            out.append(
                f"{_CANONICAL_HOME}:0: gate symbol {sym!r} has ZERO definitions "
                f"under substrate/graph/ + interfaces/research/api/app.py — the "
                f"canonical §9.0 gate home disappeared (expected exactly one in "
                f"{_CANONICAL_HOME}; #65 consolidated it there)"
            )
            continue
        for site in sites:
            out.append(
                f"{site}: gate symbol {sym!r} is defined {len(sites)} times — "
                f"the §9.0 retrieval gate has RE-FORKED (it must have exactly ONE "
                f"definition; #65 consolidated #53's parallel implementations into "
                f"the single canonical {_CANONICAL_HOME}). Other definition(s): "
                + ", ".join(s for s in sites if s != site)
            )
    return out


def main(argv: list[str] | None = None) -> int:
    """RETARGETED by SPR-07: the CLI now DELEGATES to the uniqueness REGISTRY so
    retrieval-gate uniqueness is ASSERTED in exactly ONE place (the registry's
    ``retrieval_gate`` row), not independently here AND there.

    The detection functions above (``find_definitions`` / ``find_violations``)
    remain the reusable SPR-03 library — the registry's ``retrieval_gate`` row
    IMPORTS ``find_violations`` from this module — so SPR-03's tested symbol
    counter is preserved (and its self-test
    ``tests/test_retrieval_gate_uniqueness_lint.py`` still exercises it
    directly). What changed is the ENFORCEMENT path: running this module's CLI,
    or the registry's, exercises the SAME single ``retrieval_gate`` assertion.
    The standalone CI step was removed (SPR-07); the registry meta-check is the
    one CI enforcement of every concern's uniqueness, retrieval_gate included.

    To REVERSE the retarget (make this a fully independent standalone again),
    restore the inline ``find_violations()`` summary/print block from git
    history and re-add its own CI step — but then two places assert
    retrieval-gate uniqueness, the drift the SPR-07 registry exists to remove.
    """
    parser = argparse.ArgumentParser(
        prog="tools.lint.retrieval_gate_uniqueness",
        description=(
            "Assert each §9.0 retrieval-gate symbol "
            "(non_privileged_chunk_sql_clause / is_chunk_body_withheld) has "
            "EXACTLY ONE definition — the never-re-fork guard for #65's "
            "consolidation. Delegates to the SPR-07 uniqueness registry "
            "(retrieval_gate row). Exit 1 if either count != 1."
        ),
    )
    parser.parse_args(argv)

    # Delegate to the registry's retrieval_gate row (the single assertion
    # authority). Imported lazily to avoid a hard import cycle at module load
    # (the registry imports find_violations from THIS module at its top level).
    from tools.lint.uniqueness_registry import REGISTRY

    row = next(c for c in REGISTRY if c.name == "retrieval_gate")
    ok, offenders = row.run()
    if not ok:
        print("Retrieval-gate uniqueness violations:")
        for line in offenders:
            print(f"  {line}")
        print(
            "\nEach §9.0 retrieval-gate symbol must have EXACTLY ONE definition. "
            f"#65 consolidated #53's parallel gates into the single canonical "
            f"{_CANONICAL_HOME}; a second definition re-forks the gate (callers "
            f"split across two homes that drift apart). Delete the duplicate and "
            f"import from {_CANONICAL_HOME}. Converge per "
            f"docs/decisions/convergence-owner.md. (The complementary "
            f"retrieval_gate_check.py forbids inline RE-IMPLEMENTATION of the gate "
            f"logic under a different name — a different failure mode.)"
        )
        return 1

    defs = find_definitions()
    summary = ", ".join(
        f"{sym}@{defs[sym][0]}" for sym in sorted(_WATCHED_SYMBOLS)
    )
    print(
        f"OK: each retrieval-gate symbol has exactly one definition ({summary}) "
        f"[asserted via the SPR-07 uniqueness registry]."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
