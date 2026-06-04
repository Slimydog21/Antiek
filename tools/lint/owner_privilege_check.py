#!/usr/bin/env python3
"""Owner-privilege boundary lint — forbid a PRIVILEGED ``policy_tag`` literal
reaching retrieval outside the auth-checked allowlist (Activation SPR-owner-read).

The invariant (master-spec §9.0 retrieval-time gating + the owner-read path):
the PRIVILEGED policy tags ``operator_only`` / ``private_research`` are the
§9.0 retrieval BYPASS — they admit the owner's gated (``restricted_pending_opt_in``)
AND owner-only (``personal_reading``) corpus through the deny-by-default gate
(``substrate.graph.retrieval_gate.PRIVILEGED_POLICY_TAGS``). A bypass is only
safe when an AUTH CHECK has first PROVEN the caller is the owner. The owner-read
endpoints do this server-side: ``ask_book`` / ``corpus_search`` resolve the tag
through ``_owner_read_policy_tag(request)``, which returns ``operator_only`` ONLY
for an authenticated owner (and the non-privileged default otherwise).

The risk this guards: a FUTURE endpoint (a careless new route, a worker, a
script) that passes a privileged ``policy_tag`` LITERAL — ``policy_tag="operator_only"``
or ``policy_tag=_OWNER_READ_POLICY_TAG`` — straight into ``search(...)`` or
``answer_book_question(...)`` WITHOUT first resolving it through an auth check.
That would hand the §9.0 bypass to an unauthenticated caller and leak the
owner's gated/personal corpus — the exact §9.0 (Hachette/Bartz) leak
CLAUDE.md invariant #4 + the Sprint-18 legal gate exist to prevent. Nothing
mechanical stops it today; the other §9.0 invariants ARE guarded mechanically
(``owner_boundary_check.py`` / ``retrieval_gate_check.py`` are the precedent),
so this closes the matching hole for the privileged-tag axis.

The rule, mechanically
----------------------
Flag any ``ast.Call`` whose callee is ``search`` or ``answer_book_question``
(bare-name or attribute callee — ``search(...)`` / ``mod.search(...)``) that
passes a PRIVILEGED ``policy_tag`` as a STATIC literal:

  * a string constant ``policy_tag="operator_only"`` / ``policy_tag="private_research"``;
  * the named constant ``policy_tag=_OWNER_READ_POLICY_TAG`` (the books.py
    local whose value IS ``operator_only``).

…when the call site is OUTSIDE the allowlist. The legitimate owner-read sites
resolve the tag through ``_owner_read_policy_tag(request)`` — a CALL, never a
bare literal/Name — so they do not match this rule at all; the allowlist is the
documented hard-coded set of auth-checked sites (defense in depth, so a literal
sneaking into one of them is still reviewed deliberately).

This is the precise shape because the production owner-read sites pass the tag
via the helper call (an ``ast.Call`` argument), NOT a literal — so flagging the
literal/Name form catches every NEW bypass without false-positiving the two real
sites. A tag assembled fully at runtime (a variable computed elsewhere) is not
detected; that is accepted risk, identical to the documented limitation in
``retrieval_gate_check.py`` — the covered shapes are every realistic accidental
bypass (a hard-coded privileged literal or the named constant).

Modeled EXACTLY on ``tools/lint/serve_guard_check.py`` /
``tools/lint/owner_boundary_check.py``: same ``path:line`` output, same
exit-code contract (0 = clean, 1 = a violation), same AST walk over the tree,
same test-file + lint-scanner skip.

Exit 0 = clean; exit 1 = a violation, printed as ``path:line``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

# The retrieval callees the privileged tag gates. Only these two accept a
# ``policy_tag`` that bypasses the §9.0 gate; a privileged literal at any other
# call is a different concern (and would not reach the gate).
_GUARDED_CALLEES: frozenset[str] = frozenset({"search", "answer_book_question"})

# The PRIVILEGED policy tags (mirror substrate.graph.retrieval_gate.PRIVILEGED_POLICY_TAGS;
# kept as a literal here so the lint has no import-time dependency on substrate).
_PRIVILEGED_POLICY_TAGS: frozenset[str] = frozenset({"operator_only", "private_research"})

# The named local in interfaces/research/api/books.py whose VALUE is the
# privileged ``operator_only`` tag. Passing it as a bare ``Name`` to a guarded
# callee is the same bypass as the string literal, so we flag it too.
_PRIVILEGED_TAG_NAMES: frozenset[str] = frozenset({"_OWNER_READ_POLICY_TAG"})

# Auth-checked call sites that legitimately resolve a privileged ``policy_tag``
# (today exactly the owner-read endpoints). They pass the tag via
# ``_owner_read_policy_tag(request)`` — a CALL, not a literal — so they do not
# match the literal/Name rule anyway; the allowlist is documented defense in
# depth so even a literal here is a reviewed, deliberate choice.
_ALLOWED_FILES: frozenset[str] = frozenset(
    {
        "interfaces/research/api/books.py",
    }
)


def _privileged_policy_tag_literal(call: ast.Call) -> ast.expr | None:
    """If ``call`` passes a PRIVILEGED ``policy_tag`` as a static literal/Name,
    return the offending node; else None.

    Catches BOTH forms:
      * ``policy_tag="operator_only"`` / ``policy_tag="private_research"`` — a
        ``Constant`` string in PRIVILEGED_POLICY_TAGS;
      * ``policy_tag=_OWNER_READ_POLICY_TAG`` — a bare ``Name`` whose id is a
        known privileged-tag constant.
    A non-literal value (a variable, an attribute, a CALL like
    ``_owner_read_policy_tag(request)``) is NOT flagged — that is the resolved,
    auth-checked path the legitimate sites take.
    """
    for kw in call.keywords:
        if kw.arg != "policy_tag":
            continue
        val = kw.value
        if (
            isinstance(val, ast.Constant)
            and isinstance(val.value, str)
            and val.value in _PRIVILEGED_POLICY_TAGS
        ):
            return val
        if isinstance(val, ast.Name) and val.id in _PRIVILEGED_TAG_NAMES:
            return val
    return None


def _callee_name(call: ast.Call) -> str | None:
    """The callee's simple name: ``search(...)`` → ``search``;
    ``mod.search(...)`` → ``search``; anything else → None."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_test_file(rel: str) -> bool:
    """A test file: tests/ tree, or a basename matching ``test_*.py`` /
    ``*_test.py``. Tests legitimately pass a privileged literal to exercise the
    gate's owner-path behaviour directly."""
    parts = Path(rel).parts
    if parts and parts[0] == "tests":
        return True
    stem = Path(rel).name
    return stem.startswith("test_") or stem.endswith("_test.py")


