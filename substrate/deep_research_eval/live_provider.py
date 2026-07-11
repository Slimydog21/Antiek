"""Live ``ProviderFn`` adapter for the W0 deep-research eval harness.

The harness (``runner.run_eval``) takes an injected ``ProviderFn`` —
``Callable[[Query], ResearchReport]`` — that runs ONE deep research over one
query and returns the report the pinned judge scores. This module supplies
the one live implementation of that callable, backed by the REAL product
research path: the DRW cascade (plan → approve → launch → gather →
join/merge → evidence pack, ``orchestration/cascade_session.py``) followed by
the Loop 1 synthesis tail (``orchestration/loop_one/orchestrator.py``
``run_synthesis_tail_from_pack``, :1573). It is the sibling of
``live_judge.py`` (#764) and matches its fail-closed philosophy.

Four invariants make this adapter safe to feed I-9's "two comparable weekly
runs":

Real loop only (no measurement theater)
    The adapter refuses AT CONSTRUCTION (``ValueError``) to be built around
    ``make_demo_loop`` or ``make_contract_gather_stub``
    (``runtime/research_runner/host_local.py`` :494 / :526 — the benchmark
    mock and the honest production placeholder). Both emit fabricated steps
    and retrieve nothing, so a run over them would measure theater, not the
    product. Detection is by factory identity: the closures those factories
    return carry ``__qualname__`` ``"make_demo_loop.<locals>._loop"`` /
    ``"make_contract_gather_stub.<locals>._loop"`` (``functools.partial`` and
    ``__wrapped__`` chains are unwrapped first). The live path additionally
    requires the POSITIVE identity of the real Exa gather loop
    (``make_exa_gather_loop``, host_local.py :567) — the same loop prod gates
    behind ``ANTIEK_DRW_GATHER=exa``
    (``interfaces/research/api/cascade_routes.py`` ``_research_loop_factory``,
    :260).

Fail closed to ``ProviderFailure`` (the core honesty property)
    EVERY failure path — missing keys, plan/launch refusal (including the
    SPR-05 approval gate), gather-leaf failure, budget exhaustion, legal-gate
    refusal, empty evidence pack, synthesis failure, unreadable/empty
    MASTER.md, absent dispatch accounting, timeout, event-loop-already-running
    — raises ``runner.ProviderFailure`` with a reason. The runner records the
    query ``NOT_MEASURED`` (judge never called) and the incomplete run then
    refuses a bench record — the correct fail-closed cascade. The adapter
    NEVER returns a fabricated ``ResearchReport``. Exception detail is
    extracted via ``live_judge._describe_exception`` (shared, not reinvented),
    so a hostile ``__repr__``/``__str__`` — including one raising a
    ``BaseException`` — cannot break the fail-closed conversion. Only
    ``Exception``s are converted; ``KeyboardInterrupt``/``SystemExit``
    propagate.

Honest numbers (every reported figure binds to real accounting)
    * ``answer_text`` — the rendered MASTER.md the product actually delivers
      (written by Loop 1 Phase 7, ``orchestration/loop_one/orchestrator.py``
      :1130-1169; path recorded on ``ctx.master_md_path``). Missing or empty
      → ``ProviderFailure``, never a substitute.
    * ``sources`` — ONLY real URL provenance: evidence-pack documents whose
      ``document_id`` starts with ``doc-url-`` (minted exclusively by
      ``acquisition/urls/adapter.py`` ``url_doc_id`` :92 when a real URL was
      ingested), resolved to the stored real URL via ``documents.source_uri``
      (written from the fetched final URL at adapter.py :284/:381; schema at
      ``substrate/graph/schema.py`` :65-83). ``doc-gather-*`` placeholders
      (``orchestration/session_evidence_pack.py`` :265-268) carry no real URL
      and are NEVER reported; a ``doc-url-*`` row whose ``source_uri`` is
      missing or non-http is SKIPPED, not invented — under-reporting can only
      depress the judged score, never inflate it.
    * ``tool_calls`` — the count of ``"step"``-kind ``StepEvent``s consumed
      from the session's multiplexed ``stream()`` (which terminates only when
      every research finished, so no event is missed). In the real Exa loop
      each step IS one real tool action (one ``promote_discovery`` following
      a ``discover``, host_local.py :638-645), charged to the runner's budget
      ledger (host_local.py :325-326 → ``budget.py`` ``charge`` :96-123). The
      ledger's own ``steps`` counter was rejected: it increments only on
      charged events (host_local.py :325-326), undercounting zero-cost steps.
    * ``tokens_in`` / ``tokens_out`` — the sum of ``input_tokens`` /
      ``output_tokens`` over the ``DISPATCH_CALL`` events on the session's
      and leaves' trajectories. ``DISPATCH_CALL`` is the canonical per-LLM-call
      token+cost event ("every cent comes off a DispatchCallPayload",
      ``substrate/schemas/events.py`` :726-727; payload :777-820), emitted by
      ``substrate/dispatch/router.py`` ``_emit_dispatch_call`` :325-363 on
      every routed call — the synthesis tail dispatches under the session id,
      so its usage lands on the session trajectory. The Exa gather loop makes
      no LLM calls, so gather contributes no tokens BY DESIGN (it contributes
      ``tool_calls`` and USD spend instead). A run whose trajectories carry
      ZERO ``DISPATCH_CALL`` events, or dispatch events with zero token usage,
      has no honest token numbers → ``ProviderFailure`` (never a silent 0).
      ``CascadeSession.aggregate_cost`` (cascade_session.py :210-217) was
      rejected as the token source: it tracks USD only, and the runner
      ledger's ``tokens`` counter (budget.py) is a single combined figure
      that cannot honestly split in/out.

Operator-gated live path (inert offline)
    ``allow_live=True`` is required for ANY real-machinery default, and it in
    turn requires (at construction) the real Exa loop identity AND the
    required env keys (``EXA_API_KEY`` for gather discovery,
    ``ANTHROPIC_API_KEY`` for dispatch-backed synthesis) to be present —
    otherwise construction refuses with a clear reason. Without
    ``allow_live``, every pipeline seam (gather / synthesize / usage reader /
    source-url lookup) MUST be injected, so offline tests exercise the full
    fail-closed mapping with fakes and zero network — the same
    injectable-client pattern as ``live_judge.py``. Construction never
    performs I/O either way.

Sync bridge
    ``ProviderFn`` is synchronous; the cascade is async. The adapter bridges
    with ``asyncio.run`` (one fresh loop per query). If a loop is already
    running it raises ``ProviderFailure`` — it never nests loops and never
    spawns threads. The optional per-query timeout wraps the whole pipeline
    (``asyncio.wait_for``) and converts expiry to ``ProviderFailure``.
"""

