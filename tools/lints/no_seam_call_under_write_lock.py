"""no_seam_call_under_write_lock — AST lint forbidding a network/dispatch/
subprocess SEAM call inside a held single-writer lock (nygard SPR-05, bulkhead).

The DuckDB single-writer funnel (``runtime/db_lock.connect_write`` /
``FlockWriteCoordinator.acquire_write_context``) serializes every graph write at
``--workers 1``. If a caller performs a SEAM call — an ``httpx``/``requests``
request, a ``socket`` connect, an LLM ``dispatch``, a ``.harvest``/``.fetch``/
``.download``, or a ``subprocess`` — WHILE holding the write lock, a stall on that
seam pins the funnel and stalls every other investigation. This lint flags that:
acquire late / release early — do the seam call OUTSIDE the ``with`` block, hold
the lock only for the DB writes.

Follows the ``tools/lints/`` convention (frozen ``Violation`` + ``scan_file`` /
``scan_paths`` + ``main`` with exit codes) so it plugs into
``tools.lints.cli_with_baseline``. Pre-existing intentional cases are adopted via
the baseline (shrink-only).

Detection is intentionally high-signal (exact attribute/name match) to avoid
false positives: ``cursor.fetchone`` / ``dict.get`` do NOT match; ``.fetch`` /
``.harvest`` / ``.download`` / ``.dispatch`` / ``httpx.get`` / ``requests.post`` /
``socket.create_connection`` / ``subprocess.run`` DO.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Violation", "scan_file", "scan_paths", "main"]

# The write-lock context managers whose body must stay seam-free.
_WRITE_LOCK_CTX: frozenset[str] = frozenset({"connect_write", "acquire_write_context"})

# Exact seam call names (attribute or bare name). High-signal only.
_SEAM_NAMES: frozenset[str] = frozenset(
    {"harvest", "fetch", "download", "dispatch", "stream", "create_connection"}
)
# Network HTTP methods, flagged only when the call is on an httpx/requests base
# (module or a *client*-suggesting receiver) — see _is_http_seam.
_HTTP_METHODS: frozenset[str] = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "request"}
)
_HTTP_BASES: frozenset[str] = frozenset({"httpx", "requests"})
_SUBPROCESS_FUNCS: frozenset[str] = frozenset({"run", "call", "Popen", "check_output", "check_call"})
SKIPPED_PARTS: frozenset[str] = frozenset({"tests", ".caffenagent", "docs"})


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    col: int
    seam: str

    def format_line(self) -> str:
        return (
            f"{self.path}:{self.line}:{self.col}: seam call {self.seam!r} inside a "
            "held write lock (acquire late / release early)"
        )


def _callee_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _base_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id
    return None


def _is_seam_call(node: ast.Call) -> str | None:
    name = _callee_name(node)
    if name is None:
        return None
    if name in _SEAM_NAMES:
        return name
    if name in _HTTP_METHODS and _base_name(node) in _HTTP_BASES:
        return f"{_base_name(node)}.{name}"
    if name in _SUBPROCESS_FUNCS and _base_name(node) == "subprocess":
        return f"subprocess.{name}"
    return None


def _is_write_lock_with(item: ast.withitem) -> bool:
    expr = item.context_expr
    if not isinstance(expr, ast.Call):
        return False
    func = expr.func
    callee = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else None)
    return callee in _WRITE_LOCK_CTX


class _Walker(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[Violation] = []

    def _scan_body(self, body: list[ast.stmt]) -> None:
        for stmt in body:
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call):
                    seam = _is_seam_call(node)
                    if seam is not None:
                        self.violations.append(
                            Violation(
                                path=self.path,
                                line=node.lineno,
                                col=node.col_offset,
                                seam=seam,
                            )
                        )

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        if any(_is_write_lock_with(it) for it in node.items):
            self._scan_body(node.body)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self._visit_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_with(node)


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
    walker = _Walker(path)
    walker.visit(tree)
    return walker.violations


def _iter_py_files(target: Path) -> Iterator[Path]:
    if target.is_file() and target.suffix == ".py":
        if not _is_skipped_path(target):
            yield target
        return
    if target.is_dir():
        for p in target.rglob("*.py"):
            if "__pycache__" not in p.parts and not _is_skipped_path(p):
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
            "usage: python -m tools.lints.no_seam_call_under_write_lock <path>...",
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
