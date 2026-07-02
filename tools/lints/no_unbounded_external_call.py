"""no_unbounded_external_call — AST lint requiring explicit timeouts
on external network calls in production code.

SPR-03 timeout-discipline invariant: production HTTP/socket call sites
must carry an explicit ``timeout=`` so a downstream stall cannot pin a
worker forever. Existing violations are adopted through
``tools.lints.cli_with_baseline``; the standalone mode reports every
violation it sees.

Usage::

    python -m tools.lints.no_unbounded_external_call <path>...

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
    "Violation",
    "scan_file",
    "scan_paths",
    "main",
]


HTTPX_METHODS: frozenset[str] = frozenset(
    {"request", "get", "post", "put", "patch", "delete", "head", "options", "stream"}
)
REQUESTS_METHODS: frozenset[str] = frozenset(
    {"request", "get", "post", "put", "patch", "delete", "head", "options"}
)
SKIPPED_PARTS: frozenset[str] = frozenset({"tests", ".caffenagent", "docs"})


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    col: int
    call: str

    def format_line(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: missing timeout on {self.call}"


def _has_timeout_keyword(node: ast.Call) -> bool:
    return any(kw.arg == "timeout" for kw in node.keywords)


def _attr_chain(node: ast.AST) -> tuple[str, ...] | None:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        base = _attr_chain(node.value)
        if base is None:
            return None
        return (*base, node.attr)
    return None


class _Walker(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[Violation] = []
        self._httpx_aliases: set[str] = set()
        self._httpx_client_ctor_aliases: set[str] = set()
        self._httpx_method_aliases: set[str] = set()
        self._requests_aliases: set[str] = set()
        self._requests_method_aliases: set[str] = set()
        self._socket_aliases: set[str] = set()
        self._socket_create_connection_aliases: set[str] = set()
        self._httpx_client_names: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".", 1)[0]
            if alias.name == "httpx":
                self._httpx_aliases.add(local)
            elif alias.name == "requests":
                self._requests_aliases.add(local)
            elif alias.name == "socket":
                self._socket_aliases.add(local)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "httpx":
            for alias in node.names:
                local = alias.asname or alias.name
                if alias.name in {"Client", "AsyncClient"}:
                    self._httpx_client_ctor_aliases.add(local)
                elif alias.name in HTTPX_METHODS:
                    self._httpx_method_aliases.add(local)
        elif node.module == "requests":
            for alias in node.names:
                local = alias.asname or alias.name
                if alias.name in REQUESTS_METHODS:
                    self._requests_method_aliases.add(local)
        elif node.module == "socket":
            for alias in node.names:
                local = alias.asname or alias.name
                if alias.name == "create_connection":
                    self._socket_create_connection_aliases.add(local)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Call) and self._is_httpx_client_ctor(node.value):
            for target in node.targets:
                self._remember_client_target(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.value, ast.Call) and self._is_httpx_client_ctor(node.value):
            self._remember_client_target(node.target)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self._remember_with_clients(node.items)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._remember_with_clients(node.items)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call = self._timeoutless_external_call(node)
        if call is not None:
            self.violations.append(
                Violation(
                    path=self.path,
                    line=node.lineno,
                    col=node.col_offset,
                    call=call,
                )
            )
        self.generic_visit(node)

    def _remember_client_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self._httpx_client_names.add(target.id)

    def _remember_with_clients(self, items: list[ast.withitem]) -> None:
        for item in items:
            if (
                isinstance(item.context_expr, ast.Call)
                and self._is_httpx_client_ctor(item.context_expr)
                and item.optional_vars is not None
            ):
                self._remember_client_target(item.optional_vars)

    def _is_httpx_client_ctor(self, node: ast.Call) -> bool:
        chain = _attr_chain(node.func)
        if chain is None:
            return False
        if len(chain) == 2 and chain[0] in self._httpx_aliases:
            return chain[1] in {"Client", "AsyncClient"}
        return len(chain) == 1 and chain[0] in self._httpx_client_ctor_aliases

    def _timeoutless_external_call(self, node: ast.Call) -> str | None:
        chain = _attr_chain(node.func)
        if chain is None:
            return None

        if self._is_httpx_call(chain) and not _has_timeout_keyword(node):
            return ".".join(chain)
        if self._is_requests_call(chain) and not _has_timeout_keyword(node):
            return ".".join(chain)
        if self._is_socket_create_connection(chain) and not self._has_socket_timeout(node):
            return ".".join(chain)
        return None

    def _is_httpx_call(self, chain: tuple[str, ...]) -> bool:
        if len(chain) == 2 and chain[0] in self._httpx_aliases:
            return chain[1] in HTTPX_METHODS or chain[1] in {"Client", "AsyncClient"}
        if len(chain) == 1 and chain[0] in self._httpx_client_ctor_aliases:
            return True
        if len(chain) == 1 and chain[0] in self._httpx_method_aliases:
            return True
        if len(chain) == 2 and chain[0] in self._httpx_client_names:
            return chain[1] in HTTPX_METHODS
        return False

    def _is_requests_call(self, chain: tuple[str, ...]) -> bool:
        if len(chain) == 2 and chain[0] in self._requests_aliases:
            return chain[1] in REQUESTS_METHODS
        return len(chain) == 1 and chain[0] in self._requests_method_aliases

    def _is_socket_create_connection(self, chain: tuple[str, ...]) -> bool:
        if len(chain) == 2 and chain[0] in self._socket_aliases:
            return chain[1] == "create_connection"
        if len(chain) == 1:
            return chain[0] in self._socket_create_connection_aliases
        return False

    def _has_socket_timeout(self, node: ast.Call) -> bool:
        return _has_timeout_keyword(node) or len(node.args) >= 2


def _is_skipped_path(path: Path) -> bool:
    if SKIPPED_PARTS.intersection(path.parts):
        return True
    # Also skip test modules that live OUTSIDE a ``tests/`` dir (``test_*.py`` /
    # ``*_test.py``): they drive mocked transports, not production network calls,
    # so the prod timeout invariant does not apply — and holding test code to it
    # would force timeout kwargs into fixtures for no runtime benefit.
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
        target = Path(raw)
        for f in _iter_py_files(target):
            out.extend(scan_file(f))
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(
            "usage: python -m tools.lints.no_unbounded_external_call <path>...",
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
