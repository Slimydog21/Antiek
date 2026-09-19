"""DRW SPR-06 transport — the cascade/research REST + SSE surface.

This is the HTTP layer the SPR-09 glass-box monitor consumes. SPR-06 built
the orchestration *service* (``orchestration/cascade_session.CascadeSession``)
+ the durable ``reconstruct_session`` recovery; this router wires it (and the
SPR-05 planner + SPR-02 runner) into a usable API, following the same
standalone-``APIRouter`` + one-line ``include_router`` discipline as
``speak_routes`` / ``write`` so the hot ``create_app`` factory stays mergeable.

Lifecycle model (honest, the make-or-break part):

* Live sessions are held in a process-local registry (``_SESSIONS``). Under
  the project's ``--workers 1`` single-writer invariant there is exactly one
  process + one event loop, so an in-memory registry is correct, not a
  shortcut. Launch starts the fan-out and schedules its completion
  (join + funnel-drain + merge + Loop 1 synthesis tail on the session
  parent) as a background task on that loop when a synthesis runner is wired.
* Recovery is from the **event log**, not the registry: ``GET`` status of a
  session not in memory (after eviction or restart) calls
  ``reconstruct_session`` — membership via ``investigation.spawned_from``,
  per-research state via terminal events.
* Delivery on the SSE stream is **at-least-once with idempotent client
  handling**: live sessions stream the full per-step event queue; a reconnect
  after the in-memory session is gone replays the durable lifecycle state and
  closes. The client keys on ``(investigation_id, seq)`` (SPR-09 M4). We do
  NOT claim exactly-once.

The browse loop is injected (``_research_loop_factory``) — it defaults to the
contract gather stub (``make_contract_gather_stub``); the real Exa→Browserbase
loop drops into the same seam with zero route changes. §16 honored: no Daytona;
the host-local cap is what bounds "launch 20 at once", surfaced via the
aggregate budget.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from interfaces.research.api.dispatch_failure import classify_dispatch_failure
from interfaces.research.api.investigation_access import (
    InvestigationAccessDenied,
    InvestigationAuthenticationRequired,
    RequestInvestigationAuthority,
    authority_for_investigation,
    authority_from_request,
    bind_child_investigation,
    bind_new_investigation,
    owns_investigation,
    require_investigation_owner,
)
from orchestration.cascade_session import CascadeSession, Leaf, reconstruct_session
from roles.cascade_planner import (
    PlanNotApproved,
    PlanReport,
    SubQuestion,
    build_plan,
)
from roles.cascade_planner.planner import DispatchDecomposer
from roles.cascade_planner.tenancy import (
    LaunchAttemptConflict,
    LaunchAttemptUnknown,
    PlanAuthorityDenied,
    approve_plan_authorized,
    claim_launch_attempt_authorized,
    claim_plan_launch_authorized,
    complete_launch_attempt_authorized,
    is_plan_launchable_authorized,
    load_plan_authorized,
    plan_tree_fingerprint,
    read_launch_attempt_authorized,
    save_plan_authorized,
)
from roles.cascade_planner.tree_contract import PlanTree
from runtime.db_lock import connect_read, connect_write
from runtime.research_runner import (
    BudgetCap,
    BudgetManager,
    Command,
    CommandKind,
    HostLocalRunner,
    PromotionFunnel,
    make_authorized_multi_source_gather_loop,
    make_contract_gather_stub,
    make_exa_gather_loop,
)
from runtime.research_runner.gather_launch_plan import AuthorizedGatherLaunchPlan
from runtime.research_runner.gather_plan import GatherSource, GatherSourcePlan
from runtime.research_runner.production_gather_providers import (
    arxiv_configuration_sha256,
    exa_configuration_sha256,
    parallel_configuration_sha256,
    substack_subscription_configuration_sha256,
)
from runtime.research_runner.protocol import BrowseLoop, ResearchPlan
from substrate.graph import default_db_path, ensure_initialized
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.policy_store import (
    LegalPolicyDenied,
    account_policy_authority,
    append_policy_event,
    normalize_matcher,
    policy_snapshot,
)
from substrate.legal_gate.readiness import legal_policy_readiness, require_policy_snapshot
from substrate.multi_user.auth import UserClaims

if TYPE_CHECKING:
    from orchestration.session_evidence_pack import SessionEvidencePack
    from processing.embedding import EmbeddingProvider
    from substrate.context_pack.recursive_feedback import FileRecursiveFeedbackStore

logger = logging.getLogger(__name__)

cascade_router = APIRouter(prefix="/research", tags=["deep-research"])


@cascade_router.get("/driver-readiness")
def driver_readiness(
    request: Request,
    response: Response,
    research_tier: Literal["fast", "deep", "wrestle"] = "deep",
) -> dict[str, object]:
    """Secret-free boot-attested target preview for launch surfaces."""
    from substrate.dispatch.research_tier import resolve_available_research_tier

    response.headers["Cache-Control"] = "no-store"
    try:
        target = resolve_available_research_tier(
            research_tier, getattr(request.app.state, "registered_providers", None)
        )
    except ValueError as exc:
        return {
            "research_tier": research_tier,
            "ready": False,
            "provider": None,
            "model": None,
            "candidate_rank": None,
            "availability_source": "boot_registered_providers",
            "reason": str(exc),
        }
    return {
        "research_tier": target.tier,
        "ready": True,
        "provider": target.provider,
        "model": target.model,
        "candidate_rank": target.candidate_rank,
        "availability_source": target.availability_source,
        "reason": target.why,
    }


# ---------------------------------------------------------------------------
# Process-local live-session registry (single-writer / one event loop).
# ---------------------------------------------------------------------------

_SESSIONS: dict[str, CascadeSession] = {}
_SESSION_TASKS: dict[str, asyncio.Task[None]] = {}


def _require_session_access(request: Request, session_id: str) -> RequestInvestigationAuthority:
    try:
        access = authority_from_request(request, session_id)
        require_investigation_owner(access)
        return access
    except InvestigationAuthenticationRequired as exc:
        raise HTTPException(status_code=401, detail="authentication required") from exc
    except InvestigationAccessDenied as exc:
        raise HTTPException(status_code=404, detail="research session not found") from exc


# Optional hook set by ``create_app`` after Loop 1 handlers register.
# Runs Path A synthesis tail (phases 6–9) once gather + merge finish.
SynthesisTailRunner = Callable[[CascadeSession, "SessionEvidencePack"], Awaitable[object]]
_SYNTHESIS_TAIL_RUNNER: SynthesisTailRunner | None = None


def set_synthesis_tail_runner(runner: SynthesisTailRunner) -> None:
    """Wire the Loop 1 synthesis tail into cascade background completion."""
    global _SYNTHESIS_TAIL_RUNNER
    _SYNTHESIS_TAIL_RUNNER = runner


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def _db() -> str:
    path = default_db_path()
    ensure_initialized(path)
    return path


def _recursive_feedback_store() -> FileRecursiveFeedbackStore:
    from substrate.context_pack.recursive_feedback import FileRecursiveFeedbackStore

    configured = os.environ.get("ANTIEK_RECURSIVE_FEEDBACK_DIR", "").strip()
    root = (
        Path(configured)
        if configured
        else Path(os.environ.get("ANTIEK_RESEARCH_EVENTS_DIR", ".antiek/events")).parent
        / "recursive-feedback"
    )
    return FileRecursiveFeedbackStore(root)


@contextmanager
def _write(purpose: str) -> Iterator[Any]:
    con = connect_write(_db(), purpose=purpose)
    try:
        yield con
    finally:
        con.close()


@contextmanager
def _translate() -> Iterator[None]:
    """Map DRW domain exceptions onto HTTP status codes."""
    try:
        yield
    except PlanNotApproved as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PlanAuthorityDenied as e:
        raise HTTPException(status_code=404, detail="plan not found") from e


def _embedding_provider() -> EmbeddingProvider:
    from processing.embedding import default_embedding_provider

    return default_embedding_provider()


class _LazyReuseSubstrate:
    """The §9.0-gated reuse substrate the runner's flywheel hook
    (``HostLocalRunner._maybe_reuse_prior_knowledge``) queries so a launched
    research emits ``knowledge.reused`` and the compounding flywheel turns.

    THE FIX (``docs/decisions/flywheel-reuse-single-writer.md``). #140 built the
    substrate with ``make_substrate("brute_force", _db(), …)``, whose ``.open()``
    calls ``connect_read`` (``read_only=True``). DuckDB refuses a read-only
    handle to a file already held read-write in the same process, so once the
    funnel opened its promotion writer every cascade launch raised
    ``ConnectionException`` (6 ``test_cascade_api`` failures); #178/#190 reverted
    it.

    This NEVER calls ``connect_read``. It opens ONE plain read-write
    ``duckdb.connect`` handle and builds a brute-force substrate from its
    ``.cursor()`` (``make_substrate_from_con``). Three deliberate, load-bearing
    choices:

    * Read-WRITE config, not ``connect_read``. DuckDB permits multiple handles to
      one file in one process ONLY when their configuration matches; a read-only
      handle beside the funnel's read-write writer is exactly the forbidden
      mismatch. A read-write handle shares the funnel's DuckDB instance (same
      process, same config), so the reuse read coexists with — and sees live —
      the funnel's committed writes. It is used strictly for SELECTs.
    * NO write flock (plain ``duckdb.connect``, not ``connect_write``). The funnel
      opens/closes its write lock per promotion. The single-writer flock
      invariant is untouched — the funnel stays the sole flock-holding writer.
    * LAZY open + close-on-return. A held read-write handle is the forbidden
      mismatch for EVERY ``connect_read`` reader in the process (``load_tree``,
      ``assert_launchable``, ``reconstruct_session``, ``GET /investigations``).
      ``CascadeSession.launch`` runs ``assert_launchable`` (a ``connect_read``)
      BEFORE the first ``runner.start`` reuse read, and the polling/recovery
      readers run AFTER launch returns. So the handle opens only on the first
      reuse read — inside ``launch``'s synchronous reuse-read burst, after
      ``assert_launchable`` — and the launch site closes it the instant
      ``launch()`` returns, before the background phase. The burst runs with no
      ``await`` (cooperative scheduling), so no ``connect_read`` reader overlaps
      the open handle.

    ``brute_force`` (not the ``vss`` default) keeps the read cheap — no whole-DB
    temp copy. ``model`` is ``_embedding_provider()`` — the SAME embedder the
    funnel uses — so similarity is computed in one space (a hash stub when
    sentence-transformers is absent still makes the flywheel turn)."""

    name = "brute_force"

    def __init__(self, db_path: str, model: Any) -> None:
        self._db_path = db_path
        self._model = model
        self._parent: Any | None = None
        self._inner: Any | None = None

    def _ensure(self) -> Any:
        if self._inner is None:
            import duckdb

            from substrate.graph.retrieval_substrate import make_substrate_from_con

            # Read-write, NO flock — shares the funnel's DuckDB instance.
            self._parent = duckdb.connect(self._db_path)
            self._inner = make_substrate_from_con("brute_force", self._parent, model=self._model)
        return self._inner

    @property
    def _con(self) -> Any:
        # knowledge_reuse reads node-level similarity over the substrate's own
        # connection via ``getattr(substrate, "_con", None)``; hand it the shared
        # cursor (opening the handle on first use).
        return self._ensure()._con

    def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        source_tier_max: int | None = None,
        document_ids: Sequence[str] | None = None,
        policy_tag: str = "attribution_eligible",
    ) -> dict[str, Any]:
        result: dict[str, Any] = self._ensure().query(
            text,
            top_k=top_k,
            source_tier_max=source_tier_max,
            document_ids=document_ids,
            policy_tag=policy_tag,
        )
        return result

    def close(self) -> None:
        inner, parent = self._inner, self._parent
        self._inner = None
        self._parent = None
        if inner is not None and hasattr(inner, "close"):
            with contextlib.suppress(Exception):
                inner.close()
        if parent is not None:
            with contextlib.suppress(Exception):
                parent.close()


def _reuse_substrate() -> _LazyReuseSubstrate | None:
    """Build the lazy reuse substrate for a launch, or ``None`` on failure (reuse
    is best-effort — a launch never breaks because reuse could not be set up)."""
    try:
        return _LazyReuseSubstrate(_db(), _embedding_provider())
    except Exception:  # pragma: no cover — reuse is best-effort, never fatal
        return None


def _decompose(problem: str, max_depth: int) -> PlanReport:
    """The decomposer the plan endpoint uses when the caller does not supply
    sub-questions. A module attribute so tests can monkeypatch it to a
    deterministic fake without a live model."""
    return build_plan(problem, decomposer=DispatchDecomposer(), max_depth=max_depth)


def _research_loop_factory(
    *,
    gather_mode: Literal[
        "contract_stub", "exa_reasoning", "authorized_multi_source"
    ] | None = None,
    reasoning_projected_max_cost_usd: float = 0.25,
    authority: InvestigationAuthority | None = None,
    expected_policy_snapshot_sha256: str | None = None,
    research_tier: Literal["fast", "deep", "wrestle"] = "deep",
    reasoning_provider_override: str | None = None,
    reasoning_model_override: str | None = None,
    reasoning_allowed_routes: frozenset[str] | None = None,
    multi_source_launch_plan: AuthorizedGatherLaunchPlan | None = None,
    multi_source_feed_urls: tuple[str, ...] = (),
    multi_source_exa_client: object | None = None,
    multi_source_parallel_client: object | None = None,
    multi_source_exa_configuration_attestation: str | None = None,
    multi_source_parallel_configuration_attestation: str | None = None,
    multi_source_arxiv_configuration_attestation: str | None = None,
    multi_source_arxiv_base_url: str | None = None,
    db_path: str | None = None,
    embedder: object | None = None,
) -> BrowseLoop:
    """The browse loop each investigation runs.

    Default = the contract gather stub (an honest placeholder that does
    no real retrieval — the safe prod default). When the operator sets
    ``ANTIEK_DRW_GATHER=exa``, the loop switches to the real Exa Wedge-1
    discovery layer (``make_exa_gather_loop``), which promotes documents
    into the evidence pack as ``doc-url-*`` chunks through the single
    ``ingest_url`` write seam + the legal gate. No route change either way.

    Reading the env here (not at import) keeps the exa branch — and any
    ``ExaClient`` it would build — out of the stub-default path entirely.
    """
    if gather_mode is None:
        configured = os.environ.get("ANTIEK_DRW_GATHER", "stub").strip().lower()
        resolved_mode = {
            "exa": "exa_reasoning",
            "multi_source": "authorized_multi_source",
        }.get(configured, "contract_stub")
    else:
        resolved_mode = gather_mode
    if resolved_mode == "exa_reasoning":
        return cast(
            BrowseLoop,
            make_exa_gather_loop(
                top_k=3,
                enable_reasoning=True,
                reasoning_projected_max_cost_usd=reasoning_projected_max_cost_usd,
                authority=authority,
                expected_policy_snapshot_sha256=expected_policy_snapshot_sha256,
                research_tier=research_tier,
                reasoning_provider_override=reasoning_provider_override,
                reasoning_model_override=reasoning_model_override,
                reasoning_allowed_routes=reasoning_allowed_routes,
            ),
        )
    if resolved_mode == "authorized_multi_source":
        if authority is None or multi_source_launch_plan is None:
            raise ValueError("authorized multi-source gather requires reviewed authority")
        return cast(
            BrowseLoop,
            make_authorized_multi_source_gather_loop(
                launch_plan=multi_source_launch_plan,
                authority=authority,
                feed_urls=multi_source_feed_urls,
                exa_client=multi_source_exa_client,
                parallel_client=multi_source_parallel_client,
                exa_configuration_attestation=multi_source_exa_configuration_attestation,
                parallel_configuration_attestation=multi_source_parallel_configuration_attestation,
                arxiv_configuration_attestation=multi_source_arxiv_configuration_attestation,
                arxiv_base_url=multi_source_arxiv_base_url,
                db_path=db_path,
                embedder=embedder,
            ),
        )
    return cast(BrowseLoop, make_contract_gather_stub(steps=2, cost_per_step=0.01))


def gather_status_payload(
    *,
    environ: dict[str, str] | None = None,
    legal_policy: dict[str, object] | None = None,
    reviewed_plan: AuthorizedGatherLaunchPlan | None = None,
    configuration_error: str | None = None,
    multi_source_execution_activated: bool = False,
) -> dict[str, Any]:
    """Describe the exact launch-time gather boundary without constructing a client."""
    env = os.environ if environ is None else environ
    configured = str(env.get("ANTIEK_DRW_GATHER", "stub")).strip().lower()
    configured_mode = configured if configured in {"exa", "multi_source"} else "stub"
    gather_mode = {
        "exa": "exa_reasoning",
        "multi_source": "authorized_multi_source",
    }.get(configured_mode, "contract_stub")
    key_installed = bool(str(env.get("EXA_API_KEY", "")).strip())
    parallel_key_installed = bool(str(env.get("PARALLEL_API_KEY", "")).strip())
    bypassed = (
        str(env.get("ANTIEK_LEGAL_GATE_DISABLED", "")) == "1"
        or str(env.get("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", "")) == "1"
    )
    network_retrieval = configured_mode in {"exa", "multi_source"}
    production_defensible = bool(
        legal_policy and legal_policy.get("production_defensible") and not bypassed
    )
    multi_source_ready = bool(
        reviewed_plan
        and key_installed
        and parallel_key_installed
        and production_defensible
        and configuration_error is None
        and multi_source_execution_activated
    )
    launch_ready = (
        configured_mode == "stub"
        or (configured_mode == "exa" and key_installed and production_defensible)
        or (configured_mode == "multi_source" and multi_source_ready)
    )
    reviewed = None
    if reviewed_plan is not None:
        reviewed = {
            "fingerprint": reviewed_plan.fingerprint,
            "leaf_count": reviewed_plan.leaf_count,
            "per_leaf_max_results": reviewed_plan.per_leaf_max_results,
            "per_leaf_max_cost_micros": reviewed_plan.per_leaf_max_cost_micros,
            "launch_max_results": reviewed_plan.launch_max_results,
            "launch_max_cost_micros": reviewed_plan.launch_max_cost_micros,
            "sources": [source.source.value for source in reviewed_plan.sources],
            "source_configuration_sha256": {
                source.source.value: source.source_configuration_sha256
                for source in reviewed_plan.sources
            },
        }
    return {
        "view_format": "html",
        "product_panel": "research_gather_status",
        "configured_mode": configured_mode,
        "gather_mode": gather_mode,
        "network_retrieval": network_retrieval,
        "exa_key_installed": key_installed,
        "parallel_key_installed": parallel_key_installed,
        "legal_policy": legal_policy,
        "legal_gate_bypassed": bypassed,
        "launch_ready": launch_ready,
        "production_defensible": production_defensible,
        "stub_requires_acknowledgment": configured_mode == "stub",
        "reviewed_gather_plan": reviewed,
        "configuration_error": configuration_error,
        "multi_source_execution_activated": multi_source_execution_activated,
    }


def _multi_source_feed_urls(environ: dict[str, str] | None = None) -> tuple[str, ...]:
    env = os.environ if environ is None else environ
    manifest_path = str(env.get("ANTIEK_SUBSTACK_SUBSCRIPTIONS", "")).strip()
    if not manifest_path:
        raise ValueError("ANTIEK_SUBSTACK_SUBSCRIPTIONS is not configured")
    from acquisition.substack.subscriptions import load_subscriptions

    feed_urls = tuple(item.feed_url for item in load_subscriptions(manifest_path))
    if not feed_urls:
        raise ValueError("Substack subscription manifest contains no publications")
    return feed_urls


def _multi_source_launch_plan(
    authority: InvestigationAuthority,
    *,
    legal_policy_snapshot_sha256: str,
    leaf_queries: tuple[str, ...],
    environ: dict[str, str] | None = None,
    feed_urls: tuple[str, ...] | None = None,
) -> AuthorizedGatherLaunchPlan:
    """Build the server-owned review template without constructing clients."""
    env = os.environ if environ is None else environ
    reviewed_feed_urls = _multi_source_feed_urls(env) if feed_urls is None else feed_urls
    if not reviewed_feed_urls:
        raise ValueError("multi-source review requires at least one subscription")

    sources = (
        GatherSourcePlan.reviewed(
            source=GatherSource.EXA,
            max_results=3,
            max_cost_usd="0.005",
            policy_version="exa-search-v1",
            source_configuration_sha256=exa_configuration_sha256(env),
        ),
        GatherSourcePlan.reviewed(
            source=GatherSource.PARALLEL,
            max_results=10,
            max_cost_usd="0.01",
            policy_version="parallel-search-v1",
            source_configuration_sha256=parallel_configuration_sha256(env),
        ),
        GatherSourcePlan.reviewed(
            source=GatherSource.ARXIV,
            max_results=5,
            max_cost_usd="0",
            policy_version="arxiv-export-v1",
            source_configuration_sha256=arxiv_configuration_sha256(env),
        ),
        GatherSourcePlan.reviewed(
            source=GatherSource.SUBSTACK,
            max_results=5,
            max_cost_usd="0",
            policy_version="substack-subscriptions-v1",
            source_configuration_sha256=substack_subscription_configuration_sha256(
                reviewed_feed_urls
            ),
        ),
    )
    return AuthorizedGatherLaunchPlan.reviewed(
        authority,
        legal_policy_snapshot_sha256=legal_policy_snapshot_sha256,
        leaf_queries=leaf_queries,
        sources=sources,
    )


def _command(kind: str, payload: dict[str, Any] | None) -> Command:
    try:
        return Command(kind=CommandKind(kind), payload=payload or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"unknown steer command {kind!r}") from e


def _validated_idempotency_key(value: str | None) -> str:
    if (
        value is None
        or not value.strip()
        or value != value.strip()
        or len(value) > 200
        or "\n" in value
        or "\r" in value
    ):
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must be a bounded canonical string",
            headers={"Cache-Control": "no-store"},
        )
    return value


def _launch_request_fingerprint(
    *,
    req: LaunchRequest,
    tree: PlanTree,
    gather_status: dict[str, Any],
    driver_receipt: dict[str, object],
) -> str:
    approved_tree = tree.to_dict()
    # Re-approving an unchanged version refreshes approval audit metadata. That
    # must not turn recovery of the same launch attempt into a fingerprint
    # conflict; structural content + server-owned version are the authority.
    approved_tree["approval"] = {
        "state": tree.approval.state,
        "plan_version": tree.approval.plan_version,
    }
    encoded = json.dumps(
        {
            "contract_version": 2,
            "request": req.model_dump(mode="json"),
            "approved_tree": approved_tree,
            "gather_receipt": gather_status,
            "driver_receipt": driver_receipt,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CreatePlanRequest(BaseModel):
    problem: str = Field(..., min_length=1, max_length=2000)
    # Optional manual decomposition — when given, the tree is built from these
    # focused sub-questions directly (no model call). When omitted, the
    # decomposer role runs.
    sub_questions: list[str] | None = None
    max_depth: int = Field(default=3, ge=1, le=6)


class TreeEditRequest(BaseModel):
    op: str  # add_child | remove | reword | set_budget | split
    target_local_id: str
    question: str | None = None
    budget_usd: float | None = None
    max_depth: int | None = None
    into: list[str] | None = None


class ApproveRequest(BaseModel):
    approver: str = "__operator__"


class LaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_gather_mode: Literal[
        "contract_stub", "exa_reasoning", "authorized_multi_source"
    ]
    expected_gather_plan_fingerprint: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    allow_contract_stub: bool = False
    per_research_budget_usd: float = Field(default=0.50, gt=0)
    aggregate_budget_usd: float | None = None
    recursive_asset_ids: list[str] = Field(default_factory=list, max_length=64)
    recursive_artifact_ids: list[str] = Field(default_factory=list, max_length=64)
    reasoning_projected_max_cost_usd: float = Field(default=0.25, ge=0.25, le=100)
    research_tier: Literal["fast", "deep", "wrestle"] = "deep"


class LegalPolicyEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matcher_kind: Literal["domain", "corpus", "author", "title", "content_sha256"]
    matcher_value: str = Field(min_length=1, max_length=500)
    decision: Literal["allow", "deny"]
    citation_ref: str = Field(min_length=1, max_length=500)
    issuer_id: str = Field(min_length=1, max_length=500)
    reason_code: str = Field(min_length=1, max_length=500)


class LegalPolicyRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(pattern=r"^lpe-[0-9a-f]{32}$")
    matcher_kind: Literal["domain", "corpus", "author", "title", "content_sha256"]
    matcher_value: str = Field(min_length=1, max_length=500)
    citation_ref: str = Field(min_length=1, max_length=500)
    issuer_id: str = Field(min_length=1, max_length=500)
    reason_code: str = Field(min_length=1, max_length=500)


class EmptyLeaseRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecursiveOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str = Field(min_length=1, max_length=512)
    investigation_id: str = Field(min_length=1, max_length=512)
    context_pack_event_id: str = Field(min_length=1, max_length=512)
    outcome: str


class SteerRequest(BaseModel):
    kind: str  # pause | resume | stop | redirect | deepen
    payload: dict[str, Any] | None = None


class SuggestionOut(BaseModel):
    """One "thread worth chasing" the surface renders (SPR-09 M1).

    Carries only legible, plain-language fields — the daemon's vocabulary
    (``evidentiary_gap`` / chase score / ``policy_id``) never crosses this
    boundary. ``key`` is the opaque dedupe handle the surface echoes back when
    the operator chases (so a chased gap can be dropped client-side too); it is
    never rendered as a label."""

    key: str
    question: str
    suggested_retrieval: str | None = None
    seen_in_research_count: int = 1
    source_investigation_id: str | None = None


class SuggestionsResponse(BaseModel):
    count: int
    suggestions: list[SuggestionOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Plan endpoints (SPR-05)
# ---------------------------------------------------------------------------


@cascade_router.get("/budget-defaults")
async def budget_defaults() -> dict[str, Any]:
    """The per-research spend ceiling the runner uses when the launch request
    omits one, plus the host-local concurrency cap. Both read straight off the
    contracts (``BudgetCap`` + ``host_local.DEFAULT_MAX_CONCURRENCY``) so the
    entry + monitor UIs can show "estimated up to $X for N researches" and an
    honest "N running, M queued" without hardcoding a number that would drift
    if the contract default changes. The concurrency cap is the host-local
    bound; the §16-gated remote runner raises the practical ceiling only once
    the operator provisions it."""
    from runtime.research_runner.host_local import DEFAULT_MAX_CONCURRENCY

    cap = BudgetCap()
    return {
        "per_research_cost_usd": cap.cost_usd,
        "per_research_max_steps": cap.max_steps,
        "host_local_max_concurrency": DEFAULT_MAX_CONCURRENCY,
    }


@cascade_router.get("/plans/{root_id}/gather-status")
async def gather_status(root_id: str, request: Request, response: Response) -> dict[str, Any]:
    """Return readiness for the authenticated account that owns this plan.

    Legal policy is account scoped.  A context-free readiness response cannot
    truthfully carry a snapshot and previously made every legitimate Exa
    launch look unavailable in the UI even though the root-scoped launch gate
    could pass.
    """
    access = _require_session_access(request, root_id)
    response.headers["Cache-Control"] = "no-store"
    with _write("legal_policy_gather_readiness") as con:
        readiness = legal_policy_readiness(
            con, account_policy_authority(access.authority)
        ).to_dict()
    reviewed_plan = None
    configuration_error = None
    configured = os.environ.get("ANTIEK_DRW_GATHER", "stub").strip().lower()
    if configured == "multi_source":
        with _write("multi_source_gather_review") as con:
            tree = load_plan_authorized(con, access.authority)
        if tree is None:
            raise HTTPException(status_code=404, detail="plan not found")
        try:
            reviewed_plan = _multi_source_launch_plan(
                access.authority,
                legal_policy_snapshot_sha256=cast(str, readiness["policy_snapshot_sha256"]),
                leaf_queries=tuple(leaf.question for leaf in tree.leaves),
            )
        except (OSError, TypeError, ValueError) as exc:
            configuration_error = type(exc).__name__
    return gather_status_payload(
        legal_policy=readiness,
        reviewed_plan=reviewed_plan,
        configuration_error=configuration_error,
        multi_source_execution_activated=True,
    )


def _policy_access(request: Request, root_id: str) -> RequestInvestigationAuthority:
    return _require_session_access(request, root_id)


def _policy_mutation_identity(
    *, account_digest: str, idempotency_key: str, operation: str, body: BaseModel
) -> tuple[str, str]:
    key = _validated_idempotency_key(idempotency_key)
    key_digest = hashlib.sha256(key.encode()).hexdigest()
    canonical = json.dumps(
        {"operation": operation, "body": body.model_dump(mode="json")},
        sort_keys=True,
        separators=(",", ":"),
    )
    request_fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
    if len(account_digest) != 64:
        raise HTTPException(status_code=409, detail="account policy authority is malformed")
    return key_digest, request_fingerprint


def _policy_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={"Cache-Control": "no-store"},
    )


@cascade_router.post("/plans/{root_id}/legal-policy/dry-run")
async def dry_run_legal_policy(
    root_id: str,
    body: LegalPolicyEventRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    """Preview one cited account policy event without writing it."""
    access = _policy_access(request, root_id)
    response.headers["Cache-Control"] = "no-store"
    try:
        normalized = normalize_matcher(body.matcher_kind, body.matcher_value)
        with _write("legal_policy_dry_run") as con:
            authority = account_policy_authority(access.authority)
            snapshot = policy_snapshot(con, authority, at=datetime.now(UTC))
    except (LegalPolicyDenied, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    matching = [
        event
        for event in snapshot.active_events
        if event["scope_kind"] == "account"
        and event["matcher_kind"] == body.matcher_kind
        and event["matcher_value"] == normalized
    ]
    return {
        "view_format": "html",
        "operation": "dry_run",
        "scope_kind": "account",
        "normalized_matcher_value": normalized,
        "requested_decision": body.decision,
        "citation_ref": body.citation_ref,
        "issuer_id": body.issuer_id,
        "reason_code": body.reason_code,
        "current_snapshot_sha256": snapshot.snapshot_sha256,
        "matching_active_event_ids": [event["event_id"] for event in matching],
        "would_append": not any(event["decision"] == body.decision for event in matching),
        "applied": False,
    }


@cascade_router.post("/plans/{root_id}/legal-policy/events", status_code=201)
async def apply_legal_policy(
    root_id: str,
    body: LegalPolicyEventRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Append a cited account policy event; no approval checkbox is accepted."""
    access = _policy_access(request, root_id)
    response.headers["Cache-Control"] = "no-store"
    try:
        with _write("legal_policy_apply") as con:
            authority = account_policy_authority(access.authority)
            assert authority.account_digest is not None
            key_digest, request_fingerprint = _policy_mutation_identity(
                account_digest=authority.account_digest,
                idempotency_key=idempotency_key,
                operation="apply",
                body=body,
            )
            con.execute("BEGIN TRANSACTION")
            prior = con.execute(
                "SELECT request_fingerprint, event_id, policy_snapshot_sha256 "
                "FROM legal_policy_mutation_attempts WHERE account_digest = ? "
                "AND idempotency_key_digest = ?",
                [authority.account_digest, key_digest],
            ).fetchone()
            if prior is not None:
                con.execute("COMMIT")
                if prior[0] != request_fingerprint:
                    raise _policy_error(
                        409, "Idempotency-Key was already used for another policy mutation"
                    )
                return {
                    "event_id": prior[1],
                    "scope_kind": "account",
                    "policy_snapshot_sha256": prior[2],
                    "applied": True,
                    "idempotency_replayed": True,
                }
            event_id = append_policy_event(
                con,
                authority,
                scope_kind="account",
                matcher_kind=body.matcher_kind,
                matcher_value=body.matcher_value,
                decision=body.decision,
                citation_ref=body.citation_ref,
                issuer_id=body.issuer_id,
                reason_code=body.reason_code,
                effective_at=datetime.now(UTC),
            )
            snapshot = policy_snapshot(con, authority, at=datetime.now(UTC))
            con.execute(
                "INSERT INTO legal_policy_mutation_attempts "
                "(account_digest, idempotency_key_digest, request_fingerprint, event_id, "
                "policy_snapshot_sha256) VALUES (?, ?, ?, ?, ?)",
                [
                    authority.account_digest,
                    key_digest,
                    request_fingerprint,
                    event_id,
                    snapshot.snapshot_sha256,
                ],
            )
            con.execute("COMMIT")
    except LegalPolicyDenied as exc:
        raise _policy_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _policy_error(422, str(exc)) from exc
    return {
        "event_id": event_id,
        "scope_kind": "account",
        "policy_snapshot_sha256": snapshot.snapshot_sha256,
        "applied": True,
        "idempotency_replayed": False,
    }


