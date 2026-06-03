"""Guard for the substrate-concern UNIQUENESS REGISTRY — Antiek Convergence SPR-07.

The registry (``tools/lint/uniqueness_registry.py``) is the anti-fork meta-check:
each registered concern (retrieval_gate / reading_shell / dispatch_router) must
have EXACTLY ONE implementation. This test proves the gate FIRES — the only proof
that a gate works (SPR-07 rigor #3):

  * RED on a planted duplicate: each concern's ``check`` returns ``ok=False`` with
    the planted path in the offenders, AND ``run_all`` exits non-zero with a
    ``[FORK]`` line.
  * GREEN on the negative case (no planted duplicate): every concern is
    ``ok=True`` and ``run_all`` exits 0 — so the gate is NOT trivially-always-red.
  * DATA-DRIVEN: adding a ``Concern`` row adds enforcement with NO change to the
    run engine (``run_all`` is concern-agnostic).
  * GATE FAILURE MODES are handled (canonical move/rename not a false positive;
    import/mount vs re-definition distinguished; zero-impl reds, not passes).
  * CLEANLINESS: every planted duplicate is created in a tmp tree (the registry
    checks are root-parameterised) so the REAL tree is never mutated — asserted
    with a ``git status --porcelain`` check at the end.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.lint.uniqueness_registry import (
    REGISTRY,
    Concern,
    main,
    run_all,
)

_REPO = Path(__file__).resolve().parent.parent


# ──────────────────────────────────────────────────────────────────────────────
# Fixture builders — a MINIMAL tmp tree carrying exactly one canonical impl of
# each concern, so the registry's checks (which are root-parameterised) see a
# clean tree we can then plant a duplicate into.
# ──────────────────────────────────────────────────────────────────────────────


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _canonical_retrieval_gate(repo: Path) -> Path:
    """One def of each watched §9.0 gate symbol — the #65-consolidated home."""
    p = repo / "substrate" / "graph" / "retrieval_gate.py"
    _write(
        p,
        "def non_privileged_chunk_sql_clause(*, table_alias='d'):\n"
        "    return '', []\n\n\n"
        "def is_chunk_body_withheld(content_class, *, taken_down=False):\n"
        "    return False, None\n",
    )
    return p


def _canonical_dispatch_router(repo: Path) -> Path:
    """One module-level ``def dispatch`` — the §16 single router."""
    p = repo / "substrate" / "dispatch" / "router.py"
    _write(p, "def dispatch(prompt, role, *, investigation_id):\n    return None\n")
    return p


def _canonical_reading_shell(repo: Path) -> Path:
    """One ``export function WernerIceCursorShell`` — the #54 canonical shell.
    Plus an IMPORT, a RE-EXPORT, and a JSX MOUNT in OTHER files, to prove the
    check distinguishes a DEFINITION from usages (none of these is a 2nd def)."""
    p = repo / "apps" / "reading" / "src" / "werner" / "WernerIceCursorShell.tsx"
    _write(
        p,
        "export function WernerIceCursorShell() {\n"
        "  return null;\n"
        "}\n\n"
        "export default WernerIceCursorShell;\n",
    )
    # A re-export (index barrel) — references the symbol, does NOT define it.
    _write(
        repo / "apps" / "reading" / "src" / "werner" / "index.ts",
        'export { WernerIceCursorShell } from "./WernerIceCursorShell";\n',
    )
    # A mount + import (AppShell) — references the symbol, does NOT define it.
    _write(
        repo / "apps" / "reading" / "src" / "AppShell.tsx",
        'import { WernerIceCursorShell } from "./werner/WernerIceCursorShell";\n'
        "export function AppShell() {\n"
        "  return <WernerIceCursorShell />;\n"
        "}\n",
    )
    return p


def _clean_tree(repo: Path) -> None:
    """A tmp tree with exactly one canonical impl of every registered concern."""
    _canonical_retrieval_gate(repo)
    _canonical_dispatch_router(repo)
    _canonical_reading_shell(repo)


