"""RDR SPR-04 — the REAL role-chain browse loop.

This replaces the ``make_demo_loop`` sleep-and-charge stub at the
*production* research factory (``interfaces/research/api/cascade_routes.py``
``_research_loop_factory``). It returns the **same callable shape** the demo
loop returns — a ``Callable[[LoopContext], AsyncIterator[StepEvent]]`` — so it
drops into ``HostLocalRunner`` with **no runner change** (the runner is
byte-unchanged; milestone 1's gate).

What the real loop does, per sub-question (one ``LoopContext`` == one
sub-question research):

  1. **Local-corpus retrieval first** (milestone 2). Vector search over the
     graph's chunks via ``substrate.graph.search.search`` — the *existing*
     retrieval path, no parallel module. Local evidence is preferred over
     web evidence; retrieval ALWAYS precedes any web call.
  2. **Exa web fan-out** (milestone 3). One web search per sub-question
     routed through ``acquisition/search/exa/adapter.discover`` — the
     sanctioned discovery surface, NOT a direct ``ExaClient.search``. This
     is load-bearing: ``discover`` checks the §6.5 dedup cache (a hit costs
     $0) and calls ``check_and_reserve(COST_PER_SEARCH_USD)`` against the
     §6.7 daily ceiling (``EXA_DAILY_BUDGET_USD`` ≈ $5) BEFORE any HTTP
     spend — so a 20-sub-question cascade cannot fan out 20 uncached,
     budgetless live searches the instant activation SPR-03 flips the key.
     The egress is BUDGET-bounded (the daily ceiling), NOT rate-governed:
     ``govern_if_arxiv`` is a passthrough for the ``api.exa.ai`` host
     (rate_governor.py:460 governs arXiv hosts only). All under the §16
     research-fanout exemption (``docs/decisions/s16-research-fanout-exemption.md``).
     ``discover`` is budget-reserved + cached but does NOT consult the legal
     gate (the gate sits on the promotion path per the adapter's §3
     contract), so each ``DiscoveryProposed`` it returns then passes the
     ONE fail-closed §9.0 servability/legal gate here
     (``LegalGate.check_url``, the SAME gate ``promote_discovery`` consults)
     BEFORE it can become a usable source ref — a non-servable source is
     dropped, never silently turned into a reference. No double-gating:
     discover does not gate servability, so this is the sole §9.0 gate.
  3. **Synthesis dispatch** (milestone 4). One model call via
     ``substrate.dispatch.dispatch`` as the ``evidence_retriever`` role,
     producing the insight text. The insight carries a concrete
     ``source_document_id`` ref (a local chunk id or a servable URL) — never
     a canned "insight from step N" string. The funnel
     (``promotion_funnel.py``) persists it (SPR-07's edges come from these
     refs; we only EMIT them).

INERT-AI caveat (load-bearing, NOT decoration)
----------------------------------------------
The Exa search and the synthesis dispatch BOTH require provider keys that
**activation SPR-03 owns** (``EXA_API_KEY`` + the dispatch provider creds).
Until those keys land, this loop is FUNCTIONALLY INERT — it cannot make a
real call. It is built + tested against recorded cassettes (an injected
``ExaClient`` with an ``httpx.MockTransport`` + an injected dispatch
``Provider``/``DispatchConfig``). A green test here means "the real loop is
wired and correct, and it lights up the moment activation SPR-03 flips keys"
— it does NOT mean "research works" or "the operator can feel it." Never
report otherwise.

Budget honesty (the demo loop's defect this fixes)
--------------------------------------------------
``make_demo_loop`` charges a FIXED ``cost_per_step`` for a FIXED
``range(steps)`` regardless of whether any work happened — it bills budget
for fake steps. This loop charges ONLY for real calls that actually ran: the
``cost_usd`` on each emitted ``StepEvent`` is the call's *own* reported cost
(Exa's per-search estimate; the dispatch result's computed cost). A
sub-question whose retrieval + web both come back empty does the synthesis-
declined path and is charged for exactly the calls it made — never for steps
that did not run. The runner charges budget from ``ev.cost_usd``
(``host_local.py`` ``_run``), so "billed for real steps only" follows from
emitting cost only on real calls.

Single-writer invariant (untouched)
------------------------------------
This loop NEVER opens a graph write connection. It reads the graph
(read-only retrieval), calls the web/model via sanctioned surfaces, and yields
``StepEvent``s. Graph promotion stays the ``promotion_funnel``'s job,
serialized through ``runtime/db_lock``. The §9.0 gate here is a READ-only
servability check on a discovered URL (``LegalGate.check_url``) — it does NOT
ingest (that is ``promote_discovery``, which is SPR-07's territory,
deliberately not called). The ``discover`` route's §6.5 dedup-cache write is
the only write reachable from this path, and it goes through the SAME
``runtime/db_lock`` ``connect_write`` (acquisition/search/exa/cache.store) —
serialized, never a parallel graph writer — so the single-writer invariant
holds.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .host_local import LoopContext
from .protocol import StepEvent


# ---------------------------------------------------------------------------
# Defensible numbers — every constant carries its origin (rigor #5).
# ---------------------------------------------------------------------------

# Fan-out width: how many local chunks + how many web results we pull per
# sub-question. NOT picked from the air:
#
#   * LOCAL_TOP_K = 5 mirrors ``substrate.graph.search.search``'s own
#     ``top_k`` default (search.py:135) — the retrieval layer already chose
#     5 as the in-corpus evidence width; we do not second-guess it.
#   * WEB_NUM_RESULTS = 5 is HALF the Exa client's ``num_results`` default of
#     10 (client.py:158). The web fan-out routes through ``adapter.discover``,
#     which enforces the Exa daily-budget ceiling (``EXA_DAILY_BUDGET_USD``
#     default $5, acquisition/search/exa/budget.py) via
#     ``check_and_reserve(COST_PER_SEARCH_USD)`` BEFORE every search. At
#     ≈ $0.005/search that ceiling is ~1000 searches/day; a DRW cascade of up to
#     20 sub-questions (``DEFAULT_MAX_CONCURRENCY = 20``, host_local.py:85) at 1
#     search each is 20 searches/cascade — trivially under cap, and once the cap
#     IS hit ``discover`` refuses further searches (the §6.7 hard-stop), so the
#     fan-out is bounded by the daily ceiling regardless of width. The width
#     itself (5) is chosen NOT by quota but by signal: 5 high-relevance results
#     per sub-question is enough evidence for one synthesis without flooding the
#     model's context. Raise it only with a profiling note, exactly as the
#     concurrency cap docstring says.
LOCAL_TOP_K = 5
WEB_NUM_RESULTS = 5

# The role + tier the synthesis dispatch routes as. ``evidence_retriever``
# (flash tier, config.yaml role_tiers:152 / constants.py:461) is the existing
# role whose job is exactly "given retrieved evidence, produce a grounded
# claim". We reuse it rather than coining a new role — no new dispatch path,
# no second router (§16).
SYNTHESIS_ROLE = "evidence_retriever"

# Per-research max web/synthesis fan-out width when a sub-question is split.
# Today one LoopContext == one sub-question, so this is 1 web search + 1
# synthesis per research; the constant names the ceiling so a future
# multi-query sub-question can't silently fan out unboundedly.
MAX_WEB_QUERIES_PER_RESEARCH = 1


# ---------------------------------------------------------------------------
# Findings shape — the data SPR-07 turns into edges (we only EMIT it).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRef:
    """One concrete source backing an insight. EXACTLY ONE of
    ``chunk_id`` / ``url`` is the operative ref; ``source_document_id`` is the
    canonical field name SPR-07 reads (reusing the existing
    ``source_document_id`` vocabulary — NOT a new synonym). For a local chunk
    it is the chunk's ``document_id``; for a web source it is the URL (the
    document does not exist in the graph yet — SPR-07 ingests + assigns a real
    document_id when it persists)."""

    source_document_id: str
    kind: str  # "local_chunk" | "web_url"
    chunk_id: str | None = None
    url: str | None = None
    title: str | None = None
    similarity: float | None = None
    # Exa's request id for a web source — the liveness marker (a stub can't
    # forge Exa's own request_id). None for a local chunk.
    provider_response_id: str | None = None


@dataclass(frozen=True)
class _SynthComponent:
    """One scored component of the synthesis — shaped so
    ``substrate.synthesis_rubric.scorer.score_synthesis`` (duck-typed) can read
    ``claim`` / ``supporting_chunk_ids`` / ``confidence_basis`` off it."""

    claim: str
    supporting_chunk_ids: list[str]
    confidence_basis: str = ""


@dataclass
class _SynthPayload:
    """A score_synthesis-compatible payload built from the loop's findings, so
    the loop's output is MEASURABLE (rigor / milestone 5 oracle gate), not just
    wired. Attribute names match what ``score_synthesis`` reads off a real
    ``SynthesizeDeliveredPayload`` — duck typing, no schema import."""

    thesis_summary: str = ""
    thesis_components: list[_SynthComponent] = field(default_factory=list)
    conviction_level: float | None = None
    implicit_recommendation: str | None = None
    constraint_compliance: Any | None = None


# ---------------------------------------------------------------------------
# Injectable dependencies — production defaults, test injects cassettes.
# ---------------------------------------------------------------------------


@dataclass
class RealLoopDeps:
    """Everything the real loop needs that is NOT in the LoopContext.

    Every field has a production default that resolves lazily (so importing
    this module pulls in no model / no Exa client / no DB). Tests inject:

      * ``exa_client`` — an ``ExaClient(client=httpx.Client(transport=MockTransport))``
        (the Exa cassette).
      * ``dispatch_fn`` + ``dispatch_config`` — a fake ``Provider`` registered
        via ``register_provider`` + an in-memory ``DispatchConfig`` (the model
        cassette).
      * ``search_fn`` / ``read_con_factory`` / ``embedding`` — a seeded test
        graph + ``HashEmbedding`` (genuinely exercised, not a cassette).
      * ``legal_gate`` — a ``PermissiveLegalGate`` or a denylisting gate for the
        §9.0 drop test.

    None of these is required to BUILD; all are required (as real keys) to RUN
    live — which activation SPR-03 owns.
    """

    # -- web fan-out (Exa) --
    exa_client: Any | None = None
    # The sanctioned discovery route. Production default is
    # ``acquisition.search.exa.adapter.discover`` (budget-reserved + cached +
    # event-emitting); tests inject a fake to assert the route without spend.
    discover_fn: Callable[..., Any] | None = None
    # Exa daily-budget cap override (passed to ``discover``'s
    # ``daily_budget_usd``). None → the §6.7 default ``EXA_DAILY_BUDGET_USD``.
    exa_daily_budget_usd: float | None = None
    # Where discovery-proposal events land (passed to ``discover``). None → the
    # adapter resolves ``default_discovery_events_dir()``.
    discovery_events_dir: str | None = None
    # -- synthesis (model) --
    dispatch_fn: Callable[..., Any] | None = None
    dispatch_config: Any | None = None
    # -- local retrieval --
    db_path: str | None = None
    read_con_factory: Callable[[str], Any] | None = None
    search_fn: Callable[..., dict[str, Any]] | None = None
    embedding: Any | None = None
    # -- §9.0 servability gate --
    legal_gate: Any | None = None
    # -- widths (overridable for tests; default to the defensible constants) --
    local_top_k: int = LOCAL_TOP_K
    web_num_results: int = WEB_NUM_RESULTS


# ---------------------------------------------------------------------------
# Production-default resolvers (lazy — import nothing heavy at module load).
# ---------------------------------------------------------------------------


def _resolve_db_path(deps: RealLoopDeps) -> str:
    if deps.db_path:
        return deps.db_path
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _resolve_read_con(deps: RealLoopDeps, db_path: str) -> Any:
    if deps.read_con_factory is not None:
        return deps.read_con_factory(db_path)
    from runtime.db_lock import connect_read

    return connect_read(db_path)


def _resolve_search_fn(deps: RealLoopDeps) -> Callable[..., dict[str, Any]]:
    if deps.search_fn is not None:
        return deps.search_fn
    from substrate.graph.search import search

    return search


def _resolve_embedding(deps: RealLoopDeps) -> Any:
    if deps.embedding is not None:
        return deps.embedding
    from processing.embedding.embed import default_embedding_provider

    return default_embedding_provider()


def _resolve_exa_client(deps: RealLoopDeps) -> Any:
    if deps.exa_client is not None:
        return deps.exa_client
    # Construction resolves EXA_API_KEY — raises ExaClientError when no key
    # (the INERT state). The loop catches that and degrades to "no web", so a
    # keyless run does local-only retrieval rather than dying.
    from acquisition.search.exa.client import ExaClient

    return ExaClient()


def _resolve_discover(deps: RealLoopDeps) -> Callable[..., Any]:
    if deps.discover_fn is not None:
        return deps.discover_fn
    # The sanctioned discovery route — budget-reserved (``check_and_reserve``
    # on the §6.7 daily cap) + cache-checked BEFORE any spend. Imported here so
    # module load pulls in no Exa client / no substrate DB.
    from acquisition.search.exa.adapter import discover

    return discover


def _resolve_dispatch(deps: RealLoopDeps) -> tuple[Callable[..., Any], Any]:
    dispatch_fn = deps.dispatch_fn
    if dispatch_fn is None:
        from substrate.dispatch.router import dispatch as dispatch_fn  # type: ignore[no-redef]
    return dispatch_fn, deps.dispatch_config


def _resolve_legal_gate(deps: RealLoopDeps) -> Any:
    if deps.legal_gate is not None:
        return deps.legal_gate
    from substrate.legal_gate import default_legal_gate

    return default_legal_gate()


# ---------------------------------------------------------------------------
# The loop steps.
# ---------------------------------------------------------------------------


def _retrieve_local(
    deps: RealLoopDeps, sub_question: str,
) -> list[dict[str, Any]]:
    """Milestone 2 — vector search over the local graph's chunks. Read-only.
    Returns the raw search hits (chunk_id, document_id, similarity, …). Any
    failure (no DB, empty corpus) degrades to [] — local retrieval missing is
    "no in-corpus evidence", never a dead research."""
    try:
        db_path = _resolve_db_path(deps)
        con = _resolve_read_con(deps, db_path)
    except Exception:
        return []
    try:
        search_fn = _resolve_search_fn(deps)
        embedding = _resolve_embedding(deps)
        result = search_fn(con, sub_question, model=embedding, top_k=deps.local_top_k)
        return list(result.get("results") or [])
    except Exception:
        return []
    finally:
        with contextlib.suppress(Exception):
            con.close()


def _web_search(
    deps: RealLoopDeps, sub_question: str, investigation_id: str,
) -> tuple[list[Any], str | None]:
    """Milestone 3 — one Exa web search for the sub-question, routed through the
    sanctioned ``acquisition/search/exa/adapter.discover`` surface under the §16
    research-fanout exemption (docs/decisions/s16-research-fanout-exemption.md).

    ``discover`` is the ONE budget-bounded egress route: before any HTTP spend it
    (1) checks the §6.5 dedup cache (a cache hit costs $0) and (2) calls
    ``check_and_reserve(COST_PER_SEARCH_USD)`` against the §6.7 daily ceiling
    (``EXA_DAILY_BUDGET_USD`` ≈ $5), raising ``DiscoveryBudgetExceeded`` BEFORE
    issuing the call once the cap is reached. The loop NEVER calls
    ``ExaClient.search`` directly — that bypassed the cache + the daily ceiling,
    shipping a budgetless runaway the instant activation SPR-03 flips the key.

    Returns ``(proposals, error)`` where ``proposals`` is the list of
    ``DiscoveryProposed`` objects (each carries url/title/score/cost). ``error``
    is a short failure-mode label when the search could not run:

      * ``exa_unavailable`` — no key / client construction failed (the INERT
        state). Not billable.
      * ``exa_budget_exhausted`` — the §6.7 daily cap is reached; ``discover``
        refused BEFORE spending. The caller HALTS the per-question web fan-out;
        no spend happens past the ceiling. Not billable.
      * ``exa_error`` — Exa down / rate-limited (429 after retries) / empty-query
        error. Not fatal — the loop degrades to "no web evidence" and
        synthesizes from local only.

    Exa egress is BUDGET-bounded (the daily ceiling above), NOT rate-governed:
    ``govern_if_arxiv`` is a passthrough for the ``api.exa.ai`` host
    (rate_governor.py:460 — it governs arXiv hosts only). The throttle/governor
    framing does not apply to Exa; the daily-budget hard-stop is the bound.
    """
    try:
        # Resolve the client so a no-key construction is the INERT signal
        # (``ExaClientError`` when ``EXA_API_KEY`` is unset) — discover's own
        # default would construct it too, but resolving here lets the loop
        # distinguish "no key" from "budget exhausted" / "Exa down".
        client = _resolve_exa_client(deps)
    except Exception as exc:  # ExaClientError when EXA_API_KEY unset → INERT
        return [], f"exa_unavailable: {type(exc).__name__}"

    discover = _resolve_discover(deps)
    try:
        # THE web call — through the budget-reserved, cached discovery route.
        # ``discover`` calls ``check_and_reserve(COST_PER_SEARCH_USD)`` (§6.7
        # daily ceiling) + the §6.5 cache BEFORE ``client.search``. We pass our
        # resolved cassette/real client through so the same client is exercised.
        proposals = discover(
            query=sub_question,
            investigation_id=investigation_id,
            num_results=deps.web_num_results,
            client=client,
            daily_budget_usd=deps.exa_daily_budget_usd,
            events_dir=deps.discovery_events_dir,
            db_path=deps.db_path,
        )
        return list(proposals), None
    except Exception as exc:
        name = type(exc).__name__
        # The §6.7 budget hard-stop fires BEFORE the HTTP call — surface it as a
        # distinct halt signal (no spend happened past the ceiling) so the
        # caller halts the fan-out instead of treating it like a transient Exa
        # error. ``DiscoveryBudgetExceeded`` / ``DailyAcquisitionBudgetExceeded``
        # are the two budget exceptions ``discover`` → ``check_and_reserve`` /
        # ``assert_total_budget_ok`` raise.
        if name in ("DiscoveryBudgetExceeded", "DailyAcquisitionBudgetExceeded"):
            return [], f"exa_budget_exhausted: {name}"
        # Exa down / rate-limited (429 after retries) / empty-query error —
        # surface the class, never crash the fan-out.
        return [], f"exa_error: {name}"


def _servable_web_refs(
    deps: RealLoopDeps, web_results: Sequence[Any],
) -> list[SourceRef]:
    """Milestone 3 §9.0 gate — each web candidate (a ``DiscoveryProposed`` from
    the ``discover`` route) passes the servability/legal gate (the SAME
    ``LegalGate.check_url`` ``adapter.promote_discovery`` uses) BEFORE it can
    become a usable source ref. A non-servable (denylisted) source is DROPPED,
    never silently turned into a reference. Read-only — we check servability, we
    do NOT ingest (ingestion is SPR-07).

    §9.0 RECONCILIATION (D1): ``discover`` is budget-reserved + cached but does
    NOT consult the legal gate — per the adapter's own contract the legal gate
    sits on the PROMOTION path (``promote_discovery``), not on discovery
    (adapter.py module docstring §3). So this is the ONE AND ONLY fail-closed
    §9.0 servability gate on the loop's final web refs; there is NO double-gating
    (discover does not gate, so dropping this would re-open the §9.0 leak). The
    gate reads ``url`` (+ title/score/response_id) off the ``DiscoveryProposed``
    objects exactly as it read them off the raw Exa results before."""
    gate = _resolve_legal_gate(deps)
    refs: list[SourceRef] = []
    for r in web_results:
        url = getattr(r, "url", "") or ""
        if not url.strip():
            continue
        try:
            verdict = gate.check_url(url)
        except Exception:
            # A misconfigured gate must fail CLOSED — drop the candidate
            # rather than emit an ungated source ref (the §9.0 leak this gate
            # exists to prevent).
            continue
        if not getattr(verdict, "allowed", False):
            continue
        refs.append(
            SourceRef(
                source_document_id=url,  # SPR-07 assigns a real doc id on ingest
                kind="web_url",
                url=url,
                title=getattr(r, "title", None),
                similarity=getattr(r, "relevance_score", None),
                provider_response_id=getattr(r, "provider_response_id", None),
            )
        )
    return refs


def _local_refs(local_hits: Sequence[dict[str, Any]]) -> list[SourceRef]:
    """Local chunk hits → source refs. Prefer in-corpus evidence: these come
    FIRST in the ranked ref list the synthesis cites."""
    refs: list[SourceRef] = []
    for h in local_hits:
        doc_id = h.get("document_id")
        chunk_id = h.get("chunk_id")
        if not doc_id or not chunk_id:
            continue
        refs.append(
            SourceRef(
                source_document_id=str(doc_id),
                kind="local_chunk",
                chunk_id=str(chunk_id),
                title=h.get("document_title"),
                similarity=h.get("similarity"),
            )
        )
    return refs


def _build_synthesis_prompt(
    sub_question: str,
    local_hits: Sequence[dict[str, Any]],
    web_refs: Sequence[SourceRef],
) -> str:
    """Assemble the evidence_retriever prompt from local chunks + servable web
    snippets. Deterministic string assembly — the model is what reads it."""
    lines = [f"Sub-question: {sub_question}", "", "Local evidence:"]
    if local_hits:
        for h in local_hits:
            lines.append(
                f"- [{h.get('chunk_id')}] {(h.get('chunk_text') or '')[:240]}"
            )
    else:
        lines.append("- (none in corpus)")
    lines.append("")
    lines.append("Web evidence (servable):")
    if web_refs:
        for ref in web_refs:
            lines.append(f"- [{ref.url}] {ref.title or ''}")
    else:
        lines.append("- (none servable)")
    lines.append("")
    lines.append(
        "Produce one grounded insight answering the sub-question, citing the "
        "evidence above. If evidence is insufficient, say so."
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class _SynthResult:
    text: str
    cost_usd: float
    tokens: int
    provider: str | None
    model: str | None
    dispatch_event_id: str | None


def _synthesize(
    deps: RealLoopDeps,
    investigation_id: str,
    prompt: str,
) -> _SynthResult | None:
    """Milestone 4 — one model dispatch (``evidence_retriever`` role) over the
    assembled evidence. Returns None when dispatch is unavailable/keyless (the
    INERT state) so the loop can emit an honest "synthesis declined" note
    WITHOUT charging for a call that did not happen. The DispatchResult's
    ``provider`` + ``model`` + ``event_id`` are the model-side liveness marker —
    a stub loop cannot produce a registered provider name + a real DispatchCall
    event_id."""
    dispatch_fn, dispatch_config = _resolve_dispatch(deps)
    try:
        kwargs: dict[str, Any] = {"investigation_id": investigation_id}
        if dispatch_config is not None:
            kwargs["config"] = dispatch_config
        result = dispatch_fn(prompt, SYNTHESIS_ROLE, **kwargs)
    except Exception:
        # No provider registered / provider down / no key → INERT. Degrade to
        # "no synthesis", never crash the research.
        return None
    return _SynthResult(
        text=getattr(result, "text", "") or "",
        cost_usd=float(getattr(result, "cost_usd", 0.0) or 0.0),
        tokens=(
            int(getattr(getattr(result, "usage", None), "input_tokens", 0) or 0)
            + int(getattr(getattr(result, "usage", None), "output_tokens", 0) or 0)
        ),
        provider=getattr(result, "provider", None),
        model=getattr(result, "model", None),
        dispatch_event_id=getattr(result, "event_id", None),
    )


def _synth_payload(
    sub_question: str,
    insight_text: str,
    refs: Sequence[SourceRef],
    synthesized: bool,
) -> _SynthPayload:
    """Build a ``score_synthesis``-compatible payload from the findings so the
    loop's output is measurable (milestone 5 oracle gate). Local chunk ids are
    the ``supporting_chunk_ids`` the rubric's citation-density component reads."""
    chunk_ids = [r.chunk_id for r in refs if r.chunk_id]
    if not synthesized:
        return _SynthPayload(
            thesis_summary="",
            thesis_components=[],
            conviction_level=0.0,
            implicit_recommendation="insufficient_evidence",
        )
    return _SynthPayload(
        thesis_summary=insight_text,
        thesis_components=[
            _SynthComponent(
                claim=insight_text,
                supporting_chunk_ids=chunk_ids,
                confidence_basis=(
                    f"{len(chunk_ids)} local chunk(s) + "
                    f"{sum(1 for r in refs if r.kind == 'web_url')} servable web source(s)"
                ),
            )
        ],
        conviction_level=0.6 if chunk_ids else 0.4,
        implicit_recommendation=None,
    )


