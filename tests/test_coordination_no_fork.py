"""SPR-05 M4 — the no-fork invariant test (load-bearing).

This is the mandatory gate that proves the coordination dashboard is a VIEW over
``docs/operator_gate_actions.md``, never a fork. The strategy (rigor #3): never
compare the ledger against its own parser's output — that is a tautology that
cannot catch the ledger drifting from the human-edited source. Instead:

1. Parse the canonical file by a SECOND, INDEPENDENT path
   (:func:`parse_quick_status_table` reads the top quick-status MARKDOWN TABLE;
   the ledger reads the per-section ``**Status:**`` headers). Assert the two
   agree on every gate's status — drift in either path fails the test.

2. Mutate a *fixture copy* of the source file's gate status and assert the
   ledger reflects the mutation on the next read (no stale second copy of state).

3. Feed a deliberately-divergent parser a fixture whose quick table disagrees
   with its sections, and assert the agreement check fails — proving the test
   has teeth.

Plus accuracy + grounding checks for M1 (the impact map) and M5 (the snapshot).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.coordination.gate_ledger import (
    GateStatus,
    Product,
    canonical_gate_path,
    load_gate_ledger,
    parse_gate_ledger,
    parse_quick_status_table,
)
from substrate.coordination.roadmap import build_roadmap

# ── 1. The no-fork equality: two independent parses agree ────────────────────

def test_ledger_equals_independent_quick_status_parse() -> None:
    """The load-bearing assertion: the per-section ledger and the independent
    quick-status table parse agree on every gate id and every status."""
    md = canonical_gate_path().read_text(encoding="utf-8")
    ledger = parse_gate_ledger(md, source_path="canonical")
    quick = parse_quick_status_table(md)

    # Same gate ids.
    assert set(ledger.gate_ids()) == set(quick), (
        f"gate id sets differ: ledger={ledger.gate_ids()} quick={sorted(quick)}"
    )
    # Same status on every gate — the two independent paths must agree.
    for gate in ledger.gates:
        assert quick[gate.gate_id] == gate.status, (
            f"{gate.gate_id}: section parse says {gate.status} but the "
            f"independent quick-status table says {quick[gate.gate_id]} — the "
            f"ledger has drifted from the human-edited source."
        )


def test_all_canonical_gates_present() -> None:
    ledger = load_gate_ledger()
    assert ledger.gate_ids() == (
        "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8",
        "G9", "G10", "G11", "G12", "G13",
    )


# ── 2. Mutation of a fixture copy is reflected (no stale second copy) ─────────

def _write_fixture(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "operator_gate_actions.md"
    p.write_text(body, encoding="utf-8")
    return p


_MINIMAL_DOC = """# Operator-only gate actions

## Quick status

| Gate | Status | What it blocks |
|---|---|---|
| G1 retrieval-time legal gating | {g1_quick} | — |
| G2 lawyer review | {g2_quick} | payouts |

## G1 — Retrieval-time legal gating

**Status:** {g1_section}

## G2 — Lawyer review