# The (concern_name, plant-a-duplicate) plan, data-driven so each registered
# concern is proven to fire. Each planter writes a SECOND definition of that
# concern's canonical symbol into the tmp tree and returns the rel path it
# planted (so the test asserts the offender names it).
def _plant_retrieval_gate_dup(repo: Path) -> str:
    rel = "substrate/graph/rogue_gate.py"
    _write(
        repo / rel,
        "def is_chunk_body_withheld(content_class, *, taken_down=False):\n"
        "    return True, 'rogue'  # a divergent 2nd home\n",
    )
    return rel


def _plant_dispatch_router_dup(repo: Path) -> str:
    rel = "substrate/dispatch/rogue_router.py"
    _write(
        repo / rel,
        "def dispatch(prompt, role, *, investigation_id):\n"
        "    return 'rogue'  # a parallel router — §16 violation\n",
    )
    return rel


def _plant_reading_shell_dup(repo: Path) -> str:
    rel = "apps/reading/src/shell/RogueShell.tsx"
    _write(
        repo / rel,
        "export function WernerIceCursorShell() {\n"
        "  return null;  // a 2nd definition of the #54 shell — a fork\n"
        "}\n",
    )
    return rel


_PLANTERS = {
    "retrieval_gate": _plant_retrieval_gate_dup,
    "dispatch_router": _plant_dispatch_router_dup,
    "reading_shell": _plant_reading_shell_dup,
}


def _concern(name: str) -> Concern:
    return next(c for c in REGISTRY if c.name == name)


# ──────────────────────────────────────────────────────────────────────────────
# NEGATIVE control — the gate is NOT trivially-always-red.
# ──────────────────────────────────────────────────────────────────────────────


def test_negative_clean_tree_every_concern_unique(tmp_path: Path) -> None:
    """With exactly one impl of each concern, every check is ok=True and
    run_all exits 0. (If the gate were always-red this would fail — that is
    the point of the negative control.)"""
    _clean_tree(tmp_path)
    for concern in REGISTRY:
        ok, offenders = concern.run(tmp_path)
        assert ok, f"{concern.name} should be UNIQUE on a clean tree: {offenders}"
        assert offenders == []
    code, lines = run_all(tmp_path)
    assert code == 0, lines
    assert lines == [
        "[UNIQUE] retrieval_gate",
        "[UNIQUE] reading_shell",
        "[UNIQUE] dispatch_router",
    ]


def test_negative_real_tree_passes() -> None:
    """The REAL tree (forks already converged by SPR-03/04/05) is GREEN: run_all
    exits 0 on the actual repo. If a future change forks a concern, THIS reds —
    which is the gate working."""
    code, lines = run_all(_REPO)
    assert code == 0, "\n".join(lines)
    assert main([]) == 0


# ──────────────────────────────────────────────────────────────────────────────
# RED on a planted duplicate — data-driven across EVERY registered concern.
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", list(_PLANTERS))
def test_planted_duplicate_fires_the_gate(name: str, tmp_path: Path) -> None:
    """Plant a SECOND impl of a registered concern -> that concern's check
    returns ok=False with the planted path in the offenders, AND run_all exits
    non-zero with a [FORK] line naming the concern + the offender."""
    _clean_tree(tmp_path)
    planted_rel = _PLANTERS[name](tmp_path)

    # The concern's own check fires, and the planted path is named.
    ok, offenders = _concern(name).run(tmp_path)
    assert not ok, f"{name} check must red on a planted duplicate"
    joined = "\n".join(offenders)
    assert planted_rel in joined, (
        f"the planted duplicate {planted_rel} must appear in the offenders:\n{joined}"
    )

    # run_all exits non-zero and emits a [FORK] line for this concern naming the
    # offender (and the OTHER concerns stay UNIQUE — only the planted one forks).
    code, lines = run_all(tmp_path)
    assert code == 1, lines
    report = "\n".join(lines)
    assert f"[FORK] {name}:" in report, report
    assert planted_rel in report, report
    for other in (set(_PLANTERS) - {name}):
        assert f"[UNIQUE] {other}" in report, (
            f"only {name} was forked; {other} must stay UNIQUE:\n{report}"
        )


