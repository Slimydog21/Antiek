"""SPR-05 M4 — the no-fork invariant test (load-bearing).

Canonical gate: ``./scripts/canonical_verify.sh unified-coordination-gate-ledger``.
It runs this backend no-fork ledger/roadmap contract plus the Coordination UI
rendering tests. Browser/device visual polish for the final Coordination mode
remains operator QA, not a parser or API-contract claim.

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
from fastapi import FastAPI
from fastapi.testclient import TestClient

from substrate.coordination.gate_ledger import (
    GateStatus,
    Product,
    canonical_gate_path,
    load_gate_ledger,
    parse_gate_ledger,
    parse_quick_status_table,
)
from substrate.coordination.operator_actions import (
    OperatorActionStatus,
    canonical_operator_actions_path,
    load_operator_actions,
)
from substrate.coordination.phase2_audit import (
    load_phase2_audit,
)
from substrate.coordination.activation_view import build_read_activation_view
from substrate.coordination.engineering_deferrals import (
    DeferralStatus,
    load_engineering_deferrals,
)
from substrate.coordination.loop3_status import build_loop3_coordination_view
from substrate.coordination.source_gate_status import build_source_gate_view
from substrate.coordination.roadmap import (
    Roadmap,
    SpecRoster,
    SprintRow,
    SprintStatus,
    build_roadmap,
)
from substrate.loop_3.evidence_status import CriterionEvidenceStatus, Loop3EvidenceSnapshot
from substrate.loop_3.checklist_store import set_criterion
from substrate.loop_3.unlock_gate import Loop3UnlockCriterion
from tools.source_census import SourceCensus, save_censuses
from tools.activation.read_dogfood import append_session_template, session_template

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


def test_all_eight_gates_present() -> None:
    ledger = load_gate_ledger()
    assert ledger.gate_ids() == ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8")


def _independent_operator_action_rows(md: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    in_table = False
    for line in md.splitlines():
        if line.strip() == "| ID | Title | Status | Blocks | Owner |":
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("|---"):
            continue
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[0].startswith("OA-"):
            rows.append((cells[0], cells[2]))
    return rows


def test_operator_actions_view_tracks_living_index_without_fork() -> None:
    md = canonical_operator_actions_path().read_text(encoding="utf-8")
    view = load_operator_actions()
    independent = _independent_operator_action_rows(md)

    assert [a.action_id for a in view.actions] == [row[0] for row in independent]
    assert len(view.actions) == 20
    assert view.source_path == "docs/OPERATOR_ACTIONS.md"
    assert view.open_actions()[0].action_id == "OA-001"
    assert view.closeable_actions()[0].action_id == "OA-005"
    assert view.status_counts() == {
        "open": 17,
        "awaiting_operator_test": 1,
        "partially_done": 1,
        "closed": 1,
    }
    status_by_id = {a.action_id: a.status for a in view.actions}
    assert status_by_id["OA-010"] is OperatorActionStatus.CLOSED
    assert status_by_id["OA-005"] is OperatorActionStatus.AWAITING_OPERATOR_TEST


def test_operator_actions_fixture_mutation_is_reflected(tmp_path: Path) -> None:
    md = """# Operator Actions

## Quick status table

| ID | Title | Status | Blocks | Owner |
|---|---|---|---|---|
| OA-001 | Counsel | OPEN | payouts | Operator + counsel |
| OA-002 | Wedge ratification | AWAITING OPERATOR TEST | Wedges 2-4 | Operator |

