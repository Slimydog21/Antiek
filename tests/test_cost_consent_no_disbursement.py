"""SPR-07 — the load-bearing guard suite for the unified cost + consent surface.

This file proves the invariants the spec calls its most dangerous to violate:

* **No disbursement path** (M5, rigor #5 / defensibility) — the cost/consent
  modules + their HTTP endpoints + the frontend mode/stories contain NO import
  of the payout module and NO escrow-mutation call. Greppable + structural: an
  auditor confirms "this surface cannot pay anyone" by the proven absence of a
  payout path, not by reading every handler.

* **Aggregate = sum of parts** (M1, rigor #3) — the cost view's aggregate raw
  cost equals the sum of the per-workflow raw costs exactly over a fixture event
  log; remote-exec (SPR-02) cost is included, not dropped.

* **Zero-buyer = $0** (M3, honesty #1) — a zero-buyer fixture (holders with no
  accrual) shows ``$0`` accruing, never a fabricated balance; and an idle event
  log shows ``$0`` aggregate cost.

* **Gate labels from the SPR-05 ledger** (M3) — escrow balances are labeled with
  their disbursement gate read from the gate ledger; toggling G2/G3 in a ledger
  fixture flips the labels; nothing is disbursable while a legal gate is open.

* **Honest stubs** (rigor #1) — where the economics matrix isn't applicable, the
  margin is stubbed (``margin_status == 'stubbed'``, ``margined_cost_usd is
  None``), not fabricated.

All tests are pure/fixture-driven — no live external calls, no real Stripe, no
network. The cost view reads a fixture events dir; the consent view reads an
in-memory DuckDB.
"""

from __future__ import annotations

import ast
import re
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from substrate.coordination.cost_view import (
    MarginStatus,
    Workflow,
    build_cost_view,
    workflow_for_role,
)
from substrate.coordination.consent_view import build_consent_view
from substrate.coordination.gate_ledger import parse_gate_ledger
from substrate.event_log.events import emit_typed
from substrate.graph.schema import ANTIEK_GRAPH_SCHEMA_V2_SPRINT18_SQL
from substrate.ip_holders import accrue_escrow, create_pre_onboarded
from substrate.schemas.events import DispatchCallPayload


_REPO = Path(__file__).resolve().parents[1]


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _ip_holders_ddl() -> str:
    """Just the ip_holders CREATE TABLE (the full schema pulls graph deps we
    don't need for this read-only view test). Extracted from the canonical
    Sprint-18 schema SQL so the fixture table matches production exactly."""
    sql = ANTIEK_GRAPH_SCHEMA_V2_SPRINT18_SQL
    m = re.search(r"CREATE TABLE IF NOT EXISTS ip_holders \(.*?\);", sql, re.DOTALL)
    assert m, "ip_holders DDL not found — schema drifted"
    return m.group(0)


@pytest.fixture()
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    c.execute(_ip_holders_ddl())
    return c


@pytest.fixture()
def events_dir(tmp_path: Path) -> str:
    """A fixture events dir with a known DispatchCall event log. We emit:
      - research: 2 calls, $0.10 + $0.20
      - read:     1 call,  $0.05  (note_taker → Read)
      - speak:    1 call,  $0.40  (interviewer → Speak)
      - remote:   1 research call via provider 'daytona', $0.15 (SPR-02)
      - unmapped: 1 call with an unknown role, $0.07 (must still be counted)
    Aggregate raw = 0.10+0.20+0.05+0.40+0.15+0.07 = 0.97. Remote slice = 0.15.
    """
    d = str(tmp_path / "events")

    def emit(iid: str, role: str, cost: float, provider: str = "anthropic") -> None:
        emit_typed(
            iid,
            DispatchCallPayload(
                provider=provider,
                model="m",
                tier="pro",
                target_role=role,
                input_tokens=10,
                output_tokens=20,
                cost_usd=cost,
                latency_ms=100,
                prompt_hash="h",
            ),
            role=role,
            events_dir=d,
        )

    emit("inv-1", "decomposer", 0.10)
    emit("inv-1", "synthesizer", 0.20)
    emit("inv-2", "note_taker", 0.05)
    emit("inv-2", "interviewer", 0.40)
    emit("inv-3", "user_agent", 0.15, provider="daytona")  # remote-exec leaf
    emit("inv-3", "totally_unknown_role", 0.07)            # unmapped, still counted
    return d


