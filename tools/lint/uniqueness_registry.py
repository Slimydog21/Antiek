#!/usr/bin/env python3
"""Substrate-concern UNIQUENESS registry — Antiek Convergence SPR-07.

The convergence discipline, GENERALIZED. The Antiek build loop (``/htmlspec``
authors parallel sprints -> ``/caffenagent`` executes each -> ``/PRcrouch``
ships) optimises throughput but has NO force for convergence: sprints run
parallel-and-independent by design, so two failure classes recur —

  * FORKS — two competing implementations of ONE substrate concern. The §9.0
    retrieval gate had two (#65 converged them; SPR-03 installed a never-re-fork
    guard). The Werner reading shell was alleged to have two (SPR-04 verified
    it was already one).
  * DEAD-IN-PROD FEATURES — a feature whose reachability depends on a wire no
    single sprint owns (the flywheel; SPR-01 caught it, SPR-02 wired it). That
    half is the SPR-01 reachability PROBE runner; this module is the other half.

SPR-03 installed the uniqueness half for ONE concern (the retrieval gate) as a
standalone lint. This module LIFTS that per-concern discipline into a single
declarative REGISTRY so that:

  * there is ONE place to ask "what substrate concerns must be unique, and are
    they?" (``python -m tools.lint.uniqueness_registry``);
  * adding a concern is ONE ``Concern`` row + a ``check`` callable — no change
    to the run engine (``run_all``) — so the discipline scales as new
    single-owner concerns are ratified across concurrent specs;
  * every registered concern reports in ONE shape (``[UNIQUE]`` / ``[FORK]``),
    so independent checks cannot drift in message/exit-code form the way three
    hand-rolled standalone lints would.

WHY A REGISTRY AND NOT THREE STANDALONE LINTS (fairness, SPR-07 rigor #2).
The honest steelman for NOT doing this: SPR-03's standalone
``retrieval_gate_uniqueness.py`` already works; keeping each concern's check
next to its concern is simpler, adds zero abstraction, and a single-operator
codebase rarely forks the same concern twice. The registry STILL wins because:
(a) forks RECUR across the concurrent-spec loop — a registry is the one place a
future convergence-owner reads to know the full set; (b) three independent
standalone lints drift apart in exit-code/message shape and there is no single
command that answers "is anything forked?"; (c) the cost of a missed fork is a
§9.0 polarity split or a dead feature shipping to prod — high enough that the
one-row-per-concern ceremony is cheap insurance. See
``docs/decisions/convergence-owner.md`` for the role this registry serves.

WHAT THIS DOES NOT DO. It does NOT convert forks (SPR-03 converged the gate,
SPR-04 verified the shell; this sprint REGISTERS the discipline, it does not
re-converge). It only registers concerns that ALREADY have a ruled canonical:
``retrieval_gate`` (#65 / docs/decisions, SPR-03), ``reading_shell`` (#54 /
acv-spr04-read-shell-convergence.md), ``dispatch_router``
(substrate/dispatch/router.py / acv-spr05-dispatch-fidelity.md). A concern with
no ruled canonical is NOT pre-registered (SPR-07 out-of-scope rule).

THE retrieval_gate ROW REUSES SPR-03's DETECTION (diligence, SPR-07 rigor #4).
It does NOT re-implement the symbol count — it IMPORTS
``find_definitions`` from ``tools/lint/retrieval_gate_uniqueness.py`` (the
battle-tested SPR-03 AST symbol-counter, file:line cited in that row). The
standalone ``retrieval_gate_uniqueness.py`` was RETARGETED, not deleted: its
detection functions remain the reusable library this registry imports, and its
CLI now DELEGATES to this registry's row, so uniqueness is ASSERTED in exactly
ONE place (the registry) — no two places independently assert it. What would
REVERSE that choice: if a future concern needed the gate's detection wired into
a context the registry cannot reach, lifting the function verbatim into this
module and deleting the standalone would be the alternative; we chose
delegation to preserve SPR-03's existing self-test
(``tests/test_retrieval_gate_uniqueness_lint.py``) unbroken.

OUTPUT / EXIT CONTRACT (matches the tools/lint/ idiom —
``tools/lint/owner_boundary_check.py`` / ``boundary_check.py``):

  * one ``[UNIQUE] <concern>`` line per concern with exactly one impl;
  * on a fork, ``[FORK] <concern>: <offender path:line>`` per offending site
    PLUS the offender detail in the existing bare ``path:line: message`` form;
  * exit 0 iff EVERY concern has exactly one impl; exit 1 otherwise.

GATE FAILURE MODES this registry handles (SPR-07 rigor #3):
  * canonical module moved/renamed — each ``check`` counts DEFINITION sites by
    symbol, not by path, so the canonical itself is never a false positive and
    a moved canonical still counts as the one definition wherever it lands;
  * IMPORT/usage vs RE-DEFINITION — each ``check`` matches DEFINITION syntax
    (Python ``def`` / TS ``function|const|class <Name>``), never an import,
    re-export, JSX mount, or call site;
  * ZERO implementations (canonical deleted) — reported as a FORK-class
    violation (``ok=False``), never a silent pass: a vanished canonical is as
    broken as a duplicated one (≠ 1 fails in EITHER direction).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

# A check returns (ok, offenders). ``offenders`` are bare ``path:line: message``
# strings (the tools/lint idiom) naming each site that breaks uniqueness — the
# duplicate definition sites on a fork, or the canonical-home pointer on a
# zero-definition (deleted-canonical) violation.
CheckResult = tuple[bool, list[str]]
Check = Callable[[Path], CheckResult]


# ──────────────────────────────────────────────────────────────────────────────
# retrieval_gate — REUSE SPR-03's detection (do not re-implement).
#   canonical: substrate/graph/retrieval_gate.py
#   converged by: #65 (b27b9df); guarded by SPR-03
#                 (tools/lint/retrieval_gate_uniqueness.py).
#   ruled canonical: #65 consolidation note in that module's docstring
#                    (lines 4-10) + tools/lint/retrieval_gate_check.py.
# We import SPR-03's AST symbol-counter rather than re-deriving it, so the
# DEFINITION/usage distinction, the test-file exclusion, and the zero/two count
# logic are SHARED with SPR-03 — there is exactly one symbol-counting engine.
# ──────────────────────────────────────────────────────────────────────────────
from tools.lint.retrieval_gate_uniqueness import (  # noqa: E402
    find_violations as _retrieval_gate_violations,
)


def _check_retrieval_gate(repo: Path) -> CheckResult:
    """Delegate to SPR-03's ``find_violations`` (the canonical symbol counter).
    Its output is already the bare ``path:line: message`` idiom and already
    fails on BOTH a second definition (a re-fork) AND zero definitions (the
    canonical home vanished). ``ok`` iff it returns no violations."""
    offenders = _retrieval_gate_violations(root=repo)
    return (not offenders, offenders)


# ──────────────────────────────────────────────────────────────────────────────
# dispatch_router — single ``def dispatch`` in substrate/dispatch/router.py.
#   canonical: substrate/dispatch/router.py (the one router; §16 single
#              dispatcher — there is no second dispatcher by design).
#   converged by: born single; fidelity ruled in
#                 docs/decisions/acv-spr05-dispatch-fidelity.md (SPR-05).
# A SECOND module-level ``def dispatch`` anywhere under substrate/dispatch/
# would be a parallel router — the §16 violation this row guards. AST count of
# the ``def`` named ``dispatch`` (not a call ``dispatch(...)`` or an import).
# ──────────────────────────────────────────────────────────────────────────────
_DISPATCH_CANONICAL = "substrate/dispatch/router.py"
_DISPATCH_SYMBOL = "dispatch"


def _check_dispatch_router(repo: Path) -> CheckResult:
    import ast

    root_dir = repo / "substrate" / "dispatch"
    sites: list[str] = []
    if root_dir.is_dir():
        for py in sorted(root_dir.rglob("*.py")):
            rel = py.relative_to(repo).as_posix()
            name = py.name
            if name.startswith("test_") or name.endswith("_test.py"):
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            # MODULE-LEVEL def only: a method ``def dispatch`` on a provider
            # class is a normal interface method, not a second router entry
            # point. The canonical is a module-level function.
            for node in tree.body:
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == _DISPATCH_SYMBOL
                ):
                    sites.append(f"{rel}:{node.lineno}")
    sites.sort()
    if len(sites) == 1:
        return (True, [])
    if not sites:
        return (
            False,
            [
                f"{_DISPATCH_CANONICAL}:0: dispatch_router symbol "
                f"'{_DISPATCH_SYMBOL}' has ZERO module-level definitions under "
                f"substrate/dispatch/ — the canonical router disappeared "
                f"(expected exactly one in {_DISPATCH_CANONICAL})"
            ],
        )
    others = lambda s: ", ".join(x for x in sites if x != s)  # noqa: E731
    return (
        False,
        [
            f"{s}: a SECOND module-level 'def {_DISPATCH_SYMBOL}' — the dispatch "
            f"router has FORKED (§16 forbids a second dispatcher; the one router "
            f"is {_DISPATCH_CANONICAL}). Other definition(s): {others(s)}"
            for s in sites
        ],
    )


# ──────────────────────────────────────────────────────────────────────────────
# reading_shell — single definition of the #54 canonical Werner ice-fishing
#   shell component.
#   canonical: apps/reading/src/werner/WernerIceCursorShell.tsx
#              (the #54 ice-fishing shell, mounted once in AppShell.tsx).
#   converged by: SPR-04 (verified already-converged — there was no #52 fork on
#                 this branch); ruled canonical in
#                 docs/decisions/acv-spr04-read-shell-convergence.md.
# The reading shell is FRONTEND-ONLY (TSX) — a Python AST cannot see it. This is
# a NEW text/regex scan (authored this sprint) over apps/reading/src/*.ts(x)
# asserting EXACTLY ONE DEFINITION of the canonical shell component
# ``WernerIceCursorShell``. A definition is ``function WernerIceCursorShell`` /
# ``const WernerIceCursorShell =`` / ``class WernerIceCursorShell`` — NOT an
# import, a re-export (``export { WernerIceCursorShell } from …``), a JSX mount
# (``<WernerIceCursorShell />``), or a call. A fork would re-DEFINE the shell
# component under this canonical name in a second module; that is what this
# catches. Test files are excluded (a test may stub/redeclare the symbol).
# ──────────────────────────────────────────────────────────────────────────────
_READING_SHELL_CANONICAL = (
    "apps/reading/src/werner/WernerIceCursorShell.tsx"
)
_READING_SHELL_SYMBOL = "WernerIceCursorShell"
_READING_SHELL_ROOT = "apps/reading/src"

# A DEFINITION of the component (function / arrow-or-value const / class), with
# an optional leading ``export``/``export default``. Anchored to the symbol so
# ``WernerIceCursorShellFoo`` (a different name) never matches (``\b``). This
# matches the DECLARATION SITE, never an import / re-export / mount / call.
_READING_SHELL_DEF_RE = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?"
    r"(?:async\s+)?function\s+" + re.escape(_READING_SHELL_SYMBOL) + r"\b"
    r"|^\s*(?:export\s+(?:default\s+)?)?"
    r"(?:const|let|var)\s+" + re.escape(_READING_SHELL_SYMBOL) + r"\b\s*[:=]"
    r"|^\s*(?:export\s+(?:default\s+)?)?"
    r"class\s+" + re.escape(_READING_SHELL_SYMBOL) + r"\b",
    re.MULTILINE,
)


def _is_ts_test_file(name: str) -> bool:
    return (
        name.endswith(".test.ts")
        or name.endswith(".test.tsx")
        or name.endswith(".spec.ts")
        or name.endswith(".spec.tsx")
    )


def _check_reading_shell(repo: Path) -> CheckResult:
    root_dir = repo / _READING_SHELL_ROOT
    sites: list[str] = []
    if root_dir.is_dir():
        for ext in ("*.ts", "*.tsx"):
            for ts in sorted(root_dir.rglob(ext)):
                if _is_ts_test_file(ts.name):
                    continue
                rel = ts.relative_to(repo).as_posix()
                try:
                    text = ts.read_text(encoding="utf-8")
                except OSError:
                    continue
                for m in _READING_SHELL_DEF_RE.finditer(text):
                    line = text.count("\n", 0, m.start()) + 1
                    sites.append(f"{rel}:{line}")
    sites.sort()
    if len(sites) == 1:
        return (True, [])
    if not sites:
        return (
            False,
            [
                f"{_READING_SHELL_CANONICAL}:0: reading_shell component "
                f"'{_READING_SHELL_SYMBOL}' has ZERO definitions under "
                f"{_READING_SHELL_ROOT}/ — the #54 canonical ice-fishing shell "
                f"disappeared (expected exactly one in "
                f"{_READING_SHELL_CANONICAL}; SPR-04 ruled it canonical)"
            ],
        )
    others = lambda s: ", ".join(x for x in sites if x != s)  # noqa: E731
    return (
        False,
        [
            f"{s}: a SECOND definition of reading-shell component "
            f"'{_READING_SHELL_SYMBOL}' — the #54 Werner reading shell has "
            f"FORKED (it must have exactly ONE definition; SPR-04 ruled "
            f"{_READING_SHELL_CANONICAL} canonical). Other definition(s): "
            f"{others(s)}"
            for s in sites
        ],
    )


# ──────────────────────────────────────────────────────────────────────────────
# The registry.
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Concern:
    """One substrate concern that must have exactly ONE implementation.

    name:      stable id (the ``[UNIQUE]``/``[FORK]`` key + the registry handle).
    canonical: repo-relative path of the ONE source-of-truth module/symbol.
    check:     a callable ``(repo: Path) -> (ok, offenders)``. ``ok`` is True iff
               the concern has exactly one impl; ``offenders`` are bare
               ``path:line: message`` strings naming each site that breaks
               uniqueness (duplicate definitions, or a deleted-canonical
               pointer). The check is the per-concern detection mechanism —
               retrieval_gate REUSES SPR-03's; dispatch_router + reading_shell
               are language-appropriate (Python AST / TS regex).
    converged_by: the sprint that converged (or verified-converged) the concern.
    ruled_by:  the decision record / commit that ruled the canonical (so a
               future convergence-owner does not re-derive WHY this is canonical).
    """

    name: str
    canonical: str
    check: Check
    converged_by: str
    ruled_by: str

    def run(self, repo: Path = _REPO) -> CheckResult:
        return self.check(repo)


REGISTRY: tuple[Concern, ...] = (
    Concern(
        name="retrieval_gate",
        canonical="substrate/graph/retrieval_gate.py",
        check=_check_retrieval_gate,
        # Converged by #65 (b27b9df) collapsing #53's two parallel gates; the
        # never-re-fork guard installed by SPR-03.
        converged_by="#65 (b27b9df) / SPR-03",
        ruled_by="tools/lint/retrieval_gate_uniqueness.py (SPR-03) + "
        "tools/lint/retrieval_gate_check.py",
    ),
    Concern(
        name="reading_shell",
        canonical="apps/reading/src/werner/WernerIceCursorShell.tsx",
        check=_check_reading_shell,
        # SPR-04 verified the shell was ALREADY one (#54 canonical; the alleged
        # #52 fork never touched apps/reading/src on this branch).
        converged_by="SPR-04 (verified already-converged)",
        ruled_by="docs/decisions/acv-spr04-read-shell-convergence.md",
    ),
    Concern(
        name="dispatch_router",
        canonical="substrate/dispatch/router.py",
        check=_check_dispatch_router,
        # Born single (one router by §16 design); fidelity ruled by SPR-05.
        converged_by="born single (§16) / SPR-05 fidelity",
        ruled_by="docs/decisions/acv-spr05-dispatch-fidelity.md",
    ),
)


def run_all(repo: Path = _REPO) -> tuple[int, list[str]]:
    """Run every concern's check. Return ``(exit_code, report_lines)``.

    ``exit_code`` is 0 iff EVERY concern has exactly one impl, else 1. The
    engine is concern-agnostic: adding a ``Concern`` row adds enforcement with
    NO change here (proved in tests/test_uniqueness_registry.py). Every concern
    reports — no short-circuit — so a run names ALL forks, not just the first.
    """
    exit_code = 0
    lines: list[str] = []
    for concern in REGISTRY:
        ok, offenders = concern.run(repo)
        if ok:
            lines.append(f"[UNIQUE] {concern.name}")
            continue
        exit_code = 1
        for off in offenders:
            lines.append(f"[FORK] {concern.name}: {off}")
    return exit_code, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.lint.uniqueness_registry",
        description=(
            "Assert each registered substrate concern (retrieval_gate, "
            "reading_shell, dispatch_router) has EXACTLY ONE implementation — "
            "the anti-fork meta-check. Exit 1 if any concern has forked "
            "(two impls) or vanished (zero)."
        ),
    )
    parser.add_argument(
        "--list-concerns",
        action="store_true",
        help="print the registered concerns + their canonicals and exit 0",
    )
    args = parser.parse_args(argv)

    if args.list_concerns:
        for c in REGISTRY:
            print(
                f"{c.name}: canonical={c.canonical} "
                f"converged_by={c.converged_by} ruled_by={c.ruled_by}"
            )
        return 0

    exit_code, lines = run_all()
    for line in lines:
        print(line)
    if exit_code != 0:
        print(
            "\nA registered substrate concern has FORKED (or its canonical "
            "vanished). Each concern must have EXACTLY ONE implementation; a "
            "second is the convergence failure the Antiek parallel-sprint loop "
            "recurs into. Converge it (pick the canonical, supersede the other, "
            "harvest non-overlapping parts) per the convergence-owner runbook: "
            "docs/decisions/convergence-owner.md.",
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