from __future__ import annotations

import asyncio
import functools
import os
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from .dataset import Query
from .live_judge import _describe_exception
from .rubric import ResearchReport, SourceRef
from .runner import ProviderFailure

_T = TypeVar("_T")

# Env keys the LIVE path requires at construction: Exa discovery for the real
# gather loop, Anthropic for the dispatch-backed synthesis tail. Missing keys
# refuse construction — an eval that would fail 20/20 queries at runtime for a
# known-at-construction reason must not start.
REQUIRED_LIVE_ENV: tuple[str, ...] = ("EXA_API_KEY", "ANTHROPIC_API_KEY")

# Mock/stub gather factories this adapter must NEVER wrap (host_local.py
# :494 / :526). Matching is on factory identity via the returned closure's
# __qualname__ ("<factory>.<locals>._loop") or the factory itself.
_MOCK_LOOP_FACTORIES: tuple[str, ...] = ("make_demo_loop", "make_contract_gather_stub")

# The one REAL gather factory (host_local.py :567) the live path requires,
# pinned to its defining module so a same-named function elsewhere cannot pose.
_REAL_LOOP_FACTORY = "make_exa_gather_loop"
_REAL_LOOP_MODULE_LEAF = "host_local"

# A deep research run (discover + promote + synthesis constraint loop) is
# minutes-long; the default cap only exists so a wedged live run fails closed
# instead of hanging the weekly eval forever.
DEFAULT_PER_QUERY_TIMEOUT_S = 1800.0

