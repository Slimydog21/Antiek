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
import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from interfaces.research.api.dispatch_failure import classify_dispatch_failure
from orchestration.cascade_session import CascadeSession, Leaf, reconstruct_session
from roles.cascade_planner import (
    PlanNotApproved,
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
    BudgetCap,
    BudgetManager,
    Command,
    CommandKind,
    HostLocalRunner,
    PromotionFunnel,
    make_contract_gather_stub,
    make_exa_gather_loop,
)
from substrate.graph import default_db_path, ensure_initialized

logger = logging.getLogger(__name__)

cascade_router = APIRouter(prefix="/research", tags=["deep-research"])


# ---------------------------------------------------------------------------
# Process-local live-session registry (single-writer / one event loop).
# ---------------------------------------------------------------------------

_SESSIONS: dict[str, CascadeSession] = {}
_SESSION_TASKS: dict[str, asyncio.Task] = {}

# Optional hook set by ``create_app`` after Loop 1 handlers register.
# Runs Path A synthesis tail (phases 6–9) once gather + merge finish.
_SYNTHESIS_TAIL_RUNNER: Any | None = None


def set_synthesis_tail_runner(runner: Any) -> None:
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


def _embedding_provider():
    from processing.embedding import default_embedding_provider
    return default_embedding_provider()


def _decompose(problem: str, max_depth: int):
    """The decomposer the plan endpoint uses when the caller does not supply
    sub-questions. A module attribute so tests can monkeypatch it to a
    deterministic fake without a live model."""
    return build_plan(problem, decomposer=DispatchDecomposer(), max_depth=max_depth)


def _research_loop_factory():
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
        return make_exa_gather_loop(top_k=3)
    return make_contract_gather_stub(steps=2, cost_per_step=0.01)


def _command(kind: str, payload: dict | None) -> Command:
    try:
        return Command(kind=CommandKind(kind), payload=payload or {})
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"unknown steer command {kind!r}"
        ) from exc


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
    per_research_budget_usd: float = Field(default=0.50, gt=0)
    aggregate_budget_usd: float | None = None


class SteerRequest(BaseModel):
    kind: str  # pause | resume | stop | redirect | deepen
    payload: dict | None = None


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
async def budget_defaults() -> dict:
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
async def create_plan(req: CreatePlanRequest) -> dict:
    """Decompose a problem into an editable, focus-checked sub-question tree
    and persist it. Returns the root node id + the editable tree."""
    if req.sub_questions:
        class _Fixed:
            def decompose(self, q, *, context=""):
                return [SubQuestion(question=s) for s in req.sub_questions]
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
    with _write("create_plan") as con:
        root_id = persist_tree(tree, investigation_id="__operator__",
                               embedding_provider=_embedding_provider(), con=con)
    return {"root_node_id": root_id, "tree": tree.to_dict(),
            "capped_nodes": report.capped_nodes,
            "over_broad_leaves": report.over_broad_leaves}


@cascade_router.get("/plans/{root_id}")
async def get_plan(root_id: str) -> dict:
    tree = load_tree(root_id, db_path=_db())
    if tree is None:
        raise HTTPException(status_code=404, detail=f"no plan {root_id!r}")
    return {"root_node_id": root_id, "tree": tree.to_dict(),
            "launchable": is_plan_launchable(root_id, db_path=_db())}


@cascade_router.post("/plans/{root_id}/edit")
async def edit_plan(root_id: str, req: TreeEditRequest) -> dict:
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
            persist_tree(tree, investigation_id="__operator__",
                         embedding_provider=_embedding_provider(), con=con)
    return {"root_node_id": root_id, "tree": tree.to_dict(),
            "launchable": is_plan_launchable(root_id, db_path=_db())}


def _apply_edit(tree: PlanTree, req: TreeEditRequest) -> bool:
    if req.op == "add_child":
        return tree.add_child(req.target_local_id, req.question or "New sub-question") is not None
    if req.op == "remove":
        return tree.remove(req.target_local_id)
    if req.op == "reword":
        return tree.reword(req.target_local_id, req.question or "")
    if req.op == "set_budget":
        return tree.set_budget(req.target_local_id, budget_usd=req.budget_usd, max_depth=req.max_depth)
    if req.op == "split":
        return tree.split(req.target_local_id, req.into or [])
    raise HTTPException(status_code=400, detail=f"unknown edit op {req.op!r}")


@cascade_router.post("/plans/{root_id}/approve")
async def approve(root_id: str, req: ApproveRequest) -> dict:
    with _write("approve_plan") as con:
        approval = approve_plan(root_id, approver=req.approver,
                                investigation_id="__operator__", con=con)
    return {"root_node_id": root_id, "approval": approval,
            "launchable": is_plan_launchable(root_id, db_path=_db())}


# ---------------------------------------------------------------------------
# Launch + session endpoints (SPR-06)
# ---------------------------------------------------------------------------


