"""
H-002 — Raw ``duckdb.connect`` for writes bypasses ``db_lock``.

Writes must funnel through ``runtime/db_lock.py``'s
``connect_write(db_path, purpose=...)``; read-only access is fine via
``connect_read`` or by passing ``read_only=True`` directly.

Detection is AST-based (regex would over-match function names that happen
to be called ``connect``). For every ``duckdb.connect(...)`` or
``from duckdb import connect; connect(...)`` call we check:

  1. Whitelist: the call site IS ``runtime/db_lock.py`` (the one place
     that legitimately wraps the raw API).
  2. Read-only: the call passes ``read_only=True`` as a keyword arg.
  3. In-memory: the first positional argument is the literal
     ``":memory:"`` (legitimately needs no lock).
  4. Noqa: the call's source line carries ``# noqa: H002 -- <reason ≥12>``.

Anything else is a violation.

See HERESIES.md H-002 for the carve-out semantics.
"""

from __future__ import annotations

import ast
import os
from typing import Iterable, List

from ._common import Violation, parse_noqa

MODE = "blocking"
HERESY_ID = "H-002"

# Where raw duckdb.connect is sanctioned:
#   1. db_lock.py itself — where connect_write wraps it.
#   2. Migrations — they run once at boot, internal to the substrate.
#   3. tests/ — test fixtures legitimately create isolated tmp_path DBs
#      with no other process touching them. The 2026-05-24 calibration
#      sweep found ~30 such cases vs zero production cases; whitelisting
#      tests/ here keeps the detector signal-perfect on prod code at the
#      cost of not catching "test accidentally opens a real DB" (rare in
#      practice; pytest tmp_path is the established convention).
_WHITELIST_PREFIXES = (
    "runtime/db_lock.py",
    "substrate/event_log/migrations/",
    "tests/",
)


def _is_whitelisted(rel_path: str) -> bool:
    normalized = rel_path.replace(os.sep, "/")
    return any(normalized.startswith(p) for p in _WHITELIST_PREFIXES)


def _is_duckdb_connect(call: ast.Call, from_duckdb_aliases: set[str]) -> bool:
    """Return True if this call is ``duckdb.connect(...)`` or a
    ``connect(...)`` reached via ``from duckdb import connect``."""
    # Form A: duckdb.connect(...)
    if isinstance(call.func, ast.Attribute):
        if call.func.attr == "connect" and isinstance(call.func.value, ast.Name):
            if call.func.value.id == "duckdb":
                return True
    # Form B: connect(...) where ``connect`` was imported from duckdb
    if isinstance(call.func, ast.Name) and call.func.id in from_duckdb_aliases:
        return True
    return False


def _is_read_only(call: ast.Call) -> bool:
    """Return True if this connect call passes read_only=True."""
    for kw in call.keywords:
        if kw.arg == "read_only":
            # Accept the True literal or the constant 1; conservative.
            if isinstance(kw.value, ast.Constant) and kw.value.value in (True, 1):
                return True
    return False


def _is_in_memory(call: ast.Call) -> bool:
    """Return True if first positional arg is the literal ':memory:'."""
    if not call.args:
        return False
    first = call.args[0]
    if isinstance(first, ast.Constant) and first.value == ":memory:":
        return True
    return False


def _collect_from_duckdb_aliases(tree: ast.AST) -> set[str]:
    """Find all symbols imported from duckdb that refer to ``connect``.

    Handles:
        from duckdb import connect              -> {"connect"}
        from duckdb import connect as ddconnect -> {"ddconnect"}
    Ignores any other names imported from duckdb (we only care about
    aliases for ``connect`` itself).
    """
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "duckdb":
            for n in node.names:
                if n.name == "connect":
                    aliases.add(n.asname or n.name)
    return aliases


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
            # Syntactically broken files are someone else's problem
            # (ruff, py compile). Skip rather than fail the hook.
            continue

        from_duckdb = _collect_from_duckdb_aliases(tree)
        source_lines = source.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_duckdb_connect(node, from_duckdb):
                continue
            if _is_read_only(node):
                continue
            if _is_in_memory(node):
                continue

            lineno = getattr(node, "lineno", 0) or 1
            # source_lines is 0-indexed; lineno is 1-based
            snippet = source_lines[lineno - 1] if 0 <= lineno - 1 < len(source_lines) else ""
            if parse_noqa(snippet) == HERESY_ID:
                continue

            violations.append(Violation(
                heresy_id=HERESY_ID,
                file=path,
                line=lineno,
                snippet=snippet,
                reason=(
                    "duckdb.connect for write must go through "
                    "runtime/db_lock.connect_write (or pass read_only=True for reads, "
                    "or use ':memory:' for in-memory DBs, or add "
                    "# noqa: H002 -- <reason ≥12 chars>)."
                ),
            ))
    return violations