def _is_lint_scanner(rel: str) -> bool:
    """A lint scanner under tools/lint/ — these name the literal tags in their
    own logic + docstrings; they never call the gate."""
    parts = Path(rel).parts
    return len(parts) >= 2 and parts[0] == "tools" and parts[1] == "lint"


def _scan_file(rel: str, py: Path) -> list[str]:
    out: list[str] = []
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _callee_name(node) not in _GUARDED_CALLEES:
            continue
        offender = _privileged_policy_tag_literal(node)
        if offender is not None:
            callee = _callee_name(node)
            out.append(
                f"{rel}:{offender.lineno}: privileged policy_tag literal passed "
                f"to {callee}(...) — a §9.0 retrieval BYPASS handed in without an "
                f"auth check. Resolve the tag server-side via an auth-checked "
                f"helper (interfaces/research/api/books.py::_owner_read_policy_tag), "
                f"never as a bare 'operator_only'/'private_research' literal."
            )
    return out


def find_violations(root: Path | None = None) -> list[str]:
    """Return ``path:line: message`` for every privileged-tag literal passed to
    a guarded retrieval callee outside the allowlist + test files + lint
    scanners.

    ``root`` defaults to the module-level ``_REPO`` resolved at CALL time (not
    bind time) so a test can patch the module global and have ``main()`` see the
    change — the same pattern ``owner_boundary_check.find_violations`` uses."""
    root = _REPO if root is None else root
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
        print("Owner-privilege boundary violations:")
        for line in violations:
            print(f"  {line}")
        print(
            "\nA PRIVILEGED policy_tag (operator_only / private_research) is the "
            "§9.0 retrieval bypass — it admits the owner's gated/personal corpus "
            "through the deny-by-default gate. It may be passed to search(...) / "
            "answer_book_question(...) ONLY after an auth check has proven the "
            "caller is the owner; resolve it server-side via "
            "interfaces/research/api/books.py::_owner_read_policy_tag, never as a "
            "bare literal. Handing the bypass in unchecked leaks the owner's "
            "gated/personal content (the §9.0 Hachette/Bartz leak; CLAUDE.md "
            "invariant #4). Allowlist: "
            + ", ".join(sorted(_ALLOWED_FILES))
            + "; test files; lint scanners."
        )
        return 1
    print(
        "OK: no privileged policy_tag literal passed to a retrieval callee "
        "outside the auth-checked allowlist."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
