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

Live mode = real machinery, full stop (no measurement theater)
    ``build_live_provider`` — the constructor of record — REFUSES
    (``ValueError``) any injected pipeline seam and any caller-supplied
    ``loop_fn`` when ``allow_live=True``. Live mode SELF-BUILDS the real Exa
    gather loop (``make_exa_gather_loop``,
    ``runtime/research_runner/host_local.py`` :567 — the same loop prod gates
    behind ``ANTIEK_DRW_GATHER=exa``,
    ``interfaces/research/api/cascade_routes.py`` ``_research_loop_factory``
    :260) and the real gather / synthesis / usage / source-URL seams; the
    caller may tune budgets, timeout, and discovery ``top_k`` only. There is
    therefore NO caller-supplied part on the live path — nothing to veneer,
    wrap, or attribute-spoof through the factory.

    Defense-in-depth for DIRECT dataclass construction and for
    ``dataclasses.replace`` (both re-run ``__post_init__``):
    ``LiveResearchProvider.__post_init__`` (a) refuses a ``loop_fn`` that is
    (a product of) ``make_demo_loop`` / ``make_contract_gather_stub``
    (host_local.py :494 / :526 — the benchmark mock and the honest production
    placeholder; both fabricate steps and retrieve nothing), unwrapping
    ``functools.partial`` / ``__wrapped__`` chains first; and (b) enforces a
    TWO-direction flag ⇔ seam-provenance invariant by OBJECT IDENTITY, not
    name: ``allow_live=True`` requires the env keys, a loop stamped with this
    module's private provenance token (only ``_build_real_exa_loop`` stamps
    it), and all four seams to be this module's real implementations (the two
    factory-built closures carry the same token; the two module-level seams
    are matched with direct ``is`` identity), while ``allow_live=False``
    refuses ANY real seam. So a replace that flips the flag while keeping
    fake seams, flips a real-machinery instance to "offline" (which could
    spend/hit the network from inside a test), or swaps a single seam on a
    live instance is refused, and honest uses of ``replace`` (tuning the
    timeout on an offline instance) keep working. Names were deliberately
    rejected as the provenance signal: a foreign module naturally named
    ``live_provider`` / ``host_local`` with same-named callables mimics any
    ``__qualname__``/module check with zero forgery; a module-private token
    object cannot be recreated. (The mock/stub refusal stays name-based — it
    is a NEGATIVE guard, and dressing a loop up as a known mock to get
    refused is self-sabotage, not a spoof.)

    Honest threat model: the ``__post_init__`` checks catch HONEST MISTAKES
    (grabbing the wrong factory, wiring a stub out of habit) and, with
    identity-registry provenance, also natural name collisions, deliberate
    name-mimicry, and ``functools.wraps`` wrappers (which copy ``__dict__``
    and ``__wrapped__`` but are still a different OBJECT than the registered
    real seam). The remaining out-of-scope class is now narrow and pure
    sabotage: importing this module and calling its private ``_register_real``
    on a fake, or mutating ``_REAL_BY_ROLE`` by hand. The structural guarantee
    stands: the constructor of record has no dishonest path, and every public
    mutation path (direct construction, ``dataclasses.replace``) re-validates
    the flag/provenance invariant — the adapter guards measurement integrity
    against mistakes, not against an operator deliberately sabotaging their
    own eval with the module's own internals.

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
      and are NEVER reported; an individual ``doc-url-*`` row whose
      ``source_uri`` is missing or non-http is SKIPPED, not invented —
      under-reporting can only depress the judged score, never inflate it.
      But a report with ZERO resolvable real-URL sources overall refuses
      (``ProviderFailure``): a deep-research report with no real provenance
      at all signals broken provenance wiring (or a stub posing as research),
      and letting the judge score a sourceless report would launder that
      breakage into a measured number.
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
    ``allow_live=True`` requires the env keys (``EXA_API_KEY`` for gather
    discovery, ``ANTHROPIC_API_KEY`` for dispatch-backed synthesis) at
    construction — otherwise it refuses with a clear reason — and admits NO
    injected parts (see above). Without ``allow_live``, every pipeline seam
    (gather / synthesize / usage reader / source-url lookup) MUST be
    injected and no ``loop_fn`` may be supplied (offline fakes never run a
    browse loop, so a caller loop could only exist to confuse identity), so
    offline tests exercise the full fail-closed mapping with fakes and zero
    network — the same injectable-client pattern as ``live_judge.py``.
    Construction never performs I/O either way.

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
import weakref
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

