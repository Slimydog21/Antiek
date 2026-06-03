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
  (join + funnel-drain + merge) as a background task on that loop.
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
SPR-02 demo loop; the real Exa→Browserbase loop drops into the same seam with
zero route changes (mirrors the contract-first design that let DRW's gap
detector drop into Speak). §16 honored: no Daytona; the host-local cap is what
bounds "launch 20 at once", surfaced via the aggregate budget.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager, suppress
from typing import Any, cast

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from orchestration.cascade_session import CascadeSession, Leaf, reconstruct_session
from processing.embedding import EmbeddingProvider
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
from runtime.db_lock import LockedConnection, connect_write
from runtime.research_runner import (
    BudgetCap,
    BudgetManager,
    Command,
    CommandKind,
    HostLocalRunner,
    LoopContext,
    PromotionFunnel,
    StepEvent,
)
from runtime.research_runner.browse_loop import make_reuse_consuming_loop
from substrate.graph import default_db_path, ensure_initialized

cascade_router = APIRouter(prefix="/research", tags=["deep-research"])


# ---------------------------------------------------------------------------
# Process-local live-session registry (single-writer / one event loop).
# ---------------------------------------------------------------------------

_SESSIONS: dict[str, CascadeSession] = {}
_SESSION_TASKS: dict[str, asyncio.Task[None]] = {}


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def _db() -> str:
    path = default_db_path()
    ensure_initialized(path)
    return path


@contextmanager
def _write(purpose: str) -> Iterator[LockedConnection]:
    with connect_write(_db(), purpose=purpose) as con:
        yield con


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


