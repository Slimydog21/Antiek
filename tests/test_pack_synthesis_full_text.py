"""W5 provenance — the Path A synthesis handoff never cuts evidence silently.

``_investigation_context_from_pack`` built each sub-question's answer and each
supporting claim from ``chunk.text[:500]``. A source whose measurement sits
past its introduction lost the measurement on the way to the synthesizer,
while the context still said ``insufficient_evidence=False`` with no
evidentiary gap: the synthesis could not see what it was missing, and neither
could its reader.

The handoff now carries each cited chunk's full text. The only bound is the
synthesizer's declared context window (``context_budget_tokens`` of its
dispatch tier, less its ``max_tokens``), measured against the prompt Phase 6
actually sends: the evidence block as Phase 6 serializes it (``json.dumps``
with ASCII escaping, so a CJK character travels as a six-character
``\\uXXXX`` escape), truncation markers and gap entries included, inside the
rendered synthesizer prompt. The count is the prompt's UTF-8 byte length, an
upper bound for any tokenizer whose every token spells at least one byte (a
per-character estimate is not: token-dense ASCII runs near a token a
character). What the synthesizer bridge may add on a later dispatch, the
self-repair error and the constraint-loop violation list, is clipped to the
byte room the handoff reserved for it. When that bound forces a cut, the cut is spread
max-min fairly across chunks, lands on a clean boundary so no figure is split,
and every truncated or omitted chunk is named in an ``evidentiary_gaps`` entry
that says how much was shown and how much was dropped. A pack none of whose
chunks fits fails closed before the synthesizer is dispatched.

These tests drive the real remote runner -> funnel -> pack -> Loop 1 context ->
Phase 6 synthesizer prompt path with a fake sandbox and a stub provider that
records the prompt; no paid provider is ever called.
"""

from __future__ import annotations

import dataclasses
import json
import os
import random
import re
import string
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestration.loop_one.orchestrator import (
    _CHAT_TEMPLATE_TOKENS,
    _PROMPT_PREFIX_RESERVE_TOKENS,
    _allot_pack_text,
    _evidence_block,
    _investigation_context_from_pack,
    _prompt_token_ceiling,
    _synthesis_frame_blocks,
)
from orchestration.session_evidence_pack import (
    PackChunk,
    PackDocument,
    SessionEvidencePack,
    build_session_evidence_pack,
)
from processing.embedding import _reset_default_provider, set_default_embedding_provider
from processing.embedding.embed import HashEmbedding
from roles.synthesizer.prompt import (
    PREFIX_RESERVE_BYTES,
    REPAIR_PREFIX_MAX_BYTES,
    REVISION_PREFIX_MAX_BYTES,
    build_repair_prefix,
    build_revision_prefix,
    render_full_prompt,
)
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
# A real budget that forces a cut: never silent, never past the window.
# ---------------------------------------------------------------------------

# The production synthesis tier (substrate/dispatch/config.yaml): a 256,000
# token window less 16,384 reserved for the answer.
_PROD_INPUT_TOKENS = 256_000 - 16_384


def _pack(texts: dict[str, str], *, doc: str = "doc-b",
          leaf: str = "leaf-b") -> SessionEvidencePack:
    return SessionEvidencePack(
        session_id="session-budget",
        problem_question="q?",
        chunks=[
            PackChunk(chunk_id=cid, document_id=doc, ip_holder_id=None,
                      text=text, source_investigation_id=leaf,
                      sub_question="sq")
            for cid, text in texts.items()
        ],
        documents=[PackDocument(document_id=doc, title="d", ip_holder_id=None)],
        leaf_investigation_ids=[leaf],
    )


def _words(n: int, tag: str) -> str:
    return " ".join(f"{tag}{i:04d}" for i in range(n))