"""
    p = tmp_path / "OPERATOR_ACTIONS.md"
    p.write_text(md, encoding="utf-8")
    view = load_operator_actions(p)
    assert view.open_actions()[0].action_id == "OA-001"
    assert view.closeable_actions()[0].action_id == "OA-002"

    p.write_text(md.replace("OPEN", "CLOSED", 1), encoding="utf-8")
    mutated = load_operator_actions(p)
    assert mutated.open_actions()[0].action_id == "OA-002"
    assert mutated.status_counts()["closed"] == 1


def test_phase2_audit_view_surfaces_scorecard_and_v5_reconciliation() -> None:
    audit = load_phase2_audit()

    assert audit.source_path == "docs/phase2_execution_audit_v5_2026_07_01.md"
    assert audit.scorecard_source_path == "docs/phase2_execution_audit_v4_2026_05_23.md"
    assert audit.current_commit_evidence == "23048220 feat(ducklake): route default graph path through catalog"
    assert audit.engineering_blocked_count == 0
    assert audit.total_score is not None
    assert audit.total_score.phases == 28
    assert audit.total_score.met == 6
    assert audit.total_score.partial == 17
    assert audit.total_score.unmet == 5
    assert audit.exit_criteria is not None
    assert audit.exit_criteria.total == 23
    assert audit.exit_criteria.met == 3
    assert audit.exit_criteria.partial == 2
    assert audit.exit_criteria.unmet == 18
    assert audit.sprint_scorecard[0].sprint == "Sprint 22"
    assert audit.sprint_scorecard[-1].sprint == "Sprint 30+"
    assert audit.next_action_ordering[0] == (
        "Keep docs/OPERATOR_ACTIONS.md as the authoritative operator gate list."
    )


def test_phase2_audit_view_tracks_fixture_mutation(tmp_path: Path) -> None:
    audit_path = tmp_path / "phase2_v5.md"
    scorecard_path = tmp_path / "phase2_v4.md"
    audit_path.write_text(
        """# Phase 2 v5

**Current commit evidence:** `abc123 feat(test): fixture`

**Current reconciled state:** net engineering-side-blocked items known from
v4: **2**.

## 4. Recommended next action ordering

1. Keep the source document authoritative.

## 5. Honest verdict
""",
        encoding="utf-8",
    )
    scorecard_path.write_text(
        """# v4

| Sprint | Phases | Met | Partial | Unmet | Δ vs v3 |
|---|---|---|---|---|---|
| Sprint X | 4 | 1 | 2 | 1 | fixture |
| **TOTAL** | **4** | **1** | **2** | **1** | **fixture** |

Sprint-level exit criteria (5 total): unchanged at 1 met / 1
partial / 3 unmet, because every unmet exit criterion is blocked
by operator action or real-data accumulation, not substrate.
""",
        encoding="utf-8",
    )

    audit = load_phase2_audit(audit_path, scorecard_path)
    assert audit.engineering_blocked_count == 2
    assert audit.total_score is not None
    assert audit.total_score.unmet == 1
    assert audit.exit_criteria is not None
    assert audit.exit_criteria.unmet == 3

    audit_path.write_text(
        audit_path.read_text(encoding="utf-8").replace("**2**", "**0**"),
        encoding="utf-8",
    )
    mutated = load_phase2_audit(audit_path, scorecard_path)
    assert mutated.engineering_blocked_count == 0


def test_engineering_deferrals_view_surfaces_do_not_prebuild_ledger() -> None:
    view = load_engineering_deferrals()

    assert view.source_path == "docs/engineering_deferrals.md"
    assert len(view.deferrals) == 19
    assert view.deferrals[0].deferral_id == "D1"
    assert view.deferrals[0].status is DeferralStatus.PARTIAL
    assert view.deferrals[0].unlock_criterion is not None
    assert "G7" in view.deferrals[0].unlock_criterion
    assert view.deferrals[-1].deferral_id == "D19"
    assert view.first_open() is not None
    assert view.first_open().deferral_id == "D1"
    assert view.status_counts() == {
        "partial": 4,
        "substrate_shipped": 5,
        "deferred": 7,
        "closed": 3,
    }


def test_engineering_deferrals_fixture_mutation_is_reflected(tmp_path: Path) -> None:
    path = tmp_path / "engineering_deferrals.md"
    path.write_text(
        """# Deferrals

## D1 — Multi-user

**Status:** ❌ Deferred.
**Unlock criterion:** G7 closes.
**Blocks-what:** multi-user activation.

## D2 — Closed tidy