# OBJECT-IDENTITY provenance for the real live parts, by REGISTRY not by a
# function attribute. Names can be mimicked naturally (a foreign module named
# ``live_provider`` / ``host_local`` with same-named callables passes any name
# check with zero forgery), and a stamped function ATTRIBUTE is worse than it
# looks: ``functools.wraps(real)`` copies ``__dict__``, so a fake wrapper would
# INHERIT the stamp while its own code runs. A module-private ``WeakSet`` per
# role, checked by EXPLICIT ``is`` against each member (never ``in`` — that
# consults ``__hash__``/``__eq__``, which an impostor can override to compare
# equal to a real seam), is forgery-proof: only the real object satisfies
# ``is``. Each real builder registers its product in the role's set at
# creation. The sets are module-private, unexported, and hold weak refs so a
# discarded provider's closures are collectible.
_ROLE_LOOP = "loop"
_ROLE_GATHER = "gather"
_ROLE_SYNTHESIZE = "synthesize"
_REAL_BY_ROLE: dict[str, weakref.WeakSet[object]] = {
    _ROLE_LOOP: weakref.WeakSet(),
    _ROLE_GATHER: weakref.WeakSet(),
    _ROLE_SYNTHESIZE: weakref.WeakSet(),
}

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
      Must be >= 1: the real loop's DONE path always steps, so a zero here
      means nothing real happened and the query fails closed.
    * ``investigation_ids`` — session id + every leaf id, the trajectories
      the usage reader sums ``DISPATCH_CALL`` accounting over. Must be
      non-empty and DUPLICATE-FREE: an honest gather never emits the same
      trajectory twice, and a duplicate would double-count usage. The
      adapter refuses duplicates rather than silently deduping.
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


def _callable_qualname(fn_like: object) -> str:
    """Qualname of a callable after bounded unwrapping. Used ONLY by the
    NEGATIVE mock/stub guard — name-mimicry there would be self-sabotage
    (dressing your loop up as a known mock to get refused)."""
    fn = _unwrap_loop_fn(fn_like)
    qualname = getattr(fn, "__qualname__", "")
    return qualname if isinstance(qualname, str) else ""


def _refuse_mock_loop(loop_fn: object) -> None:
    """Raise ``ValueError`` if ``loop_fn`` is (or is a product of) a known
    mock/stub gather factory. Measuring a mock is measurement theater — this
    adapter exists to measure the actual product."""
    qualname = _callable_qualname(loop_fn)
    for factory in _MOCK_LOOP_FACTORIES:
        if qualname == factory or qualname.startswith(f"{factory}."):
            raise ValueError(
                f"refusing to build the live eval provider around {factory!r}: "
                "it is a mock/stub gather loop, and scoring it would measure "
                "theater, not the product. Use the real Exa gather loop "
                "(make_exa_gather_loop) via build_live_provider(allow_live=True)."
            )


def _register_real(fn: object, role: str) -> None:
    """Record ``fn`` as the real implementation of ``role`` by object identity.
    Called by the real builders at creation; nothing else may call it, so the
    only way into a role's set is being minted by this module."""
    _REAL_BY_ROLE[role].add(fn)


def _has_real_role(fn_like: object, role: str) -> bool:
    """True iff THIS object (strict ``is`` identity, no unwrap) was registered
    for ``role``. Explicit ``is`` — NOT ``in`` — because ``WeakSet.__contains__``
    consults ``__hash__``/``__eq__``, which an impostor can override to compare
    equal to a real seam; only object identity is unforgeable. Defeats name
    mimicry, ``functools.wraps`` (a wrapper is a different object), and
    equality-spoofing impostors."""
    return any(fn_like is real for real in _REAL_BY_ROLE[role])


