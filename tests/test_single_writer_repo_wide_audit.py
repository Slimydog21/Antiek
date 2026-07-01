"""Repo-wide single-writer audit for ungoverned duckdb.connect().

Antiek invariant #1 (CLAUDE.md): DuckDB is single-writer-per-process; every
write connection MUST go through ``runtime.db_lock.connect_write`` (flock
LOCK_EX -> duckdb.connect).  ``test_remote_exec_isolation.py`` proves the
invariant holds inside ``runtime/remote_exec/``, but ~40 ``duckdb.connect(...)``
sites across ``substrate/``, ``orchestration/``, and ``interfaces/`` were
never audited mechanically.

This test closes that gap:

1. AST-scans every ``*.py`` under the three source trees for
   ``duckdb.connect(...)`` calls.
2. Classifies each: READ (``read_only=True``) vs WRITE (no ``read_only=True``).
3. Asserts every WRITE is either on an **explicit allowlist** with a cited
   reason, or raises a failure listing each file:line.
4. Non-vacuity guard: the scan must find real sites; a broken glob or empty
   tree must not pass silently.
5. ``:memory:`` connections (in-process ephemeral, never touch a file) are
   excluded from the audit entirely.

The allowlist below is the exhaustive set of non-``db_lock.py`` write sites
found on 2026-07-01.  Each entry carries a reason.  If a new write site
appears, this test **fails**; the author must either route through
``connect_write`` or add an allowlist entry with a cited decision.

Reviewers can independently verify with::

    rg --no-heading -n 'duckdb.connect(' substrate/ orchestration/ interfaces/ \\
      | grep -v 'read_only=True'

and compare against the allowlist.
"""

import ast
import pathlib
from dataclasses import dataclass

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SOURCE_DIRS = ["substrate", "orchestration", "interfaces"]


@dataclass(frozen=True)
class DuckDbConnectSite:
    path: str
    line: int
    is_read_only: bool
    enclosing_class: str | None
    enclosing_function: str | None
    first_arg: str | None


# Every non-read-only duckdb.connect() call outside runtime/db_lock.py that is
# legitimately NOT a single-writer violation. Keys are stable AST context
# fields rather than line numbers so harmless surrounding edits do not weaken
# the audit into brittle churn.
#
# To add an entry: you MUST cite a decision doc or inline rationale.  "It was
# already there" is not a reason; the point is that every raw write site is
# reviewed, not just grandfathered.

_ALLOWLIST: dict[tuple[str, str | None, str | None, str | None], str] = {
    (
        "substrate/graph/retrieval_substrate.py",
        "DuckDbVssSubstrate",
        "open",
        "copy_path",
    ): (
        "VSS index build writes to a temp copy, not the source graph; "
        "see DuckDbVssSubstrate.open docstring."
    ),
}