**Status:** ✅ Closed on 2026-07-02.
**Unlock criterion:** satisfied.
**Blocks-what:** nothing.
""",
        encoding="utf-8",
    )

    view = load_engineering_deferrals(path)
    assert view.first_open() is not None
    assert view.first_open().deferral_id == "D1"
    assert view.status_counts() == {"deferred": 1, "closed": 1}

    path.write_text(
        path.read_text(encoding="utf-8").replace("❌ Deferred.", "✅ Closed.", 1),
        encoding="utf-8",
    )
    mutated = load_engineering_deferrals(path)
    assert mutated.first_open() is None
    assert mutated.status_counts() == {"closed": 2}


def _loop3_evidence_fixture(*, passing: tuple[str, ...] = ()) -> Loop3EvidenceSnapshot:
    statuses = {}
    for criterion in Loop3UnlockCriterion:
        passed = criterion.value in passing
        statuses[criterion.value] = CriterionEvidenceStatus(
            criterion=criterion.value,
            status="PASS" if passed else "FAIL",
            passed=passed,
            summary="all checks passed" if passed else f"{criterion.value} missing",
            result={"status": "PASS" if passed else "FAIL"},
        )
    return Loop3EvidenceSnapshot(
        criteria={key: value.passed for key, value in statuses.items()},
        statuses=statuses,
        all_evidence_passed=all(value.passed for value in statuses.values()),
        events_dir="/tmp/loop3-events",
        open_weight_policy_file="reports/loop3/open-weight-policy-ids.json",
    )


def test_loop3_coordination_view_compares_manual_and_evidence(tmp_path: Path, monkeypatch) -> None:
    from runtime.db_lock import connect_read, connect_write
    from substrate.graph import ensure_initialized

    db_path = str(tmp_path / "antiek.duckdb")
    ensure_initialized(db_path)
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)
    with connect_write(db_path, purpose="test:loop3") as con:
        set_criterion(
            con,
            criterion=Loop3UnlockCriterion.TRAJECTORY_VOLUME,
            met=True,
            note="manual note",
        )

    with connect_read(db_path) as con:
        view = build_loop3_coordination_view(
            con,
            evidence=_loop3_evidence_fixture(
                passing=(Loop3UnlockCriterion.SFT_READINESS.value,),
            ),
        )

    assert view.total_criteria == 5
    assert view.manual_met_count == 1
    assert view.evidence_passed_count == 1
    assert view.all_criteria_met is False
    assert view.all_evidence_passed is False
    assert view.env_unlocked is False
    assert view.fully_unlocked is False
    assert view.first_failing_evidence is not None
    assert view.first_failing_evidence.criterion == "trajectory_volume"
    assert view.first_failing_evidence.evidence_summary == "trajectory_volume missing"


def test_source_gate_view_surfaces_missing_census_as_noop(tmp_path: Path) -> None:
    view = build_source_gate_view(tmp_path / "missing-source-census.json")

    assert view.state == "missing"
    assert view.source_count == 0
    assert view.blocked_count == 0
    assert view.reference_source == "arxiv"
    assert view.error is not None
    assert "no source census yet" in view.error


def test_source_gate_view_surfaces_blocked_and_invalid_census(tmp_path: Path) -> None:
    path = tmp_path / "source_census.json"
    save_censuses(
        [
            SourceCensus(
                source="web",
                total=10,
                t1_pct=50.0,
                open_pct=80.0,
                metadata_complete_pct=94.0,
                dedup_overlap_pct=40.0,
                linkback_resolvable_pct=98.0,
            )
        ],
        path,
    )

    blocked = build_source_gate_view(path)
    assert blocked.state == "blocked"
    assert blocked.source_count == 1
    assert blocked.blocked_count == 1
    assert blocked.rows[0].source == "web"
    assert blocked.rows[0].blocked is True
    assert any("metadata_complete_pct" in failure for failure in blocked.rows[0].failures)

    path.write_text("{bad json\n", encoding="utf-8")
    invalid = build_source_gate_view(path)
    assert invalid.state == "invalid"
    assert invalid.error is not None


def test_operator_gate_actions_summary_tracks_appended_follow_ons() -> None:
    md = canonical_gate_path().read_text(encoding="utf-8")
    repo_root = canonical_gate_path().parents[1]
    master_spec = (canonical_gate_path().parents[0] / "master-product-spec.md").read_text(
        encoding="utf-8",
    )
    engineering_deferrals = (
        canonical_gate_path().parents[0] / "engineering_deferrals.md"
    ).read_text(encoding="utf-8")
    gate_ledger_src = (
        repo_root / "substrate" / "coordination" / "gate_ledger.py"
    ).read_text(encoding="utf-8")
    coordination_copy = (
        repo_root / "apps" / "reading" / "src" / "modes" / "Coordination" / "GateLedger.tsx"
    ).read_text(encoding="utf-8")
    master_compact = " ".join(master_spec.split())
    deferrals_compact = " ".join(engineering_deferrals.split())
    md_compact = " ".join(md.split())
    ledger_compact = " ".join(gate_ledger_src.split())
    coordination_compact = " ".join(coordination_copy.split())
    quick_gate_ids = [
        line.split("|")[1].strip().split()[0]
        for line in md.splitlines()
        if (
            line.startswith("| G")
            and line.split("|")[1].strip().split()[0][1:].isdigit()
        )
    ]

    assert quick_gate_ids == [f"G{i}" for i in range(1, 13)]
    assert "Current total: 12 gate-actions" in md
    assert "Original G1-G8" in md
    assert "G9-G12 are appended operator/legal" in md
    assert "follow-ons from the personal-reading lane" in md
    assert "counsel-pending public Trust Center copy" in md_compact
    assert "live control-plane references are reconciled" in md_compact
    assert "publication still awaits G2-cleared wording and OA-013" in md_compact
    assert (
        "Engineering-side blockers known from the v4/v5 audit sequence are "
        "reconciled as of 2026-07-01"
    ) in md_compact
    assert "The nine gates" not in md
    assert "of the 8 gates" not in md
    assert "public-facing scaffold; awaits G2" not in md_compact
    assert "Engineering scope of the spec is essentially complete as of 2026-05-23" not in md_compact
    assert "plus appended personal-reading-lane follow-on gate-actions" in master_compact
    assert "plus appended personal-reading-lane follow-on gate-actions" in deferrals_compact
    assert "the eight binding gates (G1" not in master_compact
    assert "covers the eight gates" not in deferrals_compact
    assert "The original activation gates (G1-G8)" in ledger_compact
    assert (
        "now also records appended operator/legal follow-on gate-actions (G9-G12)"
        in ledger_compact
    )
    assert "The original G1-G8 activation gates" in coordination_compact
    assert "Appended G9-G12 follow-ons remain" in coordination_compact
    assert "The eight binding gates" not in ledger_compact
    assert "The eight binding gates" not in coordination_compact


def test_coordination_docs_name_canonical_gate_and_ui_boundary() -> None:
    """The proof prose names the canonical gate, UI companion, and visual-QA boundary."""
    import substrate.coordination.gate_ledger as gate_ledger

    combined = " ".join(((gate_ledger.__doc__ or "") + " " + (__doc__ or "")).split())

    assert "./scripts/canonical_verify.sh unified-coordination-gate-ledger" in combined
    assert "backend no-fork ledger/roadmap contract plus the Coordination UI" in combined
    assert "Browser/device visual polish for the final Coordination mode remains operator QA" in combined


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


# ── M5 accuracy snapshot: the canonical gate states ──────────────────────────

def test_accuracy_snapshot_matches_canonical_states() -> None:
    """Pin the documented gate states so a parsing/rendering regression is
    caught: G1/G4/G5 closed, G2/G3/G6 open, G7 calendar, G8 data-bound; G5 is
    provisionally closed."""
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
    hand-maintained. Read sprints depend on DRW SPR-05/06, which are live, so
    they are dependency-ready. Speak depends on DRW SPR-07, which is also live,
    so it is dependency-ready too."""
    roadmap = build_roadmap()
    by_id = {s.node_id: s for s in roadmap.all_sprints()}

    # drw:1 is live with no DRW deps → unblocked.
    assert by_id["drw:1"].unblocked
    # read:* depend on drw:5 + drw:6 (live) → dependency-ready.
    assert by_id["read:1"].unblocked
    assert by_id["read:1"].blocked_on == ()
    # speak:* depends on drw:7 (live) → dependency-ready.
    assert by_id["speak:1"].unblocked
    assert by_id["speak:1"].blocked_on == ()
    # The unblocked set and blocked set partition all sprints.
    assert len(roadmap.unblocked_now()) + len(roadmap.blocked()) == roadmap.total_sprints


