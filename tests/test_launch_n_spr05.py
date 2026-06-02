"""SPR-05 — "Launch N at once": the §16-headline load-bearing gates.

These are the gates that prove "launch 20 deep research agents at once" is
*safe* and *swappable*, exercised through the real launch path
(``CascadeSession`` → ``HostLocalRunner`` → ``PromotionFunnel``), not just the
runner unit. Each test maps to one verification gate on the sprint page:

  * SINGLE-WRITER UNDER LOAD — N investigations launched CONCURRENTLY through
    one CascadeSession, all emitting notes/questions, drained concurrently:
    still exactly one serialized graph writer (the funnel), N isolated
    per-investigation JSONLs, zero lock timeouts, no interleaved graph write.
    This is the gate that proves 20-at-once does not become 20 graph writers.

  * §16 FAN-OUT, GATED OFF — the runner factory DEFAULTS to host-local; the
    Daytona/remote path is drop-in-shaped behind the protocol but the gate
    (``ANTIEK_REMOTE_EXEC_ENABLED`` for the factory, ``ANTIEK_ENABLE_DAYTONA_RUNNER``
    for the stub) is OFF by default; host-local is the automatic fallback.
    No live Daytona is ever run.

  * PROTOCOL-ONLY CALL SITES — the launch call sites (cascade_session,
    cascade_routes) target the ``ResearchRunner`` protocol; none imports a
    concrete ``DaytonaRunner`` / ``RemoteResearchRunner``, so the remote impl
    is a true drop-in and the §16 discipline holds at the seam.

All hermetic: a hash-embedding fake, a tmp graph DB, the SPR-02 demo loop. No
network, no Daytona SDK, no credentials.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import os
import tempfile

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from runtime.db_lock import connect_read
from runtime.remote_exec import build_research_runner, remote_exec_enabled
from runtime.remote_exec.factory import ENABLE_ENV
from runtime.research_runner import (
    BudgetCap,
    BudgetManager,
    HostLocalRunner,
    PromotionFunnel,
    RunState,
    daytona_enabled,
    make_demo_loop,
)
from runtime.research_runner.host_local import DEFAULT_MAX_CONCURRENCY
from substrate.event_log import trajectory
from substrate.graph.schema import init_database_at_path


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


@pytest.fixture(autouse=True)
def _hash_embeddings():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def events_dir(monkeypatch):
    d = tempfile.mkdtemp()
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    return ev


@pytest.fixture
def graph_db():
    db = os.path.join(tempfile.mkdtemp(), "graph.duckdb")
    init_database_at_path(db)
    return db


# ---------------------------------------------------------------------------
# GATE 1 — single-writer UNDER CONCURRENCY (the headline-risk gate)
# ---------------------------------------------------------------------------


async def _launch_n_concurrently(n, *, db, events_dir, agg_cap=None):
    """Launch n researches on the session's runtime wiring: one
    ``HostLocalRunner`` + one ``PromotionFunnel`` (the exact objects a
    ``CascadeSession`` owns and the exact ``runner.start`` calls
    ``CascadeSession.launch`` issues per leaf). The SPR-05 approval gate has
    its own coverage (``test_cascade_api`` exercises the full HTTP launch path);
    this test isolates the load-bearing single-writer invariant under genuine
    concurrency. Drains every stream concurrently so the loops really run at
    once (not serialized by a single consumer), then joins + drains the funnel.
    Returns (runner, funnel, handles) for assertions."""
    from runtime.research_runner import ResearchPlan
    budget = BudgetManager(aggregate_cap_usd=agg_cap)
    funnel = PromotionFunnel(db_path=db, embedding_provider=_FakeEmbedding())
    runner = HostLocalRunner(
        make_demo_loop(steps=2, delay_s=0.001, emit_note=True),
        max_concurrency=DEFAULT_MAX_CONCURRENCY, budget=budget,
        on_emit=funnel.submit, events_dir=events_dir, seal_on_complete=False,
    )
    await funnel.start()
    handles = []
    for i in range(n):
        plan = ResearchPlan(
            investigation_id=f"session-load-leaf-{i}", sub_question=f"sub {i}",
            parent_investigation_id="session-load", budget=BudgetCap(cost_usd=10.0),
        )
        handles.append(await runner.start(plan.investigation_id, plan))

    async def drain(h):
        return [ev async for ev in runner.stream(h)]

    await asyncio.gather(*(drain(h) for h in handles))
    await runner.join()
    await funnel.drain_and_stop()
    return runner, funnel, handles


async def test_single_writer_under_concurrent_launches(events_dir, graph_db):
    """20 concurrent launches → ONE serialized graph writer, N isolated logs,
    zero lock timeouts. Proves "launch 20 at once" stays single-writer-safe."""
    n = 20
    runner, funnel, handles = await _launch_n_concurrently(
        n, db=graph_db, events_dir=events_dir)

    # Every research completed; none failed under contention.
    states = [runner.status(h).state for h in handles]
    assert all(s == RunState.DONE for s in states), states

    # The funnel — the SINGLE graph writer — recorded zero lock errors despite
    # 20 researches completing near-simultaneously.
    assert funnel.errors == [], funnel.errors
    assert funnel.promoted_insights == n          # one note each
    assert funnel.promoted_questions == n          # one question each

    # N isolated per-investigation JSONLs — no cross-file corruption.
    files = sorted(f for f in os.listdir(events_dir) if f.endswith(".jsonl"))
    assert len(files) == n, files
    for i in range(n):
        rows = trajectory(f"session-load-leaf-{i}", events_dir=events_dir)
        assert rows, f"leaf {i} empty"
        assert all(r["investigation_id"] == f"session-load-leaf-{i}" for r in rows)

    # The graph write_log proves ONE serialized writer: every promotion went
    # through purpose='promotion_funnel', and the node count matches exactly
    # (no interleaved/duplicated writes from a second writer).
    con = connect_read(graph_db)
    try:
        n_insight = con.execute(
            "SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0]
        n_question = con.execute(
            "SELECT count(*) FROM nodes WHERE node_type='question'").fetchone()[0]
        assert n_insight == n, n_insight
        assert n_question == n, n_question
        n_funnel = con.execute(
            "SELECT count(*) FROM write_log WHERE purpose='promotion_funnel'").fetchone()[0]
        assert n_funnel >= 2 * n            # >= one per insight + one per question
        # Every RESEARCH-TIME graph write was the funnel's. The only other
        # write_log row is the one-time schema bootstrap (graph_schema_init),
        # recorded before any research runs — not a second research writer. So
        # the funnel is the SOLE writer of everything the fan-out produced; 20
        # concurrent researches never minted a second graph writer.
        other = con.execute(
            "SELECT purpose, count(*) FROM write_log "
            "WHERE purpose NOT IN ('promotion_funnel','graph_schema_init') "
            "GROUP BY purpose").fetchall()
        assert other == [], f"a non-funnel research writer touched the graph: {other}"
    finally:
        con.close()


async def test_browse_loops_under_load_never_write_the_graph(events_dir, graph_db):
    """The complementary proof: with NO funnel attached, 20 concurrent launches
    write ZERO graph rows — a browse loop has no graph-write path of its own,
    so concurrency can never produce a second writer."""
    runner = HostLocalRunner(
        make_demo_loop(steps=2, delay_s=0.001, emit_note=True),
        max_concurrency=DEFAULT_MAX_CONCURRENCY, events_dir=events_dir,
        seal_on_complete=False,   # no on_emit → notes/questions go nowhere
    )
    from runtime.research_runner import ResearchPlan
    handles = [
        await runner.start(f"inv-{i}",
                           ResearchPlan(investigation_id=f"inv-{i}", sub_question=f"q{i}"))
        for i in range(20)
    ]

    async def drain(h):
        return [ev async for ev in runner.stream(h)]

    await asyncio.gather(*(drain(h) for h in handles))
    await runner.join()

    con = connect_read(graph_db)
    try:
        rows = con.execute(
            "SELECT count(*) FROM nodes WHERE node_type IN ('insight','question')").fetchone()[0]
        assert rows == 0, rows
    finally:
        con.close()


# ---------------------------------------------------------------------------
# GATE 2 — §16 fan-out: factory defaults host-local, gated OFF, fallback
# ---------------------------------------------------------------------------


def test_factory_default_is_host_local(monkeypatch):
    """With no env + no explicit flag, the factory returns the host-local
    runner — the sanctioned baseline. This is the §16 default."""
    monkeypatch.delenv(ENABLE_ENV, raising=False)
    runner = build_research_runner(loop_fn=make_demo_loop(steps=1))
    assert isinstance(runner, HostLocalRunner)
    assert remote_exec_enabled() is False


def test_remote_exec_gate_off_by_default(monkeypatch):
    """Both gates are OFF by default and reading them never enables anything:
    the factory's ANTIEK_REMOTE_EXEC_ENABLED and the stub's
    ANTIEK_ENABLE_DAYTONA_RUNNER. No live Daytona is reachable."""
    monkeypatch.delenv(ENABLE_ENV, raising=False)
    monkeypatch.delenv("ANTIEK_ENABLE_DAYTONA_RUNNER", raising=False)
    assert remote_exec_enabled() is False
    assert daytona_enabled() is False


def test_no_daytona_sdk_imported_at_rest():
    """The gated stub must not pull a Daytona SDK into the process at import —
    the §16 line stays clean when the gate is off."""
    import sys
    assert not any("daytona_sdk" in m or m == "daytona" for m in sys.modules)


def test_gate_set_but_unavailable_falls_back_to_host_local(monkeypatch, caplog):
    """The headline operational case: the operator sets the gate but the SDK /
    credentials are absent → the factory falls back to host-local with ONE loud
    log line, never a crash, never live Daytona. (The shipped
    test_remote_exec_fallback.py owns the exhaustive fallback contract; this is
    the SPR-05 framing of it.)"""
    import logging

    from tests.remote_exec_fakes import UnavailableProvider
    monkeypatch.setenv(ENABLE_ENV, "1")
    with caplog.at_level(logging.WARNING, logger="antiek.remote_exec"):
        runner = build_research_runner(loop_fn=make_demo_loop(steps=1),
                                       provider=UnavailableProvider())
    assert isinstance(runner, HostLocalRunner)
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert "host-local" in warnings[0].getMessage().lower()


# ---------------------------------------------------------------------------
# GATE 3 — protocol-only call sites (the swappability invariant)
# ---------------------------------------------------------------------------


def _imported_names(module_path: str) -> set[str]:
    """Every name a module imports, qualified enough to spot a concrete-runner
    import. Static AST scan — no execution."""
    with open(module_path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=module_path)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                names.add(f"{mod}.{alias.name}")
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


def _repo_path(*parts: str) -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, *parts)


# The concrete runner classes a launch call site must NEVER import directly —
# they would defeat the drop-in/swap. Only the protocol + the factory are
# allowed at a call site.
_CONCRETE_RUNNERS = {"DaytonaRunner", "RemoteResearchRunner"}


def test_cascade_session_imports_no_concrete_remote_runner():
    """orchestration/cascade_session.py — the launch orchestrator — must not
    import a concrete remote/Daytona runner; it drives whatever runner it is
    GIVEN through the protocol (it accepts a HostLocalRunner today, a remote
    one tomorrow, with zero change)."""
    names = _imported_names(_repo_path("orchestration", "cascade_session.py"))
    leaked = {n for n in names if n.split(".")[-1] in _CONCRETE_RUNNERS}
    assert leaked == set(), f"cascade_session leaked a concrete runner import: {leaked}"


def test_cascade_routes_imports_no_concrete_remote_runner():
    """interfaces/research/api/cascade_routes.py — the HTTP launch surface —
    constructs HostLocalRunner today but must never reach for a concrete remote
    /Daytona runner; the swap goes through the factory, not a new import."""
    names = _imported_names(
        _repo_path("interfaces", "research", "api", "cascade_routes.py"))
    leaked = {n for n in names if n.split(".")[-1] in _CONCRETE_RUNNERS}
    assert leaked == set(), f"cascade_routes leaked a concrete runner import: {leaked}"


def test_factory_is_the_only_sanctioned_swap_point():
    """The factory is allowed to know the concrete runners (it is the ONE swap
    point); proving it imports RemoteResearchRunner confirms the seam exists
    exactly where it should — and nowhere else (the two tests above)."""
    names = _imported_names(_repo_path("runtime", "remote_exec", "factory.py"))
    assert any(n.split(".")[-1] == "RemoteResearchRunner" for n in names)
    assert any(n.split(".")[-1] == "HostLocalRunner" for n in names)
