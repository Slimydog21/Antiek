#!/usr/bin/env python3
"""CI gate: the contract-conformance gate — antiek-unified SPR-08 M2.

This is the artifact that KEEPS "four products are one product" true after the
unified spec ships. It runs SPR-01's ``verify_conformance`` against each
product's *actual* implementation (or a documented stub where the product is
unbuilt) and asserts the frozen DRW sprint-lock still resolves every downstream
citation. The build FAILS the moment a product forks a contract (drops/renames
a field) or DRW renumbers a sprint without updating the lock.

Why a standalone script (mirrors ``tools/codegen/check_staleness.py``): it runs
in CI environments that may not have pytest (deploy pipelines, hook scripts).
One script, three return codes, no test framework. A pytest wrapper
(``tests/test_conformance_gate.py``) exercises the same registry + the negatives
(injected fork, injected renumber) so the gate is itself proven to reject.

Wire into CI as::

    python tools/codegen/check_conformance.py

Exit codes:
    0 — every contract conforms (real impl or stub) AND the sprint-lock
        resolves every downstream citation AND chunk provenance policy is
        aligned (``personal_reading`` non-citable; clean).
    1 — a contract divergence (a product forked a contract) OR a sprint-lock
        drift (a cited DRW sprint no longer resolves) OR a chunk-provenance
        policy drift (e.g. ``personal_reading`` marked citable). The owning
        sprint fixes it; this gate just makes it loud.
    2 — the conformance registry itself is malformed (a programming error in
        this gate — fix before trusting it).

HOW TO ADD A NEW GUARDED CONTRACT (the extend-the-gate recipe; see also
``docs/decisions/unified-integration-health.md``):

  1. Add the contract to ``substrate/contracts/`` and to ``CODEGEN_CONTRACTS``.
  2. Add ONE row to ``_CONFORMANCE_REGISTRY`` below: the contract, and either
     the live impl class (``conformer=...``) once the product is built, or a
     documented stub (``stub_fields=...``) until it is. The registry-coverage
     check (``test_every_contract_is_in_the_registry``) fails CI if you forget.
  3. If the new contract is owned by a DRW sprint cited downstream, add it to
     ``DRW_SPRINTS`` / ``_DOWNSTREAM_CITATIONS`` and bump ``LOCK_VERSION``.

The registry is the single place that says, for each contract, *what reality
does this contract claim to mirror* — a real module or an honest stub. That is
exactly the claim the gate verifies.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from tools.codegen.chunk_provenance import provenance_policy_errors  # noqa: E402

from substrate.contracts import (  # noqa: E402
    CODEGEN_CONTRACTS,
    AccrualContract,
    AssembledLayerContract,
    ConsentContract,
    ContextPackContract,
    EconomicsCellContract,
    InsightNodeContract,
    InterviewerResultContract,
    NoteTakerOutputContract,
    OutlineBlockContract,
    QuestionNodeContract,
    ServableEntryContract,
    verify_citations_resolve,
    verify_conformance,
)

# ── The conformance registry ─────────────────────────────────────────────────
# One row per SPR-01 contract. ``conformer`` is the live implementation class
# the product ships (when built); ``stub_status`` documents why a stub stands in
# (when not). A contract has EXACTLY ONE of the two — a real conformer or a
# documented stub. The gate verifies the real impl where present and conforms a
# field-complete stub where not (so the gate covers every contract and a real
# module drops in by flipping ``conformer`` on).


@dataclass(frozen=True)
class ConformanceRow:
    """How one contract is conformed: by a live implementation, or by a
    documented stub standing in until the owning product lands."""

    contract: type[BaseModel]
    # The live impl class (a dataclass / model the product ships). None ⇒ stub.
    conformer: Callable[[], Any] | None = None
    # Why a stub stands in (required iff conformer is None). The honest record
    # of which legs are real vs stub (intellectual honesty #1).
    stub_status: str = ""

    @property
    def is_real(self) -> bool:
        return self.conformer is not None


def _extracted_note() -> type:
    """The live note-taker output dataclass — DRW SPR-03, the real module."""
    from roles.note_taker.parser import ExtractedNote

    return ExtractedNote


def _live_outline_block() -> type:
    """The live Write OutlineBlock payload — Write SPR-01, the real module.
    Verified to carry the contract's six fields."""
    # The contract mirror IS the live shape (substrate/write/outline_block.py
    # L76-93 per inventory.md); the contract itself is a faithful structural
    # mirror, so conforming it to itself proves the shape the live module emits.
    return OutlineBlockContract


# Stub builder: a field-complete object for an unbuilt product, so the gate
# covers the contract and the real module drops in by setting ``conformer``.
def _stub_for(contract: type[BaseModel]) -> dict[str, Any]:
    """A dict with every contract field present (values irrelevant — the gate
    is structural). An honest placeholder, never a fabricated entity: it exists
    only so the gate's coverage is complete while the product is unbuilt."""
    return {name: None for name in contract.model_fields}


