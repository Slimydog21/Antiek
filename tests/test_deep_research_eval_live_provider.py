"""Offline tests for the live ``ProviderFn`` adapter (``live_provider.py``)
plus the runner's typed per-query fail-closed provider channel.

Every test runs against injected fakes — zero network, zero keys. Coverage:

1. Structural loop refusal: the factory refuses ANY caller-supplied
   ``loop_fn`` in both modes (there is nothing to veneer or spoof through
   the public API); live mode refuses every injected seam; direct dataclass
   construction still refuses the known mock/stub loops (defense-in-depth,
   incl. partial/__wrapped__ veneers); the flag ⇔ seam-provenance invariant
   survives ``dataclasses.replace`` in both directions (no fake-seam live
   instance, no real-machinery "offline" instance); and provenance is OBJECT
   IDENTITY, so a foreign module naturally named live_provider/host_local
   with the exact real qualnames (zero attribute forgery) still refuses.
2. Runner channel: a provider raising ``ProviderFailure`` marks THAT query
   NOT_MEASURED, the judge is never called for it, the other queries are
   still processed; any other exception type still propagates (a bug crashes).
3. Happy path via fakes: evidence maps to a ``ResearchReport`` with real
   ``doc-url-*``-backed provenance URLs and dispatch-bound token accounting.
4. ``allow_live`` gating: offline construction requires all seams injected;
   live construction requires env keys; direct live construction requires the
   real Exa loop identity.
5. Sync bridge: an already-running event loop refuses with ``ProviderFailure``
   (no nesting, no threads).
6. Hostile exceptions: a pipeline exception whose ``__repr__``/``__str__``
   raises (even a BaseException) still converts to a clean ``ProviderFailure``.
7. Honest-numbers fail-closed: empty evidence pack, empty answer text, zero
   dispatch accounting, zero token usage, ZERO tool calls, duplicate
   trajectory ids, zero resolvable sources — each refuses rather than
   reporting a fabricated/defaulted figure; non-URL provenance is never
   reported.
"""

from __future__ import annotations

import asyncio
import functools
import json
from collections.abc import Sequence
from typing import Any

import pytest

from runtime.research_runner import make_contract_gather_stub, make_demo_loop
from substrate.deep_research_eval import (
    AXES,
    ProviderFailure,
    Query,
    QueryDataset,
    ResearchReport,
    run_eval,
)
from substrate.deep_research_eval.live_provider import (
    DispatchUsage,
    GatherOutcome,
    LiveResearchProvider,
    build_live_provider,
)


# --------------------------------------------------------------------------- #
# Fakes (the injectable-seam analogue of live_judge's StubProvider).           #
# --------------------------------------------------------------------------- #
def _query(query_id: str = "q1") -> Query:
    return Query(
        query_id=query_id,
        question="What is the capital of testing?",
        provenance="unit-test",
        domain="test",
        query_class="factual",
        expected_coverage=("alpha", "beta"),
    )


def _two_query_dataset() -> QueryDataset:
    return QueryDataset(
        dataset_id="stub_ds",
        version="0.0.1",
        frozen=True,
        content_digest="0" * 64,
        queries=(_query("q1"), _query("q2")),
    )


def _outcome(**overrides: Any) -> GatherOutcome:
    base: dict[str, Any] = {
        "pack": {"marker": "fake-pack"},
        "chunk_count": 3,
        "documents": (
            ("doc-url-abc123", "Real ingested page"),
            ("doc-gather-session-leaf", "Gather placeholder"),
        ),
        "tool_calls": 4,
        "investigation_ids": ("dre-q1-session", "dre-q1-session-leaf-0"),
    }
    base.update(overrides)
    return GatherOutcome(**base)


