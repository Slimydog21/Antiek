"""unannotated_bypass — AST lint flagging substrate-invariant bypasses
not wrapped in ``@escape_hatch`` or ``with escape_hatch(...)``.

ARE-05 milestone 5 of the Antiek Rust-Execution Spec. Pairs with
``substrate/escape_hatch.py`` (Wave 1): the marker is the runtime audit
signal; this lint is the static enforcement.

Default bypass patterns: ``duckdb.connect``, ``requests.{get,post,put,
patch,delete,head}``, ``urllib.request.urlopen``. Configurable via
``tools/lints/bypass_patterns.toml``. A call is allowed if its enclosing
function is decorated with ``@escape_hatch(...)`` OR it is nested inside
a ``with escape_hatch(...):`` block.

Opt-in per path; usage::

    python -m tools.lints.unannotated_bypass <path>...

Exit codes match ``no_raise_in_substrate_writers``.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "DEFAULT_BYPASS_PATTERNS",
    "BypassViolation",
    "scan_file",
    "scan_paths",
    "load_patterns",
    "main",
]


DEFAULT_BYPASS_PATTERNS: tuple[tuple[str, str], ...] = (
    ("duckdb", "connect"),
    ("requests", "get"),
    ("requests", "post"),
    ("requests", "put"),
    ("requests", "patch"),
    ("requests", "delete"),
    ("requests", "head"),
    ("urllib.request", "urlopen"),
)


@dataclass(frozen=True)
class BypassViolation:
    path: Path
    line: int
    col: int
    qualifier: str
    method: str
    function_name: str | None

    def format_line(self) -> str:
        fn_part = f" (in {self.function_name})" if self.function_name else ""
        return (
            f"{self.path}:{self.line}:{self.col}: "
            f"unannotated bypass: {self.qualifier}.{self.method}(){fn_part}"
        )


def _qualifier_of(call: ast.Call) -> tuple[str, str] | None:
    func = call.func
    if not isinstance(func, ast.Attribute):
        return None
    value = func.value
    if isinstance(value, ast.Name):
        return (value.id, func.attr)
    if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
        return (f"{value.value.id}.{value.attr}", func.attr)
    return None


def _decorator_is_escape_hatch(dec: ast.expr) -> bool:
    if isinstance(dec, ast.Call):
        return _decorator_is_escape_hatch(dec.func)
    if isinstance(dec, ast.Name):
        return dec.id == "escape_hatch"
    if isinstance(dec, ast.Attribute):
        return dec.attr == "escape_hatch"
    return False


def _withitem_is_escape_hatch(item: ast.withitem) -> bool:
    ctx = item.context_expr
    if isinstance(ctx, ast.Call):
        func = ctx.func
        if isinstance(func, ast.Name):
            return func.id == "escape_hatch"
        if isinstance(func, ast.Attribute):
            return func.attr == "escape_hatch"
    return False


@dataclass
class _Scope:
    fn_name: str | None = None
    in_hatched_function: bool = False
    open_with_depth: int = 0

    @property
    def is_hatched(self) -> bool:
        return self.in_hatched_function or self.open_with_depth > 0


class _Walker(ast.NodeVisitor):
    def __init__(self, path: Path, patterns: Iterable[tuple[str, str]]) -> None:
        self.path = path
        self.patterns: set[tuple[str, str]] = set(patterns)
        self.violations: list[BypassViolation] = []
        self._scope_stack: list[_Scope] = [_Scope()]

    def _enter_function(self, name: str, decorators: list[ast.expr]) -> None:
        hatched = any(_decorator_is_escape_hatch(d) for d in decorators)
        self._scope_stack.append(_Scope(fn_name=name, in_hatched_function=hatched))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter_function(node.name, node.decorator_list)
        try:
            self.generic_visit(node)
        finally:
            self._scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter_function(node.name, node.decorator_list)
        try:
            self.generic_visit(node)
        finally:
            self._scope_stack.pop()

    def visit_With(self, node: ast.With) -> None:
        n_hatched = sum(1 for item in node.items if _withitem_is_escape_hatch(item))
        self._scope_stack[-1].open_with_depth += n_hatched
        try:
            self.generic_visit(node)
        finally:
            self._scope_stack[-1].open_with_depth -= n_hatched

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        n_hatched = sum(1 for item in node.items if _withitem_is_escape_hatch(item))
        self._scope_stack[-1].open_with_depth += n_hatched
        try:
            self.generic_visit(node)
        finally:
            self._scope_stack[-1].open_with_depth -= n_hatched

    def visit_Call(self, node: ast.Call) -> None:
        qm = _qualifier_of(node)
        if qm is not None and qm in self.patterns:
            scope = self._scope_stack[-1]
            if not scope.is_hatched:
                self.violations.append(
                    BypassViolation(
                        path=self.path,
                        line=node.lineno,
                        col=node.col_offset,
                        qualifier=qm[0],
                        method=qm[1],
                        function_name=scope.fn_name,
                    )
                )
        self.generic_visit(node)


def scan_file(
    path: Path,
    patterns: Iterable[tuple[str, str]] = DEFAULT_BYPASS_PATTERNS,
) -> list[BypassViolation]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []
    walker = _Walker(path, patterns)
    walker.visit(tree)
    return walker.violations


def _iter_py_files(target: Path) -> Iterator[Path]:
    if target.is_file() and target.suffix == ".py":
        yield target
        return
    if target.is_dir():
        for p in target.rglob("*.py"):
            if "__pycache__" not in p.parts:
                yield p


def scan_paths(
    paths: Iterable[Path | str],
    patterns: Iterable[tuple[str, str]] = DEFAULT_BYPASS_PATTERNS,
) -> list[BypassViolation]:
    out: list[BypassViolation] = []
    pats = list(patterns)
    for raw in paths:
        target = Path(raw)
        for f in _iter_py_files(target):
            out.extend(scan_file(f, patterns=pats))
    return out


def load_patterns(toml_path: Path | None) -> list[tuple[str, str]]:
    if toml_path is None or not toml_path.exists():
        return list(DEFAULT_BYPASS_PATTERNS)
    with toml_path.open("rb") as fh:
        data = tomllib.load(fh)
    raw = data.get("patterns", [])
    if not isinstance(raw, list):
        return list(DEFAULT_BYPASS_PATTERNS)
    out: list[tuple[str, str]] = []
    for entry in raw:
        if isinstance(entry, dict) and "qualifier" in entry and "method" in entry:
            out.append((str(entry["qualifier"]), str(entry["method"])))
    return out if out else list(DEFAULT_BYPASS_PATTERNS)


def main(argv: list[str]) -> int:
    if not argv:
        print(
            "usage: python -m tools.lints.unannotated_bypass <path>...",
            file=sys.stderr,
        )
        return 2
    patterns_path = Path(__file__).parent / "bypass_patterns.toml"
    patterns = load_patterns(patterns_path)
    violations = scan_paths(argv, patterns=patterns)
    for v in violations:
        print(v.format_line())
    if violations:
        print(f"\n{len(violations)} violation(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