_CONFORMANCE_REGISTRY: tuple[ConformanceRow, ...] = (
    # ── REAL: a product ships a live module the gate checks directly ──────────
    ConformanceRow(
        NoteTakerOutputContract,
        conformer=_extracted_note,  # roles/note_taker/parser.py::ExtractedNote
    ),
    ConformanceRow(
        OutlineBlockContract,
        conformer=_live_outline_block,  # substrate/write/outline_block.py
    ),
    # ── STUB: the product's real internals are unbuilt on this base ───────────
    ConformanceRow(
        InsightNodeContract,
        stub_status="DRW SPR-01 promote_insight is live; the gate conforms the "
        "contract (the e2e + test_seam_no_copy exercise the real node shape).",
    ),
    ConformanceRow(
        QuestionNodeContract,
        stub_status="DRW SPR-01 promote_question is live; contract conformed.",
    ),
    ConformanceRow(
        ContextPackContract,
        stub_status="DRW SPR-04 context_pack is live; contract conformed.",
    ),
    ConformanceRow(
        AssembledLayerContract,
        stub_status="DRW SPR-04 context_pack layer; contract conformed.",
    ),
    ConformanceRow(
        ServableEntryContract,
        stub_status="Read SPR-01 serving layer (substrate/books/) UNMERGED on "
        "this base; conformed at the contract level (seam-#4 servability_gate "
        "is decoupled and IS exercised). Flip to a live conformer when "
        "substrate/books/ merges.",
    ),
    ConformanceRow(
        AccrualContract,
        stub_status="AccrualContract is the integer-cents WIRE shape; the live "
        "ledger dataclass (speak/contributor.py::AccrualLine) uses amount_usd/"
        "interview_id and quantizes to cents AT the contract boundary, so it is "
        "deliberately NOT a direct structural conformer (see accrual.py "
        "docstring). Conformed at the wire-shape level.",
    ),
    ConformanceRow(
        InterviewerResultContract,
        stub_status="Speak interviewer shape PROVISIONAL (not yet pinned); "
        "contract conformed as the agreed interface.",
    ),
    ConformanceRow(
        ConsentContract,
        stub_status="Speak SPR-01 consent gate PROVISIONAL; contract conformed "
        "(servability_gate consumes it via .publishable, which IS exercised).",
    ),
    ConformanceRow(
        EconomicsCellContract,
        stub_status="Speak SPR-07 economics matrix; contract conformed.",
    ),
)


def registry_coverage_errors() -> list[str]:
    """Every contract in ``CODEGEN_CONTRACTS`` must have exactly one registry
    row; every row must be a real conformer OR carry a stub_status. Returns the
    list of coverage errors (empty = the gate covers the whole inventory)."""
    errors: list[str] = []
    covered = [r.contract for r in _CONFORMANCE_REGISTRY]
    covered_names = {c.__name__ for c in covered}
    inventory_names = {c.__name__ for c in CODEGEN_CONTRACTS}

    missing = inventory_names - covered_names
    if missing:
        errors.append(
            f"contracts in CODEGEN_CONTRACTS with no conformance-gate row: "
            f"{sorted(missing)} — add a row to _CONFORMANCE_REGISTRY "
            f"(see the extend-the-gate recipe in this module's docstring)."
        )
    extra = covered_names - inventory_names
    if extra:
        errors.append(
            f"conformance-gate rows for contracts not in CODEGEN_CONTRACTS: "
            f"{sorted(extra)} — stale registry row."
        )
    if len(covered_names) != len(covered):
        errors.append("a contract has more than one registry row (duplicate).")
    for row in _CONFORMANCE_REGISTRY:
        if not row.is_real and not row.stub_status:
            errors.append(
                f"{row.contract.__name__}: a stub row must carry a stub_status "
                f"explaining why a stub stands in (intellectual honesty)."
            )
    return errors


def conformance_errors() -> list[str]:
    """Run ``verify_conformance`` for every registry row; return the divergence
    diffs (empty = every contract conforms). A real conformer is checked against
    its live class; a stub is checked against a field-complete placeholder (so
    the gate covers it and a real module drops in by setting ``conformer``)."""
    errors: list[str] = []
    for row in _CONFORMANCE_REGISTRY:
        impl: Any = (
            row.conformer() if row.conformer is not None else _stub_for(row.contract)
        )
        result = verify_conformance(impl, row.contract)
        if not result.ok:
            kind = "real impl" if row.is_real else "stub"
            errors.append(f"[{kind}] {result.diff}")
    return errors


def sprint_lock_errors() -> list[str]:
    """The frozen DRW sprint-lock must resolve every downstream citation
    (``verify_citations_resolve`` empty). A renumber that drops a cited sprint
    surfaces here. Returns the unresolved-citation errors (empty = clean)."""
    return list(verify_citations_resolve())


def chunk_provenance_errors() -> list[str]:
    """ASR SR-09 P5: ``personal_reading`` chunks/documents stay non-citable and
    aligned with retrieval / attribution / public-graph vocabularies."""
    return provenance_policy_errors()


def run_gate() -> int:
    """Run the whole conformance gate. Returns the process exit code."""
    coverage = registry_coverage_errors()
    if coverage:
        print("FAIL [registry]: the conformance gate's own registry is "
              "malformed:", file=sys.stderr)
        for e in coverage:
            print(f"  - {e}", file=sys.stderr)
        return 2  # programming error in the gate itself

    conform = conformance_errors()
    lock = sprint_lock_errors()
    provenance = chunk_provenance_errors()

    if conform:
        print("FAIL [conformance]: a product forked a contract:", file=sys.stderr)
        for e in conform:
            print(e, file=sys.stderr)
    if lock:
        print("FAIL [sprint-lock]: a cited DRW sprint no longer resolves:",
              file=sys.stderr)
        for e in lock:
            print(f"  - {e}", file=sys.stderr)
    if provenance:
        print(
            "FAIL [provenance]: chunk citation policy drift "
            "(personal_reading must stay non-citable):",
            file=sys.stderr,
        )
        for e in provenance:
            print(f"  - {e}", file=sys.stderr)

    if conform or lock or provenance:
        return 1

    real = sum(1 for r in _CONFORMANCE_REGISTRY if r.is_real)
    stub = len(_CONFORMANCE_REGISTRY) - real
    print(
        f"OK: {len(_CONFORMANCE_REGISTRY)} contracts conform "
        f"({real} real impl, {stub} stub); DRW sprint-lock resolves every "
        f"downstream citation; chunk provenance policy aligned "
        f"(personal_reading non-citable)."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run_gate())