class FakePipeline:
    """One object providing all four seams, with per-seam overrides."""

    def __init__(
        self,
        *,
        outcome: GatherOutcome | None = None,
        gather_raises: BaseException | None = None,
        answer: str = "alpha and beta, covered in full.",
        synthesize_raises: BaseException | None = None,
        usage: DispatchUsage | None = None,
        urls: dict[str, str | None] | None = None,
    ):
        self.outcome = outcome if outcome is not None else _outcome()
        self.gather_raises = gather_raises
        self.answer = answer
        self.synthesize_raises = synthesize_raises
        self.usage = usage if usage is not None else DispatchUsage(2, 1200, 340)
        self.urls = urls if urls is not None else {"doc-url-abc123": "https://example.org/page"}
        self.gather_calls: list[tuple[str, str]] = []
        self.synthesized_packs: list[Any] = []
        self.usage_queries: list[tuple[str, ...]] = []

    async def gather(self, query: Query, session_id: str) -> GatherOutcome:
        self.gather_calls.append((query.query_id, session_id))
        if self.gather_raises is not None:
            raise self.gather_raises
        return self.outcome

    async def synthesize(self, pack: Any) -> str:
        self.synthesized_packs.append(pack)
        if self.synthesize_raises is not None:
            raise self.synthesize_raises
        return self.answer

    def usage_reader(self, investigation_ids: Sequence[str]) -> DispatchUsage:
        self.usage_queries.append(tuple(investigation_ids))
        return self.usage

    def source_url_lookup(self, document_id: str) -> str | None:
        return self.urls.get(document_id)

    def build(self, **kwargs: Any) -> LiveResearchProvider:
        return build_live_provider(
            gather=self.gather,
            synthesize=self.synthesize,
            usage_reader=self.usage_reader,
            source_url_lookup=self.source_url_lookup,
            **kwargs,
        )


def _valid_judge(prompt: str) -> str:
    return json.dumps({axis: 0.8 for axis in AXES})


# 1a. The factory refuses ANY caller-supplied loop, in both modes: there is
#     no loop to veneer, wrap, or attribute-spoof through the public API.
def test_factory_refuses_any_caller_loop_fn() -> None:
    fakes = FakePipeline()
    demo = make_demo_loop()

    async def lambda_veneer(ctx: Any) -> Any:  # pragma: no cover — never runs
        return await demo(ctx)  # type: ignore[operator]

    for loop in (
        make_demo_loop(),
        make_contract_gather_stub(),
        make_demo_loop,  # the factory itself, not just its product
        # A veneer that is neither partial nor __wrapped__ (the codex probe
        # shape): refused for the same STRUCTURAL reason — nothing
        # caller-supplied is accepted, so identity does not matter.
        lambda_veneer,
    ):
        with pytest.raises(ValueError, match="no caller-supplied loop_fn"):
            fakes.build(loop_fn=loop)