# ``ResearchReport.sources`` admits only real, resolvable URL provenance.
_URL_SCHEMES = ("https://", "http://")
_URL_DOC_PREFIX = "doc-url-"


@dataclass(frozen=True)
class GatherOutcome:
    """What one real gather (launch → join/merge → evidence pack) yields.

    ``pack`` is forwarded VERBATIM to the synthesize seam (the real one is a
    ``SessionEvidencePack``); the typed fields beside it are the exact facts
    the adapter validates and reports, extracted by the gather seam:

    * ``chunk_count`` — ``len(pack.chunks)``; 0 means the gather promoted no
      evidence and the query fails closed (nothing to synthesize honestly).
    * ``documents`` — ``(document_id, title)`` for every pack document; the
      adapter keeps only real ``doc-url-*`` provenance for ``sources``.
    * ``tool_calls`` — count of ``"step"``-kind StepEvents from the session
      stream (each = one real Exa discover/promote action; see module doc).
    * ``investigation_ids`` — session id + every leaf id, the trajectories
      the usage reader sums ``DISPATCH_CALL`` accounting over.
    """

    pack: Any
    chunk_count: int
    documents: tuple[tuple[str, str], ...]
    tool_calls: int
    investigation_ids: tuple[str, ...]


@dataclass(frozen=True)
class DispatchUsage:
    """Summed ``DISPATCH_CALL`` accounting over a run's trajectories."""

    dispatch_calls: int
    tokens_in: int
    tokens_out: int


# (query, session_id) → one real gather run. The session id is minted by the
# adapter so every run's event-log trajectories are unique + auditable.
GatherFn = Callable[[Query, str], Awaitable[GatherOutcome]]
# evidence pack → the answer text the product actually delivered (MASTER.md).
SynthesizeFn = Callable[[Any], Awaitable[str]]
# trajectory ids → summed real dispatch accounting.
UsageReaderFn = Callable[[Sequence[str]], DispatchUsage]
# document_id → the stored real URL (documents.source_uri), or None.
SourceUrlLookupFn = Callable[[str], str | None]


def _unwrap_loop_fn(loop_fn: object) -> object:
    """Peel ``functools.partial`` / ``__wrapped__`` layers (bounded) so a
    trivially wrapped mock loop cannot dodge the identity check."""
    fn: object = loop_fn
    for _ in range(32):
        if isinstance(fn, functools.partial):
            fn = fn.func
            continue
        wrapped = getattr(fn, "__wrapped__", None)
        if wrapped is None:
            break
        fn = wrapped
    return fn


def _loop_identity(loop_fn: object) -> tuple[str, str]:
    fn = _unwrap_loop_fn(loop_fn)
    qualname = getattr(fn, "__qualname__", "")
    module = getattr(fn, "__module__", "")
    return (
        qualname if isinstance(qualname, str) else "",
        module if isinstance(module, str) else "",
    )


def _refuse_mock_loop(loop_fn: object) -> None:
    """Raise ``ValueError`` if ``loop_fn`` is (or is a product of) a known
    mock/stub gather factory. Measuring a mock is measurement theater — this
    adapter exists to measure the actual product."""
    qualname, _ = _loop_identity(loop_fn)
    for factory in _MOCK_LOOP_FACTORIES:
        if qualname == factory or qualname.startswith(f"{factory}."):
            raise ValueError(
                f"refusing to build the live eval provider around {factory!r}: "
                "it is a mock/stub gather loop, and scoring it would measure "
                "theater, not the product. Use the real Exa gather loop "
                "(make_exa_gather_loop) via build_live_provider(allow_live=True)."
            )


