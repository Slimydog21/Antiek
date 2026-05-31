#!/usr/bin/env python3
"""One-owner-per-layer boundary lint — a shared concern has exactly ONE owning
module, and other layers IMPORT the owner rather than reimplementing it.

Provenance: this composes the *antiek-harness-hardening* sprint-04 (layered
boundary lint, "one-owner-per-layer, CI-enforced") onto the Antiek Foundation.
The harness sprint proposed an ``import-linter`` *layer-direction* contract; the
Foundation SPR-09 spec narrows the first real assertion to the **one-owner**
shape the capstone audits actually found broken: a shared concern (servability)
that had drifted into TWO predicates with OPPOSITE polarity (the §9.0 denylist
vs allowlist bug SPR-08 just collapsed onto a single owner). See
``docs/decisions/spr-09-boundary-lint-vs-import-linter.md`` for why this
narrower, mechanically-decidable shape was chosen over import-linter (which
checks layer *direction*, not single-ownership of a concern, and so would not
have caught the §9.0 polarity mismatch this lint exists to prevent).

The rule, mechanically
-----------------------
For each declared CONCERN:

* exactly ONE module (the ``owner``) may DEFINE the concern's predicate
  (a function whose name matches the concern's ``predicate`` pattern);
* every OTHER module that needs the concern must IMPORT it from the owner
  (or from a re-export the owner sanctions) — it may NOT define its own
  same-named predicate (a "second owner" / owner-bypass).

A second module defining ``def is_servable_full_text(...)`` or
``def is_chunk_servable(...)`` outside the owner is an owner-bypass: it is
exactly how the pre-SPR-08 chunk denylist diverged from the book allowlist.
This lint flags it as ``path:line``.

Why AST, not import-linter
--------------------------
import-linter enforces *direction* (a lower layer may not import a higher one).
That is a real and complementary rule, but it cannot express "this concern has
one owner": two sibling modules at the same layer can each define a servability
predicate without any upward import, and import-linter would pass them. The
capstone's §9.0 finding was precisely two same-layer definitions disagreeing —
so the Foundation needs the ownership check, and it is decidable by an AST walk
for a top-level ``def`` whose name matches the concern's predicate pattern.

Exit 0 = clean; exit 1 = a violation (a second owner / a missing owner),
printed as ``path:line`` — the same output + exit-code contract as
``tools/lint/boundary_check.py``.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Concern:
    """A shared concern that must have exactly one owning module.

    name:      human-readable id (for messages + the registry).
    owner:     the repo-relative path of the ONE module allowed to DEFINE the
               concern's predicate.
    predicate: a regex matched against top-level function names; a ``def`` whose
               name matches, defined OUTSIDE ``owner``, is a second owner.
    search_roots: directories scanned for second owners (repo-relative).
    why:       the cost if the concern drifts to two owners (rigor #5).
    """

    name: str
    owner: str
    predicate: str
    search_roots: tuple[str, ...]
    why: str

    @property
    def predicate_re(self) -> re.Pattern[str]:
        return re.compile(self.predicate)


# ──────────────────────────────────────────────────────────────────────────────
# The declared concerns. The FIRST real assertion targets the §9.0 servability
# owner SPR-08 established (Foundation SPR-09 M2). Add a concern here when a new
# single-owner discipline is established — one row, no code change.
# ──────────────────────────────────────────────────────────────────────────────
CONCERNS: tuple[Concern, ...] = (
    Concern(
        name="servability (§9.0)",
        owner="substrate/books/servability.py",
        # The three owned servability predicates. A SECOND definition of any of
        # these — the pre-SPR-08 chunk denylist was an independent
        # ``is_chunk_servable``-equivalent — is the owner-bypass we forbid.
        predicate=r"^(is_servable_full_text|is_chunk_servable|servability_of)$",
        # Scan EVERY substrate surface that consumes servability — the five
        # roots that today import substrate.books.servability:
        #   graph       — chunk (search) path
        #   attribution — money (ad-attribution) path
        #   books       — book (serve) path + the owner itself
        #   write       — write/trace.py resolves a gated book to servable_snippet
        #   speak       — speak/publish.py maps PLATFORM_AUTHORED to served full text
        # write/ and speak/ are both serve-/money-adjacent (a Speak biography that
        # publishes as servable full text, a Write trace that decides snippet-vs-
        # full-text), so leaving them out would shrink the invariant's reach below
        # what actually decides servability. They import the owner today (no
        # competing predicate), so adding them keeps the lint GREEN while widening
        # the guarded surface — the non-vacuity of the widening is proved in
        # tests/test_owner_boundary_lint.py::test_real_servability_consumers_are_scanned_and_clean.
        # Scoped to these roots (not all of substrate/) so the lint stays fast and
        # an unrelated test fixture cannot trip it.
        search_roots=(
            "substrate/graph",
            "substrate/attribution",
            "substrate/books",
            "substrate/write",
            "substrate/speak",
        ),
        why=(
            "§9.0 servability is the money/legal gate (Hachette/Bartz). A second "
            "servability predicate is how the pre-SPR-08 chunk path diverged to "
            "the OPPOSITE (serve-by-default) polarity from the book path over the "
            "same documents.content_class column — serving unknown-rights text "
            "and routing an ad-attribution money share on it. ONE owner, ONE "
            "polarity (substrate/books/servability.py) is the fix this guards."
        ),
    ),
)


def _top_level_defs(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Top-level ``def``/``async def`` only — a method on a class named
    ``servability_of`` is not a competing module-level owner, and an inner
    helper is a private detail, not a public predicate."""
    return [
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def find_violations(
    concerns: tuple[Concern, ...] | None = None,
    repo: Path | None = None,
) -> list[str]:
    """Return ``path:line: message`` strings for every one-owner violation:
    a second owner (a competing predicate definition outside the owner) or a
    missing owner (the declared owner file or its predicate is gone).

    ``concerns`` / ``repo`` default to the module-level ``CONCERNS`` / ``_REPO``
    resolved at CALL time (not bind time) so a caller — or a test — can patch
    the module globals and have ``main()`` see the change."""
    concerns = CONCERNS if concerns is None else concerns
    repo = _REPO if repo is None else repo
    out: list[str] = []
    for concern in concerns:
        owner_path = repo / concern.owner
        pat = concern.predicate_re

        # --- missing owner: the declared owner must exist AND actually define
        # at least one matching predicate. A concern that names an owner which
        # no longer defines the predicate is a silent gap (the guard would then
        # pass vacuously) — flag it loudly.
        owner_defines = False
        if owner_path.exists():
            try:
                owner_tree = ast.parse(owner_path.read_text(encoding="utf-8"))
                owner_defines = any(
                    pat.match(fn.name) for fn in _top_level_defs(owner_tree)
                )
            except (OSError, SyntaxError):
                owner_defines = False
        if not owner_path.exists():
            out.append(
                f"{concern.owner}:0: declared owner of concern "
                f"'{concern.name}' does not exist — the single owner is missing"
            )
            continue
        if not owner_defines:
            out.append(
                f"{concern.owner}:0: declared owner of concern '{concern.name}' "
                f"no longer defines a predicate matching /{concern.predicate}/ — "
                f"the owner is missing its own predicate (silent-gap risk)"
            )

        # --- second owner: any matching predicate DEFINED outside the owner.
        for root in concern.search_roots:
            root_dir = repo / root
            if not root_dir.exists():
                continue
            for py in sorted(root_dir.rglob("*.py")):
                if py.resolve() == owner_path.resolve():
                    continue  # the owner is allowed to define it
                try:
                    tree = ast.parse(py.read_text(encoding="utf-8"))
                except (OSError, SyntaxError):
                    continue
                rel = py.relative_to(repo)
                for fn in _top_level_defs(tree):
                    if pat.match(fn.name):
                        out.append(
                            f"{rel}:{fn.lineno}: defines '{fn.name}' — a SECOND "
                            f"owner of concern '{concern.name}'. Import it from "
                            f"{concern.owner} instead of reimplementing it "
                            f"(one-owner-per-layer)."
                        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list-concerns",
        action="store_true",
        help="print the declared concerns + their owners and exit 0",
    )
    args = parser.parse_args(argv)

    if args.list_concerns:
        for c in CONCERNS:
            print(f"{c.name}: owner={c.owner} predicate=/{c.predicate}/")
        return 0

    violations = find_violations()
    if violations:
        print("One-owner-per-layer boundary violations:")
        for line in violations:
            print(f"  {line}")
        print(
            "\nA shared concern must have exactly ONE owning module; other "
            "layers import the owner rather than reimplementing it. See "
            "tools/lint/owner_boundary_check.py CONCERNS + "
            "docs/decisions/spr-09-boundary-lint-vs-import-linter.md."
        )
        return 1
    print(
        "OK: every declared concern has exactly one owner "
        f"({len(CONCERNS)} concern(s) checked)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