def build_prod_retrieval_substrate() -> object | None:
    """ACV SPR-02 — the flywheel's READ side, wired into the prod launch path.

    Open the PRODUCTION ``RetrievalSubstrate`` so a launched research retrieves
    + reuses prior knowledge units (``host_local.py`` ``_maybe_reuse_prior_knowledge``
    fires only when this is non-None; with ``None`` the reuse hook early-returns
    at ``host_local.py:259`` and no ``knowledge.reused`` event is ever emitted —
    which is exactly why the flywheel shipped dead in prod).

    Two binding choices, both load-bearing:

    * **Embedding model — ``default_embedding_provider()``** (resolves to
      ``SentenceTransformerEmbedding("all-MiniLM-L6-v2")`` when sentence-transformers
      is installed, the prod posture). This MUST match the model the graph's
      knowledge units were embedded with at ingestion: cosine similarity across
      two different embedding spaces is meaningless, so a mismatched model would
      silently zero out every reuse score. We deliberately do NOT use the
      benchmark harness's ``HashEmbedding`` / ``make_substrate("brute_force")``
      test path (``compounding/benchmark/harness.py``): that would green a probe
      on the wrong code path. NOTE (honest): in an environment WITHOUT
      sentence-transformers installed, ``default_embedding_provider()`` itself
      falls back to ``HashEmbedding`` (reuse is then functional but not semantic);
      the wire is identical, only the resolved provider differs by env.

    * **Read-only over a SNAPSHOT COPY (§16 single-writer).** No substrate is a
      writer of the live graph; the serialized host funnel through ``db_lock``
      remains the sole graph writer. We open the substrate against a read-only
      SNAPSHOT COPY of the graph file, not the live file directly, for one hard
      DuckDB reason (verified SPR-02): DuckDB refuses to hold a read-only AND a
      read-write connection to the SAME file in the SAME process at the same time
      ("Can't open a connection to same database file with a different
      configuration than existing connections" — in BOTH orderings). The launch
      path opens read-write connections to the live graph (``ensure_initialized``
      at ``_db()``, the promotion funnel, the cascade merge), so a substrate that
      held a long-lived ``connect_read`` on the live file would collide with them
      and crash the launch. Reading a point-in-time COPY sidesteps the in-process
      conflict entirely and is strictly §16-safe (the copy is a throwaway temp
      file; the live file is never opened by this connection and never written).
      This mirrors what ``DuckDbVssSubstrate``'s own VSS-index path already does
      internally (it materialises its HNSW index on a temp copy precisely so it
      never writes the operator's graph). FRESHNESS (honest): reuse therefore sees
      the graph as of launch time, which is correct — reuse is read-only priming
      of a research that is about to start, not a live subscription.
      DOUBLE-COPY DE-DUP (ACV SPR-03 — landed): we pass
      ``skip_internal_copy=True`` to ``make_substrate("vss", ...)`` because we
      already own ``snapshot_path`` as a throwaway isolated copy. The substrate
      therefore indexes our snapshot IN PLACE instead of making a SECOND internal
      copy — one fewer full-DB (≈86 MB in prod) write per launch. The vss path's
      read-write connection pins the snapshot's inode on POSIX, so STEP 1's eager
      unlink still frees the dir entry immediately and DISK RECLAMATION for the
      in-place index is the substrate-CLOSE half (``close_prod_retrieval_substrate``
      on session teardown), below — the same close-half as before, now over one
      copy rather than two.

    DISK CLEANUP (ACV SPR-02 round-2 — the leak this sprint must not introduce):
    the factory's own snapshot dir is reclaimed in TWO complementary steps so a
    single Hetzner VM does not accumulate full-DB-copy temp dirs per launch:

    1. **The factory's snapshot file is unlinked the instant ``open`` returns.**
       This is provably safe on Linux/POSIX (VERIFIED on this platform). Under
       ACV SPR-03's ``skip_internal_copy=True`` BOTH the vss-active and the
       fallback paths now hold their connection on OUR snapshot directly (the
       internal second copy is gone), so the inode-pinning argument is the same
       for both:
         * vss-active path — ``DuckDbVssSubstrate.open(skip_internal_copy=True)``
           ``duckdb.connect``s OUR snapshot read-WRITE and builds + commits the
           HNSW index INTO it before returning. By the time open() returns the
           build is complete; unlinking the snapshot then removes the directory
           entry while the open connection pins the inode (POSIX), so disk is
           reclaimed when that connection closes (the close-half below). No
           second copy is made or held.
         * fallback path (vss absent) — the substrate holds ``connect_read`` on
           OUR snapshot; unlinking removes the directory entry while the open
           connection pins the inode (POSIX), so disk is reclaimed when that
           connection closes (the close-half below). VERIFIED: a DuckDB
           connection keeps serving rows after its backing file is unlinked.
       The unlink (and the empty-dir rmdir) are best-effort: a failure is logged
       and swallowed — cleanup failing must NEVER turn a working substrate into a
       failed launch.
    2. **The substrate connection is CLOSED on session completion** (see
       ``close_prod_retrieval_substrate`` + ``_run_to_completion``), which
       releases the pinned snapshot inode (now the SAME single copy on both the
       vss-active and fallback paths).

    GRACEFUL DEGRADATION (binding): returns ``None`` on ANY failure (DB missing,
    model unavailable, VSS load fails, snapshot copy fails, AND if cleanup
    registration fails) and NEVER raises — research must continue reuse-less
    rather than fail. The failure reason is LOGGED so an operator can distinguish
    "reuse disabled" (this returned None) from "reuse ran, found nothing"
    (substrate opened, graph empty → empty ``knowledge.reused`` event).
    ``host_local.py``'s ``if self._retrieval_substrate is None: return`` already
    no-ops on None — we rely on it.
    """
    import logging
    import os
    import shutil
    import tempfile

    log = logging.getLogger("antiek.cascade_routes")
    try:
        from substrate.graph import default_db_path
        from substrate.graph.retrieval_substrate import make_substrate

        live_path = default_db_path()
        if not os.path.exists(live_path):
            log.warning(
                "reuse disabled: graph DB %r does not exist; research will run "
                "without prior-knowledge reuse (no knowledge.reused event)",
                live_path,
            )
            return None

        # Point-in-time snapshot on a SEPARATE file so the substrate's connection
        # — read-WRITE on the snapshot under in-place vss indexing
        # (skip_internal_copy=True) — never collides in-process with the launch
        # path's read-write connections to the LIVE file (DuckDB refuses RO+RW to
        # the same file in one process). §16 is preserved: the live graph is only
        # read-copied, never opened by this connection. The snapshot's disk is
        # reclaimed by the two-step cleanup documented above (early-unlink here +
        # close-on-teardown), so launches do not accumulate full-DB-copy temp
        # dirs on the single prod VM.
        scratch = tempfile.mkdtemp(prefix="antiek-reuse-snapshot-")
        snapshot_path = os.path.join(scratch, "reuse_snapshot.duckdb")
        shutil.copy(live_path, snapshot_path)

        model = _embedding_provider()
        # Route through the one-factory seam the module docstring advertises
        # (retrieval_substrate.py:493) — make_substrate("vss", ...) dispatches to
        # the same DuckDbVssSubstrate.open.
        #
        # ACV SPR-03 double-copy de-dup: ``skip_internal_copy=True``. We already
        # own ``snapshot_path`` as a private, throwaway, isolated copy (mkdtemp'd
        # just above, unlinked just below), so the substrate need NOT make a
        # SECOND internal copy — it indexes our snapshot in place. This drops the
        # redundant ≈86 MB second write per launch on the single prod VM.
        # OWNERSHIP (the contract the flag documents): WE own snapshot_path's
        # lifecycle — we created it and we delete it (STEP 1 below); the substrate
        # never unlinks it. The eager unlink stays safe because the substrate's
        # read-write connection pins the snapshot's inode on POSIX (same inode-
        # pinning the vss-absent fallback already relies on), so the disk is
        # reclaimed when the connection closes (STEP 2, close-on-teardown).
        substrate = make_substrate(
            "vss", snapshot_path, model=model, skip_internal_copy=True,
        )

        # STEP 1 of disk cleanup — reclaim the WHOLE factory snapshot DIRECTORY
        # now (safe on this platform per the open() reasoning above; under
        # skip_internal_copy=True the substrate's read-write connection pins the
        # snapshot's inode on POSIX, so removing the dir entries frees them and
        # the disk is reclaimed on close()). We rmtree the entire ``scratch`` dir,
        # not just unlink the .duckdb file, because the IN-PLACE index build (the
        # SPR-03 de-dup) writes DuckDB SIDECARS into our dir — a ``.wal`` and a
        # ``.write.lock`` next to the snapshot. The old "unlink the file then
        # rmdir" left those sidecars behind, so the rmdir failed ("Directory not
        # empty") and the empty-ish dir accumulated per launch. rmtree removes the
        # snapshot + its sidecars + the dir in one step; VERIFIED on POSIX that a
        # subsequent query on the still-open connection serves rows after the dir
        # is rmtree'd (the inode is pinned). We keep the explicit ``os.unlink`` of
        # the snapshot file FIRST so the graceful-degradation contract is exercised
        # at the same call shape (test_factory_returns_substrate_even_if_eager_
        # unlink_fails). Best-effort: any failure here is logged, not raised, so
        # cleanup never breaks a working substrate.
        try:
            os.unlink(snapshot_path)
        except OSError as cleanup_exc:
            log.warning(
                "could not eagerly unlink reuse-snapshot %r (%s); it will be "
                "reclaimed when the substrate connection closes / on restart",
                snapshot_path, cleanup_exc,
            )
        # Remove the dir + any DuckDB sidecars (.wal / .write.lock) the in-place
        # index left. ignore_errors so a partially-removed dir never fails launch.
        shutil.rmtree(scratch, ignore_errors=True)
        return substrate
    except Exception as exc:  # noqa: BLE001 — reuse must never break a launch
        log.warning(
            "reuse disabled: could not open prod retrieval substrate "
            "(%s: %s); research will run without prior-knowledge reuse and "
            "no knowledge.reused event will fire for this launch",
            type(exc).__name__, exc,
        )
        return None


