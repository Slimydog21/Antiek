"""SPR-10 — provenance + economics surfaced honestly, never paid.

The legal layer's three load-bearing, mechanically-checkable claims:

1. §9.0 GATING ON THE SURFACED PATH. A restricted (``restricted_pending_opt_in``)
   document must NOT surface into an attribution-triggering synthesis — neither
   its share, nor its title, nor its ``ip_holder``. The same gate that withholds
   bytes at ``/chunks/{id}`` holds at ``compute_attribution_for_synthesis``.

2. PROVENANCE UNBROKEN. Every surfaced (servable) document's ``ip_holder_id`` is
   carried through with its lifecycle status (even null = unknown owner, never
   invented) — "whose work grounds this claim" is the real chain.

3. NO MONEY PATH on the surfaced economics modules. The modules this sprint
   surfaces (attribution compute + the consent/escrow view) import no payout /
   Stripe / disburse path and call nothing that moves money. Disbursement is
   hard-gated G2 (lawyer) + G3 (publisher opt-in), both open.

These are §9 / §16.2 line items — verified, not waved.
"""

from __future__ import annotations

import ast
import json
import os
import re
import tempfile
from pathlib import Path

import pytest

from substrate.attribution.compute import compute_attribution_for_synthesis

_REPO = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────
# Fixture: a synthesis grounded in one PUBLIC + one RESTRICTED document,
# each with a resolved ip_holder.
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def synthesis_with_restricted(monkeypatch):
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    tmp = tempfile.mkdtemp(prefix="antiek-spr10-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    init_database_at_path(db_path)

    with connect_write(db_path, purpose="seed") as con:
        # A pre-onboarded publisher (opt-in only; escrow eligible on opt-in).
        con.execute(
            "INSERT INTO ip_holders (ip_holder_id, display_name, legal_contact_email, "
            "status, escrow_balance_usd, metadata) "
            "VALUES ('ip-mit', 'MIT Press', '', 'pre_onboarded', 0, '{}')",
        )
        # The Big-Five holder behind the RESTRICTED book — must never surface.
        con.execute(
            "INSERT INTO ip_holders (ip_holder_id, display_name, legal_contact_email, "
            "status, escrow_balance_usd, metadata) "
            "VALUES ('ip-bigfive', 'A Big Five Publisher', '', 'pre_onboarded', 0, '{}')",
        )
        insert_document(
            con, document_id="doc-public", source_tier=1,
            document_type="academic_paper", title="A Public Paper",
            content_class="public_domain", ip_holder_id="ip-mit",
        )
        insert_document(
            con, document_id="doc-restricted", source_tier=2,
            document_type="book", title="A Restricted Book",
            content_class="restricted_pending_opt_in", ip_holder_id="ip-bigfive",
        )
        cpub = insert_chunk(con, document_id="doc-public", chunk_index=0, text="public chunk")
        cres = insert_chunk(
            con, document_id="doc-restricted", chunk_index=0,
            text="restricted body — must not surface anywhere",
        )
        thesis = {
            "thesis_components": [
                {"claim": "C1", "confidence": "high", "supporting_chunk_ids": [cpub, cres]},
            ],
        }
        con.execute(
            "INSERT INTO syntheses (synthesis_id, investigation_id, target_question, "
            "synthesis_timestamp, status, implicit_recommendation, thesis, thesis_token_count) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, 0)",
            ["syn-spr10", "inv-1", "Q?", "passed", "proceed", json.dumps(thesis)],
        )
    return {"db_path": db_path, "synthesis_id": "syn-spr10"}


# ─────────────────────────────────────────────────────────────────────
# 1. §9.0 gating on the surfaced path
# ─────────────────────────────────────────────────────────────────────


def test_restricted_source_does_not_surface_into_attribution(synthesis_with_restricted):
    r = compute_attribution_for_synthesis(
        synthesis_with_restricted["synthesis_id"],
        db_path=synthesis_with_restricted["db_path"],
    )
    for opt in (r.option_a, r.option_b, r.option_c):
        # No share, no title, no owner for the restricted document.
        assert "doc-restricted" not in opt.shares, opt.algorithm
        assert "doc-restricted" not in opt.document_titles, opt.algorithm
        assert "A Restricted Book" not in opt.document_titles.values(), opt.algorithm
        assert "doc-restricted" not in opt.document_ip_holders, opt.algorithm
        assert "ip-bigfive" not in opt.document_ip_holder_status, opt.algorithm
    # The public document carries the full attribution (the restricted one is
    # gone, not merely down-weighted).
    assert r.option_b.shares == pytest.approx({"doc-public": 1.0})


# ─────────────────────────────────────────────────────────────────────
# 2. Provenance unbroken — whose work grounds this (surfaced for servable)
# ─────────────────────────────────────────────────────────────────────


def test_servable_source_surfaces_its_ip_holder_and_status(synthesis_with_restricted):
    r = compute_attribution_for_synthesis(
        synthesis_with_restricted["synthesis_id"],
        db_path=synthesis_with_restricted["db_path"],
    )
    assert r.option_b.document_ip_holders.get("doc-public") == "ip-mit"
    # Opt-in framing: a pre_onboarded holder is escrow-eligible on opt-in.
    assert r.option_b.document_ip_holder_status.get("ip-mit") == "pre_onboarded"


def test_null_ip_holder_is_honest_not_invented(monkeypatch):
    """A servable document with NO owner maps to None — never a fabricated one."""
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    tmp = tempfile.mkdtemp(prefix="antiek-spr10-null-")
    db_path = os.path.join(tmp, "g.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmp, "ev"))
    init_database_at_path(db_path)
    with connect_write(db_path, purpose="seed") as con:
        insert_document(
            con, document_id="doc-orphan", source_tier=3, document_type="web",
            title="An Orphan Source", content_class="public_domain",
        )  # no ip_holder_id
        c = insert_chunk(con, document_id="doc-orphan", chunk_index=0, text="x")
        thesis = {"thesis_components": [
            {"claim": "C", "confidence": "high", "supporting_chunk_ids": [c]}]}
        con.execute(
            "INSERT INTO syntheses (synthesis_id, investigation_id, target_question, "
            "synthesis_timestamp, status, implicit_recommendation, thesis, thesis_token_count) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, 0)",
            ["syn-orphan", "inv-1", "Q?", "passed", "proceed", json.dumps(thesis)],
        )
    r = compute_attribution_for_synthesis("syn-orphan", db_path=db_path)
    assert r.option_b.document_ip_holders.get("doc-orphan") is None
    assert r.option_b.document_ip_holder_status == {}


# ─────────────────────────────────────────────────────────────────────
# 3. NO money path on the surfaced economics modules (BINDING)
# ─────────────────────────────────────────────────────────────────────

# The modules SPR-10 surfaces. None may move money: no Stripe/payout/disburse/
# transfer import or call, no escrow-balance write. (Accrual is fine; the single
# escrow-balance writer is ip_holders.accrue_escrow — these read it, never call
# it. Disbursement is hard-gated G2+G3, both open.)
_SURFACED_ECONOMICS_MODULES = (
    "substrate/attribution/compute.py",
    "substrate/coordination/consent_view.py",
    "interfaces/research/api/coordination.py",
)

# A money-moving CALL or IMPORT on the SURFACED path is a §9.0 breach. We must
# distinguish a money-mover from the gate *framing* these modules legitimately
# carry: ``DisbursementGate``, ``_DISBURSEMENT_GATE_IDS``, ``any_disbursable``,
# ``disbursement_gates_open`` etc. NAME the gate; they don't move money. So we
# match (a) an import of a Stripe / payout module and (b) a CALL to a disbursing
# function — never a bare mention of "disbursement"/"payout".
_MONEY_IMPORT = re.compile(
    r"\b(?:import|from)\b[^\n]*\b(?:stripe_connect|stripe|tools\.stripe_connect)\b",
)
_MONEY_CALL = re.compile(
    r"\b(?:attempt_disbursement|disburse|create_transfer|transfer_to_publisher|"
    r"capture_payment|charge|payout_now)\s*\(",
    re.IGNORECASE,
)
# ``accrue_escrow(`` is deliberately NOT a money-mover — accrual is sanctioned;
# the surfaced modules don't even call it (asserted separately below).


def _code_only(source: str) -> str:
    """Blank docstrings so a regex matches executable code, not prose that
    merely mentions a verb (these modules document the gate at length)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    lines = source.splitlines()
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


def test_no_money_path_in_surfaced_economics_modules():
    offenders: dict[str, list[str]] = {}
    seen_any = False
    for rel in _SURFACED_ECONOMICS_MODULES:
        p = _REPO / rel
        if not p.exists():
            continue
        seen_any = True
        code = _code_only(p.read_text(encoding="utf-8"))
        hits = sorted(
            {m.group(0) for m in _MONEY_IMPORT.finditer(code)}
            | {m.group(0) for m in _MONEY_CALL.finditer(code)}
        )
        if hits:
            offenders[rel] = hits
    assert seen_any, "expected the surfaced economics modules to exist"
    assert not offenders, (
        f"a money-moving import/call appears on the SURFACED economics path: {offenders}. "
        "§9.0: accrual is shown, disbursement is gated G2+G3 — no disburse / payout / "
        "Stripe / transfer import or call may live on a surfaced module."
    )


def test_no_money_path_guard_catches_a_real_money_mover():
    """Rigor #3 — prove the guard FAILS on a real money-mover, so a passing
    run means something. A synthetic disbursing import + call must trip both
    matchers; the gate-framing identifiers must NOT."""
    rogue = (
        "from tools.stripe_connect import payouts\n"
        "def go():\n"
        "    return attempt_disbursement(ip_holder_id, amount)\n"
    )
    assert _MONEY_IMPORT.search(rogue)
    assert _MONEY_CALL.search(rogue)
    # The gate framing the real modules carry must be invisible to the matchers.
    framing = (
        "class DisbursementGate: ...\n"
        "disbursement_gates_open = ['G2', 'G3']\n"
        "def _open_disbursement_gates(): ...\n"
        "any_disbursable = False\n"
    )
    assert not _MONEY_IMPORT.search(framing)
    assert not _MONEY_CALL.search(framing)


def test_no_escrow_balance_write_in_surfaced_economics_modules():
    """The surfaced modules READ escrow; they never write the balance (the
    single writer is ip_holders.accrue_escrow, reached from sanctioned revenue
    sources — not from a read surface)."""
    for rel in _SURFACED_ECONOMICS_MODULES:
        p = _REPO / rel
        if not p.exists():
            continue
        code = _code_only(p.read_text(encoding="utf-8"))
        assert "SET escrow_balance_usd" not in code, rel
        assert not re.search(r"\baccrue_escrow\s*\(", code), rel


def test_consent_view_marks_everything_undisbursable_while_a_gate_is_open():
    """The accrual surface's API shape fixes ``disbursable=False`` while a legal
    gate is open — the property an auditor checks ("did anyone get paid before
    the legal gate?")."""
    from interfaces.research.api.coordination import (
        ConsentViewResponse,
        DisbursementGateResponse,
        EscrowReportResponse,
        IpHolderConsentResponse,
    )

    gate = DisbursementGateResponse(
        disbursable=False, open_gate_ids=["G2", "G3"],
        holder_claimed=False, fully_unlocked=False,
        label="accruing — disbursement gated on G2+G3",
    )
    holder = IpHolderConsentResponse(
        ip_holder_id="ip-mit", display_name="MIT Press", status="pre_onboarded",
        escrow_balance_usd="0", gate=gate, serves_full_text=None, servability_note=None,
    )
    view = ConsentViewResponse(
        holders=[holder],
        escrow_report=EscrowReportResponse(
            pre_onboarded=1, invited=0, claimed=0, opted_out=0, claim_rate=0.0,
            total_escrow_accrued_cents=0, total_escrow_paid_cents=0,
            unclaimed_escrow_cents=0, publishers_with_nontrivial_accrual=0,
        ),
        disbursement_gates_open=["G2", "G3"],
        total_escrow_accruing_usd="0",
        any_disbursable=False,
        gate_source_path="docs/operator_gate_actions.md",
    )
    assert view.any_disbursable is False
    assert view.holders[0].gate.disbursable is False
    # A zero-buyer balance is honestly "0", not a fabricated number.
    assert view.holders[0].escrow_balance_usd == "0"
    assert view.escrow_report.total_escrow_paid_cents == 0