**Status:** {g2_section}
**Owner:** Operator + counsel
**Blocks:** All Stripe payouts
"""


def test_mutating_source_is_reflected(tmp_path: Path) -> None:
    """Editing the source file's gate status changes the ledger on next read —
    there is no stale second copy."""
    closed = _MINIMAL_DOC.format(
        g1_quick="✅ closed", g1_section="✅ **CLOSED**",
        g2_quick="✅ closed", g2_section="✅ **CLOSED**",
    )
    p = _write_fixture(tmp_path, closed)
    ledger = load_gate_ledger(p)
    assert ledger.by_id("G2").status is GateStatus.CLOSED

    # Operator re-opens G2 in the source file.
    reopened = _MINIMAL_DOC.format(
        g1_quick="✅ closed", g1_section="✅ **CLOSED**",
        g2_quick="❌ open", g2_section="❌ OPEN",
    )
    p.write_text(reopened, encoding="utf-8")
    ledger2 = load_gate_ledger(p)
    assert ledger2.by_id("G2").status is GateStatus.OPEN, (
        "the ledger did not reflect the re-opened gate — it is holding a stale "
        "second copy of state instead of reading the source."
    )


# ── 3. A deliberately-divergent fixture must FAIL the agreement check ─────────

def test_divergent_source_fails_agreement() -> None:
    """If the quick table and the sections disagree (e.g. a half-finished edit),
    the no-fork agreement check must catch it — proving the test has teeth."""
    divergent = _MINIMAL_DOC.format(
        g1_quick="✅ closed", g1_section="✅ **CLOSED**",
        # Quick table says open, the section says closed — a real human edit
        # mistake the no-fork check exists to catch.
        g2_quick="❌ open", g2_section="✅ **CLOSED**",
    )
    ledger = parse_gate_ledger(divergent, source_path="divergent-fixture")
    quick = parse_quick_status_table(divergent)
    mismatches = [
        g.gate_id for g in ledger.gates if quick[g.gate_id] != g.status
    ]
    assert "G2" in mismatches, (
        "the agreement check failed to catch a deliberately-divergent source — "
        "the no-fork test has no teeth."
    )


# ── 4. Read-only: no write path to gate state in the package ─────────────────

def test_gate_ledger_module_has_no_write_path() -> None:
    """Greppable absence of any write to the canonical file or a gate store.
    A future maintainer confirms 'the surface cannot change a gate' by this."""
    src = (
        Path(__file__).resolve().parents[1]
        / "substrate" / "coordination" / "gate_ledger.py"
    ).read_text(encoding="utf-8")
    forbidden = [".write_text(", "open(", ".write(", "save_", "INSERT", "UPDATE ", "connect_write"]
    offenders = [tok for tok in forbidden if tok in src]
    assert not offenders, (
        f"gate_ledger.py contains a write-shaped token {offenders} — the ledger "
        f"must be derived on read only, never write gate state."
    )


# ── M1 accuracy: the impact map is grounded in the product specs ─────────────

def test_impact_map_grounded() -> None:
    """The per-product impact map matches each spec's stated gating (rigor:
    'verified against the product specs' gate references')."""
    ledger = load_gate_ledger()

    # G2/G3 → disbursement, which only Read + Speak route. Research/Write do not.
    for gid in ("G2", "G3"):
        blocks = set(ledger.by_id(gid).blocks_products())
        assert blocks == {Product.READ, Product.SPEAK}, (
            f"{gid} should block Read+Speak disbursement, got {blocks}"
        )

    # G7 → multi-user across ALL four products.
    assert set(ledger.by_id("G7").blocks_products()) == {
        Product.RESEARCH, Product.READ, Product.WRITE, Product.SPEAK
    }

    # G8 → RL training: Write (edit-trajectory SFT) + Speak (interviewer RL).
    assert set(ledger.by_id("G8").blocks_products()) == {Product.WRITE, Product.SPEAK}

    # G6 → Research (Phase-8 enforcing + autoresearch wedges).
    assert set(ledger.by_id("G6").blocks_products()) == {Product.RESEARCH}

    # G4/G5 are infra verdicts — no per-product block.
    assert ledger.by_id("G4").blocks_products() == ()
    assert ledger.by_id("G5").blocks_products() == ()


def test_gates_blocking_only_counts_open_gates() -> None:
    """A closed gate blocks nothing, even if it has historical impact rows
    (G1)."""
    ledger = load_gate_ledger()
    # G1 has impact rows but is closed → blocks no product.
    assert ledger.by_id("G1").is_closed
    assert ledger.gates_blocking(Product.READ)  # G2/G3/G7 are open and block Read
    blocking_ids = {g.gate_id for g in ledger.gates_blocking(Product.READ)}
    assert "G1" not in blocking_ids
    assert {"G2", "G3", "G7"} <= blocking_ids


# ── G9-G12 impact map accuracy (grounded in product/legal specs) ────────────

def test_impact_map_g9_arxiv_researcher_payout() -> None:
    """G9 blocks the money-moving wave of the arXiv-ingest track (SPR-07/08).
    Research owns arXiv ingestion; the payout track is on Research's side.
    Gated in caffenagent state.json as BLOCKED-GATE."""
    ledger = load_gate_ledger()
    blocks = set(ledger.by_id("G9").blocks_products())
    assert blocks == {Product.RESEARCH}, (
        f"G9 should block Research (arXiv SPR-07/08 payout), got {blocks}"
    )