def _is_real_exa_loop(loop_fn: object) -> bool:
    """True only for the loop minted by ``_build_real_exa_loop`` (registered
    under ``"loop"``). A naturally same-named loop from a foreign ``host_local``
    module is not registered; a real non-loop component misplaced here is
    registered under the wrong role. Both fail."""
    return _has_real_role(loop_fn, _ROLE_LOOP)


def _missing_live_env() -> list[str]:
    return [key for key in REQUIRED_LIVE_ENV if not os.environ.get(key, "").strip()]


# The four seam fields of LiveResearchProvider. ``allow_live`` ⇔ all-real-seams
# is a TWO-direction invariant enforced in ``__post_init__`` — which
# ``dataclasses.replace`` re-runs, so a replace that flips the flag or swaps
# one seam cannot produce a flag/provenance mismatch through the public API.
_SEAM_FIELDS: tuple[str, ...] = (
    "gather",
    "synthesize",
    "usage_reader",
    "source_url_lookup",
)


def _is_real_seam(seam: object, role: str) -> bool:
    """Object-identity seam provenance, ROLE-SPECIFIC. The two module-level
    real seams are matched by direct ``is`` identity against the function of
    that exact role; the two factory-built closures carry the private
    ``(token, role)`` pair their builders stamped at creation. A naturally
    same-named callable from a foreign module passes neither (no name check
    to mimic), a REAL callable of a DIFFERENT role fails the role match —
    so ``replace(live, synthesize=live.gather)`` refuses — and a wrapper
    around a real seam (``functools.wraps`` copies ``__dict__`` AND
    ``__wrapped__``) or an equality-spoofing impostor both fail because the
    check is strict ``is`` identity: the executing callable itself must BE the
    registered one."""
    if role == "usage_reader":
        return seam is _read_dispatch_usage
    if role == "source_url_lookup":
        return seam is _lookup_document_source_uri
    return _has_real_role(seam, role)


def _is_real_machinery(seam: object) -> bool:
    """Role-BLIND check for the offline direction: an offline-flagged provider
    must not carry real machinery in ANY field (even the wrong one) — a real
    gather sitting in the synthesize slot could still spend money. Unlike the
    positive checks, this one DOES unwrap: hiding real machinery behind a
    wrapper must still refuse (fail closed = refuse MORE, never less).

    A ``weakref.proxy`` forwards its calls to a referent this code cannot
    cheaply deref (there is no public deref for a proxy), so it could forward
    to real machinery invisibly. An offline test double is never legitimately
    a weakref proxy, so we fail closed on ANY proxy — refuse the unprovable."""
    if isinstance(seam, weakref.ProxyTypes):
        return True
    for candidate in (seam, _unwrap_loop_fn(seam)):
        if candidate is _read_dispatch_usage or candidate is _lookup_document_source_uri:
            return True
        if any(
            candidate is real
            for real_set in _REAL_BY_ROLE.values()
            for real in real_set
        ):
            return True
    return False