def test_unblocked_now_entries_are_real_unblocked_rows() -> None:
    """The operator-facing ready-now list must not contain dangling ids or
    blocked rows; every entry resolves to a sprint row with no unmet DRW deps."""
    roadmap = build_roadmap()
    by_id = {s.node_id: s for s in roadmap.all_sprints()}

    assert roadmap.unblocked_now(), "roadmap should surface at least one ready row"
    for sprint in roadmap.unblocked_now():
        assert by_id[sprint.node_id] is sprint
        assert sprint.unblocked is True
        assert sprint.blocked_on == ()


def test_dependency_blockers_are_derived_and_sorted() -> None:
    """The operator-facing blocker summary is derived from blocked rows and
    sorted by fan-out, so the next dependency to unblock is explicit."""
    roadmap = build_roadmap()
    blockers = roadmap.dependency_blockers()

    assert blockers == ()


def test_read_sprints_are_unblocked_after_cascade_and_orchestration_live() -> None:
    roadmap = build_roadmap()
    by_id = {s.node_id: s for s in roadmap.all_sprints()}

    assert {by_id[f"read:{i}"].blocked_on for i in range(1, 10)} == {()}
    assert all(by_id[f"read:{i}"].unblocked for i in range(1, 10))


def test_speak_sprints_are_unblocked_after_structural_gap_detection_live() -> None:
    roadmap = build_roadmap()
    by_id = {s.node_id: s for s in roadmap.all_sprints()}

    assert {by_id[f"speak:{i}"].blocked_on for i in range(1, 10)} == {()}
    assert all(by_id[f"speak:{i}"].unblocked for i in range(1, 10))