def test_impact_map_g10_stripe_press_opt_in() -> None:
    """G10 blocks serving ANY in-copyright Stripe Press title. Read is the
    servable-path workflow — titles must reach a servable content_class."""
    ledger = load_gate_ledger()
    blocks = set(ledger.by_id("G10").blocks_products())
    assert blocks == {Product.READ}, (
        f"G10 should block Read (Stripe Press servable path), got {blocks}"
    )


def test_impact_map_g11_x_no_training() -> None:
    """G11 blocks training/RL export of BYOK X content. Write (edit-trajectory
    SFT) and Speak (interviewer RL) are the two products with training tracks.
    Status is 'enforced in code / standing operator duty' — classified CLOSED
    because ✅ is present, but the standing-duty nuance is preserved in
    status_raw (not flattened away)."""
    ledger = load_gate_ledger()
    blocks = set(ledger.by_id("G11").blocks_products())
    assert blocks == {Product.WRITE, Product.SPEAK}, (
        f"G11 should block Write+Speak (X no-training), got {blocks}"
    )
    # G11 contains ✅ → classified CLOSED, but the standing duty is real nuance.
    gate = ledger.by_id("G11")
    assert gate.status is GateStatus.CLOSED, (
        f"G11 has ✅ in status → CLOSED, got {gate.status}"
    )
    # The nuance is NOT thrown away — status_raw carries the full string.
    assert "standing" in gate.status_raw.lower(), (
        f"G11 status_raw should carry the standing-duty nuance, got: {gate.status_raw}"
    )
    assert "enforced" in gate.status_raw.lower(), (
        f"G11 status_raw should carry the enforced-in-code nuance, got: {gate.status_raw}"
    )


def test_impact_map_g12_bernays_renewal() -> None:
    """G12 blocks making additional 1927–1930 Bernays titles servable. Read is
    the servable-path workflow."""
    ledger = load_gate_ledger()
    blocks = set(ledger.by_id("G12").blocks_products())
    assert blocks == {Product.READ}, (
        f"G12 should block Read (Bernays per-title servable path), got {blocks}"
    )


def test_impact_map_g13_infra_only() -> None:
    """G13 (auth diagnostic matrix) is infra, closed, no per-product block."""
    ledger = load_gate_ledger()
    assert ledger.by_id("G13").blocks_products() == ()
    assert ledger.by_id("G13").is_closed


# ── M5 accuracy snapshot: the canonical gate states ──────────────────────────

def test_accuracy_snapshot_matches_canonical_states() -> None:
    """Pin the documented gate states so a parsing/rendering regression is
    caught: G1/G4/G5/G11/G13 closed, G2/G3/G6/G9/G10/G12 open, G7 calendar,
    G8 data-bound; G5 is provisionally closed. G11 carries standing-duty
    nuance in status_raw despite being classified CLOSED (✅ is present)."""
    ledger = load_gate_ledger()
    expected = {
        "G1": GateStatus.CLOSED,
        "G2": GateStatus.OPEN,
        "G3": GateStatus.OPEN,
        "G4": GateStatus.CLOSED,
        "G5": GateStatus.CLOSED,
        "G6": GateStatus.OPEN,
        "G7": GateStatus.CALENDAR,
        "G8": GateStatus.DATA_BOUND,
        "G9": GateStatus.OPEN,
        "G10": GateStatus.OPEN,
        "G11": GateStatus.CLOSED,  # ✅ enforced in code — standing duty nuance in status_raw
        "G12": GateStatus.OPEN,
        "G13": GateStatus.CLOSED,
    }
    actual = {g.gate_id: g.status for g in ledger.gates}
    assert actual == expected, f"gate-state snapshot drifted: {actual}"

    # Nuance preserved: G5 is provisionally closed (not flattened to plain closed).
    assert ledger.by_id("G5").is_provisional
    assert not ledger.by_id("G4").is_provisional
    # Closure records resolve to docs/decisions/ for the closed-with-record gates.
    assert ledger.by_id("G4").closure_record == "docs/decisions/g4-lemon-ui-verdict.md"
    assert ledger.by_id("G5").closure_record is not None
    assert ledger.by_id("G5").closure_record.startswith("docs/decisions/")
    # G13 is closed with a diagnostics evidence path (not docs/decisions/).
    assert ledger.by_id("G13").is_closed
    assert ledger.by_id("G13").closure_record == "docs/diagnostics/auth-failure-mode-matrix.md"