def _is_real_exa_loop(loop_fn: object) -> bool:
    qualname, module = _loop_identity(loop_fn)
    module_leaf = module.rsplit(".", 1)[-1]
    return (
        qualname.startswith(f"{_REAL_LOOP_FACTORY}.")
        and module_leaf == _REAL_LOOP_MODULE_LEAF
    )


def _missing_live_env() -> list[str]:
    return [key for key in REQUIRED_LIVE_ENV if not os.environ.get(key, "").strip()]


@dataclass(frozen=True)
class LiveResearchProvider:
    """Callable ``ProviderFn`` running the real product research path per
    query, fail-closed to ``ProviderFailure`` on every dishonest outcome.

    Construct via :func:`build_live_provider`. All four pipeline seams are
    REQUIRED — there is no silent default. ``loop_fn`` (when supplied) is
    identity-checked against the mock/stub factories at construction;
    ``allow_live=True`` additionally requires the real Exa loop and the
    required env keys, so a live-flagged provider can never exist around a
    mock or without operator keys.
    """

    gather: GatherFn
    synthesize: SynthesizeFn
    usage_reader: UsageReaderFn
    source_url_lookup: SourceUrlLookupFn
    loop_fn: object | None = None
    allow_live: bool = False
    per_query_timeout_s: float | None = DEFAULT_PER_QUERY_TIMEOUT_S

    def __post_init__(self) -> None:
        if self.loop_fn is not None:
            _refuse_mock_loop(self.loop_fn)
        if self.allow_live:
            if self.loop_fn is None or not _is_real_exa_loop(self.loop_fn):
                raise ValueError(
                    "allow_live=True requires the REAL Exa gather loop (a "
                    "make_exa_gather_loop product from "
                    "runtime.research_runner.host_local); refusing to flag a "
                    "provider live around anything else."
                )
            missing = _missing_live_env()
            if missing:
                raise ValueError(
                    f"allow_live=True but required env keys are missing: {missing}. "
                    "The live eval path needs EXA_API_KEY (gather discovery) and "
                    "ANTHROPIC_API_KEY (dispatch-backed synthesis) at construction."
                )
        if self.per_query_timeout_s is not None and self.per_query_timeout_s <= 0:
            raise ValueError("per_query_timeout_s must be positive (or None to disable)")

    # -- sync bridge -----------------------------------------------------

    def __call__(self, query: Query) -> ResearchReport:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass  # no running loop — the normal sync-harness case
        else:
            raise ProviderFailure(
                "an asyncio event loop is already running in this thread; the "
                "live provider owns its own asyncio.run bridge and refuses to "
                "nest loops or spawn threads"
            )
        pipeline = self._run_query(query)
        bounded = (
            pipeline
            if self.per_query_timeout_s is None
            else asyncio.wait_for(pipeline, timeout=self.per_query_timeout_s)
        )
        try:
            return asyncio.run(bounded)
        except ProviderFailure:
            raise
        except TimeoutError as exc:
            raise ProviderFailure(
                f"research run for query {query.query_id!r} timed out after "
                f"{self.per_query_timeout_s}s"
            ) from exc
        except Exception as exc:
            # Any other Exception from the pipeline is still an honest
            # research-run failure for THIS query (network, DB, provider bug
            # upstream) — convert with hostile-repr-safe detail. BaseExceptions
            # (KeyboardInterrupt/SystemExit) propagate: the operator's abort
            # must abort.
            raise ProviderFailure(_describe_exception(exc)) from exc

    # -- the per-query pipeline -------------------------------------------

    async def _run_query(self, query: Query) -> ResearchReport:
        session_id = f"dre-{query.query_id}-{uuid.uuid4().hex[:12]}"
        outcome = await self._stage("gather", lambda: self.gather(query, session_id))
        self._validate_gather(outcome)
        answer_text = await self._stage("synthesis", lambda: self.synthesize(outcome.pack))
        if not isinstance(answer_text, str) or not answer_text.strip():
            raise ProviderFailure(
                "synthesis produced no answer text; refusing to fabricate a report"
            )
        sources = self._resolve_sources(outcome.documents)
        usage = self._read_usage(outcome.investigation_ids)
        return ResearchReport(
            answer_text=answer_text,
            sources=sources,
            tool_calls=outcome.tool_calls,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
        )

    async def _stage(self, name: str, thunk: Callable[[], Awaitable[_T]]) -> _T:
        """Run one pipeline stage, converting any ``Exception`` into a
        stage-labelled ``ProviderFailure`` (hostile-repr-safe). An existing
        ``ProviderFailure`` passes through untouched."""
        try:
            return await thunk()
        except ProviderFailure:
            raise
        except Exception as exc:
            raise ProviderFailure(f"{name} failed: {_describe_exception(exc)}") from exc

    def _validate_gather(self, outcome: GatherOutcome) -> None:
        if not isinstance(outcome, GatherOutcome):
            raise ProviderFailure("gather returned a non-GatherOutcome result")
        if not _is_nonnegative_int(outcome.chunk_count):
            raise ProviderFailure("gather reported a non-integer evidence chunk count")
        if outcome.chunk_count == 0:
            raise ProviderFailure(
                "empty evidence pack: the gather promoted no evidence chunks; "
                "refusing to synthesize a report from nothing"
            )
        if not _is_nonnegative_int(outcome.tool_calls):
            raise ProviderFailure(
                "gather reported a dishonest tool_calls count (must be a "
                "non-negative integer bound to real step events)"
            )
        if not outcome.investigation_ids:
            raise ProviderFailure(
                "gather reported no investigation ids; token accounting cannot "
                "be bound to real trajectories"
            )

    def _resolve_sources(
        self, documents: tuple[tuple[str, str], ...]
    ) -> tuple[SourceRef, ...]:
        """Real-URL provenance only: ``doc-url-*`` documents resolved through
        the ``documents.source_uri`` lookup. Placeholder ``doc-gather-*`` docs
        and unresolvable/non-http rows are skipped — a missing source can only
        depress the judged score; an invented one would inflate it."""
        sources: list[SourceRef] = []
        for document_id, title in documents:
            if not document_id.startswith(_URL_DOC_PREFIX):
                continue
            try:
                url = self.source_url_lookup(document_id)
            except Exception as exc:
                raise ProviderFailure(
                    f"source url lookup failed: {_describe_exception(exc)}"
                ) from exc
            if not isinstance(url, str) or not url.startswith(_URL_SCHEMES):
                continue
            sources.append(SourceRef(url=url, title=title))
        return tuple(sources)

    def _read_usage(self, investigation_ids: tuple[str, ...]) -> DispatchUsage:
        try:
            usage = self.usage_reader(investigation_ids)
        except Exception as exc:
            raise ProviderFailure(
                f"dispatch usage read failed: {_describe_exception(exc)}"
            ) from exc
        if not isinstance(usage, DispatchUsage):
            raise ProviderFailure("usage reader returned a non-DispatchUsage result")
        if not (
            _is_nonnegative_int(usage.dispatch_calls)
            and _is_nonnegative_int(usage.tokens_in)
            and _is_nonnegative_int(usage.tokens_out)
        ):
            raise ProviderFailure("dispatch usage carries non-integer accounting")
        if usage.dispatch_calls == 0:
            raise ProviderFailure(
                "no DISPATCH_CALL accounting found on the run's trajectories; a "
                "real synthesis dispatches at least once, so token numbers "
                "cannot be honestly reported (refusing a silent 0)"
            )
        if usage.tokens_in <= 0 or usage.tokens_out <= 0:
            raise ProviderFailure(
                "DISPATCH_CALL events are present but token usage is zero — the "
                "provider reported no usage, so there is no honest token number "
                "to report (refusing a silent 0)"
            )
        return usage


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


