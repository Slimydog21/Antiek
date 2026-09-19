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
from pathlib import Path

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


def test_walk_chase_chain_reads_explicit_custom_root(tmp_path):
    from orchestration.loop_one.orchestrator import _walk_chase_chain
    from substrate.event_log import emit_typed

    custom = tmp_path / "custom-events"
    emit_typed(
        "custom-parent",
        InvestigationStartRequestedPayload(question="parent"),
        role="operator",
        events_dir=str(custom),
    )
    emit_typed(
        "custom-child",
        InvestigationStartRequestedPayload(
            question="child", parent_investigation_id="custom-parent"
        ),
        role="operator",
        events_dir=str(custom),
    )
    assert _walk_chase_chain(
        "custom-child", tenancy_root=Path(custom)
    ) == (1, "custom-parent")


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


@pytest.mark.asyncio
async def test_spawned_chase_child_uses_only_remaining_recursive_ceiling(
    monkeypatch, tmp_path
):
    """A child must not inherit the parent's separate initial-run authority."""
    from decimal import Decimal

    import interfaces.research.api.settings_budget as settings_budget
    import orchestration.loop_one.orchestrator as orch
    from substrate.dispatch.research_quote import build_research_route_manifest
    from substrate.dispatch.router import DispatchConfig
    from substrate.event_log import ResearchDelegationSnapshot, prepare_typed_event
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.schemas import (
        ResearchDelegationIssuedPayload,
        ResearchDelegationReservedPayload,
        ResearchQuotedRoute,
    )
    from tests.research_quote_support import configure_research_quote_authority

    configure_research_quote_authority(monkeypatch, tmp_path)
    manifest = build_research_route_manifest(
        DispatchConfig.from_yaml(settings_budget._dispatch_config_path())
    )

    emitted: list[object] = []

    class CapturingBroadcaster:
        def bind_event_authority(self, _event_id, _authority):
            return None

        async def broadcast(self, event):
            emitted.append(event.payload)

        async def broadcast_once(self, event):
            await self.broadcast(event)
            return True

    async def capture_emit(_bus, _investigation_id, payload, **_kwargs):
        emitted.append(payload)
        return "event-test"

    monkeypatch.setattr(orch, "_walk_chase_chain", lambda *_args, **_kwargs: (0, "inv-root"))
    monkeypatch.setattr(orch, "_accumulated_chase_cost_usd", lambda *_args, **_kwargs: 0.75)
    monkeypatch.setattr(orch, "_select_chase_question", lambda _ctx: "Chase the remaining gap")
    monkeypatch.setattr(orch, "broadcast_emit", capture_emit)
    snapshot = ResearchDelegationSnapshot(
        ceiling_usd=Decimal("2"),
        root_call_spend_usd=Decimal("0.75"),
        delegated_spend_usd=Decimal("0"),
        outstanding_usd=Decimal("0"),
    )
    monkeypatch.setattr(
        "substrate.event_log.research_delegation_snapshot_authorized",
        lambda _authority: snapshot,
    )
    monkeypatch.setattr(
        "substrate.event_log.trajectory_authorized_append_order", lambda _authority: []
    )

    def reserve(_authority, payload: ResearchDelegationReservedPayload):
        return prepare_typed_event("inv-root", payload), snapshot

    def issue(_authority, payload: ResearchDelegationIssuedPayload):
        return prepare_typed_event("inv-root", payload), snapshot

    monkeypatch.setattr("substrate.event_log.reserve_research_delegation_authorized", reserve)
    monkeypatch.setattr("substrate.event_log.mark_research_delegation_issued_authorized", issue)
    monkeypatch.setattr(
        "substrate.event_log.accept_research_delegation_authorized",
        lambda *_args, **_kwargs: (None, snapshot),
    )
    ctx = orch.InvestigationContext(
        investigation_id="inv-parent",
        question="Root question",
        chase_mode="depth",
        chase_value=2,
        chase_budget_usd=2.0,
        tenancy_root=tmp_path,
        authority=InvestigationAuthority("acct-test", "inv-parent", tmp_path),
        research_quote_id="a" * 64,
        research_route_manifest_fingerprint=manifest.fingerprint,
        research_route_manifest=tuple(
            ResearchQuotedRoute(**row.__dict__) for row in manifest.routes
        ),
    )

    await orch._maybe_spawn_chase_child(ctx, CapturingBroadcaster())

    start = next(
        payload
        for payload in emitted
        if isinstance(payload, InvestigationStartRequestedPayload)
    )
    assert start.approved_run_ceiling_usd == 1.25
    assert start.research_quote_id != ctx.research_quote_id
    assert start.research_delegated_from_quote_id == ctx.research_quote_id
    assert start.research_route_manifest == ctx.research_route_manifest
    assert start.research_quote_payload_sha256 is not None