# 1b. Live mode admits no injected parts at all: any seam refuses.
def test_allow_live_refuses_injected_seams(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fakes = FakePipeline()
    with pytest.raises(ValueError, match="refuses injected seams"):
        fakes.build(allow_live=True)  # all four seams injected
    for seam in ("gather", "synthesize", "usage_reader", "source_url_lookup"):
        with pytest.raises(ValueError, match="refuses injected seams"):
            build_live_provider(allow_live=True, **{seam: getattr(fakes, seam)})
    # And a caller loop is refused even with keys present and no seams.
    with pytest.raises(ValueError, match="no caller-supplied loop_fn"):
        build_live_provider(allow_live=True, loop_fn=make_demo_loop())


# 1c. Defense-in-depth: DIRECT dataclass construction (bypassing the factory)
#     still refuses the known mock/stub loops, incl. partial/__wrapped__
#     veneers. (Forged __qualname__/__module__ attributes on direct
#     construction are out of scope — see the module docstring threat model.)
def test_direct_construction_refuses_mock_loops() -> None:
    fakes = FakePipeline()

    def _direct(loop: object) -> LiveResearchProvider:
        return LiveResearchProvider(
            gather=fakes.gather,
            synthesize=fakes.synthesize,
            usage_reader=fakes.usage_reader,
            source_url_lookup=fakes.source_url_lookup,
            loop_fn=loop,
        )

    async def _veneer(ctx: Any) -> Any:  # pragma: no cover — never called
        raise AssertionError("never runs")

    _veneer.__wrapped__ = make_contract_gather_stub()  # type: ignore[attr-defined]

    for loop in (
        make_demo_loop(),
        make_contract_gather_stub(),
        make_demo_loop,
        make_contract_gather_stub,
        functools.partial(make_demo_loop(), None),
        _veneer,
    ):
        with pytest.raises(ValueError, match="mock/stub"):
            _direct(loop)


# 2a. Runner channel: ProviderFailure → that query NOT_MEASURED, judge not
#     called for it, the other query still MEASURED.
def test_provider_failure_marks_query_not_measured_and_continues() -> None:
    good_report = ResearchReport(
        answer_text="alpha beta",
        sources=(),
        tool_calls=1,
        tokens_in=10,
        tokens_out=5,
    )

    def provider(query: Query) -> ResearchReport:
        if query.query_id == "q1":
            raise ProviderFailure("gather failed: no keys")
        return good_report

    judged_prompts: list[str] = []

    def judge(prompt: str) -> str:
        judged_prompts.append(prompt)
        return _valid_judge(prompt)

    run = run_eval(
        _two_query_dataset(), provider, judge, run_id_seed="seed", week_id="2026-W28"
    )
    assert [s.status for s in run.scores] == ["NOT_MEASURED", "MEASURED"]
    assert run.scores[0].judge_scores is None
    assert run.scores[0].coverage_hit_rate == 0.0
    assert run.scores[0].hit_anchors == ()
    assert run.scores[1].judge_scores is not None
    # The judge was consulted exactly once — never for the failed query.
    assert len(judged_prompts) == 1
    # Fail-closed cascade: the run is incomplete, so the bench bridge refuses.
    assert run.complete is False
    from substrate.deep_research_eval import IncompleteRunError, deep_research_bench_record

    with pytest.raises(IncompleteRunError):
        deep_research_bench_record(run)


# 2b. Any OTHER exception type still propagates — a bug must crash the run.
def test_non_provider_failure_still_propagates() -> None:
    def buggy_provider(query: Query) -> ResearchReport:
        raise RuntimeError("a genuine bug")

    with pytest.raises(RuntimeError, match="a genuine bug"):
        run_eval(
            _two_query_dataset(),
            buggy_provider,
            _valid_judge,
            run_id_seed="seed",
            week_id="2026-W28",
        )


# 3. Happy path via fakes: evidence → ResearchReport with real provenance.
def test_happy_path_maps_evidence_to_report() -> None:
    fakes = FakePipeline()
    provider = fakes.build()
    report = provider(_query())

    assert isinstance(report, ResearchReport)
    assert report.answer_text == "alpha and beta, covered in full."
    # Only the doc-url-* document resolves to a source; the doc-gather-*
    # placeholder is never reported (it has no real URL).
    assert [s.url for s in report.sources] == ["https://example.org/page"]
    assert report.sources[0].title == "Real ingested page"
    # Numbers bind to the injected real-accounting fakes verbatim.
    assert report.tool_calls == 4
    assert (report.tokens_in, report.tokens_out) == (1200, 340)
    # The gather got a unique per-query session id; the usage reader was
    # asked about exactly the gather's trajectories; the synthesizer got the
    # pack verbatim.
    (query_id, session_id), = fakes.gather_calls
    assert query_id == "q1" and session_id.startswith("dre-q1-")
    assert fakes.usage_queries == [("dre-q1-session", "dre-q1-session-leaf-0")]
    assert fakes.synthesized_packs == [{"marker": "fake-pack"}]

    # End-to-end through run_eval: both queries MEASURED.
    run = run_eval(
        _two_query_dataset(), provider, _valid_judge, run_id_seed="s", week_id="2026-W28"
    )
    assert run.complete is True and run.measured_count == 2


# 4a. allow_live gating: offline construction demands every seam injected.
def test_offline_construction_requires_all_seams() -> None:
    with pytest.raises(ValueError, match="operator-gated"):
        build_live_provider()
    fakes = FakePipeline()
    with pytest.raises(ValueError, match="operator-gated"):
        build_live_provider(gather=fakes.gather, synthesize=fakes.synthesize)


# 1d. dataclasses.replace re-runs __post_init__, so the flag ⇔ seam-provenance
#     invariant holds on every public mutation path: a replace cannot flip an
#     offline instance live while keeping fake seams, cannot flip a
#     real-machinery instance to "offline" (which could spend from inside a
#     test), and cannot swap a single fake seam onto a live instance. Honest
#     uses of replace (tuning the timeout) keep working.
def test_dataclasses_replace_cannot_break_flag_seam_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dataclasses

    from substrate.deep_research_eval.live_provider import _build_real_exa_loop

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fakes = FakePipeline()
    offline = fakes.build()
    live = build_live_provider(allow_live=True, discovery_top_k=1)

    # Repro 1: offline → live, all four fake seams retained. The loop is the
    # module-minted (token-stamped) real one so the refusal is specifically
    # seam provenance, not the loop — under object-identity provenance only
    # _build_real_exa_loop mints a live-eligible loop.
    with pytest.raises(ValueError, match="not this module's real implementations"):
        dataclasses.replace(offline, allow_live=True, loop_fn=_build_real_exa_loop())

    # Repro 2: live → offline while keeping ALL real seams — an "offline"
    # provider that could actually spend/hit the network is refused. The
    # loop-slot guard fires first (offline means loop_fn=None)...
    with pytest.raises(ValueError, match="must carry loop_fn=None"):
        dataclasses.replace(live, allow_live=False)
    # ...and with the loop dropped, the seam guard still refuses.
    with pytest.raises(ValueError, match="must not carry real-machinery seams"):
        dataclasses.replace(live, allow_live=False, loop_fn=None)

    # Repro 3: live with ONE fake seam swapped in.
    with pytest.raises(ValueError, match="not this module's real implementations"):
        dataclasses.replace(live, gather=fakes.gather)

    # Honest replace still works in both modes: tuning the timeout changes
    # neither provenance nor the flag, and the offline instance still runs.
    tuned_offline = dataclasses.replace(offline, per_query_timeout_s=30.0)
    assert tuned_offline.per_query_timeout_s == 30.0
    assert isinstance(tuned_offline(_query()), ResearchReport)
    tuned_live = dataclasses.replace(live, per_query_timeout_s=60.0)
    assert tuned_live.per_query_timeout_s == 60.0 and tuned_live.allow_live is True


# 4a-role. Provenance is ROLE-SPECIFIC: a shared role-less token would prove
#     only "built by this module", letting a REAL callable be composed into
#     the WRONG seam field. Every cross-role composition must refuse.
def test_cross_role_real_seam_composition_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dataclasses

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    live = build_live_provider(allow_live=True, discovery_top_k=1)

    # A real gather in the synthesize slot: real machinery, wrong role.
    with pytest.raises(ValueError, match="not this module's real implementations"):
        dataclasses.replace(live, synthesize=live.gather)
    # And the mirror image.
    with pytest.raises(ValueError, match="not this module's real implementations"):
        dataclasses.replace(live, gather=live.synthesize)
    # The module-level pair swapped between their two slots.
    with pytest.raises(ValueError, match="not this module's real implementations"):
        dataclasses.replace(live, usage_reader=live.source_url_lookup)
    with pytest.raises(ValueError, match="not this module's real implementations"):
        dataclasses.replace(live, source_url_lookup=live.usage_reader)
    # A real seam in the LOOP slot fails the loop's role check.
    with pytest.raises(ValueError, match="requires the REAL Exa gather loop"):
        dataclasses.replace(live, loop_fn=live.gather)
    # Offline direction stays role-BLIND: real machinery in ANY field (even a
    # wrong one) must refuse — it could still spend money from inside a test.
    fakes = FakePipeline()
    with pytest.raises(ValueError, match="must not carry real-machinery seams"):
        dataclasses.replace(
            fakes.build(), synthesize=live.gather  # real gather, wrong slot, offline
        )
    # ...including the loop slot, which offline execution ignores but the
    # invariant still governs: offline means loop_fn=None, full stop.
    with pytest.raises(ValueError, match="must carry loop_fn=None"):
        dataclasses.replace(fakes.build(), loop_fn=live.gather)
    with pytest.raises(ValueError, match="must carry loop_fn=None"):
        dataclasses.replace(fakes.build(), loop_fn=live.loop_fn)


# 4a-wrap. Positive provenance holds on the EXECUTING callable, never its
#     wrappee: functools.wraps copies __wrapped__, so an unwrapping positive
#     check would let a fake wrapper inherit a real seam's provenance while
#     the wrapper's own code runs. The negative (offline) direction still
#     unwraps — hiding real machinery behind a wrapper must refuse too.
def test_wrapper_cannot_inherit_real_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dataclasses
    import functools

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    live = build_live_provider(allow_live=True, discovery_top_k=1)

    @functools.wraps(live.gather)
    async def fake_gather(*args: object, **kwargs: object) -> object:
        raise AssertionError("arbitrary replacement seam executed")

    # The wrapper carries live.gather's __wrapped__/metadata but is NOT the
    # real seam — live construction must refuse it.
    with pytest.raises(ValueError, match="not this module's real implementations"):
        dataclasses.replace(live, gather=fake_gather)

    # Negative direction keeps unwrapping: a wrapper HIDING real machinery in
    # an offline-flagged provider refuses (fail closed = refuse more).
    fakes = FakePipeline()

    @functools.wraps(live.synthesize)
    async def hidden_real(*args: object, **kwargs: object) -> object:
        return await live.synthesize(*args, **kwargs)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="must not carry real-machinery seams"):
        dataclasses.replace(fakes.build(), synthesize=hidden_real)