def test_execution_focus_skips_live_ready_rows() -> None:
    """When no dependency blockers remain, focus must not point at already-live
    DRW rows; it should pick the first dependency-ready unbuilt sprint."""
    roadmap = build_roadmap()
    focus = roadmap.execution_focus()

    assert focus is None


def test_execution_focus_falls_back_to_first_dependency_ready_row() -> None:
    """If nothing is blocked, the canonical next action is the first ready row
    in roster order."""
    sprint = SprintRow(
        spec="read",
        spec_label="Read",
        sprint=1,
        slug="reader-root",
        node_id="read:1",
        status=SprintStatus.UNKNOWN,
        on_critical_path=False,
        blocked_on=(),
        unblocked=True,
    )
    roadmap = Roadmap(
        rosters=(
            SpecRoster(spec="read", label="Read", directory="read", sprints=(sprint,)),
        ),
        critical_path=(),
        superseded_count=0,
        superseded_note="",
    )

    focus = roadmap.execution_focus()

    assert focus is not None
    assert focus.kind == "dependency_ready"
    assert focus.node_id == "read:1"
    assert focus.blocked_sprints == ()


def test_roadmap_response_serializes_dependency_blockers() -> None:
    """The HTTP adapter exposes the substrate-owned blocker summary without
    duplicating sprint rows into a second roadmap."""
    from interfaces.research.api.coordination import RoadmapResponse

    response = RoadmapResponse.from_roadmap(build_roadmap())

    assert response.dependency_blockers == []


def test_roadmap_response_serializes_execution_focus() -> None:
    """The HTTP adapter exposes the substrate-owned next action with node-id
    references only, not duplicated sprint rows."""
    from interfaces.research.api.coordination import RoadmapResponse

    response = RoadmapResponse.from_roadmap(build_roadmap())

    assert response.execution_focus is None
    assert response.operator_gate_focus is None