# ── M1 / rigor #3 — aggregate = sum of parts, remote-exec included ───────────

def test_aggregate_equals_sum_of_per_workflow(events_dir: str) -> None:
    cv = build_cost_view(events_dir=events_dir)
    summed = sum((w.raw_cost_usd for w in cv.per_workflow), Decimal("0"))
    assert cv.aggregate_raw_cost_usd == summed, (
        "aggregate must equal the sum of per-workflow raw cost — no double "
        "count, no dropped workflow"
    )
    assert cv.aggregate_raw_cost_usd == Decimal("0.97")


def test_remote_exec_cost_is_included(events_dir: str) -> None:
    cv = build_cost_view(events_dir=events_dir)
    # The daytona leaf ($0.15) is a research call → counted in research raw AND
    # in the remote-exec slice. A surface that missed remote-exec would
    # understate spend on the one feature most likely to run away.
    assert cv.aggregate_remote_exec_cost_usd == Decimal("0.15")
    research = cv.workflow(Workflow.RESEARCH)
    # research raw = decomposer .10 + synthesizer .20 + user_agent(daytona) .15
    assert research.raw_cost_usd == Decimal("0.45")
    assert research.remote_exec_cost_usd == Decimal("0.15")


def test_unmapped_role_is_counted_not_dropped(events_dir: str) -> None:
    cv = build_cost_view(events_dir=events_dir)
    unmapped = cv.workflow(Workflow.UNMAPPED)
    assert unmapped.raw_cost_usd == Decimal("0.07")
    assert cv.has_unmapped_spend() is True
    # And it is still in the aggregate (the no-drift property).
    assert cv.aggregate_raw_cost_usd == Decimal("0.97")


def test_role_to_workflow_mapping_matches_taxonomy() -> None:
    assert workflow_for_role("synthesizer") is Workflow.RESEARCH
    assert workflow_for_role("note_taker") is Workflow.READ
    assert workflow_for_role("interviewer") is Workflow.SPEAK
    assert workflow_for_role("nope") is Workflow.UNMAPPED
    assert workflow_for_role(None) is Workflow.UNMAPPED


# ── M3 / honesty #1 — idle is $0; margins are honestly stubbed ───────────────

def test_idle_event_log_shows_zero_cost(tmp_path: Path) -> None:
    """An idle instance emits no DispatchCall events ⇒ every figure is $0 — a
    real zero, not a fabricated baseline (idle posture is cost-proportional)."""
    cv = build_cost_view(events_dir=str(tmp_path / "empty"))
    assert cv.aggregate_raw_cost_usd == Decimal("0")
    assert cv.aggregate_call_count == 0
    for w in cv.per_workflow:
        assert w.raw_cost_usd == Decimal("0")
        assert w.call_count == 0


def test_margins_honestly_stubbed_where_matrix_not_applicable(events_dir: str) -> None:
    cv = build_cost_view(events_dir=events_dir)
    # Speak's matrix is per-project — a single margined total can't be picked
    # without a project context, so it is STUBBED (no fabricated number).
    speak = cv.workflow(Workflow.SPEAK)
    assert speak.margin_status is MarginStatus.STUBBED
    assert speak.margined_cost_usd is None
    assert "10%" in speak.margin_note and "50%" in speak.margin_note
    # Read's ad-economics margin isn't built → stubbed.
    read = cv.workflow(Workflow.READ)
    assert read.margin_status is MarginStatus.STUBBED
    assert read.margined_cost_usd is None
    # Research carries no economics-matrix margin → APPLIED at 0% (raw == actual).
    research = cv.workflow(Workflow.RESEARCH)
    assert research.margin_status is MarginStatus.APPLIED
    assert research.margined_cost_usd == research.raw_cost_usd


# ── Gate ledger fixtures (toggle G2/G3) ──────────────────────────────────────

