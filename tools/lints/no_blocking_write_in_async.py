"""no_blocking_write_in_async — AST lint forbidding a DuckDB write-lock
acquisition on the asyncio event loop.

THE INVARIANT. ``runtime.db_lock.connect_write`` does not await anything. It
spins on ``time.sleep(poll_interval_s)`` waiting first for the in-process write
gate and then for an exclusive ``flock`` on the sidecar lock file, up to
``timeout_s`` (default ``DEFAULT_TIMEOUT_S``). Called from the body of an
``async def``, that sleep runs *on the event loop thread*, so uvicorn — which
runs ``--workers 1`` because DuckDB is single-writer — stops serving every
other request for the whole wait, ``/health`` included. A production incident
held the lock roughly five and a half hours and starved the health probe with
it.

The fix already adopted on the hot paths (see
``docs/decisions/ads-fills-write-lock-nonblock-2026-09-18.md`` and
``docs/decisions/ads-lease-write-yield-2026-09-18.md``) is to move the whole
locked section into a worker thread and keep the flock wait short: a nested
*sync* ``def`` holding the ``with connect_write(...)`` block, dispatched via
``asyncio.to_thread`` / ``starlette.concurrency.run_in_threadpool`` /
``loop.run_in_executor``, with a small ``timeout_s`` and a 503 on
``WriteLockTimeout``. This lint holds that line for new code.

THE RULE. A call to a write-lock entry point (:data:`WRITE_LOCK_ENTRIES` —
``connect_write``, ``connect_write_retrying``, ``acquire_write_context``) is a
violation when its **nearest enclosing function scope is an ``async def``**.
"Nearest enclosing scope" is the whole design: a ``def`` or ``lambda`` nested
inside the ``async def`` interposes a new scope, and that nested callable is
exactly the sanctioned fix shape, so it is not flagged.

Being nested inside a thread hop's *arguments* is deliberately NOT an
exemption, because Python evaluates a call's arguments on the calling thread
before the callee runs. ``await asyncio.to_thread(apply, connect_write(db))``
takes the flock on the event loop and only then hands the open connection to a
worker; it blocks exactly as much as the inline form. The only shape that
really defers the acquisition is a callable — a nested ``def`` or a
``lambda`` — and the nearest-scope rule already lets that through, so an
argument-position exemption could only ever bless the eager form. An earlier
draft of this lint carried one; a mutation run showed no test could tell
whether it was there, which is how the hole surfaced.

Aliases are resolved lexically. ``from runtime.db_lock import connect_write as
_cw`` binds a new name to the same blocking function, and the tree already
writes that shape (``acquisition/youtube/adapter.py`` imports it under
``_connect_write_basis`` inside a function body), as well as the plain
rebinding ``_GRAPH_WRITER = connect_write`` in ``runtime/remote_exec``. Both
are decidable from the module's own AST, so :func:`_collect_alias_names` walks
each file first and hands the extra names to the scan. What a single module
cannot see is an alias bound in *another* module and imported from there; that
needs a call graph.

Follows the ``tools/lints/`` convention (frozen ``Violation`` + ``scan_file`` /
``scan_paths`` + ``main`` with the 0/1/2 exit-code contract) so it plugs into
``tools.lints.cli_with_baseline`` under the registry name
``blocking_write_in_async``. The pre-existing violations are adopted through
``tools/lints/baselines/no_blocking_write_in_async.json`` — that baseline is the
enumeration of the remaining migration, and it shrinks only.

WHAT IS NOT FLAGGED, AND WHY — each decision, with its cost stated
-----------------------------------------------------------------

1. **A nested sync ``def`` (or ``lambda``) inside the ``async def``.** Its body
   runs wherever the caller dispatches it, which the AST cannot see, so a
   lexical rule cannot decide. This is a deliberate FALSE NEGATIVE, and it is
   the same shape as the sanctioned fix, so flagging it would red every correct
   migration. Measured cost on the tree at baseline time: three nested sync
   defs hold a ``connect_write``, and all three reach a thread hop —
   ``ad_routes.py::_accrue_sync`` and ``books.py::convert_and_publish``
   directly, ``ad_routes.py::_decide`` through the ``_sync`` wrapper handed to
   ``run_in_executor``. So the rule gives up nothing today. It would miss a
   nested sync def that is simply *called* rather than dispatched; a reviewer
   still has to check that the closure reaches a hop.

2. **A ``@contextmanager`` helper that wraps ``connect_write`` and is called
   from async code.** This IS a real violation and this lint cannot see it: the
   ``connect_write`` sits in a module-level sync generator whose nearest scope
   is sync, and only a call graph would connect it to the async caller. Closing
   it needs whole-program analysis, which is a different and much more
   expensive tool. Recorded here rather than papered over.

3. **An alias bound in one module and imported from another.** ``_cw`` defined
   in ``helpers.py`` and imported into a route module reads as an ordinary
   name here. Same call-graph limit as 2.

4. **Tests.** ``SKIPPED_PARTS`` mirrors the sibling lints: a test may block
   freely, it owns its loop.

Where the AST cannot decide, this lint prefers a false negative to a false
positive — a lint that reds honest code gets switched off, and then it protects
nothing. Where the AST *can* decide, as with an alias bound in the same file,
it decides.

Usage::

    python -m tools.lints.no_blocking_write_in_async <path>...

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

__all__ = [
    "WRITE_LOCK_ENTRIES",
    "SKIPPED_PARTS",
    "Violation",
    "scan_file",
    "scan_paths",
    "main",
]


# Entry points that take the DuckDB single-writer lock by polling with
# ``time.sleep``. ``acquire_write_context`` is the ``FlockWriteCoordinator``
# facade over ``connect_write`` and blocks identically.
WRITE_LOCK_ENTRIES: frozenset[str] = frozenset(
    {"connect_write", "connect_write_retrying", "acquire_write_context"}
)

SKIPPED_PARTS: frozenset[str] = frozenset(
    {"tests", ".caffenagent", "docs", "node_modules", ".worktrees", "__pycache__"}
)


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    col: int
    call: str
    func: str

    def format_line(self) -> str:
        return (
            f"{self.path}:{self.line}:{self.col}: {self.call}() on the event loop "
            f"in async def {self.func} — it polls with time.sleep, so the flock "
            f"wait blocks every request on the worker. Move the locked section "
            f"into a sync def dispatched with asyncio.to_thread and pass a short "
            f"timeout_s (503 on WriteLockTimeout)."
        )


def _callee_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _collect_alias_names(tree: ast.AST) -> dict[str, str]:
    """Map every local name bound to a write-lock entry point onto that entry.

    Covers ``from runtime.db_lock import connect_write as _cw`` (at module
    level or inside a function body, which is how ``acquisition/youtube``
    writes it) and the plain rebinding ``_GRAPH_WRITER = connect_write``. The
    value is the canonical entry name so the message still says which lock is
    being taken rather than whatever the alias is called.

    The map is per file, not per scope, so an alias bound inside one function
    makes that name suspect for the whole module. Erring that way is cheap: the
    alternative is a scope-accurate binding table, and a module that binds one
    name to ``connect_write`` in one function and to something unrelated in
    another has a worse problem than this lint.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom | ast.Import):
            for imported in node.names:
                if imported.asname and imported.name.split(".")[-1] in WRITE_LOCK_ENTRIES:
                    aliases[imported.asname] = imported.name.split(".")[-1]
            continue
        if isinstance(node, ast.Assign):
            entry = _entry_of(node.value, aliases)
            if entry is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    aliases[target.id] = entry
    return aliases


