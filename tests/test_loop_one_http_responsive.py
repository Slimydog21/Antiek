"""Loop One must not stall uvicorn HTTP under --workers 1.

After spin-research broadcast (#3102), investigation.start_requested wakes
Loop One in-process. Sync embed/search + provider dispatch previously ran
on the asyncio event loop and blocked /health mid-investigation.
"""

from __future__ import annotations

import asyncio
import time

import pytest


@pytest.mark.asyncio
async def test_corpus_render_async_offloads_and_keeps_loop_responsive(monkeypatch):
    """Phase-2 corpus renders must use to_thread; event loop stays free."""
    from orchestration.loop_one import orchestrator as orch

    def slow_render(sub_question: str, *, top_k: int = 5, policy_tag: str = "x") -> str:
        time.sleep(0.35)
        return "(corpus search returned no matches above the similarity floor)"

    monkeypatch.setattr(orch, "_render_chunks_block_for_sub_question", slow_render)
    monkeypatch.setattr(orch, "_render_subgraph_block_for_sub_question", slow_render)

    heartbeats: list[float] = []

    async def heartbeat() -> None:
        while len(heartbeats) < 4:
            t0 = time.perf_counter()
            await asyncio.sleep(0.05)
            heartbeats.append(time.perf_counter() - t0)

    hb_task = asyncio.create_task(heartbeat())
    t0 = time.perf_counter()
    chunks, subgraph = await asyncio.gather(
        orch._render_chunks_block_for_sub_question_async("q", top_k=3, policy_tag="attribution_eligible"),
        orch._render_subgraph_block_for_sub_question_async("q", top_k=3, policy_tag="attribution_eligible"),
    )
    elapsed = time.perf_counter() - t0
    await hb_task

    assert "corpus search" in chunks
    assert "corpus search" in subgraph
    # Both renders sleep 0.35s; if they blocked the loop serially on-thread
    # heartbeats would stall. With to_thread, heartbeats keep ticking.
    assert len(heartbeats) >= 4
    assert max(heartbeats) < 0.25, heartbeats
    # Wall clock ~0.35s (parallel threads), not 0.7s serial on event loop.
    assert elapsed < 0.7


@pytest.mark.asyncio
async def test_role_dispatch_offload_keeps_loop_responsive(monkeypatch):
    """Role-bridge sync dispatch must not monopolize the event loop."""
    import interfaces.research.api.evidence_retriever as er

    def slow_dispatch(*args, **kwargs):
        time.sleep(0.35)
        return None, "evidence-retriever-fallback/test"

    monkeypatch.setattr(er, "_dispatch_and_parse", slow_dispatch)

    heartbeats: list[float] = []

    async def heartbeat() -> None:
        while len(heartbeats) < 4:
            t0 = time.perf_counter()
            await asyncio.sleep(0.05)
            heartbeats.append(time.perf_counter() - t0)

    from substrate.schemas import (
        ActionType,
        Event,
        EvidenceRetrieveRequestedPayload,
    )

    payload = EvidenceRetrieveRequestedPayload(
        sub_question="does citrus grafting work in arid climates?",
        category="technology_risk",
        evidence_type_required="qualitative",
        top_k=3,
        chunks_block="### chunk_id: c1\n> note\n",
        subgraph_block="(no knowledge-graph edges for this sub-question)",
    )
    event = Event(
        event_id="evt-test-1",
        investigation_id="inv-health-offload",
        action_type=ActionType.EVIDENCE_RETRIEVE_REQUESTED,
        payload=payload,
        emitted_at="2026-09-17T00:00:00Z",
        schema_version=1,
        param_version="test",
    )

    class _Bus:
        pass

    async def _noop_emit(*args, **kwargs):
        return None

    monkeypatch.setattr(er, "_emit_delivered", _noop_emit)
    handler = er.make_evidence_retriever_handler(_Bus())  # type: ignore[arg-type]
    hb_task = asyncio.create_task(heartbeat())
    await handler(event)
    await hb_task

    assert len(heartbeats) >= 4
    assert max(heartbeats) < 0.25, heartbeats
