#!/usr/bin/env python3
"""Retrieval gate drift lint — forbid RESTRICTED-only chunk-gate reimplementation.

The invariant (master-spec §9.0; RG-01/02/03 closure). Non-privileged chunk
retrieval must exclude BOTH ``restricted_pending_opt_in`` (gated-but-public)
AND ``personal_reading`` (owner-only). The pre-closure bugs reimplemented a
RESTRICTED-only denylist — ``list(RESTRICTED_CONTENT_CLASSES)`` in VSS SQL and
``content_class in RESTRICTED_CONTENT_CLASSES`` on ``GET /chunks`` — which let
``personal_reading`` leak on the default substrate and the claim-modal fetch.

Canonical surfaces (must import the helper, never hand-roll):

  * ``substrate/graph/retrieval_substrate.py`` — VSS / brute-force substrate;
    must call ``retrieval_gate.non_privileged_chunk_sql_clause`` in
    ``_vss_query`` (same as ``search()``).
  * ``interfaces/research/api/app.py`` — ``GET /chunks/{chunk_id}``; must call
    ``retrieval_gate.is_chunk_body_withheld`` (same frozensets as chunk search).

Emission point (NOT scanned — this module *defines* the gate SQL):

  * ``substrate/graph/retrieval_gate.py`` — the only place that may format the
    ``NOT IN`` clause over ``_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES``.

Consumer that already delegates (NOT scanned here — covered by import at call site):

  * ``substrate/graph/search.py`` — imports ``non_privileged_chunk_sql_clause``.

What is flagged in the watched files (executable code only — docstrings are
skipped so prose that *warns* against RESTRICTED-only does not false-positive):

  1. SQL literals (or ``+``-concatenated constant strings) with a chunk-gate
     ``NOT IN`` that names ``restricted_pending_opt_in`` but omits
     ``personal_reading`` in the same fragment.
  2. ``list(RESTRICTED_CONTENT_CLASSES)`` / ``tuple(...)`` / ``sorted(...)`` used
     to build a gate bind list — the exact VSS regression shape.
  3. ``<expr> in RESTRICTED_CONTENT_CLASSES`` — the exact HTTP regression shape
     (must use ``is_chunk_body_withheld`` instead).

A watched file that imports/uses the canonical helper AND contains no flagged
executable pattern is clean. A file that imports the helper but *also* inlines
RESTRICTED-only gate code still reds (drift with a stale import left behind).

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

# Surfaces that MUST delegate to retrieval_gate — not the whole graph tree.
_WATCHED_FILES: tuple[str, ...] = (
    "substrate/graph/retrieval_substrate.py",
    "interfaces/research/api/app.py",
)

# The canonical emitter — documented here, not scanned.
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
    # Canonical helper always binds personal_reading too.
    return _PERSONAL_CLASS_RE.search(value) is None


def _name_is_restricted_classes(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "RESTRICTED_CONTENT_CLASSES"


def _file_uses_canonical_gate(tree: ast.Module) -> bool:
    """True iff the file imports or calls the sanctioned gate helpers."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in {
                    "non_privileged_chunk_sql_clause",
                    "is_chunk_body_withheld",
                }:
                    return True
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in {
                "non_privileged_chunk_sql_clause",
                "is_chunk_body_withheld",
            }:
                return True
            if isinstance(func, ast.Attribute) and func.attr in {
                "non_privileged_chunk_sql_clause",
                "is_chunk_body_withheld",
            }:
                return True
    return False


def _scan_file(rel: str, py: Path) -> list[str]:
    out: list[str] = []
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return out

    doc_lines = _docstring_lines(tree)
    uses_canonical = _file_uses_canonical_gate(tree)
    seen_lines: set[int] = set()

    def _report(lineno: int, message: str) -> None:
        if lineno in doc_lines or lineno in seen_lines:
            return
        seen_lines.add(lineno)
        suffix = (
            ""
            if uses_canonical
            else " — file does not import non_privileged_chunk_sql_clause "
            "or is_chunk_body_withheld"
        )
        out.append(f"{rel}:{lineno}: {message}{suffix}")

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
                    "is_chunk_body_withheld",
                )

    return out


def find_violations(root: Path = _REPO) -> list[str]:
    """Return ``path:line: message`` for RESTRICTED-only gate drift."""
    out: list[str] = []
    for rel in _WATCHED_FILES:
        py = root / rel
        if not py.is_file():
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
            f"{_CANONICAL_EMITTER}; import non_privileged_chunk_sql_clause "
            f"(VSS/substrate) or is_chunk_body_withheld (HTTP). Watched surfaces: "
            + ", ".join(_WATCHED_FILES)
        )
        return 1
    print(
        "OK: no RESTRICTED-only chunk-gate reimplementation in watched surfaces."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())