# ---------------------------------------------------------------------------
# Factory — the constructor of record
# ---------------------------------------------------------------------------


def build_live_provider(
    *,
    allow_live: bool = False,
    loop_fn: object | None = None,
    gather: GatherFn | None = None,
    synthesize: SynthesizeFn | None = None,
    usage_reader: UsageReaderFn | None = None,
    source_url_lookup: SourceUrlLookupFn | None = None,
    per_query_timeout_s: float | None = DEFAULT_PER_QUERY_TIMEOUT_S,
    per_research_budget_usd: float = 5.0,
    aggregate_budget_usd: float | None = None,
) -> LiveResearchProvider:
    """Build the live ``ProviderFn``. Two construction modes, both inert
    (no I/O happens here):

    * **Offline (default, ``allow_live=False``)** — every pipeline seam
      (``gather``, ``synthesize``, ``usage_reader``, ``source_url_lookup``)
      MUST be injected; a missing seam refuses construction rather than
      silently wiring real machinery. This is the test mode.
    * **Live (``allow_live=True``)** — missing seams get the REAL defaults
      (DRW cascade gather over ``make_exa_gather_loop``, Loop 1 synthesis
      tail, ``DISPATCH_CALL`` trajectory accounting, ``documents.source_uri``
      lookup). Requires the required env keys at construction; a supplied
      ``loop_fn`` must be a real ``make_exa_gather_loop`` product. Budget
      caps bound the per-query gather exactly like a product launch
      (cascade_routes.py ``launch``).

    In BOTH modes a mock/stub ``loop_fn`` refuses construction.
    """
    if allow_live:
        if loop_fn is None:
            missing = _missing_live_env()
            if missing:
                # Refuse BEFORE importing/constructing any real machinery —
                # same message the dataclass gate raises, surfaced early.
                raise ValueError(
                    f"allow_live=True but required env keys are missing: {missing}. "
                    "The live eval path needs EXA_API_KEY (gather discovery) and "
                    "ANTHROPIC_API_KEY (dispatch-backed synthesis) at construction."
                )
            loop_fn = _build_real_exa_loop()
        if gather is None:
            gather = _build_real_gather(
                loop_fn,
                per_research_budget_usd=per_research_budget_usd,
                aggregate_budget_usd=aggregate_budget_usd,
            )
        if synthesize is None:
            synthesize = _build_real_synthesize()
        if usage_reader is None:
            usage_reader = _read_dispatch_usage
        if source_url_lookup is None:
            source_url_lookup = _lookup_document_source_uri
    else:
        missing_seams = [
            name
            for name, seam in (
                ("gather", gather),
                ("synthesize", synthesize),
                ("usage_reader", usage_reader),
                ("source_url_lookup", source_url_lookup),
            )
            if seam is None
        ]
        if missing_seams:
            raise ValueError(
                "live defaults are operator-gated: pass allow_live=True (with "
                f"keys configured) or inject the missing seams {missing_seams}. "
                "Default construction stays inert offline by design."
            )
    assert gather is not None  # narrowed by both branches above
    assert synthesize is not None
    assert usage_reader is not None
    assert source_url_lookup is not None
    return LiveResearchProvider(
        gather=gather,
        synthesize=synthesize,
        usage_reader=usage_reader,
        source_url_lookup=source_url_lookup,
        loop_fn=loop_fn,
        allow_live=allow_live,
        per_query_timeout_s=per_query_timeout_s,
    )