def score_findings(payload: _SynthPayload) -> Any:
    """Run the deterministic ``score_synthesis`` oracle on the loop's findings
    (milestone 5 absorbed must-have). Exposed as a module function so a test +
    the handoff can capture the loop's first measurable quality signal. A
    wired-but-bad loop scores low here — it is NOT hidden behind "tests pass"."""
    from substrate.synthesis_rubric.scorer import score_synthesis

    return score_synthesis(payload)


# ---------------------------------------------------------------------------
# The real loop factory — same callable shape as ``make_demo_loop``.
# ---------------------------------------------------------------------------


def real_research_loop(
    deps: RealLoopDeps | None = None,
) -> Callable[[LoopContext], AsyncIterator[StepEvent]]:
    """Build the real browse loop. Returns the SAME callable shape
    ``make_demo_loop`` returns — a ``Callable[[LoopContext], AsyncIterator[StepEvent]]``
    — so ``_research_loop_factory`` and ``HostLocalRunner`` consume it with no
    change.

    ``deps`` defaults to production resolvers (lazy — model + Exa + DB resolved
    only when the loop RUNS, which needs activation SPR-03's keys). Tests inject
    a ``RealLoopDeps`` carrying cassettes + a seeded graph.
    """
    deps = deps or RealLoopDeps()

    async def _loop(ctx: LoopContext) -> AsyncIterator[StepEvent]:
        yield ctx.plan_event(f"plan for: {ctx.sub_question}")

        # --- checkpoint (steering) BEFORE any work, like the demo loop ---
        sub_q = await ctx.checkpoint()

        # --- M2: local-corpus retrieval FIRST (provably before web) ------
        # Offloaded to a thread: the DuckDB read is blocking; running it on
        # the event loop would stall sibling researches. asyncio.to_thread
        # also means an externally-killed worker can't leak a process-pool
        # semaphore (the parameter_extractor / loky failure mode — there is
        # no process pool here to wedge).
        local_hits = await asyncio.to_thread(_retrieve_local, deps, sub_q)
        local_refs = _local_refs(local_hits)
        # NOTE: the LoopContext factories take **data (keyword fan-in), NOT a
        # ``data=`` dict — passing data={...} would nest it under a "data" key.
        yield ctx.step(
            f"local retrieval: {len(local_hits)} chunk(s)",
            phase="local_retrieval",
            chunk_count=len(local_hits),
            chunk_ids=[r.chunk_id for r in local_refs],
            top_similarity=local_hits[0].get("similarity") if local_hits else None,
        )

        await ctx.checkpoint()

        # --- M3: Exa web fan-out via the budget-reserved discover route,
        #         then §9.0 servability gate over its proposals ------------
        web_results, web_err = await asyncio.to_thread(
            _web_search, deps, sub_q, ctx.investigation_id,
        )
        servable_refs = _servable_web_refs(deps, web_results)
        dropped = len(web_results) - len(servable_refs)
        # The §6.7 daily-budget ceiling halts the web fan-out: ``discover``
        # refuses BEFORE the HTTP call once the cap is reached, so a
        # budget-exhausted question issues NO further searches and spends
        # nothing past the ceiling. Surface it on the step so the halt is
        # observable on the glass-box stream.
        web_budget_halted = bool(web_err) and web_err.startswith("exa_budget_exhausted")
        # Charge the web step ONLY when a real Exa call ran (results present OR a
        # generic ``exa_error`` after the call). INERT (``exa_unavailable``) and
        # budget-halted (``exa_budget_exhausted``, refused BEFORE the call) are
        # NOT billable — no HTTP spend happened. The per-search cost comes from
        # the proposals' own Exa estimate; an empty servable list after a real
        # call still ran the call, so it is charged.
        web_cost = 0.0
        web_ran = web_err is None or web_err.startswith("exa_error")
        if web_results:
            # Sum the per-result cost estimates Exa attributed (client.py
            # amortizes the per-call cost across results) — the call's OWN
            # reported cost, not a made-up cost_per_step.
            web_cost = sum(
                float(getattr(r, "cost_usd_estimate", 0.0) or 0.0) for r in web_results
            )
        yield ctx.step(
            f"web fan-out: {len(web_results)} result(s), {len(servable_refs)} servable, "
            f"{dropped} dropped by §9.0 gate"
            + (f" [{web_err}]" if web_err else ""),
            # §16 research-fanout exemption: this web egress is the ONE
            # sanctioned external-execution carve-out
            # (docs/decisions/s16-research-fanout-exemption.md). cost is Exa's
            # OWN per-search estimate — billed only because a real call ran.
            cost_usd=web_cost if web_ran else 0.0,
            phase="web_fanout",
            s16_exemption="research-fanout",
            web_result_count=len(web_results),
            servable_count=len(servable_refs),
            dropped_non_servable=dropped,
            web_error=web_err,
            # §6.7 daily-budget halt: discover refused BEFORE spending — the
            # fan-out is bounded by the daily ceiling, not by a rate governor.
            web_budget_halted=web_budget_halted,
            # Exa's request id — the WEB-side liveness marker.
            exa_request_ids=[
                r.provider_response_id for r in servable_refs if r.provider_response_id
            ],
        )

        await ctx.checkpoint()

        # --- M4: synthesize ONE grounded insight with a real source ref --
        # Prefer local (in-corpus) evidence; web refs follow.
        all_refs = local_refs + servable_refs
        prompt = _build_synthesis_prompt(sub_q, local_hits, servable_refs)
        synth = await asyncio.to_thread(_synthesize, deps, ctx.investigation_id, prompt)

        if synth is not None and all_refs:
            # The insight carries a CONCRETE source ref — the first ref's
            # source_document_id (local chunk's document_id preferred, else a
            # servable URL). This is the data SPR-07 turns into an edge; the
            # ``source_document_id`` field name reuses the existing vocabulary,
            # NOT a synonym. cost is the dispatch result's OWN computed cost.
            primary = all_refs[0]
            # The note carries the FINDING + its source refs (no cost — the
            # funnel promotes notes into graph insights, so the note stays a
            # clean promotion payload). The synthesis CHARGE rides on the
            # separate cost-bearing ``step`` emitted just below, so the runner
            # bills the real dispatch cost without the funnel ever seeing it.
            yield ctx.note(
                synth.text or f"insight for: {sub_q}",
                source_document_id=primary.source_document_id,
                source_kind=primary.kind,
                source_chunk_id=primary.chunk_id,
                source_url=primary.url,
                supported_by=primary.source_document_id,
                # liveness markers, recorded on the emitted finding:
                dispatch_provider=synth.provider,
                dispatch_model=synth.model,
                dispatch_event_id=synth.dispatch_event_id,
                exa_request_id=primary.provider_response_id,
                all_source_document_ids=[r.source_document_id for r in all_refs],
            )
            # A separate cost-bearing step carries the synthesis charge so the
            # note stays a clean promotion payload (the funnel promotes notes;
            # cost on the note would also work, but a dedicated step keeps the
            # ledger legible). Charged ONLY because a real dispatch ran.
            if synth.cost_usd or synth.tokens:
                yield ctx.step(
                    f"synthesis dispatch ({synth.provider}/{synth.model})",
                    cost_usd=synth.cost_usd,
                    tokens=synth.tokens,
                    phase="synthesis",
                    dispatch_event_id=synth.dispatch_event_id,
                    dispatch_provider=synth.provider,
                )
            synthesized = True
        else:
            # Honest no-result state: no servable evidence OR synthesis
            # unavailable (INERT / no key). Emit a question (the open thread)
            # and DO NOT charge — no synthesis call was billable.
            yield ctx.question(
                f"open question — insufficient servable evidence for: {sub_q}",
                phase="synthesis_declined",
                reason="no_servable_evidence" if not all_refs else "synthesis_unavailable",
                local_chunk_count=len(local_refs),
                servable_web_count=len(servable_refs),
            )
            synthesized = False

        # --- M5 oracle: score the findings so a wired-but-bad loop is seen.
        # Emitted as a ``step`` (NOT a ``note``) on purpose: the promotion
        # funnel promotes every ``note`` as a graph insight, and the quality
        # score is a diagnostic about the run, not a finding worth persisting.
        # A cost-free step is observable on the glass-box stream without
        # leaking a bogus insight into the graph.
        payload = _synth_payload(
            sub_q, synth.text if synth else "", all_refs, synthesized,
        )
        score = score_findings(payload)
        yield ctx.step(
            f"quality score: composite={score.composite:.3f}",
            phase="quality_score",
            composite=score.composite,
            citation_density=score.citation_density,
            voice_style=score.voice_style,
            constraint_compliance=score.constraint_compliance,
            rubric_notes=score.notes,
        )

    return _loop
