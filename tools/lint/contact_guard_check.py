#!/usr/bin/env python3
"""Contact-guard boundary lint — forbid NEW outbound-email send sites outside
the allowlist (SPR-09 M3).

The invariant (no-email-to-unclaimed): the ONLY sanctioned author-directed
email path is ``substrate.payouts.contact_guard.guarded_send_to_author``, which
is deny-by-default (it blocks every send while no author is claimed — see that
module). The single outbound-email chokepoint is
``substrate.auth.email_provider.EmailProvider.send(OutboundEmail)``. So a NEW
``provider.send(`` call OR a NEW ``OutboundEmail(`` construction added anywhere
makes CI go red here, forcing any future author-email path through the guard.

Two construction/call forms are caught per file:

  1. an attribute call whose attr is ``send`` AND whose receiver looks like a
     resolved email provider — i.e. ``<x>.send(<something>)`` where the single
     positional arg is an ``OutboundEmail(...)`` literal, OR the call is named
     ``provider.send`` / ``*_provider.send`` / ``get_email_provider().send``.
     We deliberately match the SEND of an email payload, not every ``.send`` in
     the tree (DB cursors, sockets, etc. also have ``.send`` — matching all of
     them would be noise). The signal we gate on is "an ``OutboundEmail`` is
     leaving via a ``.send``".
  2. a direct construction of the payload — ``OutboundEmail(...)`` (bare-name or
     attribute callee, and any aliased import bound to the ``OutboundEmail``
     symbol). Constructing an ``OutboundEmail`` anywhere new is the upstream
     signal that a new email path is being added; gating it forces the author
     send through the guard.

Allowlist (relative to repo root):

  * ``interfaces/research/api/auth.py``   — the operator magic-link sign-in. NOT
                                            author-directed (mails the operator
                                            their own link, gated to
                                            ANTIEK_OPERATOR_EMAIL). FUNCTION-SCOPED
                                            (round-2): only the ONE known site is
                                            allowed — the ``OutboundEmail(...)``
                                            construction inside
                                            ``_format_magic_link_email`` and the
                                            ``provider.send(...)`` inside the
                                            ``auth_request`` route. A NEW
                                            construction/send added in ANY OTHER
                                            function of auth.py is FLAGGED (the
                                            whole-file pass would have missed it).
  * ``substrate/auth/email_provider.py``  — the protocol + impls (where ``send``
                                            is DEFINED and where the providers
                                            call their own transports) + the
                                            ``OutboundEmail`` dataclass home.
                                            Whole-file allowed (it IS the transport
                                            home).
  * ``substrate/payouts/contact_guard.py``— the guard itself (the one place
                                            allowed to call ``provider.send`` for
                                            an author, after the claim check).
                                            Whole-file allowed.

Test files are allowlisted — they exercise the provider + the guard directly.

This is modeled EXACTLY on ``tools/lint/serve_guard_check.py``: same
``path:line`` output, same exit-code contract (0 = clean, 1 = violations), same
AST walk over the tree, same aliased-import handling, same ``root=`` parameter
so the self-test can point it at a synthetic tree.

KNOWN, ACCEPTED LIMITATIONS (honest scope):
  * A fully dynamic invocation — ``getattr(provider, "send")(...)`` or an
    ``OutboundEmail`` built via reflection — is NOT detected. Such code is exotic
    and obvious in review.
  * A ``.send(`` whose receiver is NOT named ``*provider`` / a
    ``get_email_provider()`` chain AND whose argument is a PRE-BUILT payload
    variable (``msg = OutboundEmail(...); mailer.send(msg)``) is not caught at the
    ``.send`` site. It is, however, caught at the CONSTRUCTION site: the
    ``OutboundEmail(...)`` is flagged wherever it is built (rule 2), which is the
    upstream signal that a new email path is being added — so the new path still
    reds. Only a payload constructed in an ALLOWLISTED file and then ``.send``-ed
    from a non-provider-named receiver elsewhere would slip the ``.send`` check,
    and that construction is already in an allowlisted home by definition.
The static forms cover every realistic accidental new author-email site.

Exit 0 = clean; exit 1 = a violation, printed as ``path:line``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

# The payload type whose construction signals a new email path.
_PAYLOAD = "OutboundEmail"

# Paths (relative to the repo root) where an outbound-email send / OutboundEmail
# construction is legitimate WHOLE-FILE (the transport/guard homes).
_ALLOWED_FILES: frozenset[str] = frozenset(
    {
        "substrate/auth/email_provider.py",
        "substrate/payouts/contact_guard.py",
    }
)

# auth.py is NOT whole-file allowed — only the ONE known operator-magic-link site
# is. The construction lives in ``_format_magic_link_email`` and the send in the
# ``auth_request`` route. A construction/send in ANY OTHER enclosing function of
# auth.py is flagged. Map file -> {allowed enclosing-function names}.
_FUNCTION_SCOPED_ALLOW: dict[str, frozenset[str]] = {
    "interfaces/research/api/auth.py": frozenset(
        {"_format_magic_link_email", "auth_request"}
    ),
}


def _is_test_file(rel: str) -> bool:
    """A test file: tests/ tree, or a basename matching ``test_*.py`` /
    ``*_test.py``. Tests legitimately construct OutboundEmail + call the
    provider/guard directly."""
    parts = Path(rel).parts
    if parts and parts[0] == "tests":
        return True
    stem = Path(rel).name
    return stem.startswith("test_") or stem.endswith("_test.py")


def _aliases_bound_to_payload(tree: ast.AST) -> set[str]:
    """Local names bound (by import) to the ``OutboundEmail`` symbol — catches
    the aliased-import construction:

        from substrate.auth.email_provider import OutboundEmail as _OE
        _OE(to=..., subject=...)   # callee Name is '_OE', not 'OutboundEmail'
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == _PAYLOAD:
                    bound.add(alias.asname or alias.name)
    return bound