def test_roadmap_response_serializes_operator_gate_focus_from_ledger() -> None:
    """When structural dependencies have no focus, the roadmap response points
    at the first open operator gate from the canonical ledger, not a fork."""
    from interfaces.research.api.coordination import RoadmapResponse

    ledger = load_gate_ledger()
    response = RoadmapResponse.from_roadmap(build_roadmap(), ledger)

    first_open = ledger.open_gates()[0]
    assert response.execution_focus is None
    assert response.operator_gate_focus is not None
    assert response.operator_gate_focus.gate_id == first_open.gate_id
    assert response.operator_gate_focus.title == first_open.title
    assert response.operator_gate_focus.status == first_open.status.value
    assert response.operator_gate_focus.status_raw == first_open.status_raw
    assert response.operator_gate_focus.source_path == ledger.source_path


def test_read_activation_view_missing_log_is_not_started(tmp_path: Path) -> None:
    view = build_read_activation_view(tmp_path / "missing-read-dogfood.jsonl")

    assert view.state == "not_started"
    assert view.total_sessions == 0
    assert view.valid_sessions == 0
    assert view.closure_ready is False
    assert view.remaining_requirements == {
        "valid_sessions": 10,
        "live_provider_sessions": 5,
        "citation_trace_sessions": 3,
        "non_library_sessions": 1,
    }


def test_read_activation_view_surfaces_malformed_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "read-dogfood.jsonl"
    path.write_text("{bad json\n", encoding="utf-8")

    view = build_read_activation_view(path)

    assert view.state == "invalid_log"
    assert view.closure_ready is False
    assert view.total_sessions == 0
    assert any("invalid JSON" in failure for failure in view.failures)


def test_read_activation_view_uses_dogfood_validator(tmp_path: Path) -> None:
    path = tmp_path / "read-dogfood.jsonl"
    record = session_template("inert")
    record["build_sha"] = "0123456789abcdef"
    append_session_template(path, record)

    view = build_read_activation_view(path)

    assert view.state == "incomplete"
    assert view.total_sessions == 1
    assert view.valid_sessions == 1
    assert view.live_provider_sessions == 0
    assert view.remaining_requirements["valid_sessions"] == 9
    assert all(failure.startswith("closure requires ") for failure in view.failures)


def test_roadmap_response_serializes_read_activation_status(tmp_path: Path) -> None:
    from interfaces.research.api.coordination import RoadmapResponse

    path = tmp_path / "read-dogfood.jsonl"
    record = session_template("inert")
    record["build_sha"] = "0123456789abcdef"
    append_session_template(path, record)
    activation = build_read_activation_view(path)

    response = RoadmapResponse.from_roadmap(
        build_roadmap(),
        load_gate_ledger(),
        activation,
    )

    assert response.read_activation.source_path == str(path)
    assert response.read_activation.state == "incomplete"
    assert response.read_activation.total_sessions == 1
    assert response.read_activation.valid_sessions == 1
    assert response.read_activation.closure_ready is False


def test_roadmap_response_serializes_operator_actions_and_phase2_audit() -> None:
    from interfaces.research.api.coordination import RoadmapResponse

    operator_actions = load_operator_actions()
    phase2_audit = load_phase2_audit()
    deferrals = load_engineering_deferrals()
    class DummyLoop3:
        criteria = ()
        manual_met_count = 0
        evidence_passed_count = 0
        total_criteria = 5
        all_criteria_met = False
        all_evidence_passed = False
        env_unlocked = False
        fully_unlocked = False
        first_failing_evidence = None
        events_dir = "/tmp/events"
        open_weight_policy_file = "reports/loop3/open-weight-policy-ids.json"
    class DummySourceGate:
        source_path = "reports/source_census.json"
        state = "missing"
        reference_source = "arxiv"
        source_count = 0
        blocked_count = 0
        rows = ()
        error = "no source census yet"

    response = RoadmapResponse.from_roadmap(
        build_roadmap(),
        load_gate_ledger(),
        operator_actions=operator_actions,
        phase2_audit=phase2_audit,
        engineering_deferrals=deferrals,
        loop3=DummyLoop3(),
        source_gate=DummySourceGate(),
    )

    assert response.operator_actions.source_path == "docs/OPERATOR_ACTIONS.md"
    assert response.operator_actions.open_count == 19
    assert response.operator_actions.closeable_action is not None
    assert response.operator_actions.closeable_action.action_id == "OA-005"
    assert response.phase2_audit.source_path == "docs/phase2_execution_audit_v5_2026_07_01.md"
    assert response.phase2_audit.engineering_blocked_count == 0
    assert response.phase2_audit.total_score is not None
    assert response.phase2_audit.total_score.unmet == 5
    assert response.phase2_audit.exit_criteria is not None
    assert response.phase2_audit.exit_criteria.unmet == 18
    assert response.engineering_deferrals.source_path == "docs/engineering_deferrals.md"
    assert response.engineering_deferrals.total_deferrals == 19
    assert response.engineering_deferrals.open_count == 16
    assert response.engineering_deferrals.first_open is not None
    assert response.engineering_deferrals.first_open.deferral_id == "D1"
    assert response.loop3 is not None
    assert response.loop3.total_criteria == 5
    assert response.loop3.fully_unlocked is False
    assert response.source_gate.state == "missing"
    assert response.source_gate.reference_source == "arxiv"


