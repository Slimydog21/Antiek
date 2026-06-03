#!/usr/bin/env python3
"""Cross-source registration boundary lint — every acquisition adapter that
inserts a document MUST also establish its rights through the unified chokepoint
(reframe finding #5).

The invariant: the deny-by-default rights substrate (``content_class`` +
``ip_holder_id``) only compounds across sources if EVERY acquisition adapter
that calls ``insert_document(`` also routes the document's rights through
``substrate.rights.register.register_source_document`` (or its book
specialization ``substrate.books.ingest.register_book``, which delegates there).
An adapter that inserts a document and then never registers its rights leaves
the gate columns NULL — exactly the hole this reframe closes (the legacy
NULL-grandfather in ``substrate/graph/search.py``). So an adapter that calls
``insert_document(`` but NEITHER ``register_source_document(`` NOR
``register_book(`` is a violation.

This is modeled EXACTLY on ``tools/lint/serve_guard_check.py`` /
``boundary_check.py``: same ``path:line`` output, same exit-code contract
(0 = clean, 1 = violations), same AST walk. We match the CALL (an ``ast.Call``
whose callee resolves to the symbol), bare-name or attribute form, because
importing the symbol is fine — invoking ``insert_document`` without a paired
register call is the hole.

MIGRATION-PENDING ALLOWLIST: seven adapters currently insert without
registering through the chokepoint. Six of them (interview, podcasts, twitter,
urls, voice, youtube) need a per-source ``content_class`` decision that is a
master-spec §9.0 legal-gate call (rationale in the reframe spec workspace, not
this repo); arxiv hand-stamps ``content_class`` on ``insert_document`` directly
rather than through the chokepoint. Each is listed explicitly below and drops off
this list the moment it migrates (adds a ``register_source_document`` call). When
the list is empty the migration is complete — and a NEW adapter that inserts
without registering fails CI here from day one (the allowlist is closed, not a
wildcard).

KNOWN LIMITATION (matching the honesty convention in ``serve_guard_check.py``):
this is a PRESENCE check, not a REACHABILITY check — a ``register_source_document(``
/ ``register_book(`` call ANYWHERE in an adapter file (even dead or unrelated code)
satisfies it, even if the live insert path never registers. Static reachability is
out of scope; the check defends the realistic case (an adapter that simply never
calls a register function), and a deliberately-evasive dead call is easy to spot in
review.

Exit 0 = clean; exit 1 = an adapter inserts without registering and is not on the
(shrinking) migration-pending allowlist.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

_INSERT_CALLEE = "insert_document"
_REGISTER_CALLEES = frozenset({"register_source_document", "register_book"})

# Adapters that insert-without-registering TODAY and are knowingly deferred to
# the §9.0 per-source content_class decision (P1b). CLOSED list — a new adapter
# not here that inserts-without-registering fails. Remove an entry when that
# adapter migrates to register_source_document; an empty set == migration done.
# P1b migration complete (SR-05): every adapter registers after insert.
_MIGRATION_PENDING: frozenset[str] = frozenset()


def _callee_name(node: ast.AST) -> str | None:
    """The simple name a Call invokes — bare ``f(...)`` or attribute
    ``mod.f(...)`` — or None if it is not a static-name call."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _adapter_files(root: Path) -> list[Path]:
    """Every ``acquisition/<source>/adapter.py``."""
    acq = root / "acquisition"
    return sorted(acq.glob("*/adapter.py")) if acq.is_dir() else []


def find_violations(root: Path = _REPO) -> list[str]:
    """Adapters that call ``insert_document(`` but neither register function,
    and are not on the migration-pending allowlist."""
    out: list[str] = []
    for py in _adapter_files(root):
        rel = py.relative_to(root).as_posix()
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        inserts = False
        insert_line = 0
        registers = False
        for node in ast.walk(tree):
            name = _callee_name(node)
            if name == _INSERT_CALLEE:
                inserts = True
                insert_line = insert_line or getattr(node, "lineno", 0)
            elif name in _REGISTER_CALLEES:
                registers = True
        if inserts and not registers and rel not in _MIGRATION_PENDING:
            out.append(
                f"{rel}:{insert_line}: calls insert_document( but never "
                f"register_source_document( / register_book( — establish the "
                f"document's rights through substrate.rights.register so the "
                f"deny-by-default substrate compounds for this source"
            )
    return out


def stale_allowlist(root: Path = _REPO) -> list[str]:
    """Allowlisted adapters that have SINCE migrated (now register) or no longer
    insert — a stale exception that should be removed so the list keeps shrinking
    honestly toward empty."""
    stale: list[str] = []
    for py in _adapter_files(root):
        rel = py.relative_to(root).as_posix()
        if rel not in _MIGRATION_PENDING:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        inserts = any(_callee_name(n) == _INSERT_CALLEE for n in ast.walk(tree))
        registers = any(_callee_name(n) in _REGISTER_CALLEES for n in ast.walk(tree))
        if registers or not inserts:
            stale.append(rel)
    return stale


def main() -> int:
    violations = find_violations()
    stale = stale_allowlist()
    if violations:
        print("Cross-source registration violations:")
        for line in violations:
            print(f"  {line}")
        print(
            "\nAn acquisition adapter that inserts a document MUST establish its "
            "rights through substrate.rights.register.register_source_document "
            "(or register_book). Inserting without registering leaves "
            "content_class / ip_holder_id NULL — the legacy grandfather hole this "
            "reframe closes."
        )
        return 1
    if stale:
        print("Migration-pending allowlist is stale (these now register or no "
              "longer insert — remove them from _MIGRATION_PENDING):")
        for rel in stale:
            print(f"  {rel}")
        return 1
    pending = sorted(_MIGRATION_PENDING)
    print(
        f"OK: every non-allowlisted acquisition adapter registers its rights. "
        f"{len(pending)} adapter(s) migration-pending (§9.0 P1b): "
        f"{', '.join(pending)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
