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
import json
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from interfaces.research.api.dispatch_failure import classify_dispatch_failure
from orchestration.cascade_session import CascadeSession, Leaf, reconstruct_session
from roles.cascade_planner import (
    PlanNotApproved,
    PlanReport,
    SubQuestion,
    approve_plan,
    build_plan,
    is_plan_launchable,
    load_tree,
    persist_tree,
)
from roles.cascade_planner.planner import DispatchDecomposer
from roles.cascade_planner.tree_contract import PlanTree
from runtime.db_lock import connect_write
from runtime.research_runner import (
    BillingUnit,
    BoundedUsage,
    BudgetCap,
    BudgetManager,
    Command,
    CommandKind,
    CostProjectionRequest,
    HostLocalRunner,
    ProjectionDisposition,
    PromotionFunnel,
    SpendControlMode,
    make_contract_gather_stub,
    make_exa_gather_loop,
)
from runtime.research_runner.cost_projection import project_cascade_cost
from runtime.research_runner.protocol import BrowseLoop
from runtime.research_runner.provider_gateway import (
    HARD_MODE_DISPATCH_POLICY,
    HARD_MODE_SKIPPED_STAGES,
    ResearchProviderGateway,
    ZeroCostReceipt,
    canonical_digest,
    deterministic_key,
)
from substrate.graph import default_db_path, ensure_initialized
from substrate.research_spend import (
    ResearchSpendLedger,
    RunBinding,
    RunNotFound,
    ZeroCostState,
    ZeroReplayClass,
    default_research_spend_db_path,
)
from substrate.research_spend.ledger import MAX_AUTHORITY_CENTS

if TYPE_CHECKING:
    from orchestration.session_evidence_pack import SessionEvidencePack
    from processing.embedding import EmbeddingProvider

logger = logging.getLogger(__name__)

cascade_router = APIRouter(prefix="/research", tags=["deep-research"])


# ---------------------------------------------------------------------------
# Process-local live-session registry (single-writer / one event loop).
# ---------------------------------------------------------------------------

_SESSIONS: dict[str, CascadeSession] = {}
_SESSION_TASKS: dict[str, asyncio.Task[None]] = {}
_HARD_CEILING_RUNS: dict[CascadeSession, tuple[ResearchProviderGateway, RunBinding]] = {}
_HARD_CEILING_LAUNCHING: set[str] = set()

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


def _spend_db() -> Path:
    """SQLite authority ledger kept beside, but never inside, DuckDB."""
    return default_research_spend_db_path()


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


def _reuse_substrate(
    embedding_provider: EmbeddingProvider | None = None,
) -> _LazyReuseSubstrate | None:
    """Build the lazy reuse substrate for a launch, or ``None`` on failure (reuse
    is best-effort; a launch never breaks because reuse could not be set up)."""
    try:
        return _LazyReuseSubstrate(
            _db(), embedding_provider if embedding_provider is not None else _embedding_provider()
        )
    except Exception:  # pragma: no cover - reuse is best-effort, never fatal
        return None


def _decompose(problem: str, max_depth: int) -> PlanReport:
    """The decomposer the plan endpoint uses when the caller does not supply
    sub-questions. A module attribute so tests can monkeypatch it to a
    deterministic fake without a live model."""
    return build_plan(problem, decomposer=DispatchDecomposer(), max_depth=max_depth)


def _research_loop_factory() -> BrowseLoop:
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
    mode = os.environ.get("ANTIEK_DRW_GATHER", "stub").strip().lower()
    if mode == "exa":
        return cast(BrowseLoop, make_exa_gather_loop(top_k=3))
    return cast(BrowseLoop, make_contract_gather_stub(steps=2, cost_per_step=0.01))


def _command(kind: str, payload: dict[str, Any] | None) -> Command:
    try:
        return Command(kind=CommandKind(kind), payload=payload or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"unknown steer command {kind!r}") from e


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
    spend_mode: SpendControlMode = SpendControlMode.STOP_LIMIT


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

    per_research_budget_usd: float = Field(default=0.50, gt=0, allow_inf_nan=False)
    aggregate_budget_usd: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    spend_mode: SpendControlMode = SpendControlMode.STOP_LIMIT
    hard_ceiling_usd: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    authority_digest: str | None = Field(default=None, min_length=64, max_length=64)


class SpendPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spend_mode: SpendControlMode
    amount_usd: Decimal = Field(gt=0, allow_inf_nan=False)
    per_research_budget_usd: float = Field(default=0.50, gt=0, allow_inf_nan=False)


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
    """The per-research stop limit the runner uses when the launch request
    omits one, plus the host-local concurrency cap. Both read straight off the
    contracts (``BudgetCap`` + ``host_local.DEFAULT_MAX_CONCURRENCY``) so the
    entry + monitor UIs can recommend a stop limit for N researches and show an
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


@cascade_router.get("/suggestions", response_model=SuggestionsResponse)
async def suggestions(limit: int = 8) -> SuggestionsResponse:
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

    capped = max(0, min(int(limit), 50))
    items = build_suggestions(max_suggestions=capped, min_score=0.0)
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
async def create_plan(req: CreatePlanRequest) -> dict[str, Any]:
    """Decompose a problem into an editable, focus-checked sub-question tree
    and persist it. Returns the root node id + the editable tree."""
    if req.spend_mode is SpendControlMode.HARD_CEILING and not req.sub_questions:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "hard_ceiling_provider_ineligible",
                "message": (
                    "Automatic plan decomposition is not hard-ceiling eligible; "
                    "supply reviewed sub_questions or use stop_limit mode."
                ),
            },
        )
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
    tree.seed_provenance = {
        **tree.seed_provenance,
        "decomposition_origin": (
            "manual_sub_questions" if req.sub_questions else "automatic_dispatch"
        ),
    }
    with _write("create_plan") as con:
        root_id = persist_tree(
            tree, investigation_id="__operator__", embedding_provider=_embedding_provider(), con=con
        )
    return {
        "root_node_id": root_id,
        "tree": tree.to_dict(),
        "capped_nodes": report.capped_nodes,
        "over_broad_leaves": report.over_broad_leaves,
    }


@cascade_router.get("/plans/{root_id}")
async def get_plan(root_id: str) -> dict[str, Any]:
    tree = load_tree(root_id, db_path=_db())
    if tree is None:
        raise HTTPException(status_code=404, detail=f"no plan {root_id!r}")
    return {
        "root_node_id": root_id,
        "tree": tree.to_dict(),
        "launchable": is_plan_launchable(root_id, db_path=_db()),
    }


@cascade_router.post("/plans/{root_id}/edit")
async def edit_plan(root_id: str, req: TreeEditRequest) -> dict[str, Any]:
    """Apply one edit to the tree and re-persist. Any edit re-opens the
    approval gate (SPR-05 contract)."""
    with _translate():
        tree = load_tree(root_id, db_path=_db())
        if tree is None:
            raise HTTPException(status_code=404, detail=f"no plan {root_id!r}")
        ok = _apply_edit(tree, req)
        if not ok:
            raise HTTPException(status_code=400, detail=f"edit {req.op!r} failed (bad target?)")
        with _write("edit_plan") as con:
            persist_tree(
                tree,
                investigation_id="__operator__",
                embedding_provider=_embedding_provider(),
                con=con,
            )
    return {
        "root_node_id": root_id,
        "tree": tree.to_dict(),
        "launchable": is_plan_launchable(root_id, db_path=_db()),
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
async def approve(root_id: str, req: ApproveRequest) -> dict[str, Any]:
    with _write("approve_plan") as con:
        approval = approve_plan(
            root_id, approver=req.approver, investigation_id="__operator__", con=con
        )
    return {
        "root_node_id": root_id,
        "approval": approval,
        "launchable": is_plan_launchable(root_id, db_path=_db()),
    }


@cascade_router.post("/plans/{root_id}/spend-preview")
async def spend_preview(root_id: str, req: SpendPreviewRequest, request: Request) -> dict[str, Any]:
    """Return server-owned spend semantics for one exact operator choice.

    No provider rates, credentials, run ids, or caller-authored capability claims cross
    this boundary. Preview never issues authority; the explicit spend-approval action
    records that separately after the plan is approved.
    """
    tree = load_tree(root_id, db_path=_db())
    if tree is None:
        raise HTTPException(status_code=404, detail=f"no plan {root_id!r}")
    amount_cents = _hard_ceiling_cents(req.amount_usd)
    if req.spend_mode is SpendControlMode.STOP_LIMIT:
        return {
            "spend_mode": req.spend_mode.value,
            "currency": "USD",
            "amount_cents": amount_cents,
            "eligible": True,
            "reasons": [],
            "authority_digest": None,
            "recovery_session_id": None,
            "approval_revision": tree.approval.plan_version,
            "assumptions": [
                "Research stops after reported spend reaches the limit.",
                "Final in-flight work can exceed the stop limit.",
            ],
        }
    eligible, reasons, projection_assumptions = _hard_ceiling_eligibility(
        tree=tree, request=request
    )
    return {
        "spend_mode": req.spend_mode.value,
        "currency": "USD",
        "amount_cents": amount_cents,
        "eligible": eligible,
        "reasons": list(reasons),
        "authority_digest": None,
        "recovery_session_id": None,
        "approval_revision": tree.approval.plan_version,
        "assumptions": [
            *projection_assumptions,
            "Antiek reserves each conservative maximum before provider dispatch.",
            "Unknown provider outcomes retain their full reservation until reconciled.",
            "Taxes, currency conversion, external fees, and provider misbilling are not bounded.",
            "Synthesis stages that lack enforceable billing are disabled.",
        ],
    }


# ---------------------------------------------------------------------------
# Launch + session endpoints (SPR-06)
# ---------------------------------------------------------------------------


def _hard_ceiling_cents(amount: Decimal | None) -> int:
    if amount is None:
        raise HTTPException(
            status_code=422,
            detail="hard_ceiling_usd is required when spend_mode is hard_ceiling",
        )
    try:
        cents = amount * Decimal(100)
        integral = cents.to_integral_exact()
    except (DecimalException, ValueError) as exc:
        raise HTTPException(status_code=422, detail="hard ceiling must use whole cents") from exc
    if cents != integral:
        raise HTTPException(status_code=422, detail="hard ceiling must use whole cents")
    result = int(integral)
    if result > MAX_AUTHORITY_CENTS:
        raise HTTPException(
            status_code=422,
            detail=f"hard ceiling must not exceed {MAX_AUTHORITY_CENTS} cents",
        )
    return result


def _hard_ceiling_plan_digest(*, root_id: str, tree: PlanTree, request: LaunchRequest) -> str:
    gather_mode = os.environ.get("ANTIEK_DRW_GATHER", "stub").strip().lower()
    return canonical_digest(
        {
            "root_id": root_id,
            "tree": tree.to_dict(),
            "launch": {
                "mode": request.spend_mode,
                "per_research_budget_usd": str(request.per_research_budget_usd),
                "aggregate_budget_usd": (
                    None
                    if request.aggregate_budget_usd is None
                    else str(request.aggregate_budget_usd)
                ),
                "hard_ceiling_cents": (
                    None
                    if request.hard_ceiling_usd is None
                    else _hard_ceiling_cents(request.hard_ceiling_usd)
                ),
                "gather_mode": gather_mode,
                "synthesis_tail": False,
                "dispatch_policy": HARD_MODE_DISPATCH_POLICY,
            },
        }
    )


def _hard_ceiling_eligibility(
    *, tree: PlanTree, request: Request
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    reasons: list[str] = []
    assumptions: list[str] = []
    owner_id = getattr(request.state, "user_id", None)
    if not isinstance(owner_id, str) or not owner_id:
        reasons.append("An authenticated operator identity is required.")
    if (
        getattr(request.state, "auth_method", None) == "unauthenticated_local"
        and os.environ.get("ANTIEK_ALLOW_LOCAL_HARD_CEILING", "") != "1"
    ):
        reasons.append("Hard ceilings are not enabled for this local operator session.")
    gather_mode = os.environ.get("ANTIEK_DRW_GATHER", "stub").strip().lower()
    projection_requests = (
        (
            "Operator approval",
            CostProjectionRequest(
                seam_id="cascade.operator.spend_approval",
                provider="antiek",
                model="operator-authority",
                operation="approve",
                bounded_usage=(BoundedUsage(BillingUnit.LOCAL_OPERATION, 1),),
            ),
        ),
        (
            "Session launch",
            CostProjectionRequest(
                seam_id="cascade.session.launch",
                provider="antiek",
                model="host-local",
                operation="launch",
                bounded_usage=(BoundedUsage(BillingUnit.LOCAL_OPERATION, 1),),
            ),
        ),
        (
            "Gather",
            CostProjectionRequest(
                seam_id=(
                    "cascade.gather.contract_stub"
                    if gather_mode == "stub"
                    else "cascade.gather.exa.search"
                ),
                provider="antiek" if gather_mode == "stub" else "exa",
                model="contract-stub" if gather_mode == "stub" else "search",
                operation="gather" if gather_mode == "stub" else "search",
                bounded_usage=(
                    BoundedUsage(
                        BillingUnit.LOCAL_OPERATION if gather_mode == "stub" else BillingUnit.CALL,
                        1,
                    ),
                ),
            ),
        ),
        (
            "Embedding",
            CostProjectionRequest(
                seam_id="cascade.gather.embedding.bootstrap",
                provider="local",
                model="sentence-transformers-or-hash",
                operation="embed",
                bounded_usage=(BoundedUsage(BillingUnit.LOCAL_OPERATION, 1),),
            ),
        ),
    )
    for label, projection_request in projection_requests:
        projection = project_cascade_cost(projection_request)
        assumptions.extend(projection.assumptions)
        if projection.disposition is ProjectionDisposition.INELIGIBLE:
            reason = (
                "not eligible"
                if projection.ineligibility is None
                else projection.ineligibility.value.replace("_", " ")
            )
            reasons.append(f"{label} is not hard-ceiling eligible: {reason}.")
    if tree.seed_provenance.get("decomposition_origin") != "manual_sub_questions":
        reasons.append("This automatically generated plan is stop-limit only.")
    return not reasons, tuple(reasons), tuple(dict.fromkeys(assumptions))


def _safe_hard_ceiling_snapshot(
    gateway: ResearchProviderGateway, binding: RunBinding
) -> dict[str, Any]:
    balance = gateway.ledger.balance(binding.run_id)
    recovery = gateway.ledger.recovery_work(binding.run_id)
    unknown_count = sum(
        item.kind == "paid" and item.action == "reconcile_provider" for item in recovery
    )
    return {
        "currency": "USD",
        "approval_revision": binding.approval_revision,
        "authority_digest": _hard_ceiling_authority_digest_from_binding(binding),
        "ceiling_cents": balance.ceiling_cents,
        "authorized_spent_cents": balance.authorized_spent_cents,
        "observed_provider_spend_cents": balance.observed_provider_spend_cents,
        "held_cents": balance.held_cents,
        "available_cents": balance.available_cents,
        "run_state": balance.status.value,
        "ceiling_breached": balance.ceiling_breached,
        "unknown_outcome_count": unknown_count,
        "blocked_stages": list(HARD_MODE_SKIPPED_STAGES),
    }


def _hard_ceiling_authority_digest_from_binding(binding: RunBinding) -> str:
    return canonical_digest(
        {
            "contract": "research-hard-ceiling-approval-v1",
            "owner_id": binding.owner_id,
            "plan_digest": binding.plan_digest,
            "approval_revision": binding.approval_revision,
            "currency": binding.currency,
        }
    )


def _hard_ceiling_snapshot_for_session(session_id: str, request: Request) -> dict[str, Any] | None:
    owner_id = getattr(request.state, "user_id", None)
    if not isinstance(owner_id, str) or not owner_id:
        return None
    live = _SESSIONS.get(session_id)
    if live is not None:
        hard_run = _HARD_CEILING_RUNS.get(live)
        if hard_run is not None:
            gateway, binding = hard_run
            if binding.owner_id != owner_id:
                return None
            return _safe_hard_ceiling_snapshot(gateway, binding)
    ledger = ResearchSpendLedger(_spend_db())
    ledger.ensure_schema()
    balance = ledger.balance_for_session(owner_id, session_id)
    if balance is None:
        return None
    return _safe_hard_ceiling_snapshot(ResearchProviderGateway(ledger), balance.binding)


def _enforce_hard_session_owner(session_id: str, request: Request) -> None:
    """Hide a hard session entirely when it belongs to another owner."""
    ledger = ResearchSpendLedger(_spend_db())
    ledger.ensure_schema()
    bound_owner = ledger.owner_for_session(session_id)
    if bound_owner is None:
        return
    caller = getattr(request.state, "user_id", None)
    if caller != bound_owner:
        raise HTTPException(status_code=404, detail=f"no session {session_id!r}")


def _hard_ceiling_binding(
    *, root_id: str, session_id: str, owner_id: str, tree: PlanTree, request: LaunchRequest
) -> RunBinding:
    plan_digest = _hard_ceiling_plan_digest(root_id=root_id, tree=tree, request=request)
    run_id = deterministic_key("research-hard-run", owner_id, session_id, root_id, plan_digest)
    return RunBinding(
        run_id=run_id,
        owner_id=owner_id,
        session_id=session_id,
        plan_digest=plan_digest,
        approval_revision=tree.approval.plan_version,
    )


def _receipted_hard_ceiling_loop(
    inner: BrowseLoop,
    *,
    gateway: ResearchProviderGateway,
    binding: RunBinding,
) -> BrowseLoop:
    async def _loop(ctx: Any) -> AsyncIterator[Any]:
        receipt = gateway.prepare_zero_cost(
            binding,
            logical_operation_id=f"{ctx.investigation_id}:gather",
            projection_request=CostProjectionRequest(
                seam_id="cascade.gather.contract_stub",
                provider="antiek",
                model="contract-stub",
                operation="gather",
                bounded_usage=(BoundedUsage(BillingUnit.LOCAL_OPERATION, 1),),
            ),
            operation_payload={
                "investigation_id": ctx.investigation_id,
                "sub_question": ctx.sub_question,
            },
            replay_class=ZeroReplayClass.PURE,
        )
        if receipt.attempt.state is ZeroCostState.COMPLETED:
            return
        if receipt.attempt.state is ZeroCostState.FAILED:
            raise RuntimeError("zero-cost gather attempt previously failed")
        emitted = 0
        try:
            async for event in inner(ctx):
                emitted += 1
                # The contract stub's cents are simulated stop-limit telemetry,
                # not provider billing. Hard mode reports provider cost as zero.
                yield replace(event, cost_usd=0.0)
        except BaseException as exc:
            gateway.fail_zero_cost(
                receipt,
                outcome={"exception_type": type(exc).__name__, "emitted_steps": emitted},
            )
            raise
        else:
            gateway.complete_zero_cost(receipt, outcome={"emitted_steps": emitted})

    return cast(BrowseLoop, _loop)


def _hard_ceiling_embedding_provider(
    gateway: ResearchProviderGateway, binding: RunBinding
) -> EmbeddingProvider:
    receipt = gateway.prepare_zero_cost(
        binding,
        logical_operation_id="session:embedding-bootstrap",
        projection_request=CostProjectionRequest(
            seam_id="cascade.gather.embedding.bootstrap",
            provider="local",
            model="sentence-transformers-or-hash",
            operation="embed",
            bounded_usage=(BoundedUsage(BillingUnit.LOCAL_OPERATION, 1),),
        ),
        operation_payload={"purpose": "cascade-promotion-and-reuse"},
        replay_class=ZeroReplayClass.CHECKPOINT_RESUMABLE,
    )
    if receipt.attempt.state is ZeroCostState.FAILED:
        raise RuntimeError("embedding bootstrap attempt previously failed")
    try:
        provider = _embedding_provider()
    except BaseException as exc:
        if receipt.attempt.state is ZeroCostState.PREPARED:
            gateway.fail_zero_cost(receipt, outcome={"exception_type": type(exc).__name__})
        raise
    if receipt.attempt.state is ZeroCostState.PREPARED:
        gateway.complete_zero_cost(receipt, outcome={"provider_type": type(provider).__name__})
    return provider


def _hard_ceiling_launch_receipt(
    gateway: ResearchProviderGateway,
    binding: RunBinding,
    *,
    root_id: str,
    leaves: Sequence[Leaf],
) -> ZeroCostReceipt:
    return gateway.prepare_zero_cost(
        binding,
        logical_operation_id="session:launch",
        projection_request=CostProjectionRequest(
            seam_id="cascade.session.launch",
            provider="antiek",
            model="host-local",
            operation="launch",
            bounded_usage=(BoundedUsage(BillingUnit.LOCAL_OPERATION, 1),),
        ),
        operation_payload={
            "root_id": root_id,
            "leaf_ids": [leaf.investigation_id for leaf in leaves],
        },
        replay_class=ZeroReplayClass.CHECKPOINT_RESUMABLE,
    )


def _hard_ceiling_approval_receipt(
    gateway: ResearchProviderGateway,
    binding: RunBinding,
    *,
    authority_digest: str,
    ceiling_cents: int,
) -> ZeroCostReceipt:
    return gateway.prepare_zero_cost(
        binding,
        logical_operation_id="operator:spend-approval",
        projection_request=CostProjectionRequest(
            seam_id="cascade.operator.spend_approval",
            provider="antiek",
            model="operator-authority",
            operation="approve",
            bounded_usage=(BoundedUsage(BillingUnit.LOCAL_OPERATION, 1),),
        ),
        operation_payload={
            "authority_digest": authority_digest,
            "approval_revision": binding.approval_revision,
            "ceiling_cents": ceiling_cents,
            "currency": binding.currency,
            "mode": binding.mode,
        },
        replay_class=ZeroReplayClass.PURE,
    )


@cascade_router.post("/plans/{root_id}/spend-approval")
async def approve_spend(root_id: str, req: SpendPreviewRequest, request: Request) -> dict[str, Any]:
    """Durably record explicit operator approval of one exact spend authority."""
    if req.spend_mode is not SpendControlMode.HARD_CEILING:
        raise HTTPException(status_code=422, detail="durable spend approval is for hard mode")
    tree = load_tree(root_id, db_path=_db())
    if tree is None:
        raise HTTPException(status_code=404, detail=f"no plan {root_id!r}")
    if not is_plan_launchable(root_id, db_path=_db()):
        raise HTTPException(status_code=409, detail={"code": "plan_not_approved"})
    eligible, reasons, _ = _hard_ceiling_eligibility(tree=tree, request=request)
    if not eligible:
        raise HTTPException(
            status_code=409,
            detail={"code": "hard_ceiling_ineligible", "reasons": list(reasons)},
        )
    owner_id = getattr(request.state, "user_id", None)
    if not isinstance(owner_id, str) or not owner_id:
        raise HTTPException(status_code=401, detail="authenticated owner identity required")
    launch_request = LaunchRequest(
        spend_mode=SpendControlMode.HARD_CEILING,
        hard_ceiling_usd=req.amount_usd,
        per_research_budget_usd=req.per_research_budget_usd,
    )
    plan_digest = _hard_ceiling_plan_digest(root_id=root_id, tree=tree, request=launch_request)
    authority_suffix = canonical_digest({"owner_id": owner_id, "plan_digest": plan_digest})[:16]
    session_id = f"session-{root_id}-hard-{authority_suffix}"
    binding = _hard_ceiling_binding(
        root_id=root_id,
        session_id=session_id,
        owner_id=owner_id,
        tree=tree,
        request=launch_request,
    )
    authority_digest = _hard_ceiling_authority_digest_from_binding(binding)
    ceiling_cents = _hard_ceiling_cents(req.amount_usd)
    gateway = ResearchProviderGateway(ResearchSpendLedger(_spend_db()))
    gateway.create_or_reopen_run(binding, ceiling_cents=ceiling_cents)
    receipt = _hard_ceiling_approval_receipt(
        gateway,
        binding,
        authority_digest=authority_digest,
        ceiling_cents=ceiling_cents,
    )
    if receipt.attempt.state is ZeroCostState.FAILED:
        raise HTTPException(status_code=409, detail={"code": "spend_approval_failed"})
    if receipt.attempt.state is ZeroCostState.PREPARED:
        gateway.complete_zero_cost(
            receipt,
            outcome={"approved": True, "authority_digest": authority_digest},
        )
    return {
        "spend_mode": req.spend_mode.value,
        "currency": "USD",
        "amount_cents": ceiling_cents,
        "eligible": True,
        "reasons": [],
        "authority_digest": authority_digest,
        "recovery_session_id": session_id,
        "approval_revision": binding.approval_revision,
        "assumptions": [
            "Antiek reserves each conservative maximum before provider dispatch.",
            "Unknown provider outcomes retain their full reservation until reconciled.",
            "Taxes, currency conversion, external fees, and provider misbilling are not bounded.",
            "Synthesis stages that lack enforceable billing are disabled.",
        ],
    }


@cascade_router.post("/plans/{root_id}/launch")
async def launch(root_id: str, req: LaunchRequest, request: Request) -> dict[str, Any]:
    """Launch an approved plan as N parallel researches. Refuses an
    unapproved plan (SPR-05 gate). Returns the session id + the researches.

    Background completion runs gather (per leaf) then the Loop 1 synthesis
    tail (phases 6–9 on ``session_id``) when a synthesis runner is wired —
    see ``set_synthesis_tail_runner``."""
    with _translate():
        if not is_plan_launchable(root_id, db_path=_db()):
            raise PlanNotApproved(
                f"plan {root_id!r} is not approved — the glass-box gate refuses launch."
            )
        tree = load_tree(root_id, db_path=_db())
        if tree is None:
            raise HTTPException(status_code=404, detail=f"no plan {root_id!r}")

    session_id = f"session-{root_id}"
    gateway: ResearchProviderGateway | None = None
    binding: RunBinding | None = None
    existing_durable_run = False
    if req.spend_mode is SpendControlMode.HARD_CEILING:
        owner_id = getattr(request.state, "user_id", None)
        if not isinstance(owner_id, str) or not owner_id:
            raise HTTPException(status_code=401, detail="authenticated owner identity required")
        if (
            getattr(request.state, "auth_method", None) == "unauthenticated_local"
            and os.environ.get("ANTIEK_ALLOW_LOCAL_HARD_CEILING", "") != "1"
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "hard-ceiling launch requires authenticated operator authority or "
                    "ANTIEK_ALLOW_LOCAL_HARD_CEILING=1 on an operator-controlled host"
                ),
            )
        gather_mode = os.environ.get("ANTIEK_DRW_GATHER", "stub").strip().lower()
        if gather_mode != "stub":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "hard_ceiling_provider_ineligible",
                    "message": "Exa gather lacks durable idempotency and billing reconciliation.",
                },
            )
        if tree.seed_provenance.get("decomposition_origin") != "manual_sub_questions":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "hard_ceiling_plan_ineligible",
                    "message": (
                        "Hard-ceiling launch requires a plan created from explicit "
                        "sub_questions and subsequently approved."
                    ),
                },
            )
        plan_digest = _hard_ceiling_plan_digest(root_id=root_id, tree=tree, request=req)
        authority_suffix = canonical_digest({"owner_id": owner_id, "plan_digest": plan_digest})[:16]
        session_id = f"session-{root_id}-hard-{authority_suffix}"
        binding = _hard_ceiling_binding(
            root_id=root_id,
            session_id=session_id,
            owner_id=owner_id,
            tree=tree,
            request=req,
        )
        expected_authority = _hard_ceiling_authority_digest_from_binding(binding)
        if req.authority_digest != expected_authority:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "hard_ceiling_stale_approval",
                    "message": (
                        "The approved plan, mode, provider path, currency, or ceiling changed. "
                        "Review the current spend preview before launching."
                    ),
                },
            )
        gateway = ResearchProviderGateway(ResearchSpendLedger(_spend_db()))
        ceiling_cents = _hard_ceiling_cents(req.hard_ceiling_usd)
        gateway.ledger.ensure_schema()
        try:
            existing_run = gateway.ledger.balance(binding.run_id)
        except RunNotFound:
            gateway.create_or_reopen_run(binding, ceiling_cents=ceiling_cents)
        else:
            if existing_run.binding != binding or existing_run.ceiling_cents != ceiling_cents:
                raise HTTPException(status_code=409, detail="durable run binding conflict")
            existing_durable_run = True
        approval_receipt = _hard_ceiling_approval_receipt(
            gateway,
            binding,
            authority_digest=expected_authority,
            ceiling_cents=ceiling_cents,
        )
        if approval_receipt.attempt.state is not ZeroCostState.COMPLETED:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "hard_ceiling_approval_required",
                    "message": "Approve this exact hard-ceiling authority before launching.",
                },
            )

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
    launch_receipt = (
        None
        if gateway is None or binding is None
        else _hard_ceiling_launch_receipt(gateway, binding, root_id=root_id, leaves=leaves)
    )
    durable_replay = bool(
        launch_receipt is not None and launch_receipt.attempt.state is ZeroCostState.COMPLETED
    )
    if (
        existing_durable_run
        and launch_receipt is not None
        and launch_receipt.replayed
        and launch_receipt.attempt.state is ZeroCostState.PREPARED
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "hard_ceiling_launch_interrupted",
                "message": (
                    "A prior launch did not durably complete; operator recovery "
                    "is required before this authority can be reused."
                ),
            },
        )
    if launch_receipt is not None and launch_receipt.attempt.state is ZeroCostState.FAILED:
        raise HTTPException(
            status_code=409,
            detail={"code": "hard_ceiling_launch_failed"},
        )
    existing_session = _SESSIONS.get(session_id)
    if gateway is not None and binding is not None and existing_session is not None:
        existing_hard_run = _HARD_CEILING_RUNS.get(existing_session)
        if existing_hard_run is None or existing_hard_run[1] != binding:
            raise HTTPException(status_code=409, detail="session identity is already in use")
        existing_gateway, _ = existing_hard_run
        return {
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
            "spend_mode": req.spend_mode.value,
            "replayed": True,
            "hard_ceiling": _safe_hard_ceiling_snapshot(existing_gateway, binding),
        }
    resumed = False
    if gateway is not None and binding is not None and durable_replay:
        recovered = reconstruct_session(session_id)
        if recovered.researches and recovered.all_terminal:
            return {
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
                "spend_mode": req.spend_mode.value,
                "replayed": True,
                "resumed": False,
                "hard_ceiling": _safe_hard_ceiling_snapshot(gateway, binding),
            }
        # A completed launch receipt proves acceptance, not terminal execution.
        # Rebuild the host-local session when durable lifecycle evidence is absent
        # or nonterminal. Per-leaf receipts make completed work a no-op and resume
        # only checkpoint-safe zero-cost work; paid unknowns remain held.
        resumed = True
    if gateway is not None and session_id in _HARD_CEILING_LAUNCHING:
        raise HTTPException(status_code=409, detail="hard-ceiling session launch in progress")
    embedding_provider = (
        _embedding_provider()
        if gateway is None or binding is None
        else _hard_ceiling_embedding_provider(gateway, binding)
    )
    funnel = PromotionFunnel(db_path=_db(), embedding_provider=embedding_provider)
    # Flywheel reuse ON: a §9.0-gated substrate that reads the live graph through
    # a cursor of a read-write handle SHARING the funnel's DuckDB instance (never
    # a conflicting connect_read). It opens lazily on the first reuse read inside
    # launch() and is closed the instant launch() returns, so the read-write
    # handle never overlaps a connect_read reader. Best-effort: None degrades to
    # today's no-reuse behaviour, so a launch never breaks. See _reuse_substrate.
    reuse_substrate = _reuse_substrate(embedding_provider)
    loop = _research_loop_factory()
    if gateway is not None and binding is not None:
        loop = _receipted_hard_ceiling_loop(loop, gateway=gateway, binding=binding)
    runner = HostLocalRunner(
        loop,
        budget=budget,
        on_emit=funnel.submit,
        seal_on_complete=False,
        retrieval_substrate=reuse_substrate,
    )
    session = CascadeSession(session_id, runner=runner, funnel=funnel, db_path=_db())
    if gateway is not None:
        _HARD_CEILING_LAUNCHING.add(session_id)
    try:
        await session.launch(root_id, leaves)
        if gateway is not None and launch_receipt is not None:
            gateway.complete_zero_cost(
                launch_receipt,
                outcome={"session_id": session_id, "leaf_count": len(leaves)},
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
        _HARD_CEILING_LAUNCHING.discard(session_id)
    _SESSIONS[session_id] = session
    if gateway is not None and binding is not None:
        _HARD_CEILING_RUNS[session] = (gateway, binding)
    # Drive the fan-out to completion (join + funnel drain + merge) in the
    # background so the session progresses without a connected stream client.
    _SESSION_TASKS[session_id] = asyncio.create_task(_run_to_completion(session))
    response: dict[str, Any] = {
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
        "spend_mode": req.spend_mode.value,
        "replayed": False,
        "resumed": resumed,
    }
    if binding is not None and gateway is not None:
        response["hard_ceiling"] = _safe_hard_ceiling_snapshot(gateway, binding)
    return response


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
        if _SYNTHESIS_TAIL_RUNNER is not None and session not in _HARD_CEILING_RUNS:
            stage = "synthesis_tail"
            pack = session.build_evidence_pack()
            await _SYNTHESIS_TAIL_RUNNER(session, pack)
    except Exception as exc:
        # Capture, do not swallow: record WITH the failing stage (so a join/merge
        # failure isn't mislabeled as a synthesis-tail one) + audit, stay non-fatal.
        session.record_synthesis_tail_error(exc, stage=stage)
    finally:
        hard_run = _HARD_CEILING_RUNS.get(session)
        if hard_run is not None:
            gateway, binding = hard_run
            try:
                gateway.ledger.close_execution(
                    deterministic_key("research-close", binding.run_id),
                    binding.run_id,
                    "cascade execution reached terminal state",
                )
            except Exception as exc:
                logger.exception("hard-ceiling close failed for %s: %s", binding.run_id, exc)


@cascade_router.get("/sessions/{session_id}")
async def session_status(session_id: str, request: Request) -> dict[str, Any]:
    _enforce_hard_session_owner(session_id, request)
    live = _SESSIONS.get(session_id)
    if live is not None:
        cost = live.aggregate_cost()
        terminal = live.terminal_status()
        response = {
            "session_id": session_id,
            "live": True,
            "researches": [
                {
                    "investigation_id": s.investigation_id,
                    "sub_question": s.sub_question,
                    "state": s.state,
                    "question_node_id": s.question_node_id,
                }
                for s in live.status()
            ],
            "cost": cost,
            # DRW parent-terminal observability (SPR-DRL-09 M3): surface whether
            # the session reached DeepResearchComplete and any captured
            # synthesis-tail failure, so a silent terminal failure cannot hide.
            "deep_research_complete": terminal["deep_research_complete"],
            "synthesis_tail_error": terminal["synthesis_tail_error"],
        }
        hard_ceiling = _hard_ceiling_snapshot_for_session(session_id, request)
        if hard_ceiling is not None:
            response["hard_ceiling"] = hard_ceiling
        return response
    # Recovery from the event log (durability — session evicted / restart).
    rec = reconstruct_session(session_id)
    if not rec.researches:
        raise HTTPException(status_code=404, detail=f"no session {session_id!r}")
    response = {
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
        "all_terminal": rec.all_terminal,
        # Recovered path: surface only what the event log honestly proves. We do
        # not recompute DeepResearchComplete here (its phase postconditions read
        # research artifacts the recovered view does not load) — null means
        # "not reconstructable from membership alone", not "false".
        "deep_research_complete": None,
        "synthesis_tail_error": rec.synthesis_tail_error,
    }
    hard_ceiling = _hard_ceiling_snapshot_for_session(session_id, request)
    if hard_ceiling is not None:
        response["hard_ceiling"] = hard_ceiling
    return response


@cascade_router.post("/sessions/{session_id}/spend/reconcile")
async def reconcile_session_spend(session_id: str, request: Request) -> dict[str, Any]:
    """Refresh authoritative spend evidence without retrying provider work.

    The currently reachable hard path is zero-cost and therefore has no paid adapter to
    poll. Future paid adapters register reconciliation behind the provider gateway; until
    then unresolved sends remain held and visible rather than being guessed or retried.
    """
    _enforce_hard_session_owner(session_id, request)
    snapshot = _hard_ceiling_snapshot_for_session(session_id, request)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"no hard-ceiling session {session_id!r}")
    return {
        "hard_ceiling": snapshot,
        "provider_checks_started": 0,
        "message": (
            "Authoritative status refreshed. Unresolved provider outcomes remain held "
            "until a provider reconciliation adapter supplies evidence."
            if snapshot["unknown_outcome_count"]
            else "Authoritative status refreshed; no provider outcomes need reconciliation."
        ),
    }


@cascade_router.get("/sessions/{session_id}/cost")
async def session_cost(session_id: str, request: Request) -> dict[str, Any]:
    _enforce_hard_session_owner(session_id, request)
    live = _SESSIONS.get(session_id)
    if live is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not live")
    return live.aggregate_cost()


@cascade_router.post("/sessions/{session_id}/researches/{investigation_id}/steer")
async def steer(
    session_id: str, investigation_id: str, req: SteerRequest, request: Request
) -> dict[str, Any]:
    _enforce_hard_session_owner(session_id, request)
    live = _SESSIONS.get(session_id)
    if live is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not live")
    await live.steer(investigation_id, _command(req.kind, req.payload))
    status = {s.investigation_id: s.state for s in live.status()}
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
    _enforce_hard_session_owner(session_id, request)
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
        rec = reconstruct_session(session_id)
        for r in rec.researches:
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