# 4a-eq. Provenance is STRICT `is` identity, not set membership: WeakSet.__contains__
#     consults __hash__/__eq__, which an impostor can override to compare equal
#     to a real seam. The check must survive an equality-spoofing callable.
def test_equality_spoofing_impostor_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    live = build_live_provider(allow_live=True, discovery_top_k=1)

    class _EqSpoof:
        """Compares/hashes equal to the real gather but runs its own code."""

        def __init__(self, target: object) -> None:
            self._target = target

        def __hash__(self) -> int:
            return hash(self._target)

        def __eq__(self, other: object) -> bool:
            return other is self._target or other is self

        async def __call__(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("impostor seam executed")

    impostor = _EqSpoof(live.gather)
    # It IS equal to and hashes with the real seam — a membership check accepts it.
    assert impostor == live.gather and hash(impostor) == hash(live.gather)
    with pytest.raises(ValueError, match="not this module's real implementations"):
        dataclasses.replace(live, gather=impostor)


# 4a-proxy. weakref.proxy of a real seam forwards to real machinery but is not
#     `is` the real object and cannot be cheaply dereffed. Live positive checks
#     already refuse it (not the registered object); the offline negative guard
#     fails closed on ANY proxy — an offline double is never legitimately one.
def test_weakref_proxy_seam_refused_both_directions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dataclasses
    import weakref

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    live = build_live_provider(allow_live=True, discovery_top_k=1)
    fakes = FakePipeline()

    # Live direction: a proxy is not the registered object → not real.
    with pytest.raises(ValueError, match="not this module's real implementations"):
        dataclasses.replace(live, gather=weakref.proxy(live.gather))
    # Offline direction: a proxy (of anything) refuses — fail closed on the
    # un-dereferenceable case, closing the real-machinery-forwarding hole.
    with pytest.raises(ValueError, match="must not carry real-machinery seams"):
        dataclasses.replace(fakes.build(), synthesize=weakref.proxy(live.synthesize))


# 4b. allow_live gating: missing env keys refuse construction — through the
#     factory AND through direct dataclass construction.
def test_allow_live_refused_without_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="EXA_API_KEY"):
        build_live_provider(allow_live=True)
    # Direct construction with the module-minted real loop but a key still
    # missing is refused by the dataclass gate itself (not only the factory's
    # check). The loop must come from _build_real_exa_loop — under
    # object-identity provenance a bare make_exa_gather_loop() product is no
    # longer live-eligible (it carries no token).
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    from substrate.deep_research_eval.live_provider import _build_real_exa_loop

    fakes = FakePipeline()
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        LiveResearchProvider(
            gather=fakes.gather,
            synthesize=fakes.synthesize,
            usage_reader=fakes.usage_reader,
            source_url_lookup=fakes.source_url_lookup,
            loop_fn=_build_real_exa_loop(),
            allow_live=True,
        )


