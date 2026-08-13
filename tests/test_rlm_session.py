"""RLM session orchestrator tests (Sprint 19+ RLM track)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from orchestration.rlm import (
    RLM_DOC_THRESHOLD_TOKENS,
    RLM_SESSION_COST_USD_CAP,
    RLMRatificationRequired,
    create_session,
    iterate_session,
)
from orchestration.rlm.session import RLMToolIsolationViolation


def test_ratification_required(monkeypatch):
    """Sessions refuse to start without ANTIEK_RLM_RATIFIED=1."""
    monkeypatch.delenv("ANTIEK_RLM_RATIFIED", raising=False)
    with pytest.raises(RLMRatificationRequired):
        create_session(investigation_id="inv-x", root_role="synthesizer")


def test_create_session_with_ratification(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    session = create_session(
        investigation_id="inv-quantum",
        root_role="synthesizer",
        document_id="doc-100k-tokens",
    )
    assert session.state.session_id.startswith("rlm-")
    assert session.state.investigation_id == "inv-quantum"
    assert session.state.root_role == "synthesizer"
    assert session.state.root_executor == "dispatch"
    assert session.state.prime_goal_brief is None
    assert session.state.status == "in_progress"


def test_doc_threshold_constant():
    """Per rlm_integration_spec.md §6 design decision 6: 64K token
    threshold for RLM mode."""
    assert RLM_DOC_THRESHOLD_TOKENS == 64_000


def test_session_cost_cap_constant():
    """Per rlm_integration_spec.md §6 design decision 3: $5 session cap."""
    assert Decimal("5.00") == RLM_SESSION_COST_USD_CAP


def test_iterate_session_records_cost(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    session = create_session(investigation_id="inv-x", root_role="synthesizer")
    iterate_session(session, summary="Read chapters 1-3", cost_usd=Decimal("0.50"))
    iterate_session(session, summary="Read chapters 4-6", cost_usd=Decimal("0.60"))
    assert session.state.iteration_count == 2
    assert session.state.cost_usd_accumulated == Decimal("1.10")
    assert len(session.iterations) == 2


def test_session_cost_cap_enforced(monkeypatch):
    """At $5 cap, an iteration that would push total over the cap
    marks the session cost_capped instead of recording."""
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    session = create_session(investigation_id="inv-x", root_role="synthesizer")
    iterate_session(session, summary="big read", cost_usd=Decimal("4.00"))
    # This would push to $9, over cap.
    iterate_session(session, summary="even bigger", cost_usd=Decimal("5.00"))
    assert session.state.status == "cost_capped"
    assert session.state.iteration_count == 1  # only the first recorded


def test_tool_isolation_root_repl_refused(monkeypatch):
    """Per rlm_integration_spec.md tool-isolation invariant: tools
    NEVER attach to the root REPL. The substrate refuses."""
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    session = create_session(investigation_id="inv-x", root_role="synthesizer")
    with pytest.raises(RLMToolIsolationViolation):
        session.attach_tool_to_sub_llm("root", "tool_x")
    with pytest.raises(RLMToolIsolationViolation):
        session.attach_tool_to_sub_llm("repl", "tool_y")


def test_tool_isolation_sub_llm_allowed(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    session = create_session(investigation_id="inv-x", root_role="synthesizer")
    session.attach_tool_to_sub_llm("sub_grounder", "search_chunks")
    session.attach_tool_to_sub_llm("sub_grounder", "cite_source")
    assert len(session.sub_llms) == 1
    assert session.sub_llms[0].name == "sub_grounder"
    assert session.sub_llms[0].tools == ("search_chunks", "cite_source")


def test_complete_session(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    session = create_session(investigation_id="inv-x", root_role="synthesizer")
    iterate_session(session, summary="iter 1", cost_usd=Decimal("0.10"))
    session.complete(final_summary="Three theses emerged across the corpus.")
    assert session.state.status == "completed"
    assert session.state.completed_at is not None



def test_create_session_allows_prime_executor_metadata(monkeypatch):
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    session = create_session(
        investigation_id="inv-prime",
        root_role="wrestler",
        root_executor="prime_agent",
        prime_goal_brief="prime goal",
    )
    assert session.state.root_executor == "prime_agent"
    assert session.state.prime_goal_brief == "prime goal"