# ---------------------------------------------------------------------------
# Real defaults (live path only; every import is lazy so offline use of this
# module never pays for — or depends on — the product stack).
# ---------------------------------------------------------------------------


def _build_real_exa_loop() -> object:
    """The real gather loop, mirroring prod's ``ANTIEK_DRW_GATHER=exa`` branch
    (cascade_routes.py :273-275). Construction is lazy/inert — the Exa client
    reads ``EXA_API_KEY`` on first discover, not here."""
    from runtime.research_runner import make_exa_gather_loop

    return make_exa_gather_loop(top_k=3)


def _build_real_gather(
    loop_fn: object,
    *,
    per_research_budget_usd: float,
    aggregate_budget_usd: float | None,
) -> GatherFn:
    """One real DRW cascade per query, composed exactly like the product's
    launch endpoint (cascade_routes.py ``launch`` :500-556): single-leaf plan
    persisted + approved through the SPR-05 gate, ``HostLocalRunner`` over the
    real loop, ``PromotionFunnel`` promotion, ``CascadeSession`` launch →
    join/merge → typed evidence pack. The plan approval is recorded with the
    eval harness as the named approver — auditable in the event log like any
    operator approval."""

    async def _gather(query: Query, session_id: str) -> GatherOutcome:
        from typing import cast

        from orchestration.cascade_session import CascadeSession, Leaf

        # ``default_embedding_provider`` is the same embedder prod's launch
        # endpoint hands the funnel + persist (cascade_routes.py
        # ``_embedding_provider`` :137-139, inlined to avoid importing the
        # FastAPI route module).
        from processing.embedding import default_embedding_provider
        from roles.cascade_planner import approve_plan, persist_tree
        from roles.cascade_planner.tree_contract import PlanNode, PlanTree
        from runtime.research_runner import (
            BudgetCap,
            BudgetManager,
            HostLocalRunner,
            PromotionFunnel,
        )
        from runtime.research_runner.protocol import BrowseLoop, RunState
        from substrate.graph import default_db_path, ensure_initialized

        db_path = default_db_path()
        ensure_initialized(db_path)
        embedder = default_embedding_provider()

        # Single-leaf plan: the eval query IS the research question. The
        # SPR-05 approval gate is honored, not bypassed — the plan is
        # persisted and approved under the harness's name before launch
        # (CascadeSession.launch calls assert_launchable).
        tree = PlanTree(
            root=PlanNode(question=query.question),
            seed_kind="problem",
            seed_provenance={"seed": "deep_research_eval", "query_id": query.query_id},
        )
        plan_root_id = persist_tree(
            tree,
            investigation_id=session_id,
            embedding_provider=embedder,
            db_path=db_path,
        )
        approve_plan(
            plan_root_id,
            approver="deep-research-eval",
            investigation_id=session_id,
            db_path=db_path,
        )

        leaves = [
            Leaf(
                investigation_id=f"{session_id}-leaf-{i}",
                sub_question=leaf.question,
                question_node_id=leaf.graph_node_id,
                budget=BudgetCap(cost_usd=per_research_budget_usd),
            )
            for i, leaf in enumerate(tree.leaves)
        ]
        budget = (
            BudgetManager()
            if aggregate_budget_usd is None
            else BudgetManager(aggregate_cap_usd=aggregate_budget_usd)
        )
        funnel = PromotionFunnel(db_path=db_path, embedding_provider=embedder)
        runner = HostLocalRunner(
            cast(BrowseLoop, loop_fn),
            budget=budget,
            on_emit=funnel.submit,
            seal_on_complete=False,
        )
        session = CascadeSession(session_id, runner=runner, funnel=funnel, db_path=db_path)
        await session.launch(plan_root_id, leaves)
        # Consume the multiplexed session stream to completion (the product's
        # own glass-box consumption pattern). ``stream()`` terminates only
        # after every pump task finished, so the step count cannot race a
        # trailing event the way ``drain_nowait`` right after join could.
        tool_calls = 0
        async for ev in session.stream():
            if ev.kind == "step":
                tool_calls += 1
        await session.join_and_merge()

        # Anything but DONE means the research did not honestly complete —
        # FAILED, BUDGET_HALTED (budget exhaustion), and even STOPPED (nothing
        # legitimately stops an unattended eval run) all fail closed.
        for state in session.status():
            if state.state != RunState.DONE.value:
                raise ProviderFailure(
                    f"gather leaf {state.investigation_id!r} ended "
                    f"{state.state!r} (see its event-log trajectory); refusing "
                    "to report a partial research as a result"
                )

        pack = session.build_evidence_pack(plan_root_node_id=plan_root_id)
        return GatherOutcome(
            pack=pack,
            chunk_count=len(pack.chunks),
            documents=tuple((d.document_id, d.title) for d in pack.documents),
            tool_calls=tool_calls,
            investigation_ids=(session_id, *(leaf.investigation_id for leaf in leaves)),
        )

    return _gather