# 4c. allow_live gating on direct construction: a non-mock but non-token loop
#     (home-grown, None, or even a genuine make_exa_gather_loop product that
#     this module did not mint) is refused; the fully-defaulted factory build
#     constructs (inert — no I/O at construction) and self-wires the real loop.
def test_allow_live_requires_real_exa_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    async def home_grown_loop(ctx: Any) -> Any:  # pragma: no cover — never called
        raise AssertionError("never runs")

    fakes = FakePipeline()

    def _direct(loop: object | None) -> LiveResearchProvider:
        return LiveResearchProvider(
            gather=fakes.gather,
            synthesize=fakes.synthesize,
            usage_reader=fakes.usage_reader,
            source_url_lookup=fakes.source_url_lookup,
            loop_fn=loop,
            allow_live=True,
        )

    from runtime.research_runner import make_exa_gather_loop

    with pytest.raises(ValueError, match="REAL Exa gather loop"):
        _direct(home_grown_loop)
    with pytest.raises(ValueError, match="REAL Exa gather loop"):
        _direct(None)
    # Object-identity tightening: even the genuine factory's product does not
    # qualify unless THIS module minted (token-stamped) it.
    with pytest.raises(ValueError, match="REAL Exa gather loop"):
        _direct(make_exa_gather_loop())

    # The one honest live construction: fully defaulted through the factory.
    live = build_live_provider(allow_live=True, discovery_top_k=1)
    assert live.allow_live is True and live.loop_fn is not None