def close_prod_retrieval_substrate(substrate: object | None) -> None:
    """ACV SPR-02 round-2 — STEP 2 of the per-launch disk cleanup: close the
    substrate connection on session completion so its held disk is reclaimed.

    Reclaims the COPY the substrate's connection holds open for its lifetime —
    the vss-internal index copy (vss-active) or the pinned-inode reuse snapshot
    (fallback). Without this, each launch's substrate connection lives forever in
    ``_SESSIONS`` and its backing temp DB is never freed → unbounded disk growth
    on the single prod VM.

    Uses the substrate's OWN ``close()`` when present (``DuckDbVssSubstrate`` /
    ``BruteForceSubstrate`` already expose one — we only CALL it; we do not add a
    close hook to ``retrieval_substrate.py``, which SPR-03 owns). A closed DuckDB
    connection holds no file/disk, so once ``close()`` returns the per-launch temp
    copy is reclaimed even though the (now-dead) substrate object stays referenced
    by its still-live session. If a substrate ever lacked ``close()``, the
    fallback is GC: VERIFIED on this platform that a GC'd DuckDB connection
    releases its file. Best-effort and total: never raises (a teardown that raised
    could wedge the completion task), so graceful degradation is preserved through
    cleanup too."""
    if substrate is None:
        return
    closer = getattr(substrate, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:  # noqa: BLE001 — teardown must never raise
            import logging
            logging.getLogger("antiek.cascade_routes").warning(
                "retrieval substrate close() raised during teardown; disk will "
                "be reclaimed when its connection is GC'd / on restart",
                exc_info=True,
            )
    # If there is no close(), the caller dropping the session ref is sufficient:
    # DuckDB closes the connection (and frees the file) on GC.


def _session_substrate(session: CascadeSession) -> object | None:
    """The retrieval substrate this session's runner holds, if any. Reaches it
    through the documented runner field so teardown can close it. Returns None
    when the runner is reuse-less (the substrate was None) or the field is
    absent — never raises."""
    runner = getattr(session, "_runner", None)
    return getattr(runner, "_retrieval_substrate", None)


def _decompose(problem: str, max_depth: int) -> PlanReport:
    """The decomposer the plan endpoint uses when the caller does not supply
    sub-questions. A module attribute so tests can monkeypatch it to a
    deterministic fake without a live model."""
    return build_plan(problem, decomposer=DispatchDecomposer(), max_depth=max_depth)


def _research_loop_factory() -> Callable[[LoopContext], AsyncIterator[StepEvent]]:
    """The browse loop each investigation runs.

    ACV SPR-06: the prod loop is now the reuse-CONSUMING loop
    (``make_reuse_consuming_loop``). It reads ``ctx.pack`` — the prior knowledge
    units the runner's ``start`` injected (wired by SPR-02's
    ``build_prod_retrieval_substrate``) — and SHORT-CIRCUITS any planned
    sub-question a reused unit already covers, emitting a real ``dispatch.call``
    cost ONLY for the UNCOVERED ones. So a warm research (one whose question the
    graph already has knowledge for) does LESS work — and costs less — than a
    cold one, which is the compounding the reachability ``compounding`` probe
    asserts end-to-end. With an EMPTY/cold pack it does full work (n
    dispatch.calls × cost_per_step), so a cold cascade launch's per-research cost
    is unchanged from the demo loop's (n=3 × 0.01 = 0.03). ``events_dir=None``
    lets it fall back to the SAME process-default event log the runner writes to,
    so its dispatch.call lands where the measurement reads. The real
    Exa→Browserbase loop drops in here later with no route change; the demo loop
    stays the deterministic loop for unit CI (``make_demo_loop``)."""
    return cast(
        Callable[[LoopContext], AsyncIterator[StepEvent]],
        make_reuse_consuming_loop(steps=3, cost_per_step=0.01, emit_note=True),
    )


def _command(kind: str, payload: dict[str, Any] | None) -> Command:
    try:
        return Command(kind=CommandKind(kind), payload=payload or {})
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"unknown steer command {kind!r}",
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
    if req.sub_questions:
        manual = req.sub_questions

        class _Fixed:
            def decompose(self, q: str, *, context: str = "") -> list[SubQuestion]:
                return [SubQuestion(question=s) for s in manual]

        report = build_plan(req.problem, decomposer=_Fixed(), max_depth=req.max_depth)
    else:
        try:
            report = _decompose(req.problem, req.max_depth)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"decompose_failed: {type(exc).__name__}: {exc}",
            ) from exc
    tree = report.tree
    with _write("create_plan") as con:
        root_id = persist_tree(tree, investigation_id="__operator__",
                               embedding_provider=_embedding_provider(), con=con)
    return {"root_node_id": root_id, "tree": tree.to_dict(),
            "capped_nodes": report.capped_nodes,
            "over_broad_leaves": report.over_broad_leaves}


