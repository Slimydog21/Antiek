"""Tests for the continuous-chase orchestrator wiring (Sprint 12).

Strategy: exercise the chase decision helpers in isolation (depth
walk, cost accumulation, question selection, halt-vs-spawn logic).
End-to-end chase chains require Loop 1 to actually run, which means
real LLM dispatches; that's a smoke test the operator runs against
the production VM, not a substrate-test concern.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.schemas import (
    TYPED_PAYLOAD_ACTION_TYPES,
    ActionType,
    InvestigationChaseHaltedPayload,
    InvestigationStartRequestedPayload,
)


@pytest.fixture
def events_dir(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-chase-test-")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield events_dir


# ── Schema additions ─────────────────────────────────────────────────


def test_chase_halted_in_typed_set():
    assert ActionType.INVESTIGATION_CHASE_HALTED.value in TYPED_PAYLOAD_ACTION_TYPES


def test_chase_halted_payload_round_trip():
    p = InvestigationChaseHaltedPayload(
        reason="depth_reached",
        depth_reached=3,
        duration_seconds=0.0,
        cost_total_usd=1.234,
    )
    assert p.action_type == ActionType.INVESTIGATION_CHASE_HALTED
    assert p.reason == "depth_reached"
    assert p.depth_reached == 3
    assert p.cost_total_usd == 1.234


def test_chase_halted_payload_rejects_unknown_reason():
    with pytest.raises(Exception):
        InvestigationChaseHaltedPayload(reason="bogus")  # type: ignore[arg-type]


def test_start_payload_carries_chase_fields_default_off():
    p = InvestigationStartRequestedPayload(question="Q?")
    assert p.chase_mode == "off"
    assert p.chase_value == 0
    assert p.chase_budget_usd == 2.0


def test_start_payload_accepts_chase_depth():
    p = InvestigationStartRequestedPayload(
        question="Q?",
        chase_mode="depth",
        chase_value=5,
        chase_budget_usd=10.0,
    )
    assert p.chase_mode == "depth"
    assert p.chase_value == 5
    assert p.chase_budget_usd == 10.0


def test_start_payload_rejects_bad_mode():
    with pytest.raises(Exception):
        InvestigationStartRequestedPayload(
            question="Q?", chase_mode="forever",  # type: ignore[arg-type]
        )


# ── Walk-chain helpers ───────────────────────────────────────────────


def _emit_start(investigation_id: str, *, parent_id: str | None = None) -> str:
    """Test helper: emit an INVESTIGATION_START_REQUESTED into the
    events_dir directly via the substrate's emit_typed path."""
    from substrate.event_log import emit_typed
    eid = emit_typed(
        investigation_id,
        InvestigationStartRequestedPayload(
            question="Q?",
            parent_investigation_id=parent_id,
        ),
        role="operator",
    )
    assert eid is not None
    return eid


def test_walk_chase_chain_root_depth_zero(events_dir):
    from orchestration.loop_one.orchestrator import _walk_chase_chain
    _emit_start("inv-root")
    depth, root = _walk_chase_chain("inv-root")
    assert depth == 0
    assert root == "inv-root"


def test_walk_chase_chain_three_deep(events_dir):
    from orchestration.loop_one.orchestrator import _walk_chase_chain
    _emit_start("inv-root")
    _emit_start("inv-a", parent_id="inv-root")
    _emit_start("inv-b", parent_id="inv-a")
    _emit_start("inv-c", parent_id="inv-b")
    depth, root = _walk_chase_chain("inv-c")
    assert depth == 3
    assert root == "inv-root"


def test_walk_chase_chain_cycle_safe(events_dir):
    """Cycle in parent_investigation_id values shouldn't infinite-loop."""
    from orchestration.loop_one.orchestrator import _walk_chase_chain
    _emit_start("inv-a", parent_id="inv-b")
    _emit_start("inv-b", parent_id="inv-a")
    depth, root = _walk_chase_chain("inv-a")
    # 32-hop cap protects us; just assert termination.
    assert depth >= 1


# ── Cost-accumulation helper ─────────────────────────────────────────


def test_accumulated_cost_zero_when_no_dispatches(events_dir):
    from orchestration.loop_one.orchestrator import _accumulated_chase_cost_usd
    _emit_start("inv-a")
    assert _accumulated_chase_cost_usd("inv-a") == 0.0


def test_accumulated_cost_sums_across_chain(events_dir):
    """Two-investigation chain with $0.05 + $0.03 dispatches sums to $0.08."""
    from orchestration.loop_one.orchestrator import _accumulated_chase_cost_usd
    from substrate.event_log import emit_typed
    from substrate.schemas import DispatchCallPayload

    # Parent
    _emit_start("inv-parent")
    emit_typed(
        "inv-parent",
        DispatchCallPayload(
            provider="openrouter", model="x/y", tier="flash",
            target_role="decomposer", input_tokens=100, output_tokens=50,
            cost_usd=0.05, latency_ms=1000, prompt_hash="sha256:abc",
        ),
        role="orchestrator",
    )
    # Child with parent link
    _emit_start("inv-child", parent_id="inv-parent")
    emit_typed(
        "inv-child",
        DispatchCallPayload(
            provider="openrouter", model="x/y", tier="flash",
            target_role="evidence_retriever", input_tokens=100, output_tokens=50,
            cost_usd=0.03, latency_ms=1000, prompt_hash="sha256:def",
        ),
        role="orchestrator",
    )
    assert _accumulated_chase_cost_usd("inv-child") == pytest.approx(0.08)


# ── Question selection ─────────────────────────────────────────────


def test_select_chase_question_from_evidence_gaps():
    from orchestration.loop_one.orchestrator import (
        InvestigationContext,
        _select_chase_question,
    )
    from substrate.schemas import (
        EvidenceRetrieveDeliveredPayload,
        EvidentiaryGap,
    )

    ev = EvidenceRetrieveDeliveredPayload(
        sub_question="What is X?",
        answer="The corpus did not address X.",
        supporting_claims=[],
        evidentiary_gaps=[
            EvidentiaryGap(
                gap_description="Quantitative data on X is needed.",
            ),
            EvidentiaryGap(
                gap_description="Cross-corpus comparison missing.",
            ),
        ],
        insufficient_evidence=True,
    )
    ctx = InvestigationContext(
        investigation_id="inv-test",
        question="root question",
        evidence=[ev],
    )
    assert (
        _select_chase_question(ctx) == "Quantitative data on X is needed."
    )


def test_select_chase_question_returns_none_when_no_gaps():
    from orchestration.loop_one.orchestrator import (
        InvestigationContext,
        _select_chase_question,
    )
    ctx = InvestigationContext(
        investigation_id="inv-test",
        question="root question",
        evidence=[],
    )
    assert _select_chase_question(ctx) is None