# 4d. Codex round-3 mimic probe: a foreign module NATURALLY named
#     "live_provider" / "host_local" whose callables carry the exact real
#     qualnames — zero attribute forgery — must not pass provenance in either
#     direction. Object identity (private token / is-checks) replaces names.
def test_natural_name_mimicry_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    import textwrap
    import types

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def _mimic_module(name: str, source: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        exec(compile(textwrap.dedent(source), f"<{name}>", "exec"), mod.__dict__)
        return mod

    fake_lp = _mimic_module(
        "fakepkg.live_provider",
        """
        def _build_real_gather():
            async def _gather(query, session_id):
                raise AssertionError("mimic must never run")
            return _gather

        def _build_real_synthesize():
            async def _synthesize(pack):
                raise AssertionError("mimic must never run")
            return _synthesize

        def _read_dispatch_usage(investigation_ids):
            raise AssertionError("mimic must never run")

        def _lookup_document_source_uri(document_id):
            raise AssertionError("mimic must never run")
        """,
    )
    fake_hl = _mimic_module(
        "fakepkg.host_local",
        """
        def make_exa_gather_loop(top_k=3):
            async def _loop(ctx):
                raise AssertionError("mimic must never run")
            return _loop
        """,
    )
    mimic_gather = fake_lp.__dict__["_build_real_gather"]()
    mimic_synth = fake_lp.__dict__["_build_real_synthesize"]()
    mimic_usage = fake_lp.__dict__["_read_dispatch_usage"]
    mimic_lookup = fake_lp.__dict__["_lookup_document_source_uri"]
    mimic_loop = fake_hl.__dict__["make_exa_gather_loop"]()

    # Red-proof the mimicry: these ARE the exact names + module leaves the
    # round-3 name-matching accepted. Only object identity distinguishes them.
    assert mimic_gather.__qualname__ == "_build_real_gather.<locals>._gather"
    assert mimic_gather.__module__.rsplit(".", 1)[-1] == "live_provider"
    assert mimic_loop.__qualname__ == "make_exa_gather_loop.<locals>._loop"
    assert mimic_loop.__module__.rsplit(".", 1)[-1] == "host_local"

    # Live direction, mimic loop: refused (no token).
    with pytest.raises(ValueError, match="REAL Exa gather loop"):
        LiveResearchProvider(
            gather=mimic_gather,
            synthesize=mimic_synth,
            usage_reader=mimic_usage,
            source_url_lookup=mimic_lookup,
            loop_fn=mimic_loop,
            allow_live=True,
        )

    # Live direction, genuine minted loop but mimic seams: every seam refused.
    from substrate.deep_research_eval.live_provider import (
        _build_real_exa_loop,
        _read_dispatch_usage,
    )

    with pytest.raises(ValueError, match="'gather', 'synthesize', 'usage_reader'"):
        LiveResearchProvider(
            gather=mimic_gather,
            synthesize=mimic_synth,
            usage_reader=mimic_usage,
            source_url_lookup=mimic_lookup,
            loop_fn=_build_real_exa_loop(),
            allow_live=True,
        )

    # Offline direction: the mimics are just fakes — with names out of the
    # picture they are NOT misclassified as real machinery, so offline
    # construction works (this was a false-positive under name-matching)...
    offline = LiveResearchProvider(
        gather=mimic_gather,
        synthesize=mimic_synth,
        usage_reader=mimic_usage,
        source_url_lookup=mimic_lookup,
    )
    assert offline.allow_live is False
    # ...while a GENUINE real seam under the offline flag still refuses by
    # object identity (the direction that guards real spend inside tests).
    fakes = FakePipeline()
    with pytest.raises(ValueError, match="must not carry real-machinery seams"):
        LiveResearchProvider(
            gather=fakes.gather,
            synthesize=fakes.synthesize,
            usage_reader=_read_dispatch_usage,
            source_url_lookup=fakes.source_url_lookup,
        )


# 5. Sync bridge: an already-running loop refuses (no nesting, no threads).
def test_running_event_loop_refused() -> None:
    provider = FakePipeline().build()

    async def _call_inside_loop() -> ResearchReport:
        return provider(_query())

    with pytest.raises(ProviderFailure, match="already running"):
        asyncio.run(_call_inside_loop())


# 6. Hostile exception detail (raising __repr__/__str__, even BaseException)
#    still converts to a clean ProviderFailure — never a second crash.
def test_hostile_exception_detail_is_safe() -> None:
    class HostileError(Exception):
        def __repr__(self) -> str:
            raise RuntimeError("repr blew up")

        def __str__(self) -> str:
            raise KeyboardInterrupt("escape via __str__")

    provider = FakePipeline(gather_raises=HostileError()).build()
    with pytest.raises(ProviderFailure, match="HostileError") as excinfo:
        provider(_query())
    assert "<undisplayable exception detail>" in str(excinfo.value)


# 6b. An ordinary pipeline exception converts with its stage label and detail.
def test_pipeline_exception_converts_to_provider_failure() -> None:
    provider = FakePipeline(gather_raises=ConnectionError("exa unreachable")).build()
    with pytest.raises(ProviderFailure, match="gather failed.*exa unreachable"):
        provider(_query())
    synth = FakePipeline(synthesize_raises=RuntimeError("constraint loop diverged")).build()
    with pytest.raises(ProviderFailure, match="synthesis failed.*constraint loop diverged"):
        synth(_query())
    # A seam raising ProviderFailure itself passes through with its reason.
    honest = FakePipeline(
        gather_raises=ProviderFailure("legal gate refused every proposal")
    ).build()
    with pytest.raises(ProviderFailure, match="legal gate refused"):
        honest(_query())


# 7a. Empty evidence pack fails closed — nothing is synthesized or fabricated.
def test_empty_evidence_pack_fails_closed() -> None:
    fakes = FakePipeline(outcome=_outcome(chunk_count=0))
    provider = fakes.build()
    with pytest.raises(ProviderFailure, match="empty evidence pack"):
        provider(_query())
    assert fakes.synthesized_packs == []  # synthesis never ran


# 7b. Empty answer text fails closed.
def test_empty_answer_text_fails_closed() -> None:
    provider = FakePipeline(answer="   \n").build()
    with pytest.raises(ProviderFailure, match="no answer text"):
        provider(_query())


# 7c. Token accounting must be real: zero dispatch calls or zero usage refuse
#     rather than reporting a silent 0.
def test_missing_dispatch_accounting_fails_closed() -> None:
    no_calls = FakePipeline(usage=DispatchUsage(0, 0, 0)).build()
    with pytest.raises(ProviderFailure, match="no DISPATCH_CALL accounting"):
        no_calls(_query())
    zero_usage = FakePipeline(usage=DispatchUsage(3, 0, 0)).build()
    with pytest.raises(ProviderFailure, match="token usage is zero"):
        zero_usage(_query())


# 7d. Sources are never invented, and a sourceless report is never judged:
#     an INDIVIDUALLY unresolvable/non-http row is dropped (kept sources stay
#     real), zero resolvable sources overall refuses, and a lookup crash
#     fails the query closed.
def test_sources_never_invented_and_zero_sources_refused() -> None:
    # One resolvable + one unresolvable doc-url: only the real URL survives.
    partial = FakePipeline(
        outcome=_outcome(
            documents=(
                ("doc-url-abc123", "Real ingested page"),
                ("doc-url-dead99", "Pruned row"),
            )
        ),
        urls={"doc-url-abc123": "https://example.org/page", "doc-url-dead99": None},
    )
    assert [s.url for s in partial.build()(_query()).sources] == [
        "https://example.org/page"
    ]

    # Zero resolvable sources overall → refuse (broken provenance wiring must
    # not be laundered into a judged score).
    unresolvable = FakePipeline(urls={"doc-url-abc123": None})
    with pytest.raises(ProviderFailure, match="no resolvable real-URL provenance"):
        unresolvable.build()(_query())
    non_url = FakePipeline(urls={"doc-url-abc123": "duckdb://not-a-web-source"})
    with pytest.raises(ProviderFailure, match="no resolvable real-URL provenance"):
        non_url.build()(_query())
    # A pack with only doc-gather-* placeholders refuses the same way.
    placeholders_only = FakePipeline(
        outcome=_outcome(documents=(("doc-gather-session-leaf", "placeholder"),))
    )
    with pytest.raises(ProviderFailure, match="no resolvable real-URL provenance"):
        placeholders_only.build()(_query())

    class Boom(FakePipeline):
        def source_url_lookup(self, document_id: str) -> str | None:
            raise RuntimeError("db unavailable")

    with pytest.raises(ProviderFailure, match="source url lookup failed"):
        Boom().build()(_query())


# 7f. Zero tool calls fails closed — a research run with no real tool actions
#     has nothing real behind it (the real exa loop's DONE path always steps).
def test_zero_tool_calls_fails_closed() -> None:
    fakes = FakePipeline(outcome=_outcome(tool_calls=0))
    with pytest.raises(ProviderFailure, match="zero tool calls"):
        fakes.build()(_query())
    assert fakes.synthesized_packs == []  # refused before synthesis


# 7g. Duplicate trajectory ids fail closed — never silently deduped, because a
#     duplicate would double-count dispatch usage.
def test_duplicate_investigation_ids_fail_closed() -> None:
    fakes = FakePipeline(
        outcome=_outcome(investigation_ids=("same-id", "same-id"))
    )
    with pytest.raises(ProviderFailure, match="duplicate investigation ids"):
        fakes.build()(_query())
    assert fakes.usage_queries == []  # the usage reader never saw duplicates


# 7e. Timeout converts to ProviderFailure (fail closed, never hang the week).
def test_timeout_fails_closed() -> None:
    class SlowGather(FakePipeline):
        async def gather(self, query: Query, session_id: str) -> GatherOutcome:
            await asyncio.sleep(10)
            return self.outcome  # pragma: no cover

    provider = SlowGather().build(per_query_timeout_s=0.05)
    with pytest.raises(ProviderFailure, match="timed out"):
        provider(_query())