def _ledger_md(*, g2_closed: bool, g3_closed: bool) -> str:
    g2 = "✅ CLOSED 2026-06-01" if g2_closed else "❌ OPEN"
    g3 = "✅ CLOSED 2026-06-01" if g3_closed else "❌ OPEN"
    return f"""# Operator gate actions

## G2 — Lawyer review of publisher notification template
**Status:** {g2}
**Owner:** Operator + counsel
**Blocks:** All Stripe payouts

## G3 — At least one publisher affirmatively opted in
**Status:** {g3}
**Owner:** Operator (outreach) + publisher (decision)
**Blocks:** All Stripe payouts
"""


# ── M2 / M3 — escrow accrues, gated; zero-buyer = $0 ─────────────────────────

def test_zero_buyer_balance_is_honestly_zero(con: duckdb.DuckDBPyConnection) -> None:
    """A holder with no accrual shows $0 accruing — not a fabricated balance."""
    create_pre_onboarded(con, display_name="MIT Press")
    ledger = parse_gate_ledger(_ledger_md(g2_closed=False, g3_closed=False))
    cv = build_consent_view(con, gate_ledger=ledger)
    assert len(cv.holders) == 1
    h = cv.holders[0]
    assert h.escrow_balance_usd == Decimal("0")
    assert cv.total_escrow_accruing_usd == Decimal("0")
    assert cv.escrow_report.total_escrow_accrued_cents == 0
    # And nothing fictional was paid.
    assert cv.escrow_report.total_escrow_paid_cents == 0