def test_zero_impl_canonical_deleted_reds_not_passes(tmp_path: Path) -> None:
    """A vanished canonical (zero impls) is a FORK-class failure, NOT a silent
    pass — ≠ 1 fails in EITHER direction. Build a tree missing the dispatch
    router entirely and assert the check reds."""
    _canonical_retrieval_gate(tmp_path)
    _canonical_reading_shell(tmp_path)
    # dispatch router deliberately ABSENT.
    ok, offenders = _concern("dispatch_router").run(tmp_path)
    assert not ok, "a deleted canonical (zero impls) must red, not pass"
    assert any("ZERO" in o for o in offenders), offenders
    code, lines = run_all(tmp_path)
    assert code == 1
    assert any("[FORK] dispatch_router:" in ln for ln in lines)


# ──────────────────────────────────────────────────────────────────────────────
# Gate failure modes (SPR-07 rigor #3).
# ──────────────────────────────────────────────────────────────────────────────


def test_canonical_move_is_not_a_false_positive(tmp_path: Path) -> None:
    """The check counts DEFINITION sites by SYMBOL, not by path — so moving the
    canonical to a different file is still exactly ONE def and stays GREEN. (A
    path-pinned check would false-positive here; the symbol-count does not.)"""
    _canonical_retrieval_gate(tmp_path)
    _canonical_reading_shell(tmp_path)
    # dispatch router MOVED to a non-canonical filename — still one def.
    _write(
        tmp_path / "substrate" / "dispatch" / "relocated_router.py",
        "def dispatch(prompt, role, *, investigation_id):\n    return None\n",
    )
    ok, offenders = _concern("dispatch_router").run(tmp_path)
    assert ok, f"a MOVED canonical (still one def) must not false-positive: {offenders}"


def test_imports_and_mounts_are_not_counted_as_definitions(tmp_path: Path) -> None:
    """An IMPORT / RE-EXPORT / JSX-MOUNT of the reading-shell symbol must NOT
    count as a second definition — only a real ``function/const/class
    WernerIceCursorShell`` does. The clean fixture already plants an import, a
    re-export, and a mount in OTHER files; the check must still see exactly one
    DEFINITION."""
    _clean_tree(tmp_path)
    ok, offenders = _concern("reading_shell").run(tmp_path)
    assert ok, (
        "imports / re-exports / JSX mounts of the shell symbol must not be "
        f"miscounted as definitions: {offenders}"
    )


def test_dispatch_method_on_a_class_is_not_a_second_router(tmp_path: Path) -> None:
    """A ``def dispatch`` that is a METHOD on a provider class is a normal
    interface method, not a second module-level router — it must NOT red. The
    check counts MODULE-LEVEL defs only."""
    _canonical_retrieval_gate(tmp_path)
    _canonical_reading_shell(tmp_path)
    _canonical_dispatch_router(tmp_path)
    _write(
        tmp_path / "substrate" / "dispatch" / "some_provider.py",
        "class Provider:\n"
        "    def dispatch(self, prompt):  # a method, not a module-level router\n"
        "        return None\n",
    )
    ok, offenders = _concern("dispatch_router").run(tmp_path)
    assert ok, f"a class method named dispatch must not red: {offenders}"


def test_ts_test_files_are_excluded_from_reading_shell_count(tmp_path: Path) -> None:
    """A .test.tsx file that redeclares the shell symbol (a test stub) must NOT
    count as a second definition — exercising the shell is not re-forking it."""
    _clean_tree(tmp_path)
    _write(
        tmp_path / "apps" / "reading" / "src" / "werner" / "Shell.test.tsx",
        "function WernerIceCursorShell() { return null; }  // a test stub\n",
    )
    ok, offenders = _concern("reading_shell").run(tmp_path)
    assert ok, f"a test-file stub must be excluded from the count: {offenders}"


# ──────────────────────────────────────────────────────────────────────────────
# Data-driven: adding a row adds enforcement with NO change to the engine.
# ──────────────────────────────────────────────────────────────────────────────


