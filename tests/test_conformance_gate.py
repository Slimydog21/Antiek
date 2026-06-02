"""The contract-conformance gate test — antiek-unified SPR-08 M2.

The pytest wrapper around ``tools/codegen/check_conformance.py``. It proves the
gate (a) PASSES on the current trunk — every SPR-01 contract conforms (real impl
or documented stub) and the frozen DRW sprint-lock resolves every downstream
citation — and (b) FAILS on an injected divergence: a product forking a contract
and a DRW sprint renumber. A conformance gate nobody has seen reject a real
violation is a green light that guards nothing (rigor #3).

This is the artifact that keeps "four products are one product" true AFTER the
unified spec ships: the eight resolved seams cannot quietly re-break, because a
fork or a renumber is now a loud CI failure instead of a silent drift.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from substrate.contracts import (
    CODEGEN_CONTRACTS,
    NoteTakerOutputContract,
    drw_sprint_lock,
    verify_conformance,
)
from tools.codegen import check_conformance
import tools.codegen.chunk_provenance as chunk_provenance

# ── M2 positive — the gate is clean on the current trunk ──────────────────────


def test_gate_passes_on_current_trunk() -> None:
    """The whole gate (registry coverage + conformance + sprint-lock) returns 0
    on the current trunk. This is the green the operator relies on."""
    assert check_conformance.run_gate() == 0


def test_every_contract_is_in_the_registry() -> None:
    """Acceptance: every SPR-01 contract has a conformance assertion (stub or
    real impl). The registry-coverage check finds zero gaps — a contract added
    to CODEGEN_CONTRACTS without a registry row would fail here (so the gate
    cannot rot as the product grows; defensibility #5)."""
    assert check_conformance.registry_coverage_errors() == []
    # And the coverage is exactly the inventory, no more no less.
    registry_names = {r.contract.__name__ for r in check_conformance._CONFORMANCE_REGISTRY}
    inventory_names = {c.__name__ for c in CODEGEN_CONTRACTS}
    assert registry_names == inventory_names


def test_no_contract_is_forked_on_trunk() -> None:
    """Acceptance: no product impl diverges from its contract on the trunk."""
    assert check_conformance.conformance_errors() == []


def test_sprint_lock_resolves_every_downstream_citation() -> None:
    """Acceptance: the frozen DRW sprint-lock resolves all downstream Read/
    Write/Speak citations (seam #6 risk surface clean)."""
    assert check_conformance.sprint_lock_errors() == []


def test_chunk_provenance_policy_aligned_on_trunk() -> None:
    """ASR SR-09 P5: personal_reading chunks/documents stay non-citable and
    aligned with retrieval / attribution / public-graph vocabularies."""
    assert check_conformance.chunk_provenance_errors() == []


def test_personal_reading_chunk_and_document_non_citable() -> None:
    """Explicit API pins: owner lane is never a public synthesis citation."""
    assert chunk_provenance.PERSONAL_READING_CONTENT_CLASS == "personal_reading"
    assert "personal_reading" in chunk_provenance.NON_CITABLE_CONTENT_CLASSES
    assert chunk_provenance.is_chunk_citable("personal_reading") is False
    assert chunk_provenance.is_document_citable("personal_reading") is False
    assert chunk_provenance.is_chunk_citable("public_domain") is True
    assert chunk_provenance.is_chunk_citable(None) is False


def test_real_impls_are_actually_checked_not_just_stubs() -> None:
    """Honesty #1: the gate is not all stubs — at least the note-taker output
    and the Write OutlineBlock are checked against REAL in-tree shapes, so the
    gate has teeth on the products that exist."""
    real_rows = [r for r in check_conformance._CONFORMANCE_REGISTRY if r.is_real]
    real_names = {r.contract.__name__ for r in real_rows}
    assert "NoteTakerOutputContract" in real_names
    assert "OutlineBlockContract" in real_names
    # And each real conformer genuinely satisfies its contract.
    for row in real_rows:
        assert row.conformer is not None  # narrowed by is_real
        result = verify_conformance(row.conformer(), row.contract)
        assert result.ok, result.diff


# ── M2 negative #1 — an injected contract FORK fails the gate (rigor #3) ──────


def test_injected_contract_fork_fails_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject a contract divergence — a product impl that DROPPED a contract
    field — and the gate fails with a useful field-level diff. This is the
    'a product forked a contract' failure the gate exists to catch.

    We inject by swapping the note-taker conformer for a fork that is missing
    ``source_event_ids`` (the load-bearing attribution field), then assert the
    gate returns 1 and the diff names the dropped field."""

    @dataclass
    class ForkedNote:
        note_id: str
        text: str
        confidence: str
        # FORK: ``source_event_ids`` dropped — an unattributed note shape.

    # Patch the live conformer of the NoteTakerOutputContract row to the fork.
    original = check_conformance._CONFORMANCE_REGISTRY
    patched = tuple(
        check_conformance.ConformanceRow(
            row.contract, conformer=(lambda: ForkedNote)
        )
        if row.contract is NoteTakerOutputContract and row.is_real
        else row
        for row in original
    )
    monkeypatch.setattr(check_conformance, "_CONFORMANCE_REGISTRY", patched)

    # The gate now fails (exit 1) ...
    assert check_conformance.run_gate() == 1
    # ... and the divergence is reported with the dropped field named.
    errors = check_conformance.conformance_errors()
    assert errors, "the injected fork must produce a conformance error"
    joined = "\n".join(errors)
    assert "source_event_ids" in joined
    assert "ForkedNote" in joined
    assert "NoteTakerOutputContract" in joined


def test_revert_restores_a_clean_gate() -> None:
    """After the monkeypatched fork test tears down, the gate is clean again —
    the registry is module state; the injection was scoped to one test (rigor
    #3: inject, observe failure, REVERT)."""
    assert check_conformance.conformance_errors() == []
    assert check_conformance.run_gate() == 0


# ── M2 negative #2 — an injected DRW RENUMBER fails the gate (rigor #3) ───────


def test_injected_sprint_renumber_fails_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inject a DRW sprint renumber — drop SPR-01 from the frozen lock (as if
    DRW renumbered it) WITHOUT updating the downstream citations — and the gate
    fails. Read and Write both cite DRW SPR-01; an unresolved citation is the
    seam-#6 silent-drift failure the lock exists to make loud."""
    # Renumber: remove sprint 1 from the frozen map. The downstream index still
    # cites sprint 1 (read, write) → the citation no longer resolves.
    renumbered = dict(drw_sprint_lock.DRW_SPRINTS)
    del renumbered[1]
    monkeypatch.setattr(drw_sprint_lock, "DRW_SPRINTS", renumbered)

    # verify_citations_resolve reads DRW_SPRINTS at call time → sees the drop.
    lock_errors = check_conformance.sprint_lock_errors()
    assert lock_errors, "a renumber that drops a cited sprint must be caught"
    joined = "\n".join(lock_errors)
    assert "SPR-01" in joined
    # The blast radius is named — Read and Write cite SPR-01.
    assert "read" in joined and "write" in joined

    # And the whole gate fails (exit 1) on the renumber.
    assert check_conformance.run_gate() == 1


def test_revert_restores_a_clean_sprint_lock() -> None:
    """The renumber injection was scoped; the lock resolves cleanly again."""
    assert check_conformance.sprint_lock_errors() == []


# ── M2 negative #4 — injected non-citable policy drift fails the gate ─────────


def test_injected_personal_reading_citable_fails_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If personal_reading were removed from NON_CITABLE_CONTENT_CLASSES, the
    gate must fail — the shortcut that would let owner-only reading leak into
    public synthesis citations."""
    monkeypatch.setattr(
        chunk_provenance,
        "NON_CITABLE_CONTENT_CLASSES",
        frozenset(),
    )

    errors = check_conformance.chunk_provenance_errors()
    assert errors, "empty NON_CITABLE must produce provenance errors"
    joined = "\n".join(errors)
    assert "personal_reading" in joined
    assert "NON_CITABLE_CONTENT_CLASSES" in joined

    assert check_conformance.run_gate() == 1


def test_revert_restores_clean_chunk_provenance() -> None:
    """Provenance injection was scoped; policy aligns again."""
    assert check_conformance.chunk_provenance_errors() == []
    assert chunk_provenance.is_chunk_citable("personal_reading") is False


# ── M2 negative #3 — an out-of-range citation is a loud KeyError ──────────────


def test_unresolved_sprint_number_is_a_loud_failure() -> None:
    """Belt-and-suspenders: resolving a sprint outside the locked range raises a
    KeyError that names the lock version — never a silent wrong-deliverable."""
    with pytest.raises(KeyError, match="not in the frozen sprint-lock"):
        drw_sprint_lock.resolve_drw_sprint(99)
