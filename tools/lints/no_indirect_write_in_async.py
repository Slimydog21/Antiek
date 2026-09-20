"""no_indirect_write_in_async — the write-lock reaches the event loop through
a helper, which the sibling lint deliberately cannot see.

WHY THIS EXISTS. ``no_blocking_write_in_async`` flags a write-lock entry point
whose *nearest enclosing scope* is an ``async def``. Its docstring records what
that rule gives up, under "WHAT IS NOT FLAGGED, AND WHY":

    2. **A ``@contextmanager`` helper that wraps ``connect_write`` and is
       called from async code.** This IS a real violation and this lint cannot
       see it: the ``connect_write`` sits in a module-level sync generator
       whose nearest scope is sync, and only a call graph would connect it to
       the async caller. Closing it needs whole-program analysis, which is a
       different and much more expensive tool. Recorded here rather than
       papered over.

Recorded honestly, and then never measured. On 2026-09-20 the exposure was
**38 async functions** across six modules — every Speak write route among them.
``interfaces/research/api/speak_routes.py`` alone holds 24: each does

    async def create_project(...):
        with _translate(), _write("speak/api:create_project") as con:

where ``_write`` is a module-level ``@contextmanager`` around
``connect_write``. The sibling lint sees a sync generator and moves on, while
the flock wait runs on the loop thread of a ``--workers 1`` uvicorn.

WHAT THIS ADDS, AND WHAT IT STILL GIVES UP. Whole-program analysis is not
needed for the shape that actually occurs: the helper and its async caller sit
in the SAME module. That subset is AST-decidable, and it is where all 38 live.
Cross-module aliasing (the sibling's case 3) remains out of reach and stays
out of reach here — this lint is a strict widening, never a replacement.

THE RULE. Within one module, compute by fixpoint the set of sync ``def``
helpers that reach a write-lock entry point — directly, or by calling another
such helper. An ``async def`` that CALLS one of those helpers in its own scope
is a violation.

NOT FLAGGED, deliberately:

* A helper passed BY NAME to ``asyncio.to_thread`` / ``run_in_executor`` /
  ``run_in_threadpool``. That is the sanctioned fix, and it is the reason the
  count splits 38 blocking / 49 sanctioned rather than 87: this repo has been
  migrating correctly and the lint must not red the finished work.
* A call inside a nested ``def``/``lambda``. Same reasoning as the sibling:
  the nested callable is the fix shape, so flagging it would red every correct
  migration.
* Tests, which own their loop.

Note the asymmetry with the sibling on argument position. There, a *call* in
argument position (``to_thread(apply, connect_write(db))``) is still eager and
stays flagged. Here the helper reference must be a bare ``Name`` to count as
dispatched; ``to_thread(_write(...))`` is a Call, so it is not treated as a
hop and remains a violation. Both lints therefore agree: only a callable, not
an already-evaluated call, defers the acquisition.

Usage::

    python -m tools.lints.no_indirect_write_in_async <path>...

Exit codes:
    0   no violations
    1   one or more violations (printed to stdout, count to stderr)
    2   usage error (no paths)
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from tools.lints.no_blocking_write_in_async import (
    SKIPPED_PARTS,
    WRITE_LOCK_ENTRIES,
)

__all__ = [
    "THREAD_HOPS",
    "Violation",
    "scan_file",
    "scan_paths",
    "main",
]

# Dispatchers that move a callable off the event loop. A helper handed to one
# of these by name is the sanctioned migration, not a violation.
THREAD_HOPS: frozenset[str] = frozenset(
    {"to_thread", "run_in_executor", "run_in_threadpool"}
)


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    col: int
    helper: str
    func: str

    def format_line(self) -> str:
        return (
            f"{self.path}:{self.line}:{self.col}: {self.helper}() on the event "
            f"loop in async def {self.func} — it wraps a write-lock entry "
            f"point, so the flock wait blocks every request on the worker. "
            f"Move the call into a sync def dispatched with asyncio.to_thread."
        )


def _own_scope_calls(fn: ast.AST, names: frozenset[str]) -> Iterator[ast.Call]:
    """Calls to ``names`` in ``fn``'s own scope only.

    Descending into a nested ``def``/``lambda`` would flag the sanctioned fix
    shape, so those subtrees are skipped entirely.
    """
    for child in ast.iter_child_nodes(fn):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id in names
        ):
            yield child
        yield from _own_scope_calls(child, names)


def _dispatched_names(fn: ast.AST, names: frozenset[str]) -> frozenset[str]:
    """Helpers handed BY NAME to a thread hop anywhere inside ``fn``."""
    out: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if called not in THREAD_HOPS:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Name) and arg.id in names:
                out.add(arg.id)
    return frozenset(out)


def _direct_names(fn: ast.AST) -> frozenset[str]:
    """Every plain-name call anywhere in ``fn`` (used for the fixpoint)."""
    return frozenset(
        node.func.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    )


def _write_lock_helpers(tree: ast.Module) -> frozenset[str]:
    """Sync defs in this module that reach a write-lock entry point.

    Fixpoint, so a helper that calls a helper that takes the lock is included.
    """
    sync_defs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    calls = {fn.name: _direct_names(fn) for fn in sync_defs}
    helpers = {fn.name for fn in sync_defs if calls[fn.name] & WRITE_LOCK_ENTRIES}
    changed = True
    while changed:
        changed = False
        for name, called in calls.items():
            if name not in helpers and called & helpers:
                helpers.add(name)
                changed = True
    return frozenset(helpers)


def _is_skipped_path(path: Path) -> bool:
    if SKIPPED_PARTS.intersection(path.parts):
        return True
    name = path.name
    return name.startswith("test_") or name.endswith("_test.py")


def scan_file(path: Path) -> list[Violation]:
    if _is_skipped_path(path):
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []
    helpers = _write_lock_helpers(tree)
    if not helpers:
        return []
    out: list[Violation] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        dispatched = _dispatched_names(fn, helpers)
        for call in _own_scope_calls(fn, helpers):
            assert isinstance(call.func, ast.Name)  # guaranteed by _own_scope_calls
            if call.func.id in dispatched:
                continue
            out.append(
                Violation(
                    path=path,
                    line=call.lineno,
                    col=call.col_offset,
                    helper=call.func.id,
                    func=fn.name,
                )
            )
    return out


def _iter_py_files(target: Path) -> Iterator[Path]:
    if target.is_file() and target.suffix == ".py":
        if not _is_skipped_path(target):
            yield target
        return
    if target.is_dir():
        for p in sorted(target.rglob("*.py")):
            if not _is_skipped_path(p):
                yield p


def scan_paths(paths: Iterable[Path | str]) -> list[Violation]:
    out: list[Violation] = []
    for raw in paths:
        for f in _iter_py_files(Path(raw)):
            out.extend(scan_file(f))
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(
            "usage: python -m tools.lints.no_indirect_write_in_async <path>...",
            file=sys.stderr,
        )
        return 2
    violations = scan_paths(argv)
    for v in violations:
        print(v.format_line())
    if violations:
        print(f"\n{len(violations)} violation(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