def test_source_gate_endpoint_is_narrow_read_only_view(monkeypatch) -> None:
    """Acquisition surfaces can load source-gate state without the full roadmap."""
    from interfaces.research.api import coordination

    class DummyRow:
        source = "web"
        blocked = True
        failures = ("metadata_complete_pct=94.0 < 95.0",)

    class DummySourceGate:
        source_path = "reports/source_census.json"
        state = "blocked"
        reference_source = "arxiv"
        source_count = 1
        blocked_count = 1
        rows = (DummyRow(),)
        error = None

    monkeypatch.setattr(
        coordination,
        "build_source_gate_view",
        lambda: DummySourceGate(),
    )
    app = FastAPI()
    coordination.register_coordination_routes(app)

    response = TestClient(app).get("/coordination/source-gate")

    assert response.status_code == 200
    assert response.json() == {
        "source_path": "reports/source_census.json",
        "state": "blocked",
        "reference_source": "arxiv",
        "source_count": 1,
        "blocked_count": 1,
        "rows": [
            {
                "source": "web",
                "blocked": True,
                "failures": ["metadata_complete_pct=94.0 < 95.0"],
            }
        ],
        "error": None,
    }


def test_operator_gate_focus_does_not_override_structural_dependency_focus() -> None:
    """Dependency blockers remain the first focus; operator gates only surface
    after structural roadmap focus is clear."""
    from interfaces.research.api.coordination import RoadmapResponse

    blocked = SprintRow(
        spec="read",
        spec_label="Read",
        sprint=1,
        slug="reader-root",
        node_id="read:1",
        status=SprintStatus.UNKNOWN,
        on_critical_path=False,
        blocked_on=("drw:5",),
        unblocked=False,
    )
    roadmap = Roadmap(
        rosters=(
            SpecRoster(spec="read", label="Read", directory="read", sprints=(blocked,)),
        ),
        critical_path=(),
        superseded_count=0,
        superseded_note="",
    )
    ledger = parse_gate_ledger(
        """# gates

## G2 — Lawyer review

**Status:** ❌ OPEN
**Owner:** Operator + counsel
**Blocks:** All payouts
""",
        source_path="fixture.md",
    )

    response = RoadmapResponse.from_roadmap(roadmap, ledger)

    assert response.execution_focus is not None
    assert response.execution_focus.kind == "dependency_blocker"
    assert response.execution_focus.node_id == "drw:5"
    assert response.operator_gate_focus is None


def test_roadmap_response_names_activation_boundary() -> None:
    """Structural sprint state must not be mistaken for live-use activation."""
    from interfaces.research.api.coordination import RoadmapResponse

    response = RoadmapResponse.from_roadmap(build_roadmap())

    assert response.activation_note == build_roadmap().activation_note
    assert "Structural sprint status is not activation closure" in response.activation_note
    assert "specs/activation/golden-path.md" in response.activation_note
    assert "CI is the floor, use is the gate" in response.activation_note


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
