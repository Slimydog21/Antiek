"""SPR-DRL-08 — Exa gather loop (mock-only, no live EXA_API_KEY).

The Exa analogue of the archived parallel gather templates. Proves the
chain:

    discover  →  promote_discovery  →  ingest_url (single write seam)
              →  funnel(source_document_id)  →  pack(doc-url-*)

Every test injects an ``ExaClient(client=httpx.MockTransport(...))`` — the
gate never holds a live key. ``ingest_url`` is patched to a deterministic
``FakeIngestResult`` so no network fetch happens; the legal gate is a
permissive bypass so the promotion path runs end-to-end in-process.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType, SimpleNamespace

import httpx
import pytest

from acquisition.search.exa import ExaClient, discover, promote_discovery
from acquisition.search.exa.adapter import _discovery_id
from orchestration.cascade_session import CascadeSession, Leaf
from orchestration.session_evidence_pack import build_session_evidence_pack
from processing.embedding import _reset_default_provider, set_default_embedding_provider
from roles.cascade_planner import SubQuestion, approve_plan, build_plan, persist_tree
from roles.cascade_planner.persist import load_tree
from runtime.research_runner import (
    HostLocalRunner,
    PromotionFunnel,
    ResearchPlan,
    make_contract_gather_stub,
    make_exa_gather_loop,
)
from runtime.research_runner.promotion_funnel import _promotion_metadata
from runtime.research_runner.protocol import StepEvent
from substrate.dispatch.base import NormalizedUsage
from substrate.graph.schema import init_database_at_path
from substrate.legal_gate import LegalGate, PermissiveLegalGate

# ── shared helpers ─────────────────────────────────────────────────


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


class _Dec:
    def __init__(self, subs: list[str]) -> None:
        self._subs = subs

    def decompose(self, q: str, *, context: str = ""):
        return [SubQuestion(question=s) for s in self._subs]


def _mock_exa_client(responses: list[dict], *, status: int = 200) -> ExaClient:
    """An ExaClient whose transport replays canned /search responses.

    The handler asserts the request shape (so a regression in the client's
    request body surfaces here) and never reaches the network.
    """
    it = iter(responses)
    last = [None]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/search")
        body = request.read()
        assert b"query" in body
        try:
            payload = next(it)
            last[0] = payload
        except StopIteration:
            payload = last[0] or {"results": []}
        return httpx.Response(status, json=payload)

    transport = httpx.MockTransport(handler)
    return ExaClient(
        api_key="test-key-not-used-by-mock-transport",
        client=httpx.Client(transport=transport),
        sleep=lambda _s: None,
    )


def _exa_result(url: str, *, title: str | None = None, text: str | None = None) -> dict:
    return {
        "url": url,
        "title": title,
        "publishedDate": "2024-01-15",
        "text": text or "sample excerpt",
    }


def _patch_ingest_url(monkeypatch, fake_ingest: Callable) -> None:
    mod = ModuleType("acquisition.urls.adapter")
    mod.ingest_url = fake_ingest
    monkeypatch.setitem(sys.modules, "acquisition.urls.adapter", mod)


@dataclass(frozen=True)
class FakeIngestResult:
    document_id: str
    final_url: str = ""
    chunk_ids: tuple = ()
    node_ids: tuple = ()
    document_loaded_event_id: str | None = None
    chunks_written: int = 1
    skipped_reason: str | None = None
    title: str | None = None
    author: str | None = None


def _bypass_gate() -> LegalGate:
    return PermissiveLegalGate(_bypass_acknowledgment=True)


# ── fixtures ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("ANTIEK_DISCOVERY_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("EXA_API_KEY", "test-key-not-used-by-mock-transport")
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", "1")
    yield {"events_dir": str(events_dir)}


@pytest.fixture
def graph_env(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    db = tmp_path / "g.duckdb"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("ANTIEK_DISCOVERY_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("EXA_API_KEY", "test-key-not-used-by-mock-transport")
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", "1")
    import substrate.graph.insight_question as iq

    monkeypatch.setattr(iq, "graph_db_path", lambda: str(db))
    init_database_at_path(str(db))
    return {"db": str(db), "events": str(events_dir)}


# ── M3 unit: document_id → source_document_id map ───────────────────


def test_promotion_metadata_maps_document_id_to_source_document_id():
    ev = StepEvent(
        "leaf-1",
        1,
        "note",
        text="ingested doc",
        data={"document_id": "doc-url-exa01", "gather_mode": "exa"},
    )
    meta = _promotion_metadata(ev)
    assert meta["source_document_id"] == "doc-url-exa01"
    assert meta["gather_mode"] == "exa"
    assert meta["source"] == "research_runner"


def test_promotion_metadata_without_document_id_adds_no_source():
    ev = StepEvent(
        "leaf-1", 1, "note", text="stub note", data={"gather_mode": "contract_stub"}
    )
    meta = _promotion_metadata(ev)
    assert "source_document_id" not in meta


# ── M2: factory default ─────────────────────────────────────────────


def test_factory_returns_stub_by_default(monkeypatch):
    monkeypatch.delenv("ANTIEK_DRW_GATHER", raising=False)
    from interfaces.research.api import cascade_routes

    loop_fn = cascade_routes._research_loop_factory()
    # The stub loop is built by make_contract_gather_stub; its closure name is
    # ``_loop``. Identity is hard to assert across factories, so we assert by
    # constructing the stub and comparing the qualname of the produced coroutine
    # function — both come from make_contract_gather_stub, never from exa.
    stub = make_contract_gather_stub(steps=2, cost_per_step=0.01)
    assert loop_fn.__qualname__ == stub.__qualname__
    assert "contract_gather_stub" in loop_fn.__qualname__


def test_factory_returns_exa_when_env_set(monkeypatch):
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "exa")
    from interfaces.research.api import cascade_routes

    loop_fn = cascade_routes._research_loop_factory()
    exa = make_exa_gather_loop(top_k=3)
    assert loop_fn.__qualname__ == exa.__qualname__
    assert "exa_gather_loop" in loop_fn.__qualname__


def test_factory_exa_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "  EXA  ")
    from interfaces.research.api import cascade_routes

    loop_fn = cascade_routes._research_loop_factory()
    assert "exa_gather_loop" in loop_fn.__qualname__


# ── discover/promote primitives under mock transport ────────────────


def test_exa_discover_emits_proposals(isolated_env):
    cli = _mock_exa_client(
        [{"results": [_exa_result("https://example.com/x", title="X")]}]
    )
    proposals = discover(
        query="test query",
        investigation_id="inv-1",
        client=cli,
        events_dir=isolated_env["events_dir"],
        use_cache=False,
    )
    assert len(proposals) == 1
    p = proposals[0]
    assert p.provider == "exa"
    assert p.discovery_id.startswith("disc-exa-")
    assert p.url == "https://example.com/x"


def test_promote_discovery_ingested_returns_doc_url(isolated_env, monkeypatch):
    _patch_ingest_url(
        monkeypatch, lambda *a, **k: FakeIngestResult(document_id="doc-url-exatest01")
    )
    cli = _mock_exa_client([{"results": [_exa_result("https://example.com/x")]}])
    [proposal] = discover(
        query="q",
        investigation_id="inv-1",
        client=cli,
        events_dir=isolated_env["events_dir"],
        use_cache=False,
    )
    result = promote_discovery(
        proposal,
        investigation_id="inv-1",
        legal_gate=_bypass_gate(),
        events_dir=isolated_env["events_dir"],
    )
    assert result.decision == "ingested"
    assert result.document_id == "doc-url-exatest01"
    assert str(result.document_id).startswith("disc-exa-") is False
    assert _discovery_id("https://example.com/x", "inv-1", "q").startswith("disc-exa-")


# ── M1 / M4(a): loop provenance ─────────────────────────────────────


@pytest.mark.asyncio
async def test_exa_gather_loop_emits_provenance_steps(isolated_env, monkeypatch):
    cli = _mock_exa_client(
        [
            {
                "results": [
                    _exa_result("https://example.com/one"),
                    _exa_result("https://example.com/two"),
                ]
            }
        ]
    )

    seq = {"n": 0}

    def fake_ingest(url, **kwargs):
        seq["n"] += 1
        return FakeIngestResult(document_id=f"doc-url-exa{seq['n']:02d}")

    _patch_ingest_url(monkeypatch, fake_ingest)

    loop_fn = make_exa_gather_loop(
        top_k=2,
        client=cli,
        legal_gate=_bypass_gate(),
        events_dir=isolated_env["events_dir"],
    )
    runner = HostLocalRunner(
        loop_fn, events_dir=isolated_env["events_dir"], seal_on_complete=False
    )
    plan = ResearchPlan(investigation_id="leaf-exa", sub_question="exa gather topic")
    handle = await runner.start("leaf-exa", plan)
    events = [ev async for ev in runner.stream(handle)]

    kinds = [e.kind for e in events]
    assert "plan" in kinds
    assert "step" in kinds
    assert "note" in kinds

    plan_data = [e.data for e in events if e.kind == "plan"]
    assert all(d.get("gather_mode") == "exa" for d in plan_data)

    step_data = [e.data for e in events if e.kind == "step"]
    assert len(step_data) == 2
    assert all(d.get("gather_mode") == "exa" for d in step_data)
    assert all(str(d.get("discovery_id", "")).startswith("disc-exa-") for d in step_data)
    assert all(str(d.get("document_id", "")).startswith("doc-url-") for d in step_data)
    assert all(d.get("promotion_decision") == "ingested" for d in step_data)

    note_data = [e.data for e in events if e.kind == "note"]
    assert any(str(d.get("document_id", "")).startswith("doc-url-") for d in note_data)


@pytest.mark.asyncio
async def test_exa_reasoning_mode_consumes_context_at_dispatch_boundary(
    isolated_env, monkeypatch
):
    cli = _mock_exa_client(
        [{"results": [_exa_result("https://example.com/reasoned")]}]
    )
    _patch_ingest_url(
        monkeypatch,
        lambda url, **kwargs: FakeIngestResult(document_id="doc-url-reasoned"),
    )
    captured: dict[str, object] = {}

    def fake_dispatch(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            text=(
                '{"insights":[{"text":"Grounded finding",'
                '"source_document_ids":["doc-url-reasoned"]}],"questions":[]}'
            ),
            usage=NormalizedUsage(input_tokens=80, output_tokens=20),
            cost_usd=0.01,
            event_id="evt-reasoned",
        )

    loop_fn = make_exa_gather_loop(
        top_k=1,
        client=cli,
        legal_gate=_bypass_gate(),
        events_dir=isolated_env["events_dir"],
        enable_reasoning=True,
        reasoning_dispatch_fn=fake_dispatch,
    )
    runner = HostLocalRunner(
        loop_fn, events_dir=isolated_env["events_dir"], seal_on_complete=False
    )
    plan = ResearchPlan(investigation_id="leaf-reasoned", sub_question="reason this")
    handle = await runner.start(plan.investigation_id, plan)
    events = [event async for event in runner.stream(handle)]

    assert captured["context_pack_event_id"] is None
    assert "EXPLICIT RESEARCH QUESTION:\nreason this" in str(captured["prompt"])
    reasoned_notes = [
        event for event in events
        if event.kind == "note" and event.data.get("gather_mode") == "exa_reasoning"
    ]
    assert len(reasoned_notes) == 1
    assert reasoned_notes[0].text == "Grounded finding"
    assert reasoned_notes[0].data["document_id"] == "doc-url-reasoned"
    reasoning_steps = [
        event for event in events
        if event.kind == "step" and event.data.get("gather_mode") == "exa_reasoning"
    ]
    assert reasoning_steps[0].tokens == 100
    assert reasoning_steps[0].cost_usd == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_exa_reasoning_fails_when_ingested_sources_have_no_snippets(
    isolated_env, monkeypatch
):
    result = _exa_result("https://example.com/no-snippet")
    result.pop("text")
    cli = _mock_exa_client([{"results": [result]}])
    _patch_ingest_url(
        monkeypatch,
        lambda url, **kwargs: FakeIngestResult(document_id="doc-url-no-snippet"),
    )
    calls = 0

    def forbidden_dispatch(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("reasoning dispatch requires evidence")

    loop_fn = make_exa_gather_loop(
        top_k=1,
        client=cli,
        legal_gate=_bypass_gate(),
        events_dir=isolated_env["events_dir"],
        enable_reasoning=True,
        reasoning_dispatch_fn=forbidden_dispatch,
    )
    runner = HostLocalRunner(
        loop_fn, events_dir=isolated_env["events_dir"], seal_on_complete=False
    )
    plan = ResearchPlan(
        investigation_id="leaf-no-snippet", sub_question="reason this"
    )
    handle = await runner.start(plan.investigation_id, plan)
    events = [event async for event in runner.stream(handle)]

    assert calls == 0
    error = next(event for event in events if event.kind == "error")
    assert "requires substantive source snippets" in error.text


# ── M4(d): legal-gate reject path — no fabricated doc-url-* ──────────


class _RejectAllGate:
    """Legal gate that refuses every URL."""

    def check_url(self, url: str):
        from substrate.legal_gate import LegalGateVerdict

        return LegalGateVerdict(
            allowed=False, reason="test reject", gate_kind="placeholder"
        )


@pytest.mark.asyncio
async def test_exa_gather_loop_legal_reject_records_decision_no_doc(
    isolated_env, monkeypatch
):
    # ingest_url must NEVER be called when the gate rejects; wire it to blow up
    # so a regression that bypasses the gate is caught loudly.
    def exploding_ingest(*a, **k):
        raise AssertionError("ingest_url called despite legal-gate reject")

    _patch_ingest_url(monkeypatch, exploding_ingest)

    cli = _mock_exa_client([{"results": [_exa_result("https://blocked.example/x")]}])
    loop_fn = make_exa_gather_loop(
        top_k=2,
        client=cli,
        legal_gate=_RejectAllGate(),
        events_dir=isolated_env["events_dir"],
    )
    runner = HostLocalRunner(
        loop_fn, events_dir=isolated_env["events_dir"], seal_on_complete=False
    )
    plan = ResearchPlan(investigation_id="leaf-rej", sub_question="rejected topic")
    handle = await runner.start("leaf-rej", plan)
    events = [ev async for ev in runner.stream(handle)]

    step_data = [e.data for e in events if e.kind == "step"]
    assert len(step_data) == 1
    assert step_data[0]["promotion_decision"] == "rejected_by_legal_gate"
    assert step_data[0]["document_id"] is None

    # No promoted note carries a doc-url-* — nothing was ingested, so the loop
    # emits only the honest "no servable source" note (which has no document_id).
    note_data = [e.data for e in events if e.kind == "note"]
    assert all(not d.get("document_id") for d in note_data)
    assert any("no servable source" in e.text for e in events if e.kind == "note")


@pytest.mark.asyncio
async def test_exa_gather_loop_empty_proposals_is_graceful(isolated_env):
    cli = _mock_exa_client([{"results": []}])
    loop_fn = make_exa_gather_loop(
        top_k=3,
        client=cli,
        legal_gate=_bypass_gate(),
        events_dir=isolated_env["events_dir"],
    )
    runner = HostLocalRunner(
        loop_fn, events_dir=isolated_env["events_dir"], seal_on_complete=False
    )
    plan = ResearchPlan(investigation_id="leaf-empty", sub_question="nothing found")
    handle = await runner.start("leaf-empty", plan)
    events = [ev async for ev in runner.stream(handle)]

    assert not [e for e in events if e.kind == "step"]
    notes = [e for e in events if e.kind == "note"]
    assert len(notes) == 1
    assert "no servable source" in notes[0].text


# ── failure isolation: discover() raise fails the leaf cleanly ──────


@pytest.mark.asyncio
async def test_exa_gather_loop_discover_raise_fails_leaf_cleanly(
    isolated_env, monkeypatch
):
    """A ``discover``-level raise (e.g. ``DiscoveryBudgetExceeded`` from
    ``check_and_reserve``) must fail this single leaf cleanly: the runner
    catch-all marks it FAILED and emits an ``error`` event, and the loop
    NEVER reaches its promotion notes — so no fabricated ``doc-url-*``
    provenance is minted.

    The factory lazy-imports ``discover`` from ``acquisition.search.exa`` at
    call time, so patching the attribute on that module BEFORE building the
    loop is what the loop binds to.
    """
    from acquisition.search.exa import DiscoveryBudgetExceeded

    def raising_discover(*a, **k):
        raise DiscoveryBudgetExceeded("Exa daily budget exhausted (test)")

    # Patch BEFORE make_exa_gather_loop runs its lazy `from ... import discover`.
    monkeypatch.setattr("acquisition.search.exa.discover", raising_discover)

    # If discover raises, promotion must never run; wire ingest to blow up so a
    # regression that somehow reaches promotion is caught loudly.
    def exploding_ingest(*a, **k):
        raise AssertionError("ingest_url reached despite discover() raising")

    _patch_ingest_url(monkeypatch, exploding_ingest)

    loop_fn = make_exa_gather_loop(
        top_k=3,
        client=None,
        legal_gate=_bypass_gate(),
        events_dir=isolated_env["events_dir"],
    )
    runner = HostLocalRunner(
        loop_fn, events_dir=isolated_env["events_dir"], seal_on_complete=False
    )
    plan = ResearchPlan(investigation_id="leaf-raise", sub_question="budget blown")
    handle = await runner.start("leaf-raise", plan)
    events = [ev async for ev in runner.stream(handle)]

    # (b) The research surfaces the failure: the runner emits an `error`-kind
    # StepEvent carrying RunState.FAILED, and status() reports FAILED.
    from runtime.research_runner.protocol import RunState

    error_events = [e for e in events if e.kind == "error"]
    assert len(error_events) == 1
    assert error_events[0].state == RunState.FAILED
    assert "DiscoveryBudgetExceeded" in error_events[0].text
    assert runner.status(handle).state == RunState.FAILED

    # (a) NO step/note event carries a fabricated doc-url-* document_id — the
    # loop died before any promotion note. (It dies even before its first step.)
    for e in events:
        if e.kind in ("step", "note"):
            assert not str(e.data.get("document_id") or "").startswith("doc-url-")
    # And concretely: no promotion ever ran, so there are no exa step events.
    assert not [e for e in events if e.kind == "step"]


# ── M3 / M4(b): pack fidelity — doc-url-* not doc-gather-* ───────────


@pytest.mark.asyncio
async def test_exa_gather_pack_uses_doc_url_not_placeholder(graph_env, monkeypatch):
    seq = {"n": 0}

    def fake_ingest(url, **kwargs):
        seq["n"] += 1
        return FakeIngestResult(document_id=f"doc-url-pack{seq['n']:02d}")

    _patch_ingest_url(monkeypatch, fake_ingest)

    cli = _mock_exa_client(
        [
            {
                "results": [
                    _exa_result("https://example.com/one"),
                    _exa_result("https://example.com/two"),
                ]
            }
        ]
    )
    loop_fn = make_exa_gather_loop(
        top_k=2,
        client=cli,
        legal_gate=_bypass_gate(),
        db_path=graph_env["db"],
        events_dir=graph_env["events"],
    )

    tree = build_plan("pack fidelity problem", decomposer=_Dec(["sub q"])).tree
    root_id = persist_tree(
        tree,
        investigation_id="session-pack",
        embedding_provider=_FakeEmbedding(),
        db_path=graph_env["db"],
    )
    approve_plan(
        root_id, approver="operator", investigation_id="session-pack", db_path=graph_env["db"]
    )
    loaded = load_tree(root_id, db_path=graph_env["db"])
    leaves = [
        Leaf(
            investigation_id="leaf-pack-0",
            sub_question=c.question,
            question_node_id=c.graph_node_id,
        )
        for c in loaded.root.children
    ]

    funnel = PromotionFunnel(db_path=graph_env["db"], embedding_provider=_FakeEmbedding())
    runner = HostLocalRunner(
        loop_fn,
        events_dir=graph_env["events"],
        seal_on_complete=False,
        on_emit=funnel.submit,
    )
    session = CascadeSession(
        "session-pack",
        runner=runner,
        funnel=funnel,
        events_dir=graph_env["events"],
        db_path=graph_env["db"],
    )
    await session.launch(root_id, leaves)
    _ = [ev async for ev in session.stream()]
    await session.join_and_merge()

    pack = session.build_evidence_pack(plan_root_node_id=root_id)
    assert len(pack.chunks) >= 1
    assert all(c.document_id.startswith("doc-url-") for c in pack.chunks)
    assert not any(c.document_id.startswith("doc-gather-") for c in pack.chunks)

    # content_hash stable across two builds of the same session.
    rebuilt = build_session_evidence_pack(
        "session-pack",
        events_dir=graph_env["events"],
        db_path=graph_env["db"],
        researches=[("leaf-pack-0", "sub q")],
        plan_root_node_id=root_id,
    )
    assert rebuilt.content_hash == pack.content_hash