def _prose(n_chars: int, seed: str = "") -> str:
    base = (
        f"{seed}Neutral atom platforms have drawn steady attention from "
        "laboratories and vendors over the past several years and this report "
        "surveys the state of the field. "
    ) * (n_chars // 100 + 2)
    return base[:n_chars].rsplit(" ", 1)[0]


def _frame_tokens(ctx) -> int:
    from roles.synthesizer.prompt import render_full_prompt

    return _prompt_token_ceiling(
        render_full_prompt(evidence_block="", **_synthesis_frame_blocks(ctx)),
    )


def _window_for(pack: SessionEvidencePack, evidence_tokens: int) -> int:
    """The input window that leaves ``evidence_tokens`` for the evidence."""
    ctx = _investigation_context_from_pack(pack, input_tokens=10**9)
    return _frame_tokens(ctx) + _PROMPT_PREFIX_RESERVE_TOKENS + evidence_tokens


def _sent_prompt(ctx) -> str:
    """The first synthesizer prompt Phase 6 renders for ``ctx``."""
    from roles.synthesizer.prompt import render_full_prompt

    return render_full_prompt(
        evidence_block=_evidence_block(ctx.evidence), **_synthesis_frame_blocks(ctx),
    )


_TEXTS = {
    "chunk-short": _words(10, "s"),     # 59 chars
    "chunk-mid": _words(60, "m"),       # 359 chars
    "chunk-long": _words(400, "l"),     # 2399 chars
}


def _assert_every_cut_is_named(ctx, texts: dict[str, str]) -> None:
    """The invariant: each chunk reaches the synthesizer whole, or an
    evidentiary gap names it with exactly how much was shown and dropped; a
    shown part is a verbatim prefix that does not end inside a word."""
    claims = {c.chunk_ids[0]: c for e in ctx.evidence for c in e.supporting_claims}
    gaps = _gaps(ctx)
    for cid, text in texts.items():
        named = [g for g in gaps if f"Chunk {cid} " in g]
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
        assert "truncated" in claim.confidence_basis
        answer = "\n".join(e.answer for e in ctx.evidence)
        assert f"[{cid}: truncated" in answer


def _assert_within_window(ctx, window: int) -> None:
    """What Phase 6 sends fits the window with the prefix reserve kept."""
    assert _prompt_token_ceiling(_sent_prompt(ctx)) <= (
        window - _PROMPT_PREFIX_RESERVE_TOKENS
    )


@pytest.mark.parametrize("evidence_tokens", [0, 150, 400, 700, 1_000, 1_500,
                                             2_500, 4_000, 100_000])
def test_every_truncation_is_recorded_as_a_gap(evidence_tokens):
    pack = _pack(_TEXTS)
    window = _window_for(pack, evidence_tokens)
    ctx = _investigation_context_from_pack(pack, input_tokens=window)
    _assert_every_cut_is_named(ctx, _TEXTS)
    for cid, text in _TEXTS.items():
        claim = next((c.claim for e in ctx.evidence for c in e.supporting_claims
                      if c.chunk_ids == [cid]), "")
        if claim and claim != text:
            assert text[len(claim)] == " ", "the cut split a word"
    if any(e.supporting_claims for e in ctx.evidence):
        _assert_within_window(ctx, window)
    else:
        assert all(e.insufficient_evidence for e in ctx.evidence)


def test_a_cut_falls_on_the_longest_chunk_first():
    """Max-min fair: chunks that fit their share stay whole, and the chunk
    too long for its share is the one cut, not whichever came first. The
    long chunk comes first in the pack, so a first-come allotment would spend
    the budget on it and drop the short ones."""
    first_long = {k: _TEXTS[k] for k in ("chunk-long", "chunk-mid", "chunk-short")}
    pack = _pack(first_long)
    window = _window_for(pack, 4_000)
    ctx = _investigation_context_from_pack(pack, input_tokens=window)
    claims = {c.chunk_ids[0]: c.claim for e in ctx.evidence for c in e.supporting_claims}
    assert claims["chunk-short"] == _TEXTS["chunk-short"]
    assert claims["chunk-mid"] == _TEXTS["chunk-mid"]
    assert 0 < len(claims["chunk-long"]) < len(_TEXTS["chunk-long"])
    (gap,) = _gaps(ctx)
    assert "chunk-long" in gap
    assert ctx.evidence[0].insufficient_evidence is False
    _assert_within_window(ctx, window)


def test_nothing_fits_is_insufficient_evidence_with_each_chunk_named():
    pack = _pack(_TEXTS)
    ctx = _investigation_context_from_pack(pack, input_tokens=_window_for(pack, 0))
    (ev,) = ctx.evidence
    assert ev.supporting_claims == []
    assert ev.insufficient_evidence is True
    for cid, text in _TEXTS.items():
        assert any(cid in g and f"0 of {len(text)} characters" in g for g in _gaps(ctx))


def test_a_cut_never_splits_a_figure():
    """A prefix cut mid-number would put a different figure in the source's
    mouth ("0.00071" -> "0.000", "四十八" -> "四"). The cut backs off to a
    clean boundary; a CJK text, written without spaces, can still be cut
    between two ideographs."""
    text = "The error rate was 0.00071 across 48 qubits."
    assert _allot_pack_text([text], text.index("0.00071") + 4) == ["The error rate was"]
    # A budget that ends exactly on a word boundary keeps that last word.
    assert _allot_pack_text([text], text.index(" across")) == [
        "The error rate was 0.00071",
    ]
    zh = "测得的错误率为0.00071，覆盖四十八个量子比特。"
    assert _allot_pack_text([zh], zh.index("0.00071") + 3) == ["测得的错误率为"]
    assert _allot_pack_text([zh], zh.index("四十八") + 2) == ["测得的错误率为0.00071，覆盖"]
    assert _allot_pack_text([zh], zh.index("个") + 2) == ["测得的错误率为0.00071，覆盖四十八个量"]
    # A combining mark stays with its base letter.
    decomposed = "café au lait"
    assert _allot_pack_text([decomposed], 4) == [""]


def test_the_token_ceiling_counts_what_the_synthesizer_is_sent():
    """The ceiling is the UTF-8 byte length: an escape costs its 6 bytes, a
    non-ASCII character its UTF-8 bytes, and a letter one, like a digit."""
    assert _prompt_token_ceiling(json.dumps("中")) == 2 + 6  # quotes + escape
    assert _prompt_token_ceiling("0.00071") == 7
    assert _prompt_token_ceiling("abc def") == 7
    assert _prompt_token_ceiling("é") == 2
    assert _prompt_token_ceiling("") == 0


def test_budget_comes_from_the_synthesizer_context_window(monkeypatch):
    """Without an explicit window the handoff reads the synthesizer role's
    dispatch tier: a tiny window forces a cut, and the cut is named."""
    window = _window_for(_pack(_TEXTS), 3_000)
    _patch_dispatch(monkeypatch, context_budget_tokens=window + 1_000,
                    max_tokens=1_000)
    ctx = _investigation_context_from_pack(_pack(_TEXTS))
    assert _gaps(ctx), "3,000 tokens cannot hold 2,817 characters twice"
    assert any(e.supporting_claims for e in ctx.evidence)
    _assert_every_cut_is_named(ctx, _TEXTS)
    _assert_within_window(ctx, window)


def test_an_unreadable_synthesizer_config_still_bounds_and_names_the_cut(monkeypatch):
    """A config the router cannot read falls back to the router's own tier
    defaults (32,000 context, 4,096 output tokens), never to no bound."""
    import substrate.dispatch.router as router

    def _broken(cls, path):
        raise OSError("config.yaml unreadable")

    monkeypatch.setattr(router.DispatchConfig, "from_yaml", classmethod(_broken))
    texts = {f"chunk-{i}": _prose(12_000, f"x{i} ") for i in range(3)}
    ctx = _investigation_context_from_pack(_pack(texts))
    assert len(_gaps(ctx)) == 3
    _assert_every_cut_is_named(ctx, texts)
    _assert_within_window(ctx, 32_000 - 4_096)
    # What the synthesizer prompt and the retry reserve leave of 27,904 tokens
    # at a token a byte, each shown character counted twice (answer, claim).
    claims = [c.claim for e in ctx.evidence for c in e.supporting_claims]
    assert len(claims) == 3 and sum(map(len, claims)) > 2_000


def test_production_window_carries_twenty_six_full_chunks():
    """The production ``config.yaml`` synthesizer window carries twenty-six
    4,000-character prose chunks (the funnel's largest citable chunk) whole.
    Each chunk travels twice (answer and claim) at a token a byte, so a
    forty-chunk pack is cut, and every cut is named."""
    big = {f"chunk-{i:02d}": _prose(4_000, f"w{i:02d} ") for i in range(40)}
    assert all(len(t) > 3_900 for t in big.values())
    whole = dict(list(big.items())[:26])
    ctx = _investigation_context_from_pack(_pack(whole))
    assert _gaps(ctx) == []
    claims = {c.chunk_ids[0]: c.claim for e in ctx.evidence for c in e.supporting_claims}
    assert claims == whole
    _assert_within_window(ctx, _PROD_INPUT_TOKENS)

    ctx = _investigation_context_from_pack(_pack(big))
    assert _gaps(ctx)
    _assert_every_cut_is_named(ctx, big)
    _assert_within_window(ctx, _PROD_INPUT_TOKENS)


# ---------------------------------------------------------------------------
# Codex round-2 repro: escaping and metadata count against the window.
# ---------------------------------------------------------------------------

# 3,600 characters of Chinese carrying the figures a cut must not split.
_ZH = (
    "中性原子平台在过去几年受到实验室和供应商的持续关注。"
    "测得的双量子比特门错误率为0.00071，覆盖四十八个量子比特，"
    "但仅在10 mK以下成立；高于该温度时升至0.0042。"
) * 60
_ZH = _ZH[:3_600]
_ZH_FIGURES = ("0.00071", "四十八", "0.0042", "10 mK")


def _assert_no_figure_split(shown: str, text: str) -> None:
    for fig in _ZH_FIGURES:
        for m in re.finditer(re.escape(fig), text):
            assert not m.start() < len(shown) < m.end(), (
                f"the cut at {len(shown)} splits {fig!r}"
            )


def test_non_ascii_evidence_is_budgeted_as_phase_6_escapes_it():
    """Forty 3,600-character Chinese chunks are 144,000 characters of text,
    well inside a character budget, but Phase 6 sends each character as a
    six-character ``\\uXXXX`` escape, twice (answer and claim): 1.7 million
    characters, past the production window. The handoff measures the
    serialized block, so it cuts, names every cut, keeps each shown part a
    verbatim prefix that splits no figure, and what Phase 6 sends fits."""
    texts = {f"chunk-zh-{i:02d}": _ZH for i in range(40)}
    pack = _pack(texts)
    ctx = _investigation_context_from_pack(pack, input_tokens=_PROD_INPUT_TOKENS)

    assert len(_gaps(ctx)) == 40
    _assert_every_cut_is_named(ctx, texts)
    claims = [c.claim for e in ctx.evidence for c in e.supporting_claims]
    assert len(claims) == 40 and all(claims), "every chunk is still shown in part"
    for shown in claims:
        _assert_no_figure_split(shown, _ZH)
    _assert_within_window(ctx, _PROD_INPUT_TOKENS)
    prompt = _sent_prompt(ctx)
    assert "\\u" in prompt, "the prompt carries the escapes that were budgeted"
    # The reviewer's own measure (three characters a token) also fits.
    assert len(prompt) / 3 <= _PROD_INPUT_TOKENS


def test_metadata_heavy_evidence_is_budgeted_with_its_ids_and_gaps():
    """Short chunks behind long identifiers: the chunk text is a small part
    of what Phase 6 sends; the chunk ids, document ids, leaf ids, confidence
    bases and gap entries are most of it. A budget over chunk text alone
    passes all of it; the handoff measures the whole block."""
    long_id = "x" * 100
    texts = {f"chunk-{long_id}-{i:03d}": _prose(300, f"r{i} ") for i in range(60)}
    pack = _pack(texts, doc=f"doc-{long_id}", leaf=f"leaf-{long_id}")
    text_chars = sum(len(t) for t in texts.values())
    window = _window_for(pack, 50_000)
    # A text-only budget, even at a token a character, each shown twice.
    assert text_chars * 2 < 50_000, "a text-only budget would show every chunk"

    ctx = _investigation_context_from_pack(pack, input_tokens=window)
    _assert_every_cut_is_named(ctx, texts)
    assert _gaps(ctx), "the ids and gap entries do not fit whole"
    _assert_within_window(ctx, window)
    # Cutting all sixty equal chunks a little would add a marker and a gap
    # to every one of them; omitting some whole keeps the rest whole.
    claims = [c.claim for e in ctx.evidence for c in e.supporting_claims]
    assert len(claims) >= 20
    assert all(claim in texts.values() for claim in claims)


async def _run_tail(pack, monkeypatch, *, context_budget_tokens: int,
                    max_tokens: int,
                    synth: _RecordingSynth | None = None,
                    ) -> tuple[object, _RecordingSynth]:
    from interfaces.research.api import EventBroadcaster
    from interfaces.research.api.synthesizer import register_handlers as register_synth
    from orchestration.loop_one import register_handlers, run_synthesis_tail_from_pack

    _patch_dispatch(monkeypatch, context_budget_tokens=context_budget_tokens,
                    max_tokens=max_tokens)
    synth = synth or _RecordingSynth()
    register_provider(synth)
    bus = EventBroadcaster()
    register_synth(bus)
    coordinator = register_handlers(bus)
    ctx = await run_synthesis_tail_from_pack(
        pack, broadcaster=bus, coordinator=coordinator,
    )
    return ctx, synth


@pytest.mark.asyncio
async def test_every_prompt_phase_6_sends_fits_the_window(graph, monkeypatch):
    """End to end: the Chinese pack goes through Phase 6 on the production
    window, and every prompt the synthesizer is actually sent (the first and
    any self-repair retry) fits it."""
    texts = {f"chunk-zh-{i:02d}": _ZH for i in range(40)}
    _ctx, synth = await _run_tail(_pack(texts), monkeypatch,
                                  context_budget_tokens=256_000, max_tokens=16_384)
    prompts = [p for p in synth.prompts if "senior investment analyst" in p]
    assert prompts, "the synthesizer was dispatched"
    for prompt in prompts:
        assert _prompt_token_ceiling(prompt) <= _PROD_INPUT_TOKENS
        assert "truncated" in prompt


@pytest.mark.asyncio
async def test_a_pack_that_cannot_fit_fails_closed_before_dispatch(graph, monkeypatch):
    """When even naming every chunk as omitted overflows the window, no
    prompt is sent: the tail fails at phase 6 and says why."""
    long_id = "y" * 180
    texts = {f"chunk-{long_id}-{i:03d}": _prose(400) for i in range(80)}
    pack = _pack(texts, doc=f"doc-{long_id}", leaf=f"leaf-{long_id}")
    window = _window_for(pack, 500)
    ctx, synth = await _run_tail(pack, monkeypatch,
                                 context_budget_tokens=window + 1_000, max_tokens=1_000)
    assert [p for p in synth.prompts if "senior investment analyst" in p] == []
    assert ctx.failed_phase == 6
    assert "none of the 80 gathered chunks fits" in ctx.fail_reason


# ---------------------------------------------------------------------------
# Codex round-3 repro: token-dense text is counted by an independent oracle,
# and a retry can add no more than the room the handoff reserved.
# ---------------------------------------------------------------------------

_DEBERTA = "models--MoritzLaurer--DeBERTa-v3-base-mnli-fever-anli"


def _dense_texts(n: int = 80, size: int = 3_999) -> dict[str, str]:
    """Random ASCII letters: no word a tokenizer has merged, so near a token
    a character, far above any per-character average."""
    rng = random.Random(20260924)
    return {
        f"chunk-dense-{i:02d}": "".join(rng.choices(string.ascii_letters, k=size))
        for i in range(n)
    }


def _byte_level_worst_case():
    """An independent counting oracle: a byte-level BPE with no merges, built
    with the ``tokenizers`` library. It spells every byte as its own token,
    the most tokens any byte-level BPE (DeepSeek, GLM, MiMo) can produce."""
    tokenizers = pytest.importorskip("tokenizers")
    from tokenizers import models, pre_tokenizers

    alphabet = sorted(pre_tokenizers.ByteLevel.alphabet())
    tk = tokenizers.Tokenizer(
        models.BPE(vocab={ch: i for i, ch in enumerate(alphabet)}, merges=[]),
    )
    tk.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    return tk


def _cached_deberta():
    """A real SentencePiece tokenizer from the local Hugging Face cache; the
    test that needs it skips when the cache does not hold it."""
    tokenizers = pytest.importorskip("tokenizers")
    home = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")
    found = sorted((home / "hub").glob(f"{_DEBERTA}/snapshots/*/tokenizer.json"))
    if not found:
        pytest.skip("no cached DeBERTa-v3 tokenizer to count with")
    return tokenizers.Tokenizer.from_file(str(found[0]))


def _dense_context():
    texts = _dense_texts()
    ctx = _investigation_context_from_pack(_pack(texts), input_tokens=_PROD_INPUT_TOKENS)
    return texts, ctx


def test_token_dense_ascii_fits_the_window_by_an_independent_count():
    """Eighty chunks of 3,999 random letters on the production window. The
    handoff cuts, names every cut, and the prompt Phase 6 sends fits the
    window with the retry reserve kept, counted by a byte-level tokenizer
    that is not the handoff's own arithmetic."""
    texts, ctx = _dense_context()
    assert _gaps(ctx), "640,000 characters of dense text cannot fit whole"
    _assert_every_cut_is_named(ctx, texts)
    assert any(e.supporting_claims for e in ctx.evidence)
    prompt = _sent_prompt(ctx)
    counted = len(_byte_level_worst_case().encode(prompt).ids)
    assert counted <= _prompt_token_ceiling(prompt)
    assert counted <= _PROD_INPUT_TOKENS - _PROMPT_PREFIX_RESERVE_TOKENS


def test_token_dense_ascii_is_within_the_ceiling_for_a_real_tokenizer():
    """The same prompt through a real SentencePiece tokenizer: its count is
    within the ceiling, and above what three characters a token would say,
    which is why the ceiling is not a per-character average."""
    _texts, ctx = _dense_context()
    prompt = _sent_prompt(ctx)
    counted = len(_cached_deberta().encode(prompt).ids)
    assert counted <= _prompt_token_ceiling(prompt)
    assert counted > len(prompt) // 3


@pytest.mark.parametrize("error", [
    "top: implicit_recommendation 'maybe' not in the allowed set",
    "top: implicit_recommendation '" + "9" * 10_000 + "' not in the allowed set",
    "说明" * 4_000,
    "é" * 1_500 + "x",
    "é" * 3_000 + "x",
])
def test_the_repair_prefix_is_clipped_to_its_bound(error):
    """The parse error a self-repair retry prepends can quote the response
    verbatim. It is clipped to ``REPAIR_PREFIX_MAX_BYTES`` at a character
    boundary, and the marker says exactly how many characters were dropped."""
    prefix = build_repair_prefix(error)
    assert len(prefix.encode("utf-8")) <= REPAIR_PREFIX_MAX_BYTES
    assert prefix.endswith("----\n\n")
    start = prefix.index(":\n\n    ") + len(":\n\n    ")
    marker = re.search(r" \[\.\.\. (\d+) more characters of the error not shown\]", prefix)
    unclipped = len(error.encode("utf-8")) + len(build_repair_prefix("").encode("utf-8"))
    if unclipped <= REPAIR_PREFIX_MAX_BYTES:
        assert marker is None
        assert prefix[start:].startswith(error)
        return
    assert marker is not None
    shown = prefix[start:marker.start()]
    assert shown and error.startswith(shown)
    assert len(shown) + int(marker.group(1)) == len(error)


def test_a_revision_and_its_repair_add_no_more_than_the_reserve():
    """The worst a later dispatch of the same request can add: a
    constraint-loop revision carrying an oversized violation list, whose own
    parse failure prepends an oversized repair error. Together they add at
    most ``PREFIX_RESERVE_BYTES`` to the first prompt, the room the handoff
    keeps (with the chat-template allowance) out of the window."""
    blocks = {
        "question": "q?", "decomposition_block": "d", "evidence_block": "e",
        "parameters_block": "p", "substrate_block": "s",
    }
    first = render_full_prompt(**blocks)
    violations = [
        SimpleNamespace(constraint_id=f"c{i}", constraint_kind="k",
                        strictness="hard", reason="超" * 2_000,
                        target_claim_id=f"claim-{i}")
        for i in range(50)
    ]
    revision = build_revision_prefix(violations)
    assert len(revision.encode("utf-8")) <= REVISION_PREFIX_MAX_BYTES
    assert "more characters of the violation list not shown" in revision
    assert "constraint='c0'" in revision
    revised = render_full_prompt(**blocks, extra_user_prefix=revision)
    retry = build_repair_prefix("9" * 10_000) + revised
    added = len(retry.encode("utf-8")) - len(first.encode("utf-8"))
    assert added <= PREFIX_RESERVE_BYTES
    assert _PROMPT_PREFIX_RESERVE_TOKENS == PREFIX_RESERVE_BYTES + _CHAT_TEMPLATE_TOKENS


class _OversizedErrorSynth(_RecordingSynth):
    """The first synthesizer answer names a 10,000-digit recommendation. The
    parser quotes it back in its error, and the bridge prepends that error to
    the one self-repair retry."""

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        resp = super().call(model=model, prompt=prompt, max_tokens=max_tokens,
                            temperature=temperature)
        if sum("senior investment analyst" in p for p in self.prompts) != 1:
            return resp
        answer = json.loads(resp.text)
        answer["implicit_recommendation"] = "9" * 10_000
        return dataclasses.replace(resp, text=json.dumps(answer))


@pytest.mark.asyncio
async def test_a_self_repair_retry_with_an_oversized_error_fits_the_window(
    graph, monkeypatch,
):
    """Codex repro: the Chinese pack fills the production window, the first
    answer fails the parser with a 10,000-digit value, and the retry prompt
    carries the error. Every prompt the synthesizer is sent, the retry
    included, fits the window."""
    texts = {f"chunk-zh-{i:02d}": _ZH for i in range(40)}
    _ctx, synth = await _run_tail(_pack(texts), monkeypatch,
                                  context_budget_tokens=256_000, max_tokens=16_384,
                                  synth=_OversizedErrorSynth())
    prompts = [p for p in synth.prompts if "senior investment analyst" in p]
    assert len(prompts) >= 2, "the oversized answer was retried"
    first, retry = prompts[0], prompts[1]
    assert "more characters of the error not shown" in retry
    # The first prompt fills the window, so an unclipped error would overflow it.
    room = _PROD_INPUT_TOKENS - _CHAT_TEMPLATE_TOKENS - _prompt_token_ceiling(first)
    assert room < 10_000 + REPAIR_PREFIX_MAX_BYTES
    for prompt in prompts:
        assert _prompt_token_ceiling(prompt) + _CHAT_TEMPLATE_TOKENS <= _PROD_INPUT_TOKENS