def _is_payload_construction(node: ast.AST, aliases: frozenset[str]) -> bool:
    """True iff ``node`` constructs an ``OutboundEmail`` — bare-name callee
    (``OutboundEmail(...)``), attribute callee (``mod.OutboundEmail(...)``), or an
    aliased-import callee whose ``Name`` is in ``aliases``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == _PAYLOAD or func.id in aliases
    if isinstance(func, ast.Attribute):
        return func.attr == _PAYLOAD
    return False


def _is_email_send(node: ast.AST) -> bool:
    """True iff ``node`` is a ``.send(...)`` that is sending an email payload.

    We match an attribute call whose attr is ``send`` when EITHER:
      * the single positional arg is an ``OutboundEmail(...)`` construction
        (the canonical ``provider.send(OutboundEmail(...))`` /
        ``provider.send(_format_email(...))`` is caught via the construction rule
        too, but inlined constructions are caught here); OR
      * the receiver name strongly indicates an email provider — a Name/attr
        ending in ``provider`` (e.g. ``provider.send``, ``email_provider.send``),
        or a ``get_email_provider().send`` chain.

    Matching only email-shaped ``.send`` keeps DB-cursor / socket ``.send`` out
    of the lint (which would otherwise be pure noise)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "send":
        return False
    # Receiver heuristics: a name ending in 'provider', or get_email_provider().
    recv = func.value
    if isinstance(recv, ast.Name) and recv.id.lower().endswith("provider"):
        return True
    if isinstance(recv, ast.Attribute) and recv.attr.lower().endswith("provider"):
        return True
    if (
        isinstance(recv, ast.Call)
        and isinstance(recv.func, ast.Name)
        and recv.func.id == "get_email_provider"
    ):
        return True
    if (
        isinstance(recv, ast.Call)
        and isinstance(recv.func, ast.Attribute)
        and recv.func.attr == "get_email_provider"
    ):
        return True
    # Otherwise, only flag when the payload is an inline OutboundEmail(...).
    for arg in node.args:
        if _is_payload_construction(arg, frozenset()):
            return True
    return False


def _enclosing_function_names(tree: ast.AST) -> dict[int, str]:
    """Map each AST node's ``id()`` to the name of its NEAREST enclosing
    ``def``/``async def`` (or ``""`` if at module level), so a violation can be
    function-scoped. Walks each function body and stamps every descendant with the
    nearest function name (an inner function overrides an outer one for its own
    body)."""
    stamp: dict[int, str] = {}

    def _walk(node: ast.AST, current: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                stamp[id(child)] = current  # the def itself sits in its parent fn
                _walk(child, child.name)
            else:
                stamp[id(child)] = current
                _walk(child, current)

    _walk(tree, "")
    return stamp


def find_violations(root: Path = _REPO) -> list[str]:
    """Return ``path:line: message`` strings for every NEW outbound-email send /
    ``OutboundEmail(`` construction outside the allowlist + test files."""
    out: list[str] = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root).as_posix()
        if rel in _ALLOWED_FILES or _is_test_file(rel):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        aliases = frozenset(_aliases_bound_to_payload(tree))
        # auth.py: only the named magic-link functions are allowed; everything
        # else in the file is in-scope for the lint (round-2 function scoping).
        allowed_fns = _FUNCTION_SCOPED_ALLOW.get(rel)
        fn_of = _enclosing_function_names(tree) if allowed_fns is not None else {}
        for node in ast.walk(tree):
            is_construction = _is_payload_construction(node, aliases)
            is_send = (not is_construction) and _is_email_send(node)
            if not (is_construction or is_send):
                continue
            # Function-scoped allow: skip a site whose enclosing function is one of
            # the file's allowed magic-link functions; flag everything else.
            if allowed_fns is not None and fn_of.get(id(node), "") in allowed_fns:
                continue
            if is_construction:
                out.append(
                    f"{rel}:{node.lineno}: construction of 'OutboundEmail(' "
                    "outside the allowlist — route author-directed mail through "
                    "guarded_send_to_author (substrate/payouts/contact_guard.py)"
                )
            else:
                out.append(
                    f"{rel}:{node.lineno}: outbound-email '.send(' outside the "
                    "allowlist — route author-directed mail through "
                    "guarded_send_to_author (substrate/payouts/contact_guard.py)"
                )
    return out


def main() -> int:
    violations = find_violations()
    if violations:
        print("Contact-guard boundary violations:")
        for line in violations:
            print(f"  {line}")
        print(
            "\nAuthor-directed email may be sent ONLY through "
            "guarded_send_to_author (substrate/payouts/contact_guard.py), which "
            "is deny-by-default (no author is claimed yet — SPR-07 unbuilt). "
            "Constructing an OutboundEmail or calling provider.send anywhere new "
            "risks emailing an unclaimed author. Allowlist: "
            "interfaces/research/api/auth.py (operator magic-link), "
            "substrate/auth/email_provider.py (the protocol/impls), "
            "substrate/payouts/contact_guard.py (the guard), and test files."
        )
        return 1
    print(
        "OK: no outbound-email send / OutboundEmail construction outside the "
        "guard + allowlist."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
