"""Pure tests for deep research quality budget gate compose."""

from __future__ import annotations

from substrate.deep_research_quality_budget_gate_compose import (
    compose_deep_research_quality_budget_gate,
)


def test_gate_ready():
    c = compose_deep_research_quality_budget_gate(
        session_id="dr-1",
        quality_overall=0.82,
        quality_floor=0.5,
        would_exceed=False,
        citation_pack_ready=True,
        operator_ack=True,
    )
    assert c.gate_ready is True
    assert c.live_dispatch_authorized is False
    assert c.to_dict()["live_dispatch_authorized"] is False


def test_fails_closed():
    low = compose_deep_research_quality_budget_gate(
        session_id="dr",
        quality_overall=0.2,
        quality_floor=0.5,
        would_exceed=False,
        operator_ack=True,
    )
    assert low.quality_ready is False
    assert low.gate_ready is False
    unk = compose_deep_research_quality_budget_gate(
        session_id="dr",
        quality_overall=0.9,
        would_exceed=None,
        operator_ack=True,
    )
    assert unk.budget_ready is False
    assert unk.gate_ready is False
