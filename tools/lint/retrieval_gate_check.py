#!/usr/bin/env python3
"""Retrieval gate drift lint — forbid RESTRICTED-only chunk-gate reimplementation.

The invariant (master-spec §9.0; RG-01/02/03 + ASR SR-01/02 closure).
Non-privileged chunk retrieval must exclude BOTH
``restricted_pending_opt_in`` (gated-but-public) AND ``personal_reading``
(owner-only). The pre-closure bugs reimplemented a RESTRICTED-only denylist —
``list(RESTRICTED_CONTENT_CLASSES)`` in VSS SQL and
``content_class in RESTRICTED_CONTENT_CLASSES`` on ``GET /chunks`` — which let
``personal_reading`` leak on the default substrate and the claim-modal fetch.

Allowlist (may contain gate SQL or delegate without CI-red):

  * ``substrate/graph/retrieval_gate.py`` — the **only** emitter of the
    canonical ``NOT IN`` fragment over ``_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES``.
  * ``substrate/graph/search.py`` — **delegate only**; must call
    ``non_privileged_chunk_sql_clause``, never hand-roll gate SQL.
  * test files — exercise regressions and polarity pins directly.

Every other ``.py`` file is scanned. Flagged executable patterns (docstrings
skipped so prose warnings do not false-positive):

  1. SQL literals (or ``+``-concatenated constant strings) with a chunk-gate
     ``NOT IN`` that names ``restricted_pending_opt_in`` but omits
     ``personal_reading`` in the same fragment.
  2. ``list(RESTRICTED_CONTENT_CLASSES)`` / ``tuple(...)`` / ``sorted(...)`` used
     to build a gate bind list — the exact VSS regression shape.
  3. ``content_class in RESTRICTED_CONTENT_CLASSES`` — the exact HTTP regression
     shape (must use ``_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES`` or
     ``is_chunk_body_withheld`` instead).

Modeled on ``tools/lint/serve_invariants_check.py``: same ``path:line`` output,
same exit-code contract (0 = clean, 1 = violations).

KNOWN, ACCEPTED LIMITATION: gate SQL whose class names are interpolated at runtime
(f-strings, ``.format()``, config-driven table aliases) is not detected — the
tokens never appear as static text. Covered shapes are every production regression:
literal ``NOT IN ('restricted_pending_opt_in')`` without ``personal_reading``,
``list(RESTRICTED_CONTENT_CLASSES)``, and ``in RESTRICTED_CONTENT_CLASSES``.

Exit 0 = clean; exit 1 = a violation, printed as ``path:line``.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

# Canonical emitter + search delegate — documented here, not scanned.
_ALLOWED_FILES: frozenset[str] = frozenset({
    "substrate/graph/retrieval_gate.py",
    "substrate/graph/search.py",
})

_CANONICAL_EMITTER = "substrate/graph/retrieval_gate.py"

_NOT_IN_RE = re.compile(r"\bnot\s+in\b", re.IGNORECASE)
_RESTRICTED_CLASS_RE = re.compile(r"\brestricted_pending_opt_in\b", re.IGNORECASE)
_PERSONAL_CLASS_RE = re.compile(r"\bpersonal_reading\b", re.IGNORECASE)


def _concat_constant_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _concat_constant_str(node.left)
        right = _concat_constant_str(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _docstring_lines(tree: ast.Module) -> set[int]:
    """Line numbers that belong to module/class/function docstrings."""
    lines: set[int] = set()

    def _mark_docstring(stmt: ast.stmt) -> None:
        if not isinstance(stmt, ast.Expr):
            return
        val = stmt.value
        if not isinstance(val, ast.Constant) or not isinstance(val.value, str):
            return
        end = val.end_lineno or val.lineno
        for ln in range(val.lineno, end + 1):
            lines.add(ln)

    if tree.body:
        _mark_docstring(tree.body[0])
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.body
        ):
            _mark_docstring(node.body[0])
    return lines


def _is_restricted_only_sql(value: str) -> bool:
    """True iff ``value`` is a RESTRICTED-only chunk-gate SQL fragment."""
    if not _NOT_IN_RE.search(value):
        return False
    if not _RESTRICTED_CLASS_RE.search(value):
        return False
    return _PERSONAL_CLASS_RE.search(value) is None


def _name_is_restricted_classes(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "RESTRICTED_CONTENT_CLASSES"


def _is_test_file(rel: str) -> bool:
    parts = Path(rel).parts
    if parts and parts[0] == "tests":
        return True
    stem = Path(rel).name
    return stem.startswith("test_") or stem.endswith("_test.py")


def _is_lint_scanner(rel: str) -> bool:
    parts = Path(rel).parts
    return len(parts) >= 2 and parts[0] == "tools" and parts[1] == "lint"


def _scan_file(rel: str, py: Path) -> list[str]:
    out: list[str] = []
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return out

    doc_lines = _docstring_lines(tree)
    seen_lines: set[int] = set()

    def _report(lineno: int, message: str) -> None:
        if lineno in doc_lines or lineno in seen_lines:
            return
        seen_lines.add(lineno)
        out.append(f"{rel}:{lineno}: {message}")

    for node in ast.walk(tree):
        candidate: str | None = None
        sql_site: ast.Constant | ast.BinOp | None = None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            candidate = node.value
            sql_site = node
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            candidate = _concat_constant_str(node)
            if candidate is not None:
                sql_site = node
        if (
            candidate is not None
            and sql_site is not None
            and _is_restricted_only_sql(candidate)
        ):
            _report(
                sql_site.lineno,
                "RESTRICTED-only chunk-gate SQL (NOT IN restricted_pending_opt_in "
                "without personal_reading) — use "
                "retrieval_gate.non_privileged_chunk_sql_clause",
            )

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"list", "tuple", "sorted"}
            and node.args
            and _name_is_restricted_classes(node.args[0])
        ):
            _report(
                node.lineno,
                f"RESTRICTED-only chunk gate via {node.func.id}"
                "(RESTRICTED_CONTENT_CLASSES) — use "
                "non_privileged_chunk_sql_clause",
            )

        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            if not isinstance(node.ops[0], ast.In):
                continue
            if not node.comparators or not _name_is_restricted_classes(
                node.comparators[0],
            ):
                continue
            left = node.left
            if (
                (isinstance(left, ast.Name) and left.id == "content_class")
                or (
                    isinstance(left, ast.Attribute)
                    and left.attr == "content_class"
                )
            ):
                _report(
                    node.lineno,
                    "RESTRICTED-only HTTP withhold (content_class in "
                    "RESTRICTED_CONTENT_CLASSES) — use "
                    "_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES or "
                    "is_chunk_body_withheld",
                )

    return out


def find_violations(root: Path = _REPO) -> list[str]:
    """Return ``path:line: message`` for RESTRICTED-only gate drift."""
    out: list[str] = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root).as_posix()
        if (
            rel in _ALLOWED_FILES
            or _is_test_file(rel)
            or _is_lint_scanner(rel)
        ):
            continue
        out.extend(_scan_file(rel, py))
    return sorted(out)


def main() -> int:
    violations = find_violations()
    if violations:
        print("Retrieval-gate (RESTRICTED-only reimplementation) violations:")
        for line in violations:
            print(f"  {line}")
        print(
            f"\nNon-privileged chunk retrieval must exclude both "
            f"restricted_pending_opt_in and personal_reading. Emit SQL only in "
            f"{_CANONICAL_EMITTER}; other surfaces import "
            f"non_privileged_chunk_sql_clause (VSS/substrate/search) or "
            f"_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES / is_chunk_body_withheld "
            f"(HTTP). Allowlist: "
            + ", ".join(sorted(_ALLOWED_FILES))
            + "; test files."
        )
        return 1
    print(
        "OK: no RESTRICTED-only chunk-gate reimplementation outside allowlist."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())