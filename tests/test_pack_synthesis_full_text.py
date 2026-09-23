"""W5 provenance — the Path A synthesis handoff never cuts evidence silently.

``_investigation_context_from_pack`` built each sub-question's answer and each
supporting claim from ``chunk.text[:500]``. A source whose measurement sits
past its introduction lost the measurement on the way to the synthesizer,
while the context still said ``insufficient_evidence=False`` with no
evidentiary gap: the synthesis could not see what it was missing, and neither
could its reader.

The handoff now carries each cited chunk's full text. The only bound is the
synthesizer's declared context window (``context_budget_tokens`` of its
dispatch tier). When that bound forces a cut, the cut is spread max-min fairly
across chunks, lands on a word boundary so no figure is split, and every
truncated or omitted chunk is named in an ``evidentiary_gaps`` entry that says
how much was shown and how much was dropped.

These tests drive the real remote runner -> funnel -> pack -> Loop 1 context ->
Phase 6 synthesizer prompt path with a fake sandbox and a stub provider that
records the prompt; no paid provider is ever called.
"""

from __future__ import annotations

import json
import os

import pytest

from orchestration.loop_one.orchestrator import _investigation_context_from_pack
from orchestration.session_evidence_pack import (
    PackChunk,
    PackDocument,
    SessionEvidencePack,
    build_session_evidence_pack,
)
from processing.embedding import _reset_default_provider, set_default_embedding_provider
from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_write
from runtime.remote_exec import RemotePromotionFunnel, RemoteResearchRunner
from runtime.remote_exec.provider import RemoteStepEvent, Sandbox
from runtime.research_runner import BudgetCap, ResearchPlan
from substrate.dispatch import (
    DispatchConfig,
    NormalizedUsage,
    ProviderError,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.graph.schema import init_database_at_path

# An introduction long enough that the measurement and its qualification sit
# well past character 500 of the chunk.
_INTRO = (
    "Neutral atom platforms have drawn steady attention from laboratories and "
    "vendors over the past several years, and this report surveys the state of "
    "the field before turning to the numbers. "
) * 4
_MEASUREMENT = (
    "The measured two-qubit gate error rate was 0.00071 across 48 qubits, "
    "but only below 10 mK; above that temperature it rose to 0.0042."
)
_SOURCE = _INTRO + _MEASUREMENT
_NOTE = (
    "The measured two-qubit gate error rate was 0.00071 across 48 qubits "
    "below 10 mK."
)


@pytest.fixture
def emb():
    e = HashEmbedding()
    set_default_embedding_provider(e)
    yield e
    _reset_default_provider()


@pytest.fixture
def graph(tmp_path, monkeypatch, emb):
    db = str(tmp_path / "graph.duckdb")
    events = str(tmp_path / "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(tmp_path / "research"))
    monkeypatch.setenv("ANTIEK_KNOWLEDGE_SKILLS_DIR", str(tmp_path / "skills"))
    init_database_at_path(db)
    con = connect_write(db, purpose="seed")
    try:
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, "
            "document_type, content_class) VALUES ('doc-na', 'doc-na', 1, "
            "'paper', 'public_domain')"
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
            "embedding, token_count) VALUES (?, 'doc-na', 0, ?, ?, ?)",
            ["chunk-na-1", _SOURCE, emb.encode(_SOURCE), len(_SOURCE) // 4],
        )
    finally:
        con.close()
    reset_provider_registry()
    yield {"db": db, "events": events}
    reset_provider_registry()


class _NoteSandbox:
    name = "fake-sandbox"

    def probe(self) -> None:
        return None

    async def provision(self, plan):
        return Sandbox(sandbox_id="sbx-" + plan.investigation_id,
                       investigation_id=plan.investigation_id)

    async def run(self, sandbox, plan):
        yield RemoteStepEvent(seq=1, kind="note", text=_NOTE, provider=self.name,
                              data={"document_id": "doc-na"})

    async def steer(self, sandbox, command) -> None:
        return None

    async def teardown(self, sandbox) -> None:
        return None


async def _gathered_pack(graph: dict, emb) -> SessionEvidencePack:
    funnel = RemotePromotionFunnel(db_path=graph["db"], embedding_provider=emb)
    await funnel.start()
    runner = RemoteResearchRunner(
        _NoteSandbox(), events_dir=graph["events"], outbox_db_path=graph["db"],
        seal_on_complete=False, on_emit=funnel.submit,
    )
    h = await runner.start("inv-na", ResearchPlan("inv-na", "q?",
                                                  budget=BudgetCap(cost_usd=1.0)))
    _ = [e async for e in runner.stream(h)]
    await runner.join()
    await funnel.drain_and_stop()
    assert funnel.errors == []
    assert funnel.promoted_insights == 1
    pack = build_session_evidence_pack(
        "session-na", events_dir=graph["events"], db_path=graph["db"],
        researches=[("inv-na", "What is the neutral-atom gate error rate?")],
    )
    assert [(c.chunk_id, c.text) for c in pack.chunks] == [("chunk-na-1", _SOURCE)]
    return pack


class _RecordingSynth:
    """Stub synthesizer provider that records every prompt it is sent."""

    name = "recording-synth"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.prompts.append(prompt)
        if "senior investment analyst" not in prompt:
            raise ProviderError("only the synthesizer is stubbed",
                                provider=self.name, model=model, latency_ms=0)
        return RawProviderResponse(
            text=json.dumps({
                "thesis_summary": "The gate error rate holds only below 10 mK.",
                "implicit_recommendation": "conditional",
                "thesis_components": [{
                    "claim": "Trade reporting suggests the error rate is 0.00071 below 10 mK.",
                    "confidence": "moderate",
                    "confidence_basis": "one source",
                    "supporting_chunk_ids": ["chunk-na-1"],
                    "supporting_path_indices": [],
                    "effective_source_tier": 3,
                    "hedging_required": True,
                }],
                "falsification_conditions": [{
                    "condition": "Error rate above 0.001 below 10 mK",
                    "specific_observable": "a replicated benchmark",
                    "timeframe": "within 2 quarters",
                }],
                "execution_risks": [],
                "constraint_compliance": {
                    "hard_constraints_satisfied": True,
                    "soft_constraints_violated": [],
                    "violations_justified": [],
                },
                "reasoning_paths_used": [],
                "conviction_level": 0.5,
                "constraint_loop_status": "single_pass",
                "constraint_loop_iterations": 1,
            }),
            raw_usage={"input_tokens": 50, "output_tokens": 80},
            finish_reason="end_turn",
            latency_ms=3,
        )

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


def _patch_dispatch(monkeypatch, *, context_budget_tokens: int, max_tokens: int,
                    provider: str = "recording-synth") -> None:
    import substrate.dispatch.router as router

    tier = TierConfig(
        name="synthesis", provider=provider, model="stub", max_tokens=max_tokens,
        temperature=0.1, context_budget_tokens=context_budget_tokens,
        pricing=TierPricing(input_per_mtok=0.0, output_per_mtok=0.0),
        fallback=None,
    )
    config = DispatchConfig(
        role_tiers={"synthesizer": "synthesis", "knowledge_extractor": "synthesis"},
        tiers={"synthesis": tier},
    )
    monkeypatch.setattr(router.DispatchConfig, "from_yaml",
                        classmethod(lambda cls, path: config))


def _gaps(ctx) -> list[str]:
    return [g.gap_description for e in ctx.evidence for g in e.evidentiary_gaps]


# ---------------------------------------------------------------------------
# Codex repro: the measurement past character 500 reaches the synthesizer.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_measurement_past_char_500_reaches_the_synthesis_prompt(
    graph, emb, monkeypatch,
):
    """Remote runner -> funnel -> pack -> context -> Phase 6 prompt. The
    measurement and its qualification sit past character 500 of the cited
    chunk; both the context and the prompt the synthesizer is sent carry the
    whole chunk, and nothing is reported missing because nothing is."""
    assert _SOURCE.index(_MEASUREMENT) > 500
    pack = await _gathered_pack(graph, emb)

    ctx = _investigation_context_from_pack(pack)
    (ev,) = ctx.evidence
    assert ev.answer == _SOURCE
    assert [c.claim for c in ev.supporting_claims] == [_SOURCE]
    assert ev.insufficient_evidence is False
    assert ev.evidentiary_gaps == []

    from interfaces.research.api import EventBroadcaster
    from interfaces.research.api.synthesizer import register_handlers as register_synth
    from orchestration.loop_one import register_handlers, run_synthesis_tail_from_pack

    _patch_dispatch(monkeypatch, context_budget_tokens=256_000, max_tokens=16_384)
    synth = _RecordingSynth()
    register_provider(synth)
    bus = EventBroadcaster()
    register_synth(bus)
    coordinator = register_handlers(bus)
    await run_synthesis_tail_from_pack(pack, broadcaster=bus, coordinator=coordinator)

    synth_prompts = [p for p in synth.prompts if "senior investment analyst" in p]
    assert synth_prompts, "the synthesizer was dispatched"
    prompt = synth_prompts[0]
    assert "0.00071 across 48 qubits" in prompt
    assert "above that temperature it rose to 0.0042" in prompt
    assert "truncated" not in prompt


# ---------------------------------------------------------------------------
# A real budget that forces a cut: never silent.
# ---------------------------------------------------------------------------


def _pack(texts: dict[str, str]) -> SessionEvidencePack:
    return SessionEvidencePack(
        session_id="session-budget",
        problem_question="q?",
        chunks=[
            PackChunk(chunk_id=cid, document_id="doc-b", ip_holder_id=None,
                      text=text, source_investigation_id="leaf-b",
                      sub_question="sq")
            for cid, text in texts.items()
        ],
        documents=[PackDocument(document_id="doc-b", title="d", ip_holder_id=None)],
        leaf_investigation_ids=["leaf-b"],
    )


def _words(n: int, tag: str) -> str:
    return " ".join(f"{tag}{i:04d}" for i in range(n))


_TEXTS = {
    "chunk-short": _words(10, "s"),     # 59 chars
    "chunk-mid": _words(60, "m"),       # 359 chars
    "chunk-long": _words(400, "l"),     # 2399 chars
}


def _assert_every_cut_is_named(ctx, texts: dict[str, str]) -> None:
    """The invariant: each chunk reaches the synthesizer whole, or an
    evidentiary gap names it with exactly how much was shown and dropped; a
    shown part is a verbatim prefix ending on a word boundary."""
    claims = {c.chunk_ids[0]: c for e in ctx.evidence for c in e.supporting_claims}
    gaps = _gaps(ctx)
    for cid, text in texts.items():
        named = [g for g in gaps if cid in g]
        claim = claims.get(cid)
        if claim is not None and claim.claim == text:
            assert named == [], f"{cid} is whole but a gap names it"
            continue
        assert len(named) == 1, f"{cid} was cut without a gap: {gaps}"
        shown = len(claim.claim) if claim is not None else 0
        assert f"{shown} of {len(text)} characters" in named[0]
        assert f"{len(text) - shown} dropped" in named[0]
        if claim is None:
            continue
        assert text.startswith(claim.claim)
        assert text[len(claim.claim)] == " ", "the cut split a word"
        assert "truncated" in claim.confidence_basis
        answer = "\n".join(e.answer for e in ctx.evidence)
        assert f"[{cid}: truncated" in answer


@pytest.mark.parametrize("budget", [0, 40, 120, 500, 900, 1500, 2816, 2817, 10_000])
def test_every_truncation_is_recorded_as_a_gap(budget):
    ctx = _investigation_context_from_pack(_pack(_TEXTS), evidence_char_budget=budget)
    _assert_every_cut_is_named(ctx, _TEXTS)
    shown = sum(len(c.claim) for e in ctx.evidence for c in e.supporting_claims)
    assert shown <= budget


def test_a_cut_falls_on_the_longest_chunk_first():
    """Max-min fair: chunks that fit their share stay whole, and the chunk
    too long for its share is the one cut, not whichever came first. The
    long chunk comes first in the pack, so a first-come allotment would spend
    the budget on it and drop the short ones."""
    first_long = {k: _TEXTS[k] for k in ("chunk-long", "chunk-mid", "chunk-short")}
    ctx = _investigation_context_from_pack(_pack(first_long), evidence_char_budget=1500)
    claims = {c.chunk_ids[0]: c.claim for e in ctx.evidence for c in e.supporting_claims}
    assert claims["chunk-short"] == _TEXTS["chunk-short"]
    assert claims["chunk-mid"] == _TEXTS["chunk-mid"]
    assert 0 < len(claims["chunk-long"]) < len(_TEXTS["chunk-long"])
    # The shares the short chunks did not need go to the long one: it gets
    # the whole remainder, less at most one word backed off at the cut.
    spare = 1500 - len(_TEXTS["chunk-short"]) - len(_TEXTS["chunk-mid"])
    assert spare - 6 <= len(claims["chunk-long"]) <= spare
    (gap,) = _gaps(ctx)
    assert "chunk-long" in gap
    assert ctx.evidence[0].insufficient_evidence is False


def test_nothing_fits_is_insufficient_evidence_with_each_chunk_named():
    ctx = _investigation_context_from_pack(_pack(_TEXTS), evidence_char_budget=0)
    (ev,) = ctx.evidence
    assert ev.supporting_claims == []
    assert ev.insufficient_evidence is True
    for cid, text in _TEXTS.items():
        assert any(cid in g and f"0 of {len(text)} characters" in g for g in _gaps(ctx))


def test_a_cut_never_splits_a_figure():
    """A prefix cut mid-number would put a different figure in the source's
    mouth ("0.00071" -> "0.000"). The cut backs off to a word boundary."""
    text = "The error rate was 0.00071 across 48 qubits."
    budget = text.index("0.00071") + 4
    ctx = _investigation_context_from_pack(_pack({"chunk-fig": text}),
                                           evidence_char_budget=budget)
    presented = [c.claim for e in ctx.evidence for c in e.supporting_claims]
    assert presented == ["The error rate was"]

    # A budget that ends exactly on a word boundary keeps that last word.
    budget = text.index(" across")
    ctx = _investigation_context_from_pack(_pack({"chunk-fig": text}),
                                           evidence_char_budget=budget)
    presented = [c.claim for e in ctx.evidence for c in e.supporting_claims]
    assert presented == ["The error rate was 0.00071"]


def test_budget_comes_from_the_synthesizer_context_window(monkeypatch):
    """Without an explicit budget the handoff reads the synthesizer role's
    dispatch tier: a tiny window forces a cut, and the cut is named."""
    _patch_dispatch(monkeypatch, context_budget_tokens=1_500, max_tokens=1_000)
    ctx = _investigation_context_from_pack(_pack(_TEXTS))
    assert _gaps(ctx), "a 500-token input window cannot hold 2,800 characters twice"
    _assert_every_cut_is_named(ctx, _TEXTS)


def test_an_unreadable_synthesizer_config_still_bounds_and_names_the_cut(monkeypatch):
    """A config the router cannot read falls back to the router's own tier
    defaults (32,000 context, 4,096 output tokens), never to no bound."""
    import substrate.dispatch.router as router

    def _broken(cls, path):
        raise OSError("config.yaml unreadable")

    monkeypatch.setattr(router.DispatchConfig, "from_yaml", classmethod(_broken))
    texts = {f"chunk-{i}": _words(1_700, f"x{i}") for i in range(3)}
    assert sum(len(t) for t in texts.values()) > 20_928
    ctx = _investigation_context_from_pack(_pack(texts))
    assert len(_gaps(ctx)) == 3
    _assert_every_cut_is_named(ctx, texts)
    shown = sum(len(c.claim) for e in ctx.evidence for c in e.supporting_claims)
    assert 20_000 < shown <= 20_928


def test_production_window_carries_forty_full_chunks():
    """The production ``config.yaml`` synthesizer window carries forty
    4,000-character chunks (the funnel's largest citable chunk) whole."""
    big = {f"chunk-{i:02d}": _words(666, f"w{i:02d}")[:4000].rsplit(" ", 1)[0]
           for i in range(40)}
    assert all(len(t) > 3_900 for t in big.values())
    ctx = _investigation_context_from_pack(_pack(big))
    assert _gaps(ctx) == []
    claims = {c.chunk_ids[0]: c.claim for e in ctx.evidence for c in e.supporting_claims}
    assert claims == big