@cascade_router.get("/plans/{root_id}")
async def get_plan(root_id: str) -> dict[str, Any]:
    tree = load_tree(root_id, db_path=_db())
    if tree is None:
        raise HTTPException(status_code=404, detail=f"no plan {root_id!r}")
    return {"root_node_id": root_id, "tree": tree.to_dict(),
            "launchable": is_plan_launchable(root_id, db_path=_db())}


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
async def approve(root_id: str, req: ApproveRequest) -> dict[str, Any]:
    with _write("approve_plan") as con:
        approval = approve_plan(root_id, approver=req.approver,
                                investigation_id="__operator__", con=con)
    return {"root_node_id": root_id, "approval": approval,
            "launchable": is_plan_launchable(root_id, db_path=_db())}


# ---------------------------------------------------------------------------
# Launch + session endpoints (SPR-06)
# ---------------------------------------------------------------------------


@cascade_router.post("/plans/{root_id}/launch")
async def launch(root_id: str, req: LaunchRequest) -> dict[str, Any]:
    """Launch an approved plan as N parallel researches. Refuses an
    unapproved plan (SPR-05 gate). Returns the session id + the researches."""
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
    # ACV SPR-02 — wire the flywheel's READ side. Without this kwarg the runner's
    # reuse hook (host_local.py:259) early-returns on None and NO knowledge.reused
    # event fires — the dead-flywheel defect. The factory uses
    # default_embedding_provider() (all-MiniLM-L6-v2 in prod) because the graph's
    # knowledge units were embedded with that model at ingestion and cosine across
    # a different model is meaningless; it opens READ-ONLY (§16 single-writer — the
    # host funnel through db_lock stays the sole graph writer). The factory returns
    # None (never raises) if the substrate can't open, so a dead substrate degrades
    # to a reuse-less research, never a broken launch.
    runner = HostLocalRunner(_research_loop_factory(), budget=budget,
                             on_emit=funnel.submit, seal_on_complete=False,
                             retrieval_substrate=build_prod_retrieval_substrate())
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
    try:
        with suppress(Exception):  # best-effort: a merge failure is non-fatal
            await session.join_and_merge()
    finally:
        # ACV SPR-02 round-2 — on completion, CLOSE the retrieval substrate. This
        # is the disk-reclamation half of the leak fix: closing the substrate's
        # DuckDB connection frees the temp DB copy it held open for the runner's
        # lifetime (the vss-internal index copy, or the inode pinned by the
        # fallback's read-only connection). A CLOSED DuckDB connection holds no
        # disk, so leaving the now-dead substrate object referenced by the
        # still-live session is harmless — the ~86 MB-per-launch DISK is the
        # blocker, and it is reclaimed here. Best-effort: never raises.
        #
        # We deliberately do NOT evict the session from _SESSIONS/_SESSION_TASKS
        # on completion: the established contract (test_session_reconstructs_after
        # _eviction simulates a RESTART by popping _SESSIONS; the /cost + /steer
        # endpoints are live-only) is that a completed session stays
        # live-and-steerable until a restart/explicit drop — eviction is the
        # recovery path's trigger, not a completion side effect. The residual
        # in-memory _SESSIONS growth is tiny (small dead objects), pre-existing,
        # and not the disk blocker this sprint must fix.
        close_prod_retrieval_substrate(_session_substrate(session))


