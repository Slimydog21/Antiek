#!/usr/bin/env python3
"""Serve-guard boundary lint — forbid direct ``serve_full_text(`` calls outside
the allowlist (SPR-02 M4).

The invariant (SPR-02 rights model): the ONLY full-body serve path is the
serving-boundary guard ``substrate.books.serve_guard.serve_full_text_guarded``
(re-exported through the ``interfaces.research.api.serve_guard`` shim), which
composes the content_class gate with an INDEPENDENT license-tier cross-check.
The raw gate ``substrate.books.serve.serve_full_text`` clears a body on
``content_class`` alone — calling it directly bypasses the license-tier drift
check that defends against a non-{T1} body being served from Antiek storage (a
redistribution / NC-commercial-use violation). So a direct CALL to
``serve_full_text(`` is forbidden everywhere except:

  * ``substrate/books/serve.py``        — where it is DEFINED.
  * ``substrate/books/serve_guard.py``  — the guard, the one sanctioned caller
                                          (it adds the tier arm).
  * test files                          — tests exercise the raw gate's unit
                                          behaviour directly.

(The ``interfaces/research/api/serve_guard.py`` shim only re-exports the GUARDED
name and never calls ``serve_full_text`` itself, so it need not be allowlisted.)

A NEW direct ``serve_full_text(`` call added anywhere else (a careless future
endpoint, a worker, a script) makes CI go red here, forcing it through the
guard.

This is modeled EXACTLY on ``tools/lint/boundary_check.py``: same ``path:line``
output, same exit-code contract (0 = clean, 1 = violations), same AST walk over
the tree. We match the CALL (``ast.Call`` whose callee resolves to the
``serve_full_text`` symbol), not the import per se, because importing the symbol
is fine — ``serve_guard`` and the tests legitimately do — what must be gated is
INVOKING it outside the allowlist. Three call forms are caught per file:

  1. a bare-name callee ``serve_full_text(con, ...)``;
  2. an attribute callee ``serve.serve_full_text(con, ...)``;
  3. an ALIASED-import callee — ``from substrate.books.serve import
     serve_full_text as _sft`` then ``_sft(con, ...)``. We first walk the file's
     ``import`` / ``from ... import`` statements and collect every local name
     bound to the ``serve_full_text`` symbol (its ``asname`` when aliased, else
     the imported name), then flag any ``Call`` whose ``Name`` callee is in that
     set. Without this, an aliased import is a real "grep proves no bypass"
     hole.

KNOWN, ACCEPTED LIMITATION: a fully dynamic invocation —
``getattr(mod, "serve_full_text")(...)`` or a name assembled at runtime — is NOT
detected (the callee is not a static ``Name``/``Attribute``/aliased binding).
This is accepted risk: such an invocation is exotic, easy to spot in review, and
chasing arbitrary dynamic dispatch is out of scope for a static AST lint. The
three static forms above cover every realistic accidental bypass.

Exit 0 = clean; exit 1 = a violation, printed as ``path:line``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

# The forbidden callee. A direct call to this name outside the allowlist
# bypasses the license-tier arm of the serving boundary.
_GUARDED_CALLEE = "serve_full_text"

# The guarded callee's own GUARDED form — never flag it (its name is a strict
# superset of _GUARDED_CALLEE, so guard against a false positive on it).
_GUARD_CALLEE = "serve_full_text_guarded"

# Paths (relative to the repo root) where a direct ``serve_full_text(`` call is
# legitimate: where it is defined, the one guard that wraps it (its real home),
# and tests. The interfaces shim only re-exports the guarded name and does not
# call ``serve_full_text``, so it is NOT allowlisted.
_ALLOWED_FILES: frozenset[str] = frozenset(
    {
        "substrate/books/serve.py",
        "substrate/books/serve_guard.py",
        # The standing corpus audit calls serve_full_text READ-ONLY to AUDIT the
        # gate itself — it asserts a gated doc does NOT leak a body through the
        # raw content_class projection. It wants the unguarded projection on
        # purpose (the guarded path would raise); it never serves to a client.
        "substrate/corpus_audit.py",
    }
)


def _aliases_bound_to_guarded(tree: ast.AST) -> set[str]:
    """Local names in this module bound (by import) to the ``serve_full_text``
    symbol. Catches the aliased-import bypass:

        from substrate.books.serve import serve_full_text as _sft
        _sft(con, document_id)   # callee Name is '_sft', not 'serve_full_text'

    For each ``import`` / ``from ... import`` alias whose imported ``name`` is
    exactly ``serve_full_text``, we record the LOCAL binding (``asname`` if
    present, else the imported name). ``serve_full_text_guarded`` is a distinct
    symbol and is never collected. We do not resolve the module path — binding
    ANY local name to a symbol literally named ``serve_full_text`` is the signal
    we gate on."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == _GUARDED_CALLEE:
                    bound.add(alias.asname or alias.name)
    return bound


def _is_guarded_call(node: ast.AST, aliases: frozenset[str]) -> bool:
    """True iff ``node`` is a direct call to the ``serve_full_text`` symbol (and
    NOT the allowed ``serve_full_text_guarded``). Matches a bare-name callee
    (``serve_full_text(con, ...)``), an attribute callee
    (``serve.serve_full_text(con, ...)``), and an aliased-import callee whose
    ``Name`` is in ``aliases`` (``_sft(con, ...)``)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        name = func.id
        # A bare match on the canonical name, OR an alias bound to the symbol.
        if name in aliases and name != _GUARD_CALLEE:
            return True
    elif isinstance(func, ast.Attribute):
        name = func.attr
    else:
        return False
    return name == _GUARDED_CALLEE and name != _GUARD_CALLEE


def _is_test_file(rel: str) -> bool:
    """A test file: tests/ tree, or a basename matching ``test_*.py`` /
    ``*_test.py``. Tests legitimately call the raw gate to assert its unit
    behaviour."""
    parts = Path(rel).parts
    if parts and parts[0] == "tests":
        return True
    stem = Path(rel).name
    return stem.startswith("test_") or stem.endswith("_test.py")


def find_violations(root: Path = _REPO) -> list[str]:
    """Return ``path:line: message`` strings for every direct
    ``serve_full_text(`` call outside the allowlist + test files."""
    out: list[str] = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root).as_posix()
        if rel in _ALLOWED_FILES or _is_test_file(rel):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        # Per-file: local names this module bound to the serve_full_text symbol
        # via an (possibly aliased) import, so an aliased-import call is caught.
        aliases = frozenset(_aliases_bound_to_guarded(tree))
        for node in ast.walk(tree):
            if _is_guarded_call(node, aliases):
                out.append(
                    f"{rel}:{node.lineno}: direct call to "
                    f"'{_GUARDED_CALLEE}(' outside the allowlist — route the "
                    f"full-body serve through serve_full_text_guarded "
                    f"(substrate/books/serve_guard.py)"
                )
    return out


def main() -> int:
    violations = find_violations()
    if violations:
        print("Serve-guard boundary violations:")
        for line in violations:
            print(f"  {line}")
        print(
            "\nA full body may leave Antiek storage ONLY through "
            "serve_full_text_guarded (substrate/books/serve_guard.py), "
            "which adds the independent license-tier drift check on top of the "
            "content_class gate. Calling serve_full_text directly bypasses it "
            "and risks serving a non-T1 body (a redistribution / NC-commercial "
            "violation). Allowlist: substrate/books/serve.py (definition), "
            "substrate/books/serve_guard.py (the guard), and test files."
        )
        return 1
    print(
        "OK: no direct serve_full_text() calls outside the guard + allowlist."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
