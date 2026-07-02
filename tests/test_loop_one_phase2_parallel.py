"""ANT-DRL-03 — bounded parallel Phase 2 + graph orientation seeds."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import EventBroadcaster  # noqa: E402
from orchestration.loop_one.coordinator import InvestigationCoordinator  # noqa: E402
from orchestration.loop_one.orchestrator import (  # noqa: E402
    PHASE_2_MAX_CONCURRENCY,
    _prior_graph_knowledge_section,
)
from substrate.schemas import (  # noqa: E402
    ActionType,
    EvidenceRetrieveDeliveredPayload,
    Event,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    yield


@pytest.mark.asyncio
async def test_coordinator_correlated_wait_for_sub_question():
    """Parallel Phase 2 waiters resolve by payload.sub_question."""
    bus = EventBroadcaster()
    coord = InvestigationCoordinator(bus)

    async def emit_sq(sq: str, answer: str) -> None:
        await asyncio.sleep(0)  # yield so waiters register first
        from substrate.event_log import emit_typed

        emit_typed(
            "inv-p2",
            EvidenceRetrieveDeliveredPayload(
                sub_question=sq,
                answer=answer,
            ),
            role="evidence_retriever",
        )
        rows = __import__(
            "substrate.event_log", fromlist=["trajectory"],
        ).trajectory("inv-p2")
        event = Event.model_validate(rows[-1])
        await bus.broadcast(event)

    wait_tasks = [
        asyncio.create_task(
            coord.wait_for(
                "inv-p2",
                ActionType.EVIDENCE_RETRIEVE_DELIVERED.value,
                correlation=sq,
                timeout=5.0,
            )
        )
        for sq in ("sq-a", "sq-b", "sq-c")
    ]
    await asyncio.sleep(0)
    await asyncio.gather(
        emit_sq("sq-b", "answer-b"),
        emit_sq("sq-a", "answer-a"),
        emit_sq("sq-c", "answer-c"),
    )
    results = await asyncio.gather(*wait_tasks)

    answers = {r.payload.sub_question: r.payload.answer for r in results}
    assert answers == {
        "sq-a": "answer-a",
        "sq-b": "answer-b",
        "sq-c": "answer-c",
    }


def test_phase_2_concurrency_cap_default_is_four():
    assert PHASE_2_MAX_CONCURRENCY == 4


def test_prior_graph_section_cites_chunk_ids(monkeypatch):
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._render_chunks_block_for_sub_question",
        lambda _q, top_k=3: (
            "### chunk_id: chunk_abc123\nSource tier: 1\n\ntext\n"
            "### chunk_id: chunk_def456\nSource tier: 2\n\ntext2\n"
        ),
    )
    section = _prior_graph_knowledge_section("any question")
    assert "chunk_abc123" in section
    assert "chunk_def456" in section


def test_prior_graph_section_fallback_markers(monkeypatch):
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._render_chunks_block_for_sub_question",
        lambda _q, top_k=3: "(corpus search returned no matches above the similarity floor)",
    )
    section = _prior_graph_knowledge_section("cold question")
    assert "chunk_orientation_marker" in section
    assert "node_orchestrator_start" in section


def test_trajectory_append_order_preserved_under_sequential_emit():
    """Event log append order is stable (monotonic timestamps)."""
    from substrate.event_log import emit_typed, trajectory

    inv = "inv-seq"
    for i in range(5):
        emit_typed(
            inv,
            EvidenceRetrieveDeliveredPayload(
                sub_question=f"sq-{i}",
                answer=f"a-{i}",
            ),
            role="evidence_retriever",
        )
    rows = trajectory(inv)
    assert len(rows) == 5
    stamps = [row["emitted_at"] for row in rows]
    assert stamps == sorted(stamps)
    assert [r["payload"]["sub_question"] for r in rows] == [
        f"sq-{i}" for i in range(5)
    ]