@cascade_router.post("/plans/{root_id}/legal-policy/revoke", status_code=201)
async def revoke_legal_policy(
    root_id: str,
    body: LegalPolicyRevokeRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict[str, Any]:
    access = _policy_access(request, root_id)
    response.headers["Cache-Control"] = "no-store"
    try:
        with _write("legal_policy_revoke") as con:
            authority = account_policy_authority(access.authority)
            assert authority.account_digest is not None
            key_digest, request_fingerprint = _policy_mutation_identity(
                account_digest=authority.account_digest,
                idempotency_key=idempotency_key,
                operation="revoke",
                body=body,
            )
            con.execute("BEGIN TRANSACTION")
            prior = con.execute(
                "SELECT request_fingerprint, event_id, policy_snapshot_sha256 "
                "FROM legal_policy_mutation_attempts WHERE account_digest = ? "
                "AND idempotency_key_digest = ?",
                [authority.account_digest, key_digest],
            ).fetchone()
            if prior is not None:
                con.execute("COMMIT")
                if prior[0] != request_fingerprint:
                    raise _policy_error(
                        409, "Idempotency-Key was already used for another policy mutation"
                    )
                return {
                    "event_id": prior[1],
                    "revoked_event_id": body.event_id,
                    "policy_snapshot_sha256": prior[2],
                    "applied": True,
                    "idempotency_replayed": True,
                }
            event_id = append_policy_event(
                con,
                authority,
                scope_kind="account",
                matcher_kind=body.matcher_kind,
                matcher_value=body.matcher_value,
                decision="revoke",
                citation_ref=body.citation_ref,
                issuer_id=body.issuer_id,
                reason_code=body.reason_code,
                effective_at=datetime.now(UTC),
                supersedes_event_id=body.event_id,
            )
            snapshot = policy_snapshot(con, authority, at=datetime.now(UTC))
            con.execute(
                "INSERT INTO legal_policy_mutation_attempts "
                "(account_digest, idempotency_key_digest, request_fingerprint, event_id, "
                "policy_snapshot_sha256) VALUES (?, ?, ?, ?, ?)",
                [
                    authority.account_digest,
                    key_digest,
                    request_fingerprint,
                    event_id,
                    snapshot.snapshot_sha256,
                ],
            )
            con.execute("COMMIT")
    except LegalPolicyDenied as exc:
        raise _policy_error(409, str(exc)) from exc
    except ValueError as exc:
        raise _policy_error(422, str(exc)) from exc
    return {
        "event_id": event_id,
        "revoked_event_id": body.event_id,
        "policy_snapshot_sha256": snapshot.snapshot_sha256,
        "applied": True,
        "idempotency_replayed": False,
    }


_LEASE_TERMINAL_ACTIONS = frozenset(
    {"investigation.completed", "investigation.failed", "investigation.chase_halted"}
)
_LEASE_LIFECYCLE_ACTIONS = _LEASE_TERMINAL_ACTIONS | {"investigation.start_requested"}


def _lease_terminal_evidence(
    access: RequestInvestigationAuthority,
    holder_investigation_id: str,
    *,
    lease_id: str,
    policy_snapshot_sha256: str,
    rows: list[dict[str, Any]] | None = None,
) -> tuple[str, str, datetime] | None:
    """Return terminal action and exact event fingerprint for an owned stream."""
    from substrate.event_log import trajectory_authorized

    holder = InvestigationAuthority(
        access.authority.account_id,
        holder_investigation_id,
        access.authority.root,
    )
    resolved_rows = trajectory_authorized(holder) if rows is None else rows
    claim_indexes = [
        index
        for index, row in enumerate(resolved_rows)
        if row.get("action_type") == "legal_policy.dispatch_claimed"
        and isinstance(row.get("payload"), dict)
        and row["payload"].get("lease_id") == lease_id
        and row["payload"].get("policy_snapshot_sha256") == policy_snapshot_sha256
    ]
    if len(claim_indexes) != 1:
        raise ValueError("dispatch claim evidence is missing or ambiguous")
    lifecycle = [
        row
        for row in resolved_rows[claim_indexes[0] + 1 :]
        if row.get("action_type") in _LEASE_LIFECYCLE_ACTIONS
    ]
    if not lifecycle or lifecycle[-1].get("action_type") not in _LEASE_TERMINAL_ACTIONS:
        return None
    row = lifecycle[-1]
    emitted_raw = row.get("emitted_at")
    if not isinstance(emitted_raw, str):
        raise ValueError("terminal event has no emission time")
    emitted_at = datetime.fromisoformat(emitted_raw.replace("Z", "+00:00"))
    if emitted_at.tzinfo is None:
        raise ValueError("terminal event emission time is not timezone-aware")
    encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return str(row["action_type"]), hashlib.sha256(encoded.encode()).hexdigest(), emitted_at


@cascade_router.get("/plans/{root_id}/legal-policy/dispatch-leases")
async def list_legal_policy_dispatch_leases(
    root_id: str, request: Request, response: Response
) -> dict[str, Any]:
    from substrate.legal_gate.readiness import list_policy_dispatch_leases

    access = _policy_access(request, root_id)
    response.headers["Cache-Control"] = "no-store"
    with _write("legal_policy_list_dispatch_leases") as con:
        authority = account_policy_authority(access.authority)
        leases = list_policy_dispatch_leases(con, authority)
    views: list[dict[str, Any]] = []
    for lease in leases:
        holder_id = lease["holder_investigation_id"]
        state = "evidence_invalid"
        terminal_action = None
        if isinstance(holder_id, str) and holder_id:
            try:
                evidence = _lease_terminal_evidence(
                    access,
                    holder_id,
                    lease_id=str(lease["lease_id"]),
                    policy_snapshot_sha256=str(lease["policy_snapshot_sha256"]),
                )
            except Exception:  # malformed/missing/foreign storage stays closed
                evidence = None
                state = "evidence_invalid"
            else:
                # The exact claim event is emitted only after lease insertion;
                # lifecycle evidence is sliced strictly after that claim.
                recoverable = evidence is not None
                state = "terminal_recoverable" if recoverable else "active"
                terminal_action = evidence[0] if recoverable and evidence is not None else None
        views.append(
            {
                "lease_id": lease["lease_id"],
                "holder_investigation_id": holder_id,
                "acquired_at": str(lease["acquired_at"]),
                "diagnostic_deadline": str(lease["diagnostic_deadline"]),
                "recovery_state": state,
                "terminal_action": terminal_action,
            }
        )
    return {"count": len(views), "leases": views}


@cascade_router.post("/plans/{root_id}/legal-policy/dispatch-leases/{lease_id}/recover")
async def recover_legal_policy_dispatch_lease(
    root_id: str,
    lease_id: str,
    body: EmptyLeaseRecoveryRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict[str, Any]:
    del body
    from substrate.legal_gate.readiness import (
        list_policy_dispatch_leases,
        recover_policy_dispatch_lease,
    )

    access = _policy_access(request, root_id)
    response.headers["Cache-Control"] = "no-store"
    key = _validated_idempotency_key(idempotency_key)
    key_digest = hashlib.sha256(key.encode()).hexdigest()
    with _write("legal_policy_find_dispatch_lease") as con:
        authority = account_policy_authority(access.authority)
        matching = [
            lease
            for lease in list_policy_dispatch_leases(con, authority)
            if lease["lease_id"] == lease_id
        ]
        # A replay no longer has a live row, so allow the recovery primitive to
        # resolve the receipt by key without re-reading client-supplied evidence.
        if not matching:
            prior = con.execute(
                "SELECT holder_investigation_digest, terminal_event_fingerprint "
                "FROM legal_policy_lease_recoveries WHERE account_digest = ? "
                "AND idempotency_key_digest = ? AND lease_id = ?",
                [authority.account_digest, key_digest, lease_id],
            ).fetchone()
            if prior is None:
                raise _policy_error(404, "dispatch lease not found")
            holder_digest, terminal_fingerprint = prior
            stream_guard = contextlib.nullcontext(None)
        else:
            from substrate.event_log import locked_trajectory_authorized

            lease = matching[0]
            holder_id = lease["holder_investigation_id"]
            if not isinstance(holder_id, str) or not holder_id:
                raise _policy_error(409, "dispatch lease has no recoverable terminal evidence")
            holder = InvestigationAuthority(
                access.authority.account_id, holder_id, access.authority.root
            )
            if holder.investigation_digest != lease["holder_investigation_digest"]:
                raise _policy_error(409, "dispatch lease holder evidence is invalid")
            holder_digest = holder.investigation_digest
            stream_guard = locked_trajectory_authorized(holder)
        with stream_guard as locked_rows:
            if matching:
                try:
                    evidence = _lease_terminal_evidence(
                        access,
                        holder_id,
                        lease_id=lease_id,
                        policy_snapshot_sha256=str(lease["policy_snapshot_sha256"]),
                        rows=locked_rows,
                    )
                except Exception as exc:
                    raise _policy_error(409, "dispatch lease terminal evidence is invalid") from exc
                if evidence is None:
                    raise _policy_error(409, "dispatch holder is not terminal")
                _terminal_action, terminal_fingerprint, _terminal_at = evidence
            con.execute("BEGIN TRANSACTION")
            try:
                receipt = recover_policy_dispatch_lease(
                    con,
                    authority,
                    lease_id=lease_id,
                    holder_investigation_digest=holder_digest,
                    terminal_event_fingerprint=terminal_fingerprint,
                    idempotency_key_digest=key_digest,
                )
                con.execute("COMMIT")
            except LegalPolicyDenied as exc:
                with contextlib.suppress(Exception):
                    con.execute("ROLLBACK")
                raise _policy_error(409, str(exc)) from exc
            except Exception:
                with contextlib.suppress(Exception):
                    con.execute("ROLLBACK")
                raise
    return {
        "lease_id": receipt.lease_id,
        "policy_snapshot_sha256": receipt.policy_snapshot_sha256,
        "terminal_event_fingerprint": receipt.terminal_event_fingerprint,
        "recovered": True,
        "idempotency_replayed": receipt.idempotency_replayed,
    }


@cascade_router.get("/suggestions", response_model=SuggestionsResponse)
async def suggestions(request: Request, limit: int = 8) -> SuggestionsResponse:
    """The §7 compounding flywheel, surfaced (SPR-09 M1). Reads the continuous
    daemon's *existing* scored evidentiary gaps off the event log and returns
    the top ones as plain-language "threads worth chasing".

    READ-ONLY — the load-bearing invariant of this sprint. Building suggestions
    scans the event log and ranks with the daemon's own scorer; it spawns
    nothing, reserves no budget, and does not run the daemon. A suggestion
    costs nothing until the operator explicitly chases it through the existing
    capped launch path (``POST /investigations`` / the cascade launch). With no
    daemon output (no keys, daemon never ran) the result is an empty list — the
    honest no-result state, never a fabricated thread.

    The displayed count is bounded (rigor #3: rank + cap, don't dump a flood of
    low-score gaps). ``limit`` is a *display* bound only — it changes nothing
    about the daemon's §7.4 budget/cadence caps."""
    from orchestration.continuous.suggestions import build_suggestions

    try:
        access = authority_from_request(request, "__suggestions_collection__")
    except InvestigationAuthenticationRequired as exc:
        raise HTTPException(status_code=401, detail="authentication required") from exc
    capped = max(0, min(int(limit), 50))
    items = build_suggestions(
        max_suggestions=capped,
        min_score=0.0,
        authority=access.authority,
    )
    return SuggestionsResponse(
        count=len(items),
        suggestions=[
            SuggestionOut(
                key=s.key,
                question=s.question,
                suggested_retrieval=s.suggested_retrieval,
                seen_in_research_count=s.seen_in_research_count,
                source_investigation_id=s.source_investigation_id,
            )
            for s in items
        ],
    )


@cascade_router.post("/plans")
async def create_plan(req: CreatePlanRequest, request: Request) -> dict[str, Any]:
    """Decompose a problem into an editable, focus-checked sub-question tree
    and persist it. Returns the root node id + the editable tree."""
    if req.sub_questions:
        sub_questions = req.sub_questions

        class _Fixed:
            def decompose(self, q: str, *, context: str = "") -> list[SubQuestion]:
                return [SubQuestion(question=s) for s in sub_questions]

        report = build_plan(req.problem, decomposer=_Fixed(), max_depth=req.max_depth)
    else:
        try:
            report = _decompose(req.problem, req.max_depth)
        except Exception as exc:
            c = classify_dispatch_failure(exc)
            logger.warning(
                "create_plan decompose failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            # Status per docs/decisions/drw-plan-failure-contract.md §3.
            raise HTTPException(
                status_code=c.status,
                detail={
                    "code": c.code,
                    "message": c.message,
                    "retryable": c.retryable,
                },
            ) from exc
    tree = report.tree
    plan_id = f"plan-{secrets.token_hex(16)}"
    access = authority_from_request(request, plan_id)
    try:
        bind_new_investigation(access)
    except InvestigationAccessDenied as exc:
        raise HTTPException(status_code=404, detail="plan not found") from exc
    with _write("create_plan") as con:
        root_id = save_plan_authorized(
            con,
            access.authority,
            tree,
            embedding_provider=_embedding_provider(),
        )
    return {
        "root_node_id": root_id,
        "tree": tree.to_dict(),
        "capped_nodes": report.capped_nodes,
        "over_broad_leaves": report.over_broad_leaves,
    }


@cascade_router.get("/plans/{root_id}")
async def get_plan(root_id: str, request: Request) -> dict[str, Any]:
    access = _require_session_access(request, root_id)
    with _translate(), _write("get_plan_authorized") as con:
        tree = load_plan_authorized(con, access.authority)
        launchable = is_plan_launchable_authorized(con, access.authority)
    if tree is None:
        raise HTTPException(status_code=404, detail="plan not found")
    return {
        "root_node_id": root_id,
        "tree": tree.to_dict(),
        "launchable": launchable,
    }


@cascade_router.post("/plans/{root_id}/edit")
async def edit_plan(root_id: str, req: TreeEditRequest, request: Request) -> dict[str, Any]:
    """Apply one edit to the tree and re-persist. Any edit re-opens the
    approval gate (SPR-05 contract)."""
    with _translate():
        access = _require_session_access(request, root_id)
        with _write("edit_plan") as con:
            tree = load_plan_authorized(con, access.authority)
            if tree is None:
                raise HTTPException(status_code=404, detail="plan not found")
            ok = _apply_edit(tree, req)
            if not ok:
                raise HTTPException(status_code=400, detail=f"edit {req.op!r} failed (bad target?)")
            save_plan_authorized(
                con,
                access.authority,
                tree,
                embedding_provider=_embedding_provider(),
            )
    return {
        "root_node_id": root_id,
        "tree": tree.to_dict(),
        "launchable": tree.approval.is_launchable,
    }


def _apply_edit(tree: PlanTree, req: TreeEditRequest) -> bool:
    if req.op == "add_child":
        return tree.add_child(req.target_local_id, req.question or "New sub-question") is not None
    if req.op == "remove":
        return tree.remove(req.target_local_id)
    if req.op == "reword":
        return tree.reword(req.target_local_id, req.question or "")
    if req.op == "set_budget":
        return tree.set_budget(
            req.target_local_id, budget_usd=req.budget_usd, max_depth=req.max_depth
        )
    if req.op == "split":
        return tree.split(req.target_local_id, req.into or [])
    raise HTTPException(status_code=400, detail=f"unknown edit op {req.op!r}")


@cascade_router.post("/plans/{root_id}/approve")
async def approve(root_id: str, req: ApproveRequest, request: Request) -> dict[str, Any]:
    access = _require_session_access(request, root_id)
    with _translate(), _write("approve_plan") as con:
        approval = approve_plan_authorized(
            con,
            access.authority,
            approver=access.authority.account_id,
            embedding_provider=_embedding_provider(),
        )
    return {
        "root_node_id": root_id,
        "approval": approval,
        "launchable": True,
    }


# ---------------------------------------------------------------------------
# Launch + session endpoints (SPR-06)
# ---------------------------------------------------------------------------


@cascade_router.get("/plans/{root_id}/launch-attempt")
async def launch_attempt_status(
    root_id: str,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Report durable attempt truth. This path is deliberately read-only."""
    attempt_key = _validated_idempotency_key(idempotency_key)
    access = _require_session_access(request, root_id)
    try:
        con = connect_read(default_db_path())
        try:
            attempt = read_launch_attempt_authorized(
                con, access.authority, idempotency_key=attempt_key
            )
        finally:
            con.close()
    except LaunchAttemptConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
            headers={"Cache-Control": "no-store"},
        ) from exc
    if attempt is None:
        raise HTTPException(
            status_code=404,
            detail="launch attempt not found",
            headers={"Cache-Control": "no-store"},
        )

    session_id = str(attempt["session_id"])
    session_access = authority_for_investigation(access, session_id)
    session_authority_present = owns_investigation(session_access)
    launch_evidence_present = False
    if session_authority_present:
        from substrate.event_log import trajectory_authorized

        launch_evidence_present = any(
            row.get("action_type") == "cascade.launched"
            for row in trajectory_authorized(session_access.authority)
        )
    response.headers["Cache-Control"] = "no-store"
    return {
        **attempt,
        "session_authority_present": session_authority_present,
        "launch_evidence_present": launch_evidence_present,
        "action": (
            "inspect_session"
            if session_authority_present and launch_evidence_present
            else "await_operator_reconciliation"
        ),
    }


@cascade_router.post("/plans/{root_id}/launch")
async def launch(
    root_id: str,
    req: LaunchRequest,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Launch an approved plan as N parallel researches. Refuses an
    unapproved plan (SPR-05 gate). Returns the session id + the researches.

    Background completion runs gather (per leaf) then the Loop 1 synthesis
    tail (phases 6–9 on ``session_id``) when a synthesis runner is wired —
    see ``set_synthesis_tail_runner``."""
    attempt_key = _validated_idempotency_key(idempotency_key)
    with _translate():
        access = _require_session_access(request, root_id)
        with _write("launch_plan_authorized") as con:
            if not is_plan_launchable_authorized(con, access.authority):
                raise PlanNotApproved(
                    f"plan {root_id!r} is not approved — the glass-box gate refuses launch."
                )
            tree = load_plan_authorized(con, access.authority)
            if tree is None:
                raise HTTPException(status_code=404, detail="plan not found")
        with _write("legal_policy_launch_readiness") as con:
            policy_authority = account_policy_authority(access.authority)
            readiness = legal_policy_readiness(con, policy_authority).to_dict()
        reviewed_plan = None
        reviewed_feed_urls: tuple[str, ...] = ()
        # One immutable snapshot owns both review and client construction. No
        # provider may re-read mutable process configuration after this point.
        runtime_env = dict(os.environ)
        configuration_error = None
        if runtime_env.get("ANTIEK_DRW_GATHER", "stub").strip().lower() == "multi_source":
            try:
                reviewed_feed_urls = _multi_source_feed_urls(runtime_env)
                reviewed_plan = _multi_source_launch_plan(
                    access.authority,
                    legal_policy_snapshot_sha256=cast(
                        str, readiness["policy_snapshot_sha256"]
                    ),
                    leaf_queries=tuple(leaf.question for leaf in tree.leaves),
                    environ=runtime_env,
                    feed_urls=reviewed_feed_urls,
                )
            except (OSError, TypeError, ValueError) as exc:
                configuration_error = type(exc).__name__
        gather_status = gather_status_payload(
            environ=runtime_env,
            legal_policy=readiness,
            reviewed_plan=reviewed_plan,
            configuration_error=configuration_error,
            multi_source_execution_activated=True,
        )
        if req.expected_gather_mode != gather_status["gather_mode"]:
            raise HTTPException(
                status_code=409,
                detail="research gather mode changed; review launch again",
            )
        reviewed_fingerprint = (
            gather_status["reviewed_gather_plan"]["fingerprint"]
            if gather_status["reviewed_gather_plan"] is not None
            else None
        )
        if req.expected_gather_plan_fingerprint != reviewed_fingerprint:
            raise HTTPException(
                status_code=409,
                detail="research gather plan changed; review launch again",
            )
        if reviewed_plan is not None:
            per_research_micros = int(Decimal(str(req.per_research_budget_usd)) * 1_000_000)
            if per_research_micros < reviewed_plan.per_leaf_max_cost_micros:
                raise HTTPException(
                    status_code=409,
                    detail="per-research budget is below the reviewed gather ceiling",
                )
            if req.aggregate_budget_usd is not None:
                aggregate_micros = int(
                    Decimal(str(req.aggregate_budget_usd)) * 1_000_000
                )
                if aggregate_micros < reviewed_plan.launch_max_cost_micros:
                    raise HTTPException(
                        status_code=409,
                        detail="aggregate budget is below the reviewed gather ceiling",
                    )
        if gather_status["gather_mode"] == "contract_stub" and not req.allow_contract_stub:
            raise HTTPException(
                status_code=409,
                detail="contract-stub research requires explicit acknowledgment",
            )
        if not gather_status["launch_ready"]:
            raise HTTPException(
                status_code=503,
                detail="configured research gather is not ready",
            )
        if (
            gather_status["gather_mode"] == "exa_reasoning"
            and not gather_status["production_defensible"]
        ):
            raise HTTPException(
                status_code=503,
                detail="durable legal-policy boundary is not production-defensible",
            )
        # Construction is side-effect free; do it before the durable attempt
        # claim so recursive-context compatibility can fail without leaving an
        # ambiguous claimed row. Dispatch still happens only after the claim.
        from substrate.dispatch.research_tier import resolve_available_research_tier

        try:
            driver = resolve_available_research_tier(
                req.research_tier,
                getattr(request.app.state, "registered_providers", None),
            )
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        factory_kwargs: dict[str, Any] = {
            "gather_mode": cast(
                Literal[
                    "contract_stub", "exa_reasoning", "authorized_multi_source"
                ],
                gather_status["gather_mode"],
            ),
            "reasoning_projected_max_cost_usd": req.reasoning_projected_max_cost_usd,
            "research_tier": req.research_tier,
            "reasoning_provider_override": driver.provider,
            "reasoning_model_override": driver.model,
            "reasoning_allowed_routes": frozenset({f"{driver.provider}/{driver.model}"}),
        }
        if gather_status["gather_mode"] in {
            "exa_reasoning",
            "authorized_multi_source",
        }:
            factory_kwargs["authority"] = access.authority
            factory_kwargs["expected_policy_snapshot_sha256"] = readiness["policy_snapshot_sha256"]
        if gather_status["gather_mode"] == "authorized_multi_source":
            if reviewed_plan is None:
                raise HTTPException(status_code=503, detail="reviewed gather plan is unavailable")
            source_configurations = {
                source.source: source.source_configuration_sha256
                for source in reviewed_plan.sources
            }
            captured_configurations = {
                GatherSource.EXA: exa_configuration_sha256(runtime_env),
                GatherSource.PARALLEL: parallel_configuration_sha256(runtime_env),
                GatherSource.ARXIV: arxiv_configuration_sha256(runtime_env),
            }
            if any(
                source_configurations.get(source) != attestation
                for source, attestation in captured_configurations.items()
            ):
                raise HTTPException(
                    status_code=409,
                    detail="provider configuration changed after gather review",
                )
            from acquisition.search.exa.client import ExaClient
            from acquisition.search.parallel.client import ParallelClient

            factory_kwargs["multi_source_launch_plan"] = reviewed_plan
            factory_kwargs["multi_source_feed_urls"] = reviewed_feed_urls
            factory_kwargs["multi_source_exa_client"] = ExaClient(
                api_key=runtime_env["EXA_API_KEY"],
                base_url=runtime_env.get("EXA_BASE_URL", "https://api.exa.ai"),
            )
            factory_kwargs["multi_source_parallel_client"] = ParallelClient(
                api_key=runtime_env["PARALLEL_API_KEY"],
                base_url=runtime_env.get("PARALLEL_BASE_URL", "https://api.parallel.ai"),
            )
            factory_kwargs["multi_source_exa_configuration_attestation"] = captured_configurations[
                GatherSource.EXA
            ]
            factory_kwargs["multi_source_parallel_configuration_attestation"] = captured_configurations[
                GatherSource.PARALLEL
            ]
            factory_kwargs["multi_source_arxiv_configuration_attestation"] = captured_configurations[
                GatherSource.ARXIV
            ]
            factory_kwargs["multi_source_arxiv_base_url"] = runtime_env.get(
                "ANTIEK_ARXIV_BASE_URL", "https://export.arxiv.org/api/query"
            )
            factory_kwargs["db_path"] = _db()
        research_loop = _research_loop_factory(**factory_kwargs)
        driver_receipt: dict[str, object] = {
            "research_tier": driver.tier,
            "reviewed_primary_provider": driver.provider,
            "reviewed_primary_model": driver.model,
            "why": driver.why,
            "reasoning_projected_max_cost_usd": req.reasoning_projected_max_cost_usd,
            "candidate_rank": driver.candidate_rank,
            "availability_source": driver.availability_source,
        }
        if (req.recursive_asset_ids or req.recursive_artifact_ids) and not bool(
            getattr(research_loop, "consumes_prompt_context", False)
        ):
            raise HTTPException(
                status_code=409,
                detail="recursive context requires the Exa reasoning research mode",
            )
        claims = getattr(request.state, "user_claims", None)
        if not isinstance(claims, UserClaims):
            raise HTTPException(
                status_code=503,
                detail="validated request identity is unavailable",
            )
        request_fingerprint = _launch_request_fingerprint(
            req=req,
            tree=tree,
            gather_status=gather_status,
            driver_receipt=driver_receipt,
        )
        reviewed_tree_fingerprint = plan_tree_fingerprint(tree)

    proposed_session_id = f"session-{secrets.token_hex(16)}"
    proposed_launch_access = authority_for_investigation(access, proposed_session_id)
    try:
        with _write("claim_launch_attempt_authorized") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                reviewed_snapshot = gather_status["legal_policy"]["policy_snapshot_sha256"]
                require_policy_snapshot(
                    con,
                    policy_authority,
                    expected_sha256=cast(str, reviewed_snapshot),
                )
                session_id, replay = claim_launch_attempt_authorized(
                    con,
                    access.authority,
                    idempotency_key=attempt_key,
                    request_fingerprint=request_fingerprint,
                    proposed_session_id=proposed_session_id,
                )
                if replay is None:
                    claim_plan_launch_authorized(
                        con,
                        access.authority,
                        proposed_launch_access.authority,
                        expected_tree_fingerprint=reviewed_tree_fingerprint,
                    )
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
    except LaunchAttemptConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LegalPolicyDenied as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LaunchAttemptUnknown as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "launch_outcome_unknown",
                "message": "The prior launch outcome is unknown; automatic redispatch is refused.",
                "session_id": exc.session_id,
            },
        ) from exc
    except PlanAuthorityDenied as exc:
        raise HTTPException(
            status_code=409,
            detail="cascade plan changed after launch review",
        ) from exc
    if replay is not None:
        replay["idempotency_replayed"] = True
        return replay

    try:
        bind_child_investigation(access, session_id)
    except InvestigationAccessDenied as exc:
        raise HTTPException(status_code=404, detail="plan not found") from exc
    launch_access = authority_for_investigation(access, session_id)
    # The exact reviewed tree was frozen atomically with the attempt claim.
    # Continue using the already-reviewed in-memory snapshot for leaf creation.
    leaves = [
        Leaf(
            investigation_id=f"{session_id}-leaf-{i}",
            sub_question=leaf.question,
            question_node_id=leaf.graph_node_id,
            budget=BudgetCap(cost_usd=req.per_research_budget_usd),
        )
        for i, leaf in enumerate(tree.leaves)
    ]
    budget = BudgetManager(aggregate_cap_usd=req.aggregate_budget_usd)
    funnel = PromotionFunnel(db_path=_db(), embedding_provider=_embedding_provider())
    # Flywheel reuse ON: a §9.0-gated substrate that reads the live graph through
    # a cursor of a read-write handle SHARING the funnel's DuckDB instance (never
    # a conflicting connect_read). It opens lazily on the first reuse read inside
    # launch() and is closed the instant launch() returns, so the read-write
    # handle never overlaps a connect_read reader. Best-effort: None degrades to
    # today's no-reuse behaviour, so a launch never breaks. See _reuse_substrate.
    reuse_substrate = _reuse_substrate()
    recursive_notes_provider = None
    if req.recursive_asset_ids or req.recursive_artifact_ids:
        from interfaces.research.api.engagement_routes import get_account_engagement_store
        from substrate.context_pack import build_canonical_recursive_pack

        owner_user_id = str(getattr(request.state, "user_id", "") or "").strip()
        if not owner_user_id:
            raise HTTPException(
                status_code=503,
                detail="authenticated request identity is unavailable",
            )
        asset_ids = tuple(dict.fromkeys(req.recursive_asset_ids))
        artifact_ids = tuple(dict.fromkeys(req.recursive_artifact_ids))
        engagement_store = get_account_engagement_store(owner_user_id, create_if_missing=True)

        def recursive_notes_provider(_investigation_id: str, plan: ResearchPlan) -> Any:
            with _write("canonical_recursive_context") as con:
                owner_rows = con.execute(
                    "SELECT deliverable_id, owner_user_id FROM deliverables "
                    "WHERE deliverable_id = ANY(?)",
                    [list(asset_ids)],
                ).fetchall()
                owners = {str(row[0]): str(row[1]) for row in owner_rows}
                pack = build_canonical_recursive_pack(
                    store=engagement_store,
                    con=con,
                    owner_user_id=owner_user_id,
                    asset_ids=asset_ids,
                    asset_owner=owners.get,
                    goal=plan.sub_question,
                    artifact_ids=artifact_ids,
                )
            from substrate.context_pack.recursive_ranking import (
                apply_advisory_ranking,
                build_ranking_snapshot,
            )

            feedback_store = _recursive_feedback_store()
            snapshot = build_ranking_snapshot(
                owner_user_id=owner_user_id,
                task_class="research_reasoning",
                receipts=feedback_store.list(owner_user_id),
                now_ms=int(time.time() * 1000),
            )
            return apply_advisory_ranking(
                pack,
                owner_user_id=owner_user_id,
                snapshot=snapshot,
            )

    runner = HostLocalRunner(
        research_loop,
        claims=claims,
        budget=budget,
        on_emit=funnel.submit,
        seal_on_complete=False,
        retrieval_substrate=reuse_substrate,
        recursive_notes_provider=recursive_notes_provider,
    )
    session = CascadeSession(
        session_id,
        claims=claims,
        runner=runner,
        funnel=funnel,
        db_path=_db(),
        plan_authority=access.authority,
        launch_authority=launch_access.authority,
    )
    try:
        await session.launch(
            root_id,
            leaves,
            gather_receipt=gather_status,
            driver_receipt=driver_receipt,
        )
    finally:
        # The reuse reads happen synchronously during launch(); close the shared
        # read handle NOW so it never overlaps the connect_read readers that run
        # during the background/polling phase (a held read-write handle is the
        # forbidden RO+RW same-file mismatch for every connect_read on the file).
        # runner.join() will best-effort close it again later — idempotent.
        if reuse_substrate is not None:
            with contextlib.suppress(Exception):
                reuse_substrate.close()
    response_payload = {
        "session_id": session_id,
        "researches": [
            {
                "investigation_id": leaf.investigation_id,
                "sub_question": leaf.sub_question,
                "question_node_id": leaf.question_node_id,
            }
            for leaf in leaves
        ],
        "aggregate_cap_usd": budget.aggregate_cap_usd,
        "gather_receipt": gather_status,
        "driver_receipt": driver_receipt,
        "idempotency_replayed": False,
    }
    _SESSIONS[session_id] = session
    # Once leaf runners exist they need join/drain/merge even if sealing the
    # HTTP replay receipt fails. The driver is independent of receipt storage.
    _SESSION_TASKS[session_id] = asyncio.create_task(_run_to_completion(session))
    try:
        with _write("complete_launch_attempt_authorized") as con:
            complete_launch_attempt_authorized(
                con,
                access.authority,
                idempotency_key=attempt_key,
                request_fingerprint=request_fingerprint,
                session_id=session_id,
                response=response_payload,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="launch started but its durable response receipt could not be sealed",
        ) from exc
    return response_payload


@cascade_router.post("/recursive-context/outcomes")
async def record_recursive_context_outcome(
    body: RecursiveOutcomeRequest, request: Request
) -> dict[str, Any]:
    from dataclasses import asdict

    from substrate.context_pack.recursive_feedback import (
        FeedbackUnitRef,
        build_outcome_receipt,
    )
    from substrate.event_log import trajectory_authorized

    investigation_access = _require_session_access(request, body.investigation_id)
    owner_user_id = investigation_access.authority.account_id
    rows = trajectory_authorized(investigation_access.authority)
    context_event = next(
        (
            row
            for row in rows
            if row.get("event_id") == body.context_pack_event_id
            and row.get("action_type") == "context_pack.assembled"
        ),
        None,
    )
    if context_event is None:
        raise HTTPException(status_code=404, detail="context pack event not found")
    payload = context_event.get("payload")
    recursive_context = payload.get("recursive_context") if isinstance(payload, dict) else None
    included = (
        recursive_context.get("included_units") if isinstance(recursive_context, dict) else None
    )
    if not isinstance(included, list) or not included:
        raise HTTPException(
            status_code=409,
            detail="context pack contains no consumed recursive units",
        )
    units = [
        FeedbackUnitRef(
            unit_id=str(unit.get("unit_id") or ""),
            text_digest=str(unit.get("text_digest") or ""),
        )
        for unit in included
        if isinstance(unit, dict)
    ]
    from substrate.context_pack import account_scope_digest

    expected_scope = account_scope_digest(owner_user_id)
    if len(units) != len(included) or any(
        str(unit.get("owner_scope_digest") or "") != expected_scope
        for unit in included
        if isinstance(unit, dict)
    ):
        raise HTTPException(
            status_code=403,
            detail="recursive context does not belong to authenticated identity",
        )
    dispatch_event = next(
        (
            row
            for row in reversed(rows)
            if row.get("action_type") == "dispatch.call"
            and isinstance(row.get("payload"), dict)
            and row["payload"].get("context_pack_event_id") == body.context_pack_event_id
        ),
        None,
    )
    if dispatch_event is None:
        raise HTTPException(
            status_code=409,
            detail="recursive context was assembled but no linked dispatch consumed it",
        )
    try:
        receipt = build_outcome_receipt(
            owner_user_id=owner_user_id,
            observation_id=body.observation_id,
            context_pack_event_id=body.context_pack_event_id,
            dispatch_event_id=str(dispatch_event.get("event_id") or ""),
            units=units,
            # This route only records feedback for a research cascade. The
            # ranking cohort is server-owned, not a client classification.
            task_class="research_reasoning",
            model_policy_id=str(dispatch_event.get("policy_id") or "unknown"),
            outcome=body.outcome,  # type: ignore[arg-type]
            observed_at_ms=int(time.time() * 1000),
        )
        stored = _recursive_feedback_store().append(owner_user_id, receipt)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"receipt": asdict(stored), "text_logged": False}


@cascade_router.delete("/recursive-context/outcomes")
async def delete_recursive_context_outcomes(request: Request) -> dict[str, Any]:
    owner_user_id = str(getattr(request.state, "user_id", "") or "").strip()
    if not owner_user_id:
        raise HTTPException(
            status_code=503,
            detail="authenticated request identity is unavailable",
        )
    deleted = _recursive_feedback_store().delete_and_opt_out(owner_user_id)
    return {"deleted_receipt_count": deleted, "opted_out": True}


async def _run_to_completion(session: CascadeSession) -> None:
    """Drive a launched session to completion on the event loop.

    Background completion is best-effort in the sense that it must NEVER crash
    the loop — but a *silent* swallow of a synthesis-tail failure is exactly the
    split-brain / silent-synthesis hazard the ANT-DRL programme guards against
    (a session that failed to reach ``DeepResearchComplete`` would look fine and
    the operator would never know). So we capture the failure, record it as the
    session's ``synthesis_tail_error`` and emit a durable audit trail (a typed
    event on the session trajectory + a structured log), then return — the task
    stays non-fatal, the failure stays visible in trajectory/status."""
    stage = "join_and_merge"
    try:
        await session.join_and_merge()
        if _SYNTHESIS_TAIL_RUNNER is not None:
            stage = "synthesis_tail"
            pack = session.build_evidence_pack()
            await _SYNTHESIS_TAIL_RUNNER(session, pack)
    except Exception as exc:
        # Capture, do not swallow: record WITH the failing stage (so a join/merge
        # failure isn't mislabeled as a synthesis-tail one) + audit, stay non-fatal.
        session.record_synthesis_tail_error(exc, stage=stage)


@cascade_router.get("/sessions/{session_id}")
async def session_status(session_id: str, request: Request) -> dict[str, Any]:
    access = _require_session_access(request, session_id)
    return _session_status_authorized(session_id, access)


def _gather_reports_authorized(
    access: RequestInvestigationAuthority,
    investigation_ids: Sequence[str],
    *,
    errors: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    """Recover validated secret-free leaf reports from canonical trajectories."""
    from pydantic import ValidationError

    from substrate.event_log import trajectory_authorized
    from substrate.schemas.events import ActionType, GatherReportRecordedPayload

    reports: list[dict[str, object]] = []
    for investigation_id in sorted(investigation_ids):
        child = authority_for_investigation(access, investigation_id)
        if not owns_investigation(child):
            continue
        rows = trajectory_authorized(child.authority)
        matching = [
            row
            for row in rows
            if row.get("action_type") == ActionType.GATHER_REPORT_RECORDED.value
        ]
        if not matching:
            continue
        try:
            payload = GatherReportRecordedPayload.model_validate(
                matching[-1].get("payload")
            )
        except (TypeError, ValidationError):
            if errors is not None:
                errors.append(
                    {
                        "investigation_id": investigation_id,
                        "code": "gather_report_invalid",
                    }
                )
            continue
        reports.append(
            {
                "investigation_id": investigation_id,
                **payload.model_dump(mode="json", exclude={"action_type"}),
            }
        )
    return reports


def _session_status_authorized(
    session_id: str, access: RequestInvestigationAuthority
) -> dict[str, Any]:
    """Build status only after a request or machine boundary validates access."""
    live = _SESSIONS.get(session_id)
    if live is not None:
        cost = live.aggregate_cost()
        terminal = live.terminal_status()
        live_status = live.status()
        gather_report_errors: list[dict[str, str]] = []
        gather_reports = _gather_reports_authorized(
            access,
            [item.investigation_id for item in live_status],
            errors=gather_report_errors,
        )
        return {
            "session_id": session_id,
            "live": True,
            "researches": [
                {
                    "investigation_id": s.investigation_id,
                    "sub_question": s.sub_question,
                    "state": s.state,
                    "question_node_id": s.question_node_id,
                }
                for s in live_status
            ],
            "gather_reports": gather_reports,
            "gather_report_errors": gather_report_errors,
            "cost": cost,
            # DRW parent-terminal observability (SPR-DRL-09 M3): surface whether
            # the session reached DeepResearchComplete and any captured
            # synthesis-tail failure, so a silent terminal failure cannot hide.
            "deep_research_complete": terminal["deep_research_complete"],
            "synthesis_tail_error": terminal["synthesis_tail_error"],
        }
    # Recovery from the event log (durability — session evicted / restart).
    rec = reconstruct_session(session_id, authority=access.authority)
    rec.researches = [
        research
        for research in rec.researches
        if owns_investigation(authority_for_investigation(access, research.investigation_id))
    ]
    if not rec.researches:
        raise HTTPException(status_code=404, detail=f"no session {session_id!r}")
    gather_report_errors: list[dict[str, str]] = []
    gather_reports = _gather_reports_authorized(
        access,
        [research.investigation_id for research in rec.researches],
        errors=gather_report_errors,
    )
    return {
        "session_id": session_id,
        "live": False,
        "researches": [
            {
                "investigation_id": r.investigation_id,
                "sub_question": r.sub_question,
                "state": r.state,
            }
            for r in rec.researches
        ],
        "gather_reports": gather_reports,
        "gather_report_errors": gather_report_errors,
        "all_terminal": rec.all_terminal,
        # Recovered path: surface only what the event log honestly proves. We do
        # not recompute DeepResearchComplete here (its phase postconditions read
        # research artifacts the recovered view does not load) — null means
        # "not reconstructable from membership alone", not "false".
        "deep_research_complete": None,
        "synthesis_tail_error": rec.synthesis_tail_error,
    }


@cascade_router.get("/sessions/{session_id}/cost")
async def session_cost(session_id: str, request: Request) -> dict[str, Any]:
    _require_session_access(request, session_id)
    live = _SESSIONS.get(session_id)
    if live is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not live")
    return live.aggregate_cost()


@cascade_router.post("/sessions/{session_id}/researches/{investigation_id}/steer")
async def steer(
    session_id: str,
    investigation_id: str,
    req: SteerRequest,
    request: Request,
) -> dict[str, Any]:
    access = _require_session_access(request, session_id)
    live = _SESSIONS.get(session_id)
    if live is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not live")
    status = {s.investigation_id: s.state for s in live.status()}
    if investigation_id not in status or not owns_investigation(
        authority_for_investigation(access, investigation_id)
    ):
        raise HTTPException(status_code=404, detail="research session not found")
    await live.steer(investigation_id, _command(req.kind, req.payload))
    return {
        "session_id": session_id,
        "investigation_id": investigation_id,
        "state": status.get(investigation_id),
    }


@cascade_router.get("/sessions/{session_id}/stream")
async def session_stream(session_id: str, request: Request) -> StreamingResponse:
    """Server-sent events: the multiplexed per-research step stream. Live
    sessions stream their full event queue; a reconnect after the session is
    gone replays the durable lifecycle state and closes. At-least-once —
    clients dedup on (investigation_id, seq)."""
    access = _require_session_access(request, session_id)
    live = _SESSIONS.get(session_id)

    async def _live(live_session: CascadeSession) -> AsyncIterator[str]:
        # Poll-drain rather than consume ``session.stream()`` directly: the
        # drain + ``asyncio.sleep`` give the in-process research tasks loop
        # time (so the fan-out progresses while the client watches) and the
        # ``is_complete`` check guarantees the stream terminates — it never
        # hangs waiting on a queue sentinel.
        idle_after_complete = 0
        while True:
            for ev in live_session.drain_nowait():
                yield _sse(
                    {
                        "investigation_id": ev.investigation_id,
                        "seq": ev.seq,
                        "kind": ev.kind,
                        "text": ev.text,
                        "cost_usd": ev.cost_usd,
                        "tokens": ev.tokens,
                        "state": ev.state.value if ev.state else None,
                        "data": ev.data,
                    }
                )
            if live_session.is_complete():
                # Drain one more cycle to flush any final events, then close.
                idle_after_complete += 1
                if idle_after_complete >= 2:
                    break
            await asyncio.sleep(0.02)
        for ev in live_session.drain_nowait():
            yield _sse(
                {
                    "investigation_id": ev.investigation_id,
                    "seq": ev.seq,
                    "kind": ev.kind,
                    "text": ev.text,
                    "cost_usd": ev.cost_usd,
                    "tokens": ev.tokens,
                    "state": ev.state.value if ev.state else None,
                    "data": ev.data,
                }
            )
        yield _sse({"kind": "session_done"})

    async def _recovered() -> AsyncIterator[str]:
        rec = reconstruct_session(session_id, authority=access.authority)
        for r in rec.researches:
            if not owns_investigation(authority_for_investigation(access, r.investigation_id)):
                continue
            yield _sse(
                {
                    "investigation_id": r.investigation_id,
                    "kind": "status",
                    "text": r.sub_question,
                    "state": r.state,
                }
            )
        yield _sse({"kind": "session_done", "recovered": True})

    gen = _live(live) if live is not None else _recovered()
    return StreamingResponse(gen, media_type="text/event-stream")


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, default=str)}\n\n"