@cascade_router.get("/sessions/{session_id}")
async def session_status(session_id: str) -> dict[str, Any]:
    live = _SESSIONS.get(session_id)
    if live is not None:
        cost = live.aggregate_cost()
        return {
            "session_id": session_id, "live": True,
            "researches": [
                {"investigation_id": s.investigation_id, "sub_question": s.sub_question,
                 "state": s.state, "question_node_id": s.question_node_id}
                for s in live.status()
            ],
            "cost": cost,
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
    }


@cascade_router.get("/sessions/{session_id}/cost")
async def session_cost(session_id: str) -> dict[str, Any]:
    live = _SESSIONS.get(session_id)
    if live is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not live")
    return live.aggregate_cost()


@cascade_router.post("/sessions/{session_id}/researches/{investigation_id}/steer")
async def steer(session_id: str, investigation_id: str, req: SteerRequest) -> dict[str, Any]:
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

    async def _live(sess: CascadeSession) -> AsyncIterator[str]:
        # Poll-drain rather than consume ``session.stream()`` directly: the
        # drain + ``asyncio.sleep`` give the in-process research tasks loop
        # time (so the fan-out progresses while the client watches) and the
        # ``is_complete`` check guarantees the stream terminates — it never
        # hangs waiting on a queue sentinel.
        idle_after_complete = 0
        while True:
            for ev in sess.drain_nowait():
                yield _sse({
                    "investigation_id": ev.investigation_id, "seq": ev.seq, "kind": ev.kind,
                    "text": ev.text, "cost_usd": ev.cost_usd, "tokens": ev.tokens,
                    "state": ev.state.value if ev.state else None, "data": ev.data,
                })
            if sess.is_complete():
                # Drain one more cycle to flush any final events, then close.
                idle_after_complete += 1
                if idle_after_complete >= 2:
                    break
            await asyncio.sleep(0.02)
        for ev in sess.drain_nowait():
            yield _sse({
                "investigation_id": ev.investigation_id, "seq": ev.seq, "kind": ev.kind,
                "text": ev.text, "cost_usd": ev.cost_usd, "tokens": ev.tokens,
                "state": ev.state.value if ev.state else None, "data": ev.data,
            })
        yield _sse({"kind": "session_done"})

    async def _recovered() -> AsyncIterator[str]:
        rec = reconstruct_session(session_id)
        for r in rec.researches:
            yield _sse({"investigation_id": r.investigation_id, "kind": "status",
                        "text": r.sub_question, "state": r.state})
        yield _sse({"kind": "session_done", "recovered": True})

    gen = _live(live) if live is not None else _recovered()
    return StreamingResponse(gen, media_type="text/event-stream")


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, default=str)}\n\n"