def _entry_of(value: ast.expr, aliases: dict[str, str]) -> str | None:
    """Resolve a bare-reference expression to the write-lock entry it names."""
    if isinstance(value, ast.Name):
        name = value.id
    elif isinstance(value, ast.Attribute):
        name = value.attr
    else:
        return None
    if name in WRITE_LOCK_ENTRIES:
        return name
    return aliases.get(name)


class _Walker(ast.NodeVisitor):
    """Track the nearest enclosing function scope.

    ``_scope`` is a stack of the enclosing callables, innermost last, each
    tagged ``async`` / ``sync`` / ``lambda``, paired with the name used in the
    message. Only a top-of-stack ``async`` entry makes a write-lock call
    blocking — anything nested inside a ``def`` or ``lambda`` runs wherever its
    caller dispatches it.
    """

    def __init__(self, path: Path, entries: dict[str, str]) -> None:
        self.path = path
        self.entries = entries
        self.violations: list[Violation] = []
        self._scope: list[tuple[str, str]] = []

    def _enter(self, node: ast.AST, kind: str, name: str) -> None:
        self._scope.append((kind, name))
        self.generic_visit(node)
        self._scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter(node, "async", node.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter(node, "sync", node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._enter(node, "lambda", "<lambda>")

    def visit_Call(self, node: ast.Call) -> None:
        name = _callee_name(node)
        entry = self.entries.get(name) if name is not None else None

        if entry is not None and self._scope and self._scope[-1][0] == "async":
            self.violations.append(
                Violation(
                    path=self.path,
                    line=node.lineno,
                    col=node.col_offset,
                    call=entry,
                    func=self._scope[-1][1],
                )
            )

        self.generic_visit(node)


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
    entries = {name: name for name in WRITE_LOCK_ENTRIES}
    entries.update(_collect_alias_names(tree))
    walker = _Walker(path, entries)
    walker.visit(tree)
    return walker.violations


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
            "usage: python -m tools.lints.no_blocking_write_in_async <path>...",
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