def _is_duckdb_connect(call: ast.Call) -> bool:
    """True if ``call`` is ``duckdb.connect(...)``."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "connect":
        val = func.value
        if isinstance(val, ast.Name) and val.id == "duckdb":
            return True
    return False


def _has_read_only_true(call: ast.Call) -> bool:
    """True if the call has ``read_only=True`` as a keyword argument."""
    for kw in call.keywords:
        if (
            kw.arg == "read_only"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
        ):
            return True
    return False


def _first_arg_name(call: ast.Call) -> str | None:
    """Return a stable representation of the first positional argument."""
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Name):
        return arg.id
    if isinstance(arg, ast.Constant):
        return repr(arg.value)
    if isinstance(arg, ast.Attribute):
        parts: list[str] = []
        current: ast.AST = arg
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
    return ast.dump(arg, annotate_fields=False, include_attributes=False)


def _is_memory_connection(call: ast.Call) -> bool:
    """True if the first positional arg is the string '':memory:''.

    In-memory connections never touch a database file and are exempt from
    the single-writer audit.
    """
    if call.args:
        arg = call.args[0]
        if isinstance(arg, ast.Constant) and arg.value == ":memory:":
            return True
    return False


class _DuckDbConnectVisitor(ast.NodeVisitor):
    def __init__(self, git_rel: str):
        self.git_rel = git_rel
        self.class_stack: list[str] = []
        self.function_stack: list[str] = []
        self.results: list[DuckDbConnectSite] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.class_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.function_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self.function_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self.function_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if _is_duckdb_connect(node) and not _is_memory_connection(node):
            self.results.append(
                DuckDbConnectSite(
                    path=self.git_rel,
                    line=node.lineno,
                    is_read_only=_has_read_only_true(node),
                    enclosing_class=self.class_stack[-1] if self.class_stack else None,
                    enclosing_function=(
                        self.function_stack[-1] if self.function_stack else None
                    ),
                    first_arg=_first_arg_name(node),
                )
            )
        self.generic_visit(node)


def _scan_source_tree() -> list[DuckDbConnectSite]:
    """Scan all ``*.py`` files under the source dirs.

    Returns every ``duckdb.connect(...)`` call found. ``:memory:`` connections
    are excluded because they never touch a database file.
    """
    results: list[DuckDbConnectSite] = []
    for dir_name in _SOURCE_DIRS:
        source_dir = _REPO_ROOT / dir_name
        if not source_dir.is_dir():
            continue
        for py_file in sorted(source_dir.rglob("*.py")):
            # Skip __pycache__ and .pyc artifacts
            if "__pycache__" in py_file.parts:
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue
            git_rel = str(py_file.relative_to(_REPO_ROOT))
            visitor = _DuckDbConnectVisitor(git_rel)
            visitor.visit(tree)
            results.extend(visitor.results)
    return results


def test_single_writer_audit_repo_wide():
    """Every non-read-only duckdb.connect() outside runtime/db_lock.py must be
    on the explicit allowlist.  A raw ``duckdb.connect(path)`` added to
    substrate/, orchestration/, or interfaces/ without routing through
    ``connect_write`` will FAIL here; the author must either fix it or
    add an allowlist entry with a cited reason.

    Non-vacuity guard: the scan must find at least one real site.
    """
    sites = _scan_source_tree()

    assert len(sites) > 0, (
        "Audit scan found zero duckdb.connect() calls across "
        f"{_SOURCE_DIRS}.  Either the source trees are missing or the "
        "glob is broken; a vacuous pass is worse than a failure."
    )

    violations: list[str] = []
    matched_allowlist: set[tuple[str, str | None, str | None, str | None]] = set()
    for site in sites:
        if site.is_read_only:
            continue
        allow_key = (
            site.path,
            site.enclosing_class,
            site.enclosing_function,
            site.first_arg,
        )
        if allow_key in _ALLOWLIST:
            matched_allowlist.add(allow_key)
            continue
        violations.append(
            f"  {site.path}:{site.line} "
            f"({site.enclosing_class or '<module>'}."
            f"{site.enclosing_function or '<module>'}, arg={site.first_arg})"
        )

    assert violations == [], (
        "Ungoverned duckdb.connect() WRITE outside runtime/db_lock.py.\n"
        "Every write connection must go through connect_write() or be on "
        "the allowlist in this test.\n\n"
        "Violations:\n"
        + "\n".join(violations)
        + "\n\nFix: route through runtime.db_lock.connect_write(), or add "
        "an allowlist entry with a cited reason."
    )
    stale_allowlist = sorted(set(_ALLOWLIST) - matched_allowlist)
    assert stale_allowlist == [], (
        "Stale duckdb.connect() write allowlist entries found. Remove or "
        "re-justify these entries:\n"
        + "\n".join(f"  {entry!r}" for entry in stale_allowlist)
    )

    read_count = sum(1 for site in sites if site.is_read_only)
    write_count = sum(1 for site in sites if not site.is_read_only)
    print(
        f"\n  Single-writer audit: {len(sites)} sites scanned - "
        f"{read_count} read-only, {write_count} write (all on allowlist)."
    )