@cascade_router.post("/plans/{root_id}/launch")
async def launch(root_id: str, req: LaunchRequest) -> dict:
    """Launch an approved plan as N parallel researches. Refuses an
    unapproved plan (SPR-05 gate). Returns the session id + the researches.

    Background completion runs gather (per leaf) then the Loop 1 synthesis
    tail (phases 6–9 on ``session_id``) when a synthesis runner is wired —
    see ``set_synthesis_tail_runner``."""
    with _translate():
        if not is_plan_launchable(root_id, db_path=_db()):
            raise PlanNotApproved(
                f"plan {root_id!r} is not approved — the glass-box gate refuses launch.")
        tree = load_tree(root_id, db_path=_db())
        if tree is None:
            raise HTTPException(status_code=404, detail=f"no plan {root_id!r}")

    session_id = f"session-{root_id}"
    leaves = [
        Leaf(investigation_id=f"{session_id}-leaf-{i}", sub_question=leaf.question,
             question_node_id=leaf.graph_node_id,
             budget=BudgetCap(cost_usd=req.per_research_budget_usd))
        for i, leaf in enumerate(tree.leaves)
    ]
    budget = BudgetManager(aggregate_cap_usd=req.aggregate_budget_usd)
    funnel = PromotionFunnel(db_path=_db(), embedding_provider=_embedding_provider())
    runner = HostLocalRunner(_research_loop_factory(), budget=budget,
                             on_emit=funnel.submit, seal_on_complete=False)
    session = CascadeSession(session_id, runner=runner, funnel=funnel, db_path=_db())
    await session.launch(root_id, leaves)
    _SESSIONS[session_id] = session
    # Drive the fan-out to completion (join + funnel drain + merge) in the
    # background so the session progresses without a connected stream client.
    _SESSION_TASKS[session_id] = asyncio.create_task(_run_to_completion(session))
    return {
        "session_id": session_id,
        "researches": [
            {"investigation_id": leaf.investigation_id, "sub_question": leaf.sub_question,
             "question_node_id": leaf.question_node_id}
            for leaf in leaves
        ],
        "aggregate_cap_usd": budget.aggregate_cap_usd,
    }


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
async def session_status(session_id: str) -> dict:
    live = _SESSIONS.get(session_id)
    if live is not None:
        cost = live.aggregate_cost()
        terminal = live.terminal_status()
        return {
            "session_id": session_id, "live": True,
            "researches": [
                {"investigation_id": s.investigation_id, "sub_question": s.sub_question,
                 "state": s.state, "question_node_id": s.question_node_id}
                for s in live.status()
            ],
            "cost": cost,
            # DRW parent-terminal observability (SPR-DRL-09 M3): surface whether
            # the session reached DeepResearchComplete and any captured
            # synthesis-tail failure, so a silent terminal failure cannot hide.
            "deep_research_complete": terminal["deep_research_complete"],
            "synthesis_tail_error": terminal["synthesis_tail_error"],
        }
    # Recovery from the event log (durability — session evicted / restart).
    rec = reconstruct_session(session_id)
    if not rec.researches:
        raise HTTPException(status_code=404, detail=f"no session {session_id!r}")
    return {
        "session_id": session_id, "live": False,
        "researches": [
            {"investigation_id": r.investigation_id, "sub_question": r.sub_question,
             "state": r.state}
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


@cascade_router.get("/sessions/{session_id}/cost")
async def session_cost(session_id: str) -> dict:
    live = _SESSIONS.get(session_id)
    if live is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not live")
    return live.aggregate_cost()


@cascade_router.post("/sessions/{session_id}/researches/{investigation_id}/steer")
async def steer(session_id: str, investigation_id: str, req: SteerRequest) -> dict:
    live = _SESSIONS.get(session_id)
    if live is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not live")
    await live.steer(investigation_id, _command(req.kind, req.payload))
    status = {s.investigation_id: s.state for s in live.status()}
    return {"session_id": session_id, "investigation_id": investigation_id,
            "state": status.get(investigation_id)}


@cascade_router.get("/sessions/{session_id}/stream")
async def session_stream(session_id: str) -> StreamingResponse:
    """Server-sent events: the multiplexed per-research step stream. Live
    sessions stream their full event queue; a reconnect after the session is
    gone replays the durable lifecycle state and closes. At-least-once —
    clients dedup on (investigation_id, seq)."""
    live = _SESSIONS.get(session_id)

    async def _live() -> Any:
        # Poll-drain rather than consume ``session.stream()`` directly: the
        # drain + ``asyncio.sleep`` give the in-process research tasks loop
        # time (so the fan-out progresses while the client watches) and the
        # ``is_complete`` check guarantees the stream terminates — it never
        # hangs waiting on a queue sentinel.
        idle_after_complete = 0
        while True:
            for ev in live.drain_nowait():
                yield _sse({
                    "investigation_id": ev.investigation_id, "seq": ev.seq, "kind": ev.kind,
                    "text": ev.text, "cost_usd": ev.cost_usd, "tokens": ev.tokens,
                    "state": ev.state.value if ev.state else None, "data": ev.data,
                })
            if live.is_complete():
                # Drain one more cycle to flush any final events, then close.
                idle_after_complete += 1
                if idle_after_complete >= 2:
                    break
            await asyncio.sleep(0.02)
        for ev in live.drain_nowait():
            yield _sse({
                "investigation_id": ev.investigation_id, "seq": ev.seq, "kind": ev.kind,
                "text": ev.text, "cost_usd": ev.cost_usd, "tokens": ev.tokens,
                "state": ev.state.value if ev.state else None, "data": ev.data,
            })
        yield _sse({"kind": "session_done"})

    async def _recovered() -> Any:
        rec = reconstruct_session(session_id)
        for r in rec.researches:
            yield _sse({"investigation_id": r.investigation_id, "kind": "status",
                        "text": r.sub_question, "state": r.state})
        yield _sse({"kind": "session_done", "recovered": True})

    gen = _live() if live is not None else _recovered()
    return StreamingResponse(gen, media_type="text/event-stream")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, default=str)}\n\n"