def _build_real_synthesize() -> SynthesizeFn:
    """The real Loop 1 synthesis tail (phases 6-9) over the evidence pack,
    wired the same way ``create_app`` wires it (app.py :1876-1902): a fresh
    ``EventBroadcaster``, the synthesizer bridge, an
    ``InvestigationCoordinator``, then ``run_synthesis_tail_from_pack``. The
    answer text is the rendered MASTER.md the product delivers (Phase 7)."""

    async def _synthesize(pack: Any) -> str:
        from pathlib import Path

        from interfaces.research.api.broadcast import EventBroadcaster
        from interfaces.research.api.synthesizer import (
            register_handlers as register_synthesizer,
        )
        from orchestration.loop_one.coordinator import InvestigationCoordinator
        from orchestration.loop_one.orchestrator import run_synthesis_tail_from_pack

        bus = EventBroadcaster()
        register_synthesizer(bus)
        coordinator = InvestigationCoordinator(bus)
        ctx = await run_synthesis_tail_from_pack(
            pack, broadcaster=bus, coordinator=coordinator
        )
        if ctx.failed_phase is not None:
            raise ProviderFailure(
                f"synthesis tail failed at phase {ctx.failed_phase}: "
                f"{ctx.fail_reason or '(no reason recorded)'}"
            )
        if ctx.synthesis is None:
            raise ProviderFailure("synthesis tail completed without a synthesis payload")
        if not ctx.master_md_path:
            raise ProviderFailure(
                "synthesis completed but recorded no MASTER.md path; there is "
                "no delivered report to score"
            )
        try:
            text = Path(ctx.master_md_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise ProviderFailure(
                f"cannot read the delivered MASTER.md at {ctx.master_md_path!r}"
            ) from exc
        if not text.strip():
            raise ProviderFailure(
                f"delivered MASTER.md at {ctx.master_md_path!r} is empty"
            )
        return text

    return _synthesize


def _read_dispatch_usage(investigation_ids: Sequence[str]) -> DispatchUsage:
    """Sum ``DISPATCH_CALL`` token accounting over the given trajectories —
    the same per-call events the cost view reconciles USD from (the canonical
    accounting stream; see module docstring for file:line provenance)."""
    from substrate.event_log import trajectory
    from substrate.schemas.events import ActionType

    calls = 0
    tokens_in = 0
    tokens_out = 0
    for investigation_id in investigation_ids:
        for event in trajectory(investigation_id):
            if event.get("action_type") != ActionType.DISPATCH_CALL.value:
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            calls += 1
            tokens_in += _as_token_count(payload.get("input_tokens"))
            tokens_out += _as_token_count(payload.get("output_tokens"))
    return DispatchUsage(dispatch_calls=calls, tokens_in=tokens_in, tokens_out=tokens_out)


def _as_token_count(value: object) -> int:
    """A stored token figure that is not a non-negative int contributes 0 —
    the zero-usage guard in ``_read_usage`` then fails the query closed
    rather than reporting a number backed by corrupt accounting."""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


def _lookup_document_source_uri(document_id: str) -> str | None:
    """Resolve a ``doc-url-*`` document to its stored real URL
    (``documents.source_uri``, written from the fetched final URL by
    ``acquisition/urls/adapter.py``). Read-only connection; None when the
    row or the URI is absent — the caller skips, never invents."""
    import duckdb

    from substrate.graph import default_db_path

    con = duckdb.connect(default_db_path(), read_only=True)
    try:
        row = con.execute(
            "SELECT source_uri FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    if row is None or row[0] is None:
        return None
    uri = str(row[0]).strip()
    return uri or None