def test_adding_a_row_adds_enforcement_without_touching_run_all(tmp_path: Path) -> None:
    """run_all is concern-agnostic: append a brand-new Concern with its own
    check and run_all enforces it — no edit to run_all required. Prove it by
    running run_all over an AUGMENTED registry whose extra concern is forked,
    and asserting the new concern reds while the engine code is untouched."""
    from tools.lint import uniqueness_registry as reg

    # A throwaway concern that reds iff a sentinel file has != 1 'def sentinel'.
    import ast

    def _sentinel_check(repo: Path):
        sites = []
        d = repo / "substrate" / "ext"
        if d.is_dir():
            for py in sorted(d.rglob("*.py")):
                tree = ast.parse(py.read_text(encoding="utf-8"))
                for node in tree.body:
                    if isinstance(node, ast.FunctionDef) and node.name == "sentinel":
                        sites.append(f"{py.relative_to(repo).as_posix()}:{node.lineno}")
        if len(sites) == 1:
            return True, []
        return False, [f"{s}: sentinel forked" for s in sites] or [
            "substrate/ext/sentinel.py:0: sentinel has ZERO definitions"
        ]

    extra = reg.Concern(
        name="sentinel_concern",
        canonical="substrate/ext/sentinel.py",
        check=_sentinel_check,
        converged_by="(test)",
        ruled_by="(test)",
    )

    # Build a clean tree + TWO sentinel defs (a fork of the new concern).
    _clean_tree(tmp_path)
    _write(tmp_path / "substrate" / "ext" / "a.py", "def sentinel():\n    pass\n")
    _write(tmp_path / "substrate" / "ext" / "b.py", "def sentinel():\n    pass\n")

    # Monkeypatch the registry tuple to include the extra row — run_all is NOT
    # modified, only the data it iterates.
    original = reg.REGISTRY
    try:
        reg.REGISTRY = original + (extra,)
        code, lines = reg.run_all(tmp_path)
    finally:
        reg.REGISTRY = original

    assert code == 1, lines
    report = "\n".join(lines)
    assert "[FORK] sentinel_concern:" in report, report
    # The three real concerns stay UNIQUE (the clean fixture).
    for name in ("retrieval_gate", "reading_shell", "dispatch_router"):
        assert f"[UNIQUE] {name}" in report, report


# ──────────────────────────────────────────────────────────────────────────────
# Cleanliness — no planted duplicate leaks into the real tree.
# ──────────────────────────────────────────────────────────────────────────────


def test_runner_leaves_the_tree_clean() -> None:
    """Every planted duplicate is created in a tmp_path tree (the checks are
    root-parameterised), so the REAL repo is never mutated. Assert
    ``git status --porcelain`` over the source files this sprint added/touched
    is empty AFTER all the planting tests have had a chance to run. (Run as part
    of the same module so a leak from any sibling test would surface here.)"""
    # Scope the check to the files this sprint owns + the dirs the planters
    # write into, so an unrelated dirty working tree elsewhere does not fail it.
    watched = [
        "tools/lint/uniqueness_registry.py",
        "tools/reachability/sweep.py",
        "substrate/graph",
        "substrate/dispatch",
        "apps/reading/src/werner",
        "apps/reading/src/shell",
    ]
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", *watched],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    # Only UNTRACKED or MODIFIED files would indicate a leak from the temp
    # planters. (Committed-but-clean returns nothing.) Filter out the files this
    # sprint legitimately ADDED (they show as untracked until committed): the
    # leak we guard against is a rogue_gate.py / RogueShell.tsx etc. under the
    # watched source dirs, which the planters write ONLY under tmp_path.
    leaks = [
        ln
        for ln in result.stdout.splitlines()
        if "rogue" in ln.lower()
        or "relocated_router" in ln
        or "sentinel" in ln
        or ln.rstrip().endswith("/ext/a.py")
        or ln.rstrip().endswith("/ext/b.py")
    ]
    assert not leaks, (
        "a planted duplicate leaked into the real tree (the temp-fixture "
        "duplicate escaped tmp_path):\n" + "\n".join(leaks)
    )
