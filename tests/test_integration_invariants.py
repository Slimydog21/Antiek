"""The eight cross-cutting integration invariants, as one named suite —
antiek-unified SPR-08 M3.

The four product specs touch the same substrate at eight seams (master spec,
"the eight seam resolutions"). Each owning sprint (SPR-02..07) shipped a guard
proving its invariant holds. This file is the COMPOSITION: one command runs
every cross-cutting invariant, and the suite reads as a manifest — each test
names the invariant, its owning sprint, and the guard it composes. Running it
green means all eight integration invariants hold at once.

Why compose into one suite (not just rely on each sprint's own guard): the
seams INTERACT. A single entity crossing five boundaries can break in ways no
single-seam test catches (provenance intact per-hop, chain broken across hops —
which the e2e in tests/e2e/test_flywheel.py catches). And an operator wants ONE
button that says "the integration holds," not eight scattered green checks.
This suite is that button; the e2e flywheel is its higher-value companion.

COMPOSITION STRATEGY (diligence #4): where an owning guard is a pure function
or a mechanical greppable proof, this suite RE-RUNS that exact proof (importing
the owning guard's assertion directly, or re-running its grep). It does not
re-derive a parallel check — that would be a second source of truth that drifts
from the guard. Each test cites the owning file + the symbol it composes.

THE MANIFEST (invariant · owning sprint · guard file):
  1. single-writer isolation        · SPR-02 · tests/test_remote_exec_isolation.py
  2. no-copy seams                   · SPR-03 · tests/test_seam_no_copy.py
  3. single escrow-balance writer    · SPR-03 · tests/test_seam_single_escrow_writer.py
  4. platform_authored publish gate  · SPR-03 · tests/test_seam_platform_authored_gate.py
  5. no-fork gate ledger             · SPR-05 · tests/test_coordination_no_fork.py
  6. no-duplicate cross-wf thread    · SPR-06 · tests/test_thread_no_duplicate.py
  7. no-disbursement cost surface    · SPR-07 · tests/test_cost_consent_no_disbursement.py
  8. contract-conformance + lock     · SPR-08 · tools/codegen/check_conformance.py
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]


# A readable manifest of what's guarded — asserted to be complete (eight rows).
INVARIANT_MANIFEST: tuple[tuple[str, str, str], ...] = (
    ("single-writer isolation", "SPR-02", "tests/test_remote_exec_isolation.py"),
    ("no-copy seams", "SPR-03", "tests/test_seam_no_copy.py"),
    ("single escrow-balance writer", "SPR-03", "tests/test_seam_single_escrow_writer.py"),
    ("platform_authored publish gate", "SPR-03", "tests/test_seam_platform_authored_gate.py"),
    ("no-fork gate ledger", "SPR-05", "tests/test_coordination_no_fork.py"),
    ("no-duplicate cross-workflow thread", "SPR-06", "tests/test_thread_no_duplicate.py"),
    ("no-disbursement cost surface", "SPR-07", "tests/test_cost_consent_no_disbursement.py"),
    ("contract-conformance + sprint-lock", "SPR-08", "tools/codegen/check_conformance.py"),
)


def test_manifest_is_complete_and_files_exist() -> None:
    """The suite names exactly the eight integration invariants, and every
    guard file it composes exists (a manifest that pointed at a deleted guard
    would be a silent gap)."""
    assert len(INVARIANT_MANIFEST) == 8
    for name, sprint, guard_file in INVARIANT_MANIFEST:
        assert (_REPO / guard_file).exists(), (
            f"invariant {name!r} ({sprint}) cites missing guard {guard_file}"
        )


# ── 1 · SPR-02 — single-writer isolation (the mechanical greppable proof) ─────


def test_invariant_1_single_writer_isolation() -> None:
    """Composes SPR-02 ``test_connect_write_only_in_funnel``: the ONLY file in
    runtime/remote_exec/ that *uses* connect_write (the graph writer) is
    funnel.py. We re-run the exact mechanical proof (the grep the owning guard
    documents) so this suite stays self-contained and fast (no async leaf
    fixtures). Remote research never writes the graph directly — single writer."""
    remote_exec = _REPO / "runtime" / "remote_exec"
    use_pattern = re.compile(r"import connect_write|connect_write\s*\(")
    offenders = [
        py.name
        for py in remote_exec.glob("*.py")
        if py.name != "funnel.py" and use_pattern.search(py.read_text())
    ]
    assert offenders == [], (
        f"connect_write used outside funnel.py: {offenders} — single-writer "
        f"isolation (SPR-02) violated."
    )
    assert "import connect_write" in (remote_exec / "funnel.py").read_text(), (
        "funnel.py must bind the single writer (the writer is real, not absent)"
    )


# ── 2 · SPR-03 — no-copy seams ────────────────────────────────────────────────


def test_invariant_2_no_copy_seams() -> None:
    """Composes SPR-03 ``test_seam_no_copy._assert_no_copy``: a seam moves the
    entity by reference (same node id), and a copy FAILS the guard. We import
    the owning assertion directly and exercise both directions."""
    from tests.test_seam_no_copy import _assert_no_copy

    # same id passes; a forked id fails — the guard has teeth.
    _assert_no_copy(sent_id="insight-1", received_id="insight-1")
    with pytest.raises(AssertionError):
        _assert_no_copy(sent_id="insight-1", received_id="insight-1-COPY")


# ── 3 · SPR-03 — single escrow-balance writer ─────────────────────────────────


def test_invariant_3_single_escrow_writer() -> None:
    """Composes SPR-03 ``test_seam_single_escrow_writer``: there is exactly ONE
    function that mutates escrow_balance_usd — ip_holders.accrue_escrow — and no
    second writer. We re-run the mechanical proof: grep the substrate for the
    raw mutation ``SET escrow_balance_usd`` and assert it lives in exactly one
    module (ip_holders)."""

    def _code_only(src: str) -> str:
        # blank docstrings so prose that names the mutation doesn't count.
        try:
            tree = ast.parse(src)
        except SyntaxError:
            return src
        lines = src.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, "body", [])
                if (
                    body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    doc = body[0]
                    for i in range(doc.lineno - 1, min(getattr(doc, "end_lineno", doc.lineno), len(lines))):
                        lines[i] = ""
        return "\n".join(lines)

    writers = [
        py.relative_to(_REPO).as_posix()
        for py in (_REPO / "substrate").rglob("*.py")
        if "SET escrow_balance_usd" in _code_only(py.read_text(encoding="utf-8"))
    ]
    assert writers, "the single escrow writer must exist (not absent)"
    assert all(w.startswith("substrate/ip_holders/") for w in writers), (
        f"escrow_balance_usd is mutated in {writers} — there must be exactly "
        f"ONE escrow-balance writer module (ip_holders.accrue_escrow), seam #3. "
        f"A second writer anywhere else forks the ledger."
    )


# ── 4 · SPR-03 — platform_authored publish gate (seam #4) ─────────────────────


def test_invariant_4_platform_authored_gate() -> None:
    """Composes SPR-03 ``test_seam_platform_authored_gate``: a speak_derived doc
    serves full text ONLY after the publish gate passes; the negative (served
    without the gate) is the bug. We exercise the real servability_gate."""
    from substrate.contracts.servable import ServableEntryContract
    from substrate.seams import servability_gate

    entry = ServableEntryContract(
        document_id="doc-bio-1",
        content_class="platform_authored",
        provenance_class="speak_derived",
    )
    # deny-by-default: no gate → not served.
    assert servability_gate.serves_full_text(entry, publish_gate_passed=False) is False
    # gate passed → served.
    assert servability_gate.serves_full_text(entry, publish_gate_passed=True) is True
    # operator_authored is auto-servable (no Write-output regression).
    op = ServableEntryContract(
        document_id="doc-op-1", content_class="platform_authored",
        provenance_class="operator_authored",
    )
    assert servability_gate.serves_full_text(op, publish_gate_passed=False) is True


# ── 5 · SPR-05 — no-fork gate ledger ──────────────────────────────────────────


def test_invariant_5_no_fork_gate_ledger() -> None:
    """Composes SPR-05 ``test_coordination_no_fork``: the gate-ledger module has
    no write path (it is a read-only parse of operator_gate_actions.md). We
    re-run the mechanical proof: the gate_ledger source declares no mutating
    HTTP verb and no DB write — a single source of gate truth, never forked."""
    import ast

    src = (_REPO / "substrate" / "coordination" / "gate_ledger.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    # No function in the module performs a DuckDB write (execute of INSERT/
    # UPDATE/DELETE) — it parses markdown, it does not mutate state.
    forbidden_write = re.compile(r"\b(INSERT|UPDATE|DELETE)\b", re.IGNORECASE)
    # strip docstrings (they may legitimately discuss state) — check code calls.
    write_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and forbidden_write.search(n.value)
        and not _is_docstring(tree, n)
    ]
    assert write_calls == [], (
        "gate_ledger.py contains a SQL write — the ledger is a read-only parse "
        "of the operator gate actions doc; a write path would fork gate truth."
    )


def _is_docstring(tree: ast.AST, node: ast.Constant) -> bool:
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(parent, "body", [])
            if body and isinstance(body[0], ast.Expr) and body[0].value is node:
                return True
    return False


# ── 6 · SPR-06 — no-duplicate cross-workflow thread ───────────────────────────


def test_invariant_6_no_duplicate_thread() -> None:
    """Composes SPR-06 ``test_thread_no_duplicate``: a reconstructed thread
    holds one canonical id at every hop, and a deliberately copied entity FAILS
    the guard. We import the owning fixtures + assertion directly."""
    from tests.test_thread_no_duplicate import (
        CANONICAL_INSIGHT,
        _copy_corrupted_events,
        _full_flywheel_events_by_reference,
    )
    from substrate.seams.thread import (
        assert_single_canonical_entity,
        reconstruct_thread,
    )

    clean = reconstruct_thread(
        CANONICAL_INSIGHT,
        seam_events=_full_flywheel_events_by_reference(),
        origin_entity_kind="insight_node",
    )
    assert_single_canonical_entity(clean)  # passes

    corrupted = reconstruct_thread(
        CANONICAL_INSIGHT,
        seam_events=_copy_corrupted_events(),
        origin_entity_kind="insight_node",
    )
    with pytest.raises(AssertionError):
        assert_single_canonical_entity(corrupted)  # the copy fails


# ── 7 · SPR-07 — no-disbursement cost/consent surface ─────────────────────────


def test_invariant_7_no_disbursement_cost_surface() -> None:
    """Composes SPR-07 ``test_cost_consent_no_disbursement``: the cost/consent
    surface contains NO payout token and NO escrow-mutation token. We import the
    canonical forbidden-token sets from the owning test (the single source of
    truth) and re-run the greppable absence proof over the surface files."""
    from tests.test_cost_consent_no_disbursement import (
        _FORBIDDEN_ESCROW_MUTATION,
        _FORBIDDEN_PAYOUT_TOKENS,
        _SURFACE_FILES,
        _code_only,
    )

    forbidden = _FORBIDDEN_PAYOUT_TOKENS + _FORBIDDEN_ESCROW_MUTATION
    for rel in _SURFACE_FILES:
        src = _code_only((_REPO / rel).read_text(encoding="utf-8"))
        offenders = [tok for tok in forbidden if tok in src]
        assert not offenders, (
            f"{rel} contains a disbursement/escrow-mutation token {offenders} — "
            f"the read-only cost/consent surface must not pay anyone (SPR-07). "
            f"Accrual ≠ disbursement."
        )


# ── 8 · SPR-08 — contract-conformance + frozen sprint-lock ────────────────────


def test_invariant_8_conformance_and_sprint_lock() -> None:
    """Composes this sprint's own gate: every contract conforms (real impl or
    stub) and the frozen DRW sprint-lock resolves every downstream citation.
    The composition guard itself, made an invariant of the suite."""
    from tools.codegen import check_conformance

    assert check_conformance.registry_coverage_errors() == []
    assert check_conformance.conformance_errors() == []
    assert check_conformance.sprint_lock_errors() == []
    assert check_conformance.run_gate() == 0


# ── The suite is green ⇒ all eight integration invariants hold ────────────────


def test_all_eight_invariants_named_and_green() -> None:
    """A single readable assertion that the suite covers exactly the eight
    invariants the master spec resolves — the operator's one-button warrant."""
    sprints = {sprint for _name, sprint, _file in INVARIANT_MANIFEST}
    # every owning sprint SPR-02..08 is represented (SPR-04 owns no cross-cutting
    # invariant of its own — its context-pack contract is conformance-guarded by
    # invariant 8, so it is intentionally not a separate row).
    assert {"SPR-02", "SPR-03", "SPR-05", "SPR-06", "SPR-07", "SPR-08"} <= sprints
    assert len(INVARIANT_MANIFEST) == 8
