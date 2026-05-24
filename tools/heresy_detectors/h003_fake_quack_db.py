"""
H-003 — Fake Quack DB: multiple write handles to the same DuckDB file
in one module.

The pattern: a module opens two write handles to the same file path
(possibly under different variable names). Both go through ``db_lock``
so the cross-process flock is honored, but in-process they are two
distinct connections and the calling code starts treating them as
separate stores. The bug surfaces months later as silent data divergence
when one handle's transactions don't see the other's committed state.

Detection: count the distinct call sites in each file that pass the
same *string-literal* path to either ``connect_write(...)`` or
``duckdb.connect(...)``. Files where the same path literal appears as
the first argument to ≥2 connect-style calls are flagged. We
deliberately do NOT try to follow variable-bound paths (``DB_PATH =
"..."; connect_write(DB_PATH)`` then ``connect_write(DB_PATH)``) — that
heuristic would mis-flag every helper that takes the path as a
parameter and gets called twice in tests. The string-literal heuristic
finds the *real* fake-Quack shape (someone hardcoded the path twice)
and leaves the legitimate forms alone.

See HERESIES.md H-003 for the carve-out semantics.
"""

from __future__ import annotations

import ast
import os
from collections import defaultdict
from typing import Iterable, List

from ._common import Violation, parse_noqa

MODE = "blocking"
HERESY_ID = "H-003"

# These files legitimately open the lock file twice (the lock module itself
# wraps duckdb.connect; tests deliberately exercise the lock's reentrancy).
_WHITELIST_PREFIXES = (
    "runtime/db_lock.py",
    "tests/test_db_lock",      # any test file starting with this prefix
    "tests/test_fake_quack",   # this sprint's own detector tests
)


def _is_whitelisted(rel_path: str) -> bool:
    normalized = rel_path.replace(os.sep, "/")
    return any(normalized.startswith(p) for p in _WHITELIST_PREFIXES)


def _is_connect_call(call: ast.Call) -> bool:
    """Recognize ``connect_write(...)``, ``duckdb.connect(...)``, or
    ``connect_read(...)`` — anything that yields a DuckDB handle."""
    if isinstance(call.func, ast.Name) and call.func.id in {"connect_write", "connect_read"}:
        return True
    if isinstance(call.func, ast.Attribute):
        if call.func.attr in {"connect", "connect_write", "connect_read"}:
            return True
    return False


def _first_arg_literal(call: ast.Call) -> str | None:
    """If the first positional arg is a string literal, return it. Else None.

    We intentionally don't try to resolve variables (see module docstring).
    """
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def run(files: Iterable[str]) -> List[Violation]:
    violations: List[Violation] = []
    for path in files:
        if not path.endswith(".py"):
            continue
        if _is_whitelisted(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            continue

        source_lines = source.splitlines()
        # path-literal -> [(lineno, snippet), ...]
        per_path_literal: dict[str, list[tuple[int, str]]] = defaultdict(list)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_connect_call(node):
                continue
            literal = _first_arg_literal(node)
            if literal is None:
                continue
            # In-memory databases are not the heresy
            if literal == ":memory:":
                continue
            lineno = getattr(node, "lineno", 0) or 1
            snippet = source_lines[lineno - 1] if 0 <= lineno - 1 < len(source_lines) else ""
            # Per-call-site noqa wins
            if parse_noqa(snippet) == HERESY_ID:
                continue
            per_path_literal[literal].append((lineno, snippet))

        for literal, sites in per_path_literal.items():
            if len(sites) < 2:
                continue
            # All but the first call site are reported as violations so
            # the operator sees exactly which extra handles to remove.
            for lineno, snippet in sites[1:]:
                violations.append(Violation(
                    heresy_id=HERESY_ID,
                    file=path,
                    line=lineno,
                    snippet=snippet,
                    reason=(
                        f"Second write handle to {literal!r} in this module — "
                        "pass the existing connection through, or # noqa: H003 -- "
                        "sequential, not parallel (and explain why)."
                    ),
                ))
    return violations