@dataclass(frozen=True)
class LiveResearchProvider:
    """Callable ``ProviderFn`` running the real product research path per
    query, fail-closed to ``ProviderFailure`` on every dishonest outcome.

    Construct via :func:`build_live_provider` — the constructor of record,
    whose live mode admits NO injected parts. All four pipeline seams are
    REQUIRED fields — there is no silent default. ``__post_init__`` enforces
    a TWO-direction flag ⇔ seam-provenance invariant on every construction
    path (``dataclasses.replace`` re-runs it): ``allow_live=True`` requires
    the self-built real Exa loop, the env keys, AND every seam to be this
    module's real implementation; ``allow_live=False`` refuses any real
    seam, so an offline-flagged provider can never run real machinery or
    spend. Provenance is OBJECT IDENTITY (a module-private token / direct
    ``is`` checks), not names — natural name collisions and deliberate
    name-mimicry both fail. The only remaining bypass is attaching this
    module's private token to a fake by hand — pure sabotage, documented
    out of scope in the module docstring's threat model.
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
                    "allow_live=True requires the REAL Exa gather loop minted "
                    "by this module's _build_real_exa_loop (object-identity "
                    "provenance token; a same-named loop from elsewhere does "
                    "not qualify); refusing to flag a provider live around "
                    "anything else."
                )
            missing = _missing_live_env()
            if missing:
                raise ValueError(
                    f"allow_live=True but required env keys are missing: {missing}. "
                    "The live eval path needs EXA_API_KEY (gather discovery) and "
                    "ANTHROPIC_API_KEY (dispatch-backed synthesis) at construction."
                )
            non_real = [
                name
                for name in _SEAM_FIELDS
                if not _is_real_seam(getattr(self, name), name)
            ]
            if non_real:
                raise ValueError(
                    f"allow_live=True requires the REAL pipeline seams, each in "
                    f"its OWN role; these are not this module's real "
                    f"implementations for their field: {non_real}. A live-flagged "
                    "provider composed from injected or role-swapped parts could "
                    "measure anything (dataclasses.replace re-runs this check, "
                    "so flipping the flag or swapping seams on an instance is "
                    "refused too)."
                )
        else:
            if self.loop_fn is not None:
                raise ValueError(
                    "allow_live=False must carry loop_fn=None: offline fakes "
                    "never run a browse loop (the factory's own contract), so "
                    "anything in the loop slot of an offline instance — real "
                    "machinery included — is a flag/seam mismatch."
                )
            real = [
                name for name in _SEAM_FIELDS if _is_real_machinery(getattr(self, name))
            ]
            if real:
                raise ValueError(
                    f"allow_live=False must not carry real-machinery seams: {real}. "
                    "An offline-flagged provider around real seams could spend "
                    "money and hit the network from inside a test; construct "
                    "live providers only via build_live_provider(allow_live=True)."
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
        if outcome.tool_calls == 0:
            raise ProviderFailure(
                "gather reported zero tool calls: a real research run always "
                "performs tool actions (the Exa loop's completion path always "
                "steps), so nothing real backs this report"
            )
        if not outcome.investigation_ids:
            raise ProviderFailure(
                "gather reported no investigation ids; token accounting cannot "
                "be bound to real trajectories"
            )
        if len(set(outcome.investigation_ids)) != len(outcome.investigation_ids):
            raise ProviderFailure(
                "gather reported duplicate investigation ids: an honest gather "
                "never emits the same trajectory twice, and a duplicate would "
                "double-count dispatch usage (refusing rather than deduping)"
            )

    def _resolve_sources(
        self, documents: tuple[tuple[str, str], ...]
    ) -> tuple[SourceRef, ...]:
        """Real-URL provenance only: ``doc-url-*`` documents resolved through
        the ``documents.source_uri`` lookup. Placeholder ``doc-gather-*`` docs
        and INDIVIDUALLY unresolvable/non-http rows are skipped — one missing
        source among others can only depress the judged score; an invented one
        would inflate it. But ZERO resolvable sources overall refuses: a
        deep-research report with no real-URL provenance at all signals broken
        provenance wiring (or non-research posing as research), and handing
        the judge a sourceless report would launder that breakage into a
        measured score."""
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
        if not sources:
            raise ProviderFailure(
                "no resolvable real-URL provenance in the evidence pack: a "
                "deep-research report with zero real sources signals broken "
                "provenance wiring; refusing to let the judge score a "
                "sourceless report"
            )
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
    discovery_top_k: int = 3,
) -> LiveResearchProvider:
    """Build the live ``ProviderFn``. Two mutually exclusive construction
    modes, both inert (no I/O happens here):

    * **Offline (default, ``allow_live=False``)** — every pipeline seam
      (``gather``, ``synthesize``, ``usage_reader``, ``source_url_lookup``)
      MUST be injected; a missing seam refuses construction rather than
      silently wiring real machinery. No ``loop_fn`` may be supplied (fakes
      never run a browse loop). This is the test mode.
    * **Live (``allow_live=True``)** — REAL MACHINERY, FULL STOP. Any
      injected seam or caller-supplied ``loop_fn`` REFUSES construction.
      Live mode self-builds the real Exa gather loop and the real seams
      (DRW cascade gather, Loop 1 synthesis tail, ``DISPATCH_CALL``
      trajectory accounting, ``documents.source_uri`` lookup) and requires
      the env keys at construction. The caller may tune ONLY budgets,
      timeout, and ``discovery_top_k`` — the knobs a product launch exposes
      (cascade_routes.py ``launch``), none of which change WHAT is measured.

    ``loop_fn`` exists as a parameter solely to refuse it loudly with a
    reasoned ``ValueError`` (rather than an opaque ``TypeError``) — there is
    no accepted value in either mode.
    """
    if loop_fn is not None:
        raise ValueError(
            "build_live_provider accepts no caller-supplied loop_fn in any "
            "mode: live mode self-builds the real Exa gather loop, and "
            "offline fakes never run a browse loop. A caller-supplied loop "
            "could only exist to substitute what gets measured."
        )
    if allow_live:
        injected = [
            name
            for name, seam in (
                ("gather", gather),
                ("synthesize", synthesize),
                ("usage_reader", usage_reader),
                ("source_url_lookup", source_url_lookup),
            )
            if seam is not None
        ]
        if injected:
            raise ValueError(
                f"allow_live=True refuses injected seams {injected}: live mode "
                "is real machinery, full stop — a live-flagged provider "
                "composed from injected parts could measure anything. Tune "
                "budgets/timeout/discovery_top_k, or drop allow_live for the "
                "fully-injected offline mode."
            )
        missing = _missing_live_env()
        if missing:
            # Refuse BEFORE importing/constructing any real machinery —
            # same message the dataclass gate raises, surfaced early.
            raise ValueError(
                f"allow_live=True but required env keys are missing: {missing}. "
                "The live eval path needs EXA_API_KEY (gather discovery) and "
                "ANTHROPIC_API_KEY (dispatch-backed synthesis) at construction."
            )
        real_loop = _build_real_exa_loop(top_k=discovery_top_k)
        return LiveResearchProvider(
            gather=_build_real_gather(
                real_loop,
                per_research_budget_usd=per_research_budget_usd,
                aggregate_budget_usd=aggregate_budget_usd,
            ),
            synthesize=_build_real_synthesize(),
            usage_reader=_read_dispatch_usage,
            source_url_lookup=_lookup_document_source_uri,
            loop_fn=real_loop,
            allow_live=True,
            per_query_timeout_s=per_query_timeout_s,
        )
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
    assert gather is not None  # narrowed by the check above
    assert synthesize is not None
    assert usage_reader is not None
    assert source_url_lookup is not None
    return LiveResearchProvider(
        gather=gather,
        synthesize=synthesize,
        usage_reader=usage_reader,
        source_url_lookup=source_url_lookup,
        loop_fn=None,
        allow_live=False,
        per_query_timeout_s=per_query_timeout_s,
    )


# ---------------------------------------------------------------------------
# Real defaults (live path only; every import is lazy so offline use of this
# module never pays for — or depends on — the product stack).
# ---------------------------------------------------------------------------


def _build_real_exa_loop(*, top_k: int = 3) -> object:
    """The real gather loop, mirroring prod's ``ANTIEK_DRW_GATHER=exa`` branch
    (cascade_routes.py :273-275, default ``top_k=3``), stamped with this
    module's private provenance token — the ONLY way a loop can satisfy the
    ``allow_live`` identity check. Construction is lazy/inert — the Exa client
    reads ``EXA_API_KEY`` on first discover, not here."""
    from runtime.research_runner import make_exa_gather_loop

    loop = make_exa_gather_loop(top_k=top_k)
    _register_real(loop, _ROLE_LOOP)
    return loop


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

    # Register by object identity (not a copyable attribute): the allow_live
    # seam check tests membership, which functools.wraps cannot forge.
    _register_real(_gather, _ROLE_GATHER)
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

    # Same identity registration as _build_real_gather's closure.
    _register_real(_synthesize, _ROLE_SYNTHESIZE)
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
