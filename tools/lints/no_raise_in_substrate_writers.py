"""no_raise_in_substrate_writers — AST lint flagging ``raise`` statements
in code that should return ``Result[T, SubstrateError]`` instead.

ARE-02 milestone 7 of the Antiek Rust-Execution Spec
(``~/specs/antiek-rust-execution/``). Pairs with ``substrate/results.py``
(Wave 1): the encoding is the carrier; this lint is the enforcement.

Opt-in per path: pass the paths you want to scan as arguments. Today's
default scan list is empty; the operator wires it into CI once a batch
of boundary refactors has landed and the allow-list is curated.

Allow-list:
- ``ALLOWED_SYSTEM_EXCEPTIONS`` (hard-coded) covers OSError /
  MemoryError / KeyboardInterrupt / SystemExit / BaseException plus
  programmer-error signals (AssertionError / NotImplementedError /
  ResultUnwrapError from ``substrate.results``).
- ``tools/lints/raise_allowlist.toml``'s ``allowed_exceptions`` array
  extends the allow-list per repo policy.

Usage::

    python -m tools.lints.no_raise_in_substrate_writers <path>...

Exit codes:
    0   no violations
    1   one or more violations (printed to stdout, count to stderr)
    2   usage error (no paths)
"""

from __future__ import annotations

import ast
import sys
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ALLOWED_SYSTEM_EXCEPTIONS",
    "Violation",
    "scan_file",
    "scan_paths",
    "load_allowlist",
    "main",
]


ALLOWED_SYSTEM_EXCEPTIONS: frozenset[str] = frozenset(
    {
        "OSError",
        "MemoryError",
        "KeyboardInterrupt",
        "SystemExit",
        "BaseException",
        "AssertionError",
        "NotImplementedError",
        "ResultUnwrapError",
    }
)


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    col: int
    exception_name: str
    function_name: str | None

    def format_line(self) -> str:
        fn_part = f" (in {self.function_name})" if self.function_name else ""
        return f"{self.path}:{self.line}:{self.col}: raise {self.exception_name}{fn_part}"


def _exception_name(node: ast.Raise) -> str:
    if node.exc is None:
        return "<bare-reraise>"
    exc = node.exc
    if isinstance(exc, ast.Name):
        return exc.id
    if isinstance(exc, ast.Call):
        if isinstance(exc.func, ast.Name):
            return exc.func.id
        if isinstance(exc.func, ast.Attribute):
            return exc.func.attr
    if isinstance(exc, ast.Attribute):
        return exc.attr
    return "<dynamic>"


class _Walker(ast.NodeVisitor):
    def __init__(self, path: Path, allow: frozenset[str] | set[str]) -> None:
        self.path = path
        self.allow = allow
        self.violations: list[Violation] = []
        self._fn_stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._fn_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self._fn_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._fn_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self._fn_stack.pop()

    def visit_Raise(self, node: ast.Raise) -> None:
        name = _exception_name(node)
        if name == "<bare-reraise>":
            return
        if name not in self.allow:
            self.violations.append(
                Violation(
                    path=self.path,
                    line=node.lineno,
                    col=node.col_offset,
                    exception_name=name,
                    function_name=self._fn_stack[-1] if self._fn_stack else None,
                )
            )
        self.generic_visit(node)


def scan_file(
    path: Path, allow_extra: Iterable[str] | None = None
) -> list[Violation]:
    allow: frozenset[str] | set[str] = ALLOWED_SYSTEM_EXCEPTIONS
    if allow_extra:
        allow = ALLOWED_SYSTEM_EXCEPTIONS | set(allow_extra)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []
    walker = _Walker(path, allow)
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
    paths: Iterable[Path | str], allow_extra: Iterable[str] | None = None
) -> list[Violation]:
    out: list[Violation] = []
    for raw in paths:
        target = Path(raw)
        for f in _iter_py_files(target):
            out.extend(scan_file(f, allow_extra=allow_extra))
    return out


def load_allowlist(toml_path: Path | None) -> set[str]:
    if toml_path is None or not toml_path.exists():
        return set()
    with toml_path.open("rb") as fh:
        data = tomllib.load(fh)
    raw = data.get("allowed_exceptions", [])
    if not isinstance(raw, list):
        return set()
    return {str(name) for name in raw}


def main(argv: list[str]) -> int:
    if not argv:
        print(
            "usage: python -m tools.lints.no_raise_in_substrate_writers <path>...",
            file=sys.stderr,
        )
        return 2
    allowlist_path = Path(__file__).parent / "raise_allowlist.toml"
    extra = load_allowlist(allowlist_path)
    violations = scan_paths(argv, allow_extra=extra)
    for v in violations:
        print(v.format_line())
    if violations:
        print(f"\n{len(violations)} violation(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