# ── M2 roadmap: count reconciliation + critical path + unblocked-now ─────────

def test_roadmap_count_reconciles_to_45() -> None:
    """Rigor #1 — the count is summed from the real roster files, not trusted
    from prose. DRW 10 + Read 9 + Write 9 + Speak 9 + unified 8 = 45."""
    roadmap = build_roadmap()
    by_spec = {r.spec: r.count for r in roadmap.rosters}
    assert by_spec == {"drw": 10, "read": 9, "write": 9, "speak": 9, "unified": 8}, (
        f"roster counts changed: {by_spec}"
    )
    assert roadmap.total_sprints == 45
    assert roadmap.superseded_count == 6  # shell, superseded — not added


def test_roadmap_surfaces_drw_critical_path() -> None:
    """The DRW critical path drw:1 → drw:3 → drw:10 must be surfaced explicitly
    (consumed from SPR-01's DAG, not hand-set)."""
    roadmap = build_roadmap()
    assert roadmap.critical_path == ("drw:1", "drw:3", "drw:10")
    crit_ids = {s.node_id for s in roadmap.all_sprints() if s.on_critical_path}
    assert crit_ids == {"drw:1", "drw:3", "drw:10"}


def test_unblocked_now_is_derived_from_dependency_state() -> None:
    """Unblocked-now is computed from the DAG + sprint-lock status, not
    hand-maintained. Read sprints depend on DRW SPR-05/06 (planned) → blocked;
    DRW SPR-01 (live, no deps) → unblocked."""
    roadmap = build_roadmap()
    by_id = {s.node_id: s for s in roadmap.all_sprints()}

    # drw:1 is live with no DRW deps → unblocked.
    assert by_id["drw:1"].unblocked
    # read:* depend on drw:5 + drw:6 (planned) → blocked on them.
    assert not by_id["read:1"].unblocked
    assert "drw:5" in by_id["read:1"].blocked_on
    assert "drw:6" in by_id["read:1"].blocked_on
    # The unblocked set and blocked set partition all sprints.
    assert len(roadmap.unblocked_now()) + len(roadmap.blocked()) == roadmap.total_sprints


def test_roadmap_reads_rosters_from_fixture_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The roadmap reads roster filenames from disk (it authors nothing). Point
    it at a fixture and it reflects the fixture's files."""
    (tmp_path / "deep-research-workspace").mkdir()
    (tmp_path / "deep-research-workspace" / "sprint-01-foo.html").write_text("x")
    (tmp_path / "read").mkdir()
    (tmp_path / "read" / "sprint-01-bar.html").write_text("x")
    (tmp_path / "read" / "sprint-02-baz.html").write_text("x")
    roadmap = build_roadmap(specs_root=tmp_path)
    by_spec = {r.spec: r.count for r in roadmap.rosters}
    assert by_spec["drw"] == 1
    assert by_spec["read"] == 2
    # Specs with no fixture dir contribute 0 (read-only, no invention).
    assert by_spec["write"] == 0


def test_roadmap_rejects_duplicate_sprint_identity(tmp_path: Path) -> None:
    """Two filenames cannot claim the same canonical ``<spec>:<sprint>`` node."""
    spec_dir = tmp_path / "deep-research-workspace"
    spec_dir.mkdir()
    (spec_dir / "sprint-01-first.html").write_text("x")
    (spec_dir / "sprint-01-contradiction.html").write_text("x")

    with pytest.raises(ValueError, match="duplicate sprint identity 01"):
        build_roadmap(specs_root=tmp_path)


def test_default_roadmap_falls_back_per_missing_canonical_roster(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unrelated directory in the operator specs root must not suppress the
    committed canonical roster manifest and collapse the atlas to zero."""
    (tmp_path / "unrelated-future-spec").mkdir()
    monkeypatch.setenv("ANTIEK_SPECS_ROOT", str(tmp_path))
    roadmap = build_roadmap()
    assert roadmap.total_sprints == 45
    assert {r.spec: r.count for r in roadmap.rosters} == {
        "drw": 10,
        "read": 9,
        "write": 9,
        "speak": 9,
        "unified": 8,
    }