@pytest.mark.asyncio
async def test_chase_spawn_replay_converges_on_one_root_allocation_and_child(
    monkeypatch, tmp_path
):
    import interfaces.research.api.settings_budget as settings_budget
    import orchestration.loop_one.orchestrator as orch
    from interfaces.research.api.broadcast import EventBroadcaster
    from substrate.dispatch.research_quote import build_research_route_manifest
    from substrate.dispatch.router import DispatchConfig
    from substrate.event_log import (
        append_event_once_authorized,
        prepare_typed_event,
        trajectory_authorized_append_order,
    )
    from substrate.investigation_streams import initialize_composite_stream
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.schemas import InvestigationStartRequestedPayload, ResearchQuotedRoute
    from tests.research_quote_support import configure_research_quote_authority

    configure_research_quote_authority(monkeypatch, tmp_path)
    manifest = build_research_route_manifest(
        DispatchConfig.from_yaml(settings_budget._dispatch_config_path())
    )
    root = InvestigationAuthority("acct-test", "inv-root", tmp_path)
    initialize_composite_stream(root)
    start = prepare_typed_event(
        root.investigation_id,
        InvestigationStartRequestedPayload(
            question="Root question",
            chase_mode="depth",
            chase_value=2,
            chase_budget_usd=2.0,
            research_tier="deep",
            approved_run_ceiling_usd=1.0,
            research_quote_id="a" * 64,
            research_quote_payload_sha256="b" * 64,
            research_route_manifest_fingerprint=manifest.fingerprint,
            research_quote_expires_at_ms=4_102_444_800_000,
            research_route_manifest=tuple(
                ResearchQuotedRoute(**row.__dict__) for row in manifest.routes
            ),
        ),
        event_id="evt-root-start",
    )
    append_event_once_authorized(root, start)
    monkeypatch.setattr(orch, "_walk_chase_chain", lambda *_a, **_k: (0, "inv-root"))
    monkeypatch.setattr(orch, "_accumulated_chase_cost_usd", lambda *_a, **_k: 0.0)
    monkeypatch.setattr(orch, "_select_chase_question", lambda _ctx: "Chase gap")
    ctx = orch.InvestigationContext(
        investigation_id=root.investigation_id,
        question="Root question",
        authority=root,
        tenancy_root=tmp_path,
        chase_mode="depth",
        chase_value=2,
        chase_budget_usd=2.0,
        research_tier="deep",
        research_quote_id="a" * 64,
        research_route_manifest_fingerprint=manifest.fingerprint,
        research_route_manifest=tuple(
            ResearchQuotedRoute(**row.__dict__) for row in manifest.routes
        ),
    )
    bus = EventBroadcaster()
    executed_child_starts: list[str] = []

    async def observe_child_start(event):
        executed_child_starts.append(event.event_id)

    bus.register_handler("investigation.start_requested", observe_child_start)
    import substrate.dispatch.research_quote as research_quote
    import substrate.event_log as event_log

    real_mark = event_log.mark_research_delegation_issued_authorized
    real_accept = event_log.accept_research_delegation_authorized
    real_issue_quote = research_quote.issue_research_quote

    def crash_after_sign(*args, **kwargs):
        real_issue_quote(*args, **kwargs)
        raise RuntimeError("crash after in-memory sign")

    monkeypatch.setattr(research_quote, "issue_research_quote", crash_after_sign)
    with pytest.raises(RuntimeError, match="in-memory sign"):
        await orch._maybe_spawn_chase_child(ctx, bus)
    root_rows = trajectory_authorized_append_order(root)
    assert sum(
        row["action_type"] == "research.delegation_reserved" for row in root_rows
    ) == 1
    assert not any(
        row["action_type"] == "research.delegation_issued" for row in root_rows
    )
    monkeypatch.setattr(research_quote, "issue_research_quote", real_issue_quote)

    def crash_after_issue(*args, **kwargs):
        real_mark(*args, **kwargs)
        raise RuntimeError("crash after issue receipt")

    monkeypatch.setattr(
        event_log, "mark_research_delegation_issued_authorized", crash_after_issue
    )
    with pytest.raises(RuntimeError, match="after issue"):
        await orch._maybe_spawn_chase_child(ctx, bus)
    root_rows = trajectory_authorized_append_order(root)
    assert sum(
        row["action_type"] == "research.delegation_issued" for row in root_rows
    ) == 1
    assert not any(
        row["action_type"] == "research.delegation_accepted" for row in root_rows
    )

    monkeypatch.setattr(
        event_log, "mark_research_delegation_issued_authorized", real_mark
    )

    def crash_after_child_append(*_args, **_kwargs):
        raise RuntimeError("crash after child append")

    monkeypatch.setattr(
        event_log, "accept_research_delegation_authorized", crash_after_child_append
    )
    with pytest.raises(RuntimeError, match="after child append"):
        await orch._maybe_spawn_chase_child(ctx, bus)
    await bus.wait_for_handlers()
    assert executed_child_starts == []
    monkeypatch.setattr(event_log, "accept_research_delegation_authorized", real_accept)

    real_broadcast_once = bus.broadcast_once

    async def crash_after_acceptance(_event):
        raise RuntimeError("crash after root acceptance")

    bus.broadcast_once = crash_after_acceptance  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="after root acceptance"):
        await orch._maybe_spawn_chase_child(ctx, bus)
    await bus.wait_for_handlers()
    assert executed_child_starts == []
    bus.broadcast_once = real_broadcast_once  # type: ignore[method-assign]

    await orch._maybe_spawn_chase_child(ctx, bus)
    await orch._maybe_spawn_chase_child(ctx, bus)
    await bus.wait_for_handlers()

    root_rows = trajectory_authorized_append_order(root)
    for action in (
        "research.delegation_reserved",
        "research.delegation_issued",
        "research.delegation_accepted",
    ):
        assert sum(row["action_type"] == action for row in root_rows) == 1
    reservation = next(
        row["payload"]
        for row in root_rows
        if row["action_type"] == "research.delegation_reserved"
    )
    child = InvestigationAuthority(
        root.account_id, reservation["child_investigation_id"], tmp_path
    )
    child_rows = trajectory_authorized_append_order(child)
    assert sum(
        row["action_type"] == "investigation.start_requested" for row in child_rows
    ) == 1
    assert sum(
        row["action_type"] == "investigation.spawned_from" for row in child_rows
    ) == 1
    assert executed_child_starts == [child_rows[0]["event_id"]]