def test_escrow_accrues_but_is_not_disbursable_while_gates_open(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Money accrues into escrow; with G2/G3 open it is labeled accruing-not-
    disbursing and NOTHING is disbursable — even for a claimed holder."""
    hid = create_pre_onboarded(con, display_name="Cambridge UP")
    accrue_escrow(con, hid, Decimal("12.34"))
    # Promote to claimed to prove even a claimed holder is not disbursable
    # while the legal gate is open.
    con.execute("UPDATE ip_holders SET status='claimed' WHERE ip_holder_id=?", [hid])

    ledger = parse_gate_ledger(_ledger_md(g2_closed=False, g3_closed=False))
    cv = build_consent_view(con, gate_ledger=ledger)
    h = cv.holders[0]
    assert h.escrow_balance_usd == Decimal("12.340000")
    assert h.gate.disbursable is False
    assert set(h.gate.open_gate_ids) == {"G2", "G3"}
    assert "G2+G3" in h.gate.label
    assert h.gate.holder_claimed is True
    assert h.gate.fully_unlocked is False           # legal gate still open
    assert cv.any_disbursable is False
    assert set(cv.disbursement_gates_open) == {"G2", "G3"}


def test_gate_labels_track_ledger_toggle(con: duckdb.DuckDBPyConnection) -> None:
    """Closing G2/G3 in the ledger fixture flips the labels — gate state is read
    from the SPR-05 ledger, never hardcoded or re-derived here."""
    hid = create_pre_onboarded(con, display_name="Princeton UP")
    accrue_escrow(con, hid, Decimal("5"))

    # Only G2 closed → G3 still gates.
    cv = build_consent_view(
        con, gate_ledger=parse_gate_ledger(_ledger_md(g2_closed=True, g3_closed=False))
    )
    assert cv.disbursement_gates_open == ("G3",)
    assert "G3" in cv.holders[0].gate.label and "G2" not in cv.holders[0].gate.label

    # Both closed but holder not claimed → still not disbursable (claim pending).
    cv2 = build_consent_view(
        con, gate_ledger=parse_gate_ledger(_ledger_md(g2_closed=True, g3_closed=True))
    )
    assert cv2.disbursement_gates_open == ()
    assert cv2.any_disbursable is False  # holder is pre_onboarded, not claimed
    assert "awaiting publisher claim" in cv2.holders[0].gate.label

    # Both closed AND claimed → eligible, but STILL not performed here (no path).
    con.execute("UPDATE ip_holders SET status='claimed' WHERE ip_holder_id=?", [hid])
    cv3 = build_consent_view(
        con, gate_ledger=parse_gate_ledger(_ledger_md(g2_closed=True, g3_closed=True))
    )
    assert cv3.holders[0].gate.fully_unlocked is True
    assert cv3.holders[0].gate.disbursable is False  # the surface never disburses
    assert "operator-only; not performed here" in cv3.holders[0].gate.label


def test_slop_does_not_earn(con: duckdb.DuckDBPyConnection) -> None:
    """A holder whose contribution was slop-gated accrues 0 (slop doesn't earn,
    ≤0.70 rubric). We model the resulting state — a holder with $0 balance — and
    assert it surfaces as an honest $0, not omitted."""
    create_pre_onboarded(con, display_name="Slop Co")   # no accrue_escrow call
    cv = build_consent_view(
        con, gate_ledger=parse_gate_ledger(_ledger_md(g2_closed=False, g3_closed=False))
    )
    assert cv.holders[0].escrow_balance_usd == Decimal("0")


# ── M5 / defensibility — NO disbursement path (greppable + structural) ───────

# The modules + surfaces that make up the cost/consent surface. None may import
# a payout module or call an escrow mutation.
_SURFACE_FILES: tuple[str, ...] = (
    "substrate/coordination/cost_view.py",
    "substrate/coordination/consent_view.py",
    "interfaces/research/api/coordination.py",
)

# Tokens that would indicate a disbursement / payout / escrow-mutation path.
# A maintainer adding any of these to the surface breaks this test. NOTE these
# are PAYOUT-ACTION symbols, matched as substrings of executable code — they are
# deliberately distinct from the legible nouns this surface DOES use to describe
# the gated reality (``disbursable`` / ``disbursement_gates_open`` /
# ``_disbursement_gate_for``), which are gate-labeling state, not a payout path.
_FORBIDDEN_PAYOUT_TOKENS: tuple[str, ...] = (
    "stripe_connect",            # the payout package path
    "payouts.py",                # tools/stripe_connect/payouts.py
    "route_impression_revenue",  # the disbursement function
    "RevSharePayoutRouter",
    "attempt_disbursement",      # the speak disbursement entry point
    "disburse(",                 # any call to a disburse* function
    "disburse_",                 # any disburse_<verb> helper call
    ".settle(",                  # Stripe settlement call
)

# Escrow-balance mutation: the single writer + any SQL that mutates the column.
_FORBIDDEN_ESCROW_MUTATION: tuple[str, ...] = (
    "accrue_escrow",                 # the single escrow-balance writer
    "SET escrow_balance_usd",        # the raw mutation
)


def _code_only(source: str) -> str:
    """Blank every docstring so the grep matches executable code, not prose
    (our docstrings legitimately *name* accrue_escrow / payouts to explain why
    they are absent). Mirrors the SPR-03 seam test's technique."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                doc = body[0]
                end = min(getattr(doc, "end_lineno", doc.lineno), len(lines))
                for i in range(doc.lineno - 1, end):
                    lines[i] = ""
    # Also blank trailing-comment text (a comment mentioning "payouts" in prose
    # is not a code path) by stripping everything after an unquoted '#'.
    cleaned: list[str] = []
    for ln in lines:
        # naive but sufficient: drop inline comments. String literals with '#'
        # are rare here and would only ever ADD a false positive we'd catch.
        hashpos = ln.find("#")
        cleaned.append(ln[:hashpos] if hashpos != -1 else ln)
    return "\n".join(cleaned)


@pytest.mark.parametrize("rel", _SURFACE_FILES)
def test_surface_has_no_payout_path(rel: str) -> None:
    """Greppable absence of any disbursement/payout path in the surface code."""
    src = _code_only((_REPO / rel).read_text(encoding="utf-8"))
    offenders = [tok for tok in _FORBIDDEN_PAYOUT_TOKENS if tok in src]
    assert not offenders, (
        f"{rel} contains a payout-shaped token {offenders} — the cost/consent "
        f"surface MUST NOT import or call any disbursement path. Disbursement is "
        f"operator-only after G2+G3; it does not live in this read-only surface."
    )


@pytest.mark.parametrize("rel", _SURFACE_FILES)
def test_surface_imports_no_payout_module(rel: str) -> None:
    """Structural (AST) check: no import statement in the surface references the
    stripe_connect / payouts module. Complements the substring grep — an import
    is the most direct way a payout path could enter, so we forbid it by AST."""
    tree = ast.parse((_REPO / rel).read_text(encoding="utf-8"))
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad += [a.name for a in node.names if "stripe_connect" in a.name or "payout" in a.name]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if "stripe_connect" in mod or "payout" in mod:
                bad.append(mod)
            bad += [a.name for a in node.names if "payout" in a.name.lower() or "disburse" in a.name.lower()]
    assert not bad, (
        f"{rel} imports a payout/disbursement symbol {bad} — forbidden in this "
        f"read-only surface."
    )


@pytest.mark.parametrize("rel", _SURFACE_FILES)
def test_surface_has_no_escrow_mutation(rel: str) -> None:
    """The surface reads escrow; it never writes it. No accrue_escrow call and
    no SET escrow_balance_usd anywhere in the executable code."""
    src = _code_only((_REPO / rel).read_text(encoding="utf-8"))
    offenders = [tok for tok in _FORBIDDEN_ESCROW_MUTATION if tok in src]
    assert not offenders, (
        f"{rel} contains an escrow-mutation token {offenders} — this surface is "
        f"read-only; the single escrow-balance writer is ip_holders.accrue_escrow, "
        f"reached only from the attribution pipeline, never from this view."
    )


def test_surface_has_no_mutating_http_verb() -> None:
    """The coordination API exposes only GET — no POST/PUT/PATCH/DELETE that
    could mutate escrow, a gate, or fire a payout."""
    src = _code_only(
        (_REPO / "interfaces/research/api/coordination.py").read_text(encoding="utf-8")
    )
    for verb in (".post(", ".put(", ".patch(", ".delete("):
        assert verb not in src, (
            f"coordination.py declares a {verb} route — the coordination surface "
            f"is GET-only; a mutating verb here could become a write path."
        )


def test_consent_view_does_not_import_payout_module() -> None:
    """Structural: import the consent_view module and assert the payout module
    is not in its dependency closure via a direct import. (Greppable test above
    covers source; this asserts the import graph at the module level.)"""
    import substrate.coordination.consent_view as cv_mod

    src = _code_only(Path(cv_mod.__file__).read_text(encoding="utf-8"))
    # No `import tools.stripe_connect` / `from tools.stripe_connect`.
    assert "tools.stripe_connect" not in src
    assert "from tools" not in src or "stripe_connect" not in src


# ── Frontend surface — no payout path in the mode/stories (defensibility) ────

_FRONTEND_SURFACE_FILES: tuple[str, ...] = (
    "apps/reading/src/modes/Coordination/CostConsent.tsx",
    "apps/reading/src/modes/Coordination/CostConsent.stories.tsx",
)


@pytest.mark.parametrize("rel", _FRONTEND_SURFACE_FILES)
def test_frontend_surface_has_no_payout_path(rel: str) -> None:
    """The CostConsent mode + its stories must not call a payout/disbursement
    endpoint or render a 'disburse' control. Greppable on the TSX source."""
    p = _REPO / rel
    if not p.exists():
        pytest.skip(f"{rel} not present yet")
    text = p.read_text(encoding="utf-8")
    # Strip JS/TS comments so prose explaining the absence doesn't trip the grep.
    text_no_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text_no_line = re.sub(r"//[^\n]*", "", text_no_block)
    # PAYOUT-ACTION patterns — a fetch to a payout endpoint or a disburse call.
    # Deliberately distinct from the gated-reality LABELS the surface must show
    # (``disbursable`` / "disbursement gated on" / ``DisbursementGateView``),
    # which are read-only state, not a payout path.
    forbidden = [
        "/payouts",                       # the Stripe transfer-log endpoint
        "creator-payouts",                # the per-recipient payout endpoint
        "/coordination/disburse",         # a hypothetical disburse route
        "disburse(",                      # a call to a disburse* function
        "POST",                           # the mode is GET-only
        "method: \"post\"",               # any mutating fetch
    ]
    offenders = [tok for tok in forbidden if tok in text_no_line]
    assert not offenders, (
        f"{rel} references a payout/disbursement/mutating path {offenders} — the "
        f"CostConsent surface is read-only and must not disburse."
    )
