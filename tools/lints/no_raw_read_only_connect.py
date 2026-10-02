"""no_raw_read_only_connect — read sites must use ``connect_read``.

THE INVARIANT. ``runtime/db_lock.py:921`` says it plainly: "Use this instead
of raw duckdb.connect(..., read_only=True) at read sites so every DB access
funnels through one module." The reason is not tidiness. DuckDB REFUSES a
read-only handle when the same process already holds that file read-write:

    duckdb.connect(db, read_only=True)
    -> ConnectionException: Can't open a connection to same database file
       with a different configuration than existing connections

Under ``uvicorn --workers 1`` — which this service runs because DuckDB is
single-writer — a live write handle is the STEADY STATE, not an edge case.
``connect_read`` catches that exact conflict (and the newer BinderError
variant) and falls back to a read-oriented read-write handle. A raw call
does not, and callers typically catch ``IOException`` only, so the
``ConnectionException`` escapes as a 500.

HOW THIS WAS FOUND. ``tools/reachability/probes/usability_keystone.py`` —
a five-leg journey probe that exists in the tree and that no workflow runs —
failed on its first execution at ``app.py:3018``, in ``get_chunk``. Every
per-brick test passed. The journey did not. That one site is fixed; this
lint makes the rest countable instead of waiting for the next probe.

THE RULE. A call to ``.connect(...)`` (or a bare ``connect(...)``) with
``read_only=True`` passed as a keyword constant, anywhere outside
``runtime/db_lock.py``, is a violation. AST, not regex: the grep form found
45 sites and missed 9 that span lines.

NOT FLAGGED, deliberately:

* ``runtime/db_lock.py`` itself, which is where the sanctioned fallback
  lives and must make the raw call.
* ``read_only`` passed as a variable rather than a literal ``True``. The
  AST cannot decide it, and guessing would red honest code. A deliberate
  false negative, recorded here rather than papered over.

Baselined shrink-only: the existing sites are grandfathered so the gate
holds the line for new code without redding a 54-site migration in flight.

Usage::

    python -m tools.lints.no_raw_read_only_connect <path>...

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

__all__ = ["SKIPPED_PARTS", "Violation", "scan_file", "scan_paths", "main"]

SKIPPED_PARTS: frozenset[str] = frozenset(
    {"tests", "docs", "node_modules", ".worktrees", "__pycache__", ".venv"}
)

#: The one module that must make the raw call — it IS the fallback.
_SANCTIONED = ("runtime/db_lock.py",)


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    col: int
    call: str

    def format_line(self) -> str:
        return (
            f"{self.path}:{self.line}:{self.col}: raw {self.call}(read_only=True) "
            f"— use runtime.db_lock.connect_read instead. DuckDB refuses a "
            f"read-only handle when this process already holds the file "
            f"read-write (the --workers 1 steady state), and the resulting "
            f"ConnectionException is not an IOException, so it escapes as a 500."
        )


def _is_skipped(path: Path) -> bool:
    if SKIPPED_PARTS.intersection(path.parts):
        return True
    posix = path.as_posix()
    if any(posix.endswith(s) for s in _SANCTIONED):
        return True
    name = path.name
    return name.startswith("test_") or name.endswith("_test.py")


def scan_file(path: Path) -> list[Violation]:
    if _is_skipped(path):
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "connect":
            continue
        for kw in node.keywords:
            if (
                kw.arg == "read_only"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
            ):
                out.append(
                    Violation(
                        path=path, line=node.lineno, col=node.col_offset, call=name
                    )
                )
    return out


def _iter_py_files(target: Path) -> Iterator[Path]:
    if target.is_file() and target.suffix == ".py":
        if not _is_skipped(target):
            yield target
        return
    if target.is_dir():
        for p in sorted(target.rglob("*.py")):
            if not _is_skipped(p):
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
            "usage: python -m tools.lints.no_raw_read_only_connect <path>...",
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
