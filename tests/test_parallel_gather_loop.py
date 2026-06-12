"""SPR-DRL-08 — Parallel Search gather loop (mock-only, no live API key)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Callable, List, Optional

import httpx
import pytest

from acquisition.search.parallel import ParallelClient, discover, promote_discovery
from acquisition.search.parallel.adapter import _discovery_id
from runtime.research_runner import HostLocalRunner, ResearchPlan, make_parallel_gather_loop
from substrate.legal_gate import PermissiveLegalGate


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("PARALLEL_API_KEY", "test-key-not-used-by-mock-transport")
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", "1")
    yield {"events_dir": str(events_dir)}


def _mock_parallel_client(responses: List[dict], *, status: int = 200) -> ParallelClient:
    responses_iter = iter(responses)
    last = [None]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-api-key") == "test-key"
        body = json.loads(request.content.decode())
        assert body.get("search_queries")
        try:
            payload = next(responses_iter)
            last[0] = payload
        except StopIteration:
            payload = last[0] or {"results": []}
        return httpx.Response(status, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return ParallelClient(api_key="test-key", client=client, sleep=lambda _s: None)


def _patch_ingest_url(monkeypatch, fake_ingest: Callable) -> None:
    mod = ModuleType("acquisition.urls.adapter")
    mod.ingest_url = fake_ingest
    monkeypatch.setitem(sys.modules, "acquisition.urls.adapter", mod)


def _parallel_result(url: str, *, title: Optional[str] = None, excerpt: Optional[str] = None) -> dict:
    return {
        "url": url,
        "title": title,
        "publish_date": "2024-01-15",
        "excerpts": [excerpt or "sample excerpt"],
    }


def test_parallel_client_search_happy_path():
    cli = _mock_parallel_client(
        [
            {
                "search_id": "search_abc123",
                "session_id": "session_xyz",
                "results": [
                    _parallel_result("https://example.com/a", title="A"),
                    _parallel_result("https://arxiv.org/abs/1234", title="Paper"),
                ],
            }
        ]
    )
    resp = cli.search(
        objective="What is quantum error correction?",
        search_queries=["quantum error correction", "QEC overview"],
        max_results=5,
    )
    assert resp.search_id == "search_abc123"
    assert len(resp.results) == 2
    assert resp.results[0].url == "https://example.com/a"
    assert resp.results[0].text_snippet_preview == "sample excerpt"


def test_parallel_discover_emits_proposed_events(isolated_env):
    cli = _mock_parallel_client(
        [
            {
                "search_id": "search_1",
                "results": [_parallel_result("https://example.com/x", title="X")],
            }
        ]
    )
    proposals = discover(query="test query", investigation_id="inv-1", client=cli)
    assert len(proposals) == 1
    p = proposals[0]
    assert p.provider == "parallel"
    assert p.discovery_id.startswith("disc-parallel-")
    assert p.url == "https://example.com/x"
    assert p.proposed_event_id is not None


def test_discovery_id_stable_and_query_sensitive():
    a = _discovery_id("https://e.com", "inv", "q1")
    b = _discovery_id("https://e.com", "inv", "q2")
    c = _discovery_id("https://e.com", "inv", "q1")
    assert a == c
    assert a != b
    assert a.startswith("disc-parallel-")


def test_promote_discovery_ingested(isolated_env, monkeypatch):
    @dataclass(frozen=True)
    class FakeIngestResult:
        document_id: str = "doc-url-paralleltest01"
        final_url: str = "https://example.com/x"
        chunk_ids: tuple = ()
        node_ids: tuple = ()
        document_loaded_event_id: Optional[str] = "evt-loaded"
        chunks_written: int = 3
        skipped_reason: Optional[str] = None
        title: Optional[str] = "Test"
        author: Optional[str] = None

    _patch_ingest_url(monkeypatch, lambda *a, **k: FakeIngestResult())

    cli = _mock_parallel_client(
        [{"search_id": "s1", "results": [_parallel_result("https://example.com/x")]}]
    )
    [proposal] = discover(query="q", investigation_id="inv-1", client=cli)
    result = promote_discovery(
        proposal,
        investigation_id="inv-1",
        legal_gate=PermissiveLegalGate(_bypass_acknowledgment=True),
    )
    assert result.decision == "ingested"
    assert result.document_id == "doc-url-paralleltest01"
    assert result.chunks_written == 3


@pytest.mark.asyncio
async def test_parallel_gather_loop_emits_provenance_steps(isolated_env, monkeypatch):
    cli = _mock_parallel_client(
        [
            {
                "search_id": "search_loop",
                "results": [
                    _parallel_result("https://example.com/one"),
                    _parallel_result("https://example.com/two"),
                ],
            }
        ]
    )

    @dataclass(frozen=True)
    class FakeIngestResult:
        document_id: str
        final_url: str = ""
        chunk_ids: tuple = ()
        node_ids: tuple = ()
        document_loaded_event_id: Optional[str] = None
        chunks_written: int = 1
        skipped_reason: Optional[str] = None
        title: Optional[str] = None
        author: Optional[str] = None

    seq = {"n": 0}

    def fake_ingest(url, **kwargs):
        seq["n"] += 1
        return FakeIngestResult(document_id=f"doc-url-loop{seq['n']:02d}")

    _patch_ingest_url(monkeypatch, fake_ingest)

    loop_fn = make_parallel_gather_loop(
        top_k=2,
        client=cli,
        legal_gate=PermissiveLegalGate(_bypass_acknowledgment=True),
        events_dir=isolated_env["events_dir"],
    )
    runner = HostLocalRunner(loop_fn, events_dir=isolated_env["events_dir"], seal_on_complete=False)
    plan = ResearchPlan(
        investigation_id="leaf-parallel",
        sub_question="parallel gather topic",
    )
    handle = await runner.start("leaf-parallel", plan)
    events = []
    async for ev in runner.stream(handle):
        events.append(ev)

    kinds = [e.kind for e in events]
    assert "plan" in kinds
    assert "step" in kinds
    assert "note" in kinds

    step_data = [e.data for e in events if e.kind == "step"]
    assert any(d.get("gather_mode") == "parallel" for d in step_data)
    promoted_steps = [d for d in step_data if d.get("discovery_id")]
    assert len(promoted_steps) == 2
    assert all(d.get("promotion_decision") == "ingested" for d in promoted_steps)
    assert all(str(d.get("document_id", "")).startswith("doc-url-") for d in promoted_steps)
    assert all(str(d.get("discovery_id", "")).startswith("disc-parallel-") for d in promoted_steps)