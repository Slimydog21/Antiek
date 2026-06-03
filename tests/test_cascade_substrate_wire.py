"""ACV SPR-02 — the flywheel wire regression gate.

The compounding flywheel shipped DEAD in prod because the one user research
entrypoint (``interfaces/research/api/cascade_routes.py`` ``launch`` →
``HostLocalRunner(...)``) constructed the runner with ``retrieval_substrate``
left ``None``, so ``host_local.py``'s ``_maybe_reuse_prior_knowledge`` early-
returned and no ``knowledge.reused`` event ever fired. SPR-02 wired a real
production ``RetrievalSubstrate`` (``build_prod_retrieval_substrate``) into that
construction. These tests are the never-revert guard:

* ``test_launch_constructs_runner_with_non_none_substrate`` — drives the REAL
  launch route and asserts the ``HostLocalRunner`` it builds received a
  non-None ``retrieval_substrate``. This FAILS if the kwarg is removed from
  ``cascade_routes.py`` (the silent-revert this gate exists to catch).

* ``test_factory_returns_none_not_raises_on_unopenable_substrate`` — proves the
  factory's graceful-degradation contract (M2): on ANY failure opening the
  substrate it returns ``None`` (never raises), so a dead substrate degrades to
  a reuse-less research rather than a broken launch.

Mirrors the lightweight ``test_cascade_create_plan_light`` discipline: mount
only ``cascade_router`` + stub the seams, no multi-thousand-line ``create_app``.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import interfaces.research.api.cascade_routes as cr
from interfaces.research.api.cascade_routes import cascade_router


class _StubEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        return [0.1] * self.dimension


@pytest.fixture
def cascade_client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="cascade-substrate-wire-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
    app = FastAPI()
    app.include_router(cascade_router)
    yield TestClient(app)


def _approved_plan(client) -> str:
    """Create + approve a one-leaf plan with an explicit sub-question (no live
    decomposer) and return its root id, ready to launch."""
    r = client.post(
        "/research/plans",
        json={
            "problem": "substrate-wire regression",
            "sub_questions": ["a single minimal sub-question for the wire test"],
            "max_depth": 1,
        },
    )
    assert r.status_code == 200, r.text
    root_id = r.json()["root_node_id"]
    r = client.post(f"/research/plans/{root_id}/approve", json={"approver": "__test__"})
    assert r.status_code == 200, r.text
    return root_id


def test_launch_constructs_runner_with_non_none_substrate(cascade_client, monkeypatch):
    """The real launch path must build HostLocalRunner with a non-None
    retrieval_substrate. FAILS if the ``retrieval_substrate=`` kwarg is dropped
    from cascade_routes.py (silent revert of the flywheel wire)."""
    captured: dict[str, object] = {}

    real_runner_cls = cr.HostLocalRunner

    class _SpyRunner(real_runner_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            captured["retrieval_substrate"] = kwargs.get("retrieval_substrate", "<<MISSING>>")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(cr, "HostLocalRunner", _SpyRunner)

    # Make the factory return a sentinel so this test asserts the WIRE (the kwarg
    # is passed through), not the substrate's open() behaviour (covered by the
    # probe + the second test). A truthy sentinel is enough to prove non-None.
    sentinel = object()
    monkeypatch.setattr(cr, "build_prod_retrieval_substrate", lambda: sentinel)

    root_id = _approved_plan(cascade_client)
    r = cascade_client.post(
        f"/research/plans/{root_id}/launch",
        json={"per_research_budget_usd": 1.0, "aggregate_budget_usd": 5.0},
    )
    assert r.status_code == 200, r.text

    assert "retrieval_substrate" in captured, "HostLocalRunner was never constructed"
    assert captured["retrieval_substrate"] != "<<MISSING>>", (
        "launch built HostLocalRunner WITHOUT a retrieval_substrate kwarg — the "
        "flywheel wire reverted; host_local.py:259 would early-return and no "
        "knowledge.reused event would fire (the dead-flywheel defect)"
    )
    assert captured["retrieval_substrate"] is sentinel, (
        "the retrieval_substrate passed to HostLocalRunner was not the value the "
        "prod factory produced"
    )


def test_launch_wires_factory_output(cascade_client, monkeypatch):
    """Belt-and-braces: the kwarg is wired from build_prod_retrieval_substrate()
    specifically (not some other source), so renaming/bypassing the factory
    also trips this gate."""
    calls: list[int] = []
    sentinel = object()

    def _factory():
        calls.append(1)
        return sentinel

    captured: dict[str, object] = {}
    real_runner_cls = cr.HostLocalRunner

    class _SpyRunner(real_runner_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            captured["sub"] = kwargs.get("retrieval_substrate")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(cr, "HostLocalRunner", _SpyRunner)
    monkeypatch.setattr(cr, "build_prod_retrieval_substrate", _factory)

    root_id = _approved_plan(cascade_client)
    r = cascade_client.post(
        f"/research/plans/{root_id}/launch",
        json={"per_research_budget_usd": 1.0, "aggregate_budget_usd": 5.0},
    )
    assert r.status_code == 200, r.text
    assert calls == [1], "build_prod_retrieval_substrate() was not called exactly once per launch"
    assert captured["sub"] is sentinel


def test_factory_returns_none_not_raises_on_unopenable_substrate(monkeypatch):
    """M2 graceful-degradation: the factory returns None (never raises) when the
    substrate cannot open, so research continues reuse-less rather than failing.

    We force DuckDbVssSubstrate.open to raise; the factory must swallow it,
    log, and return None."""
    import substrate.graph.retrieval_substrate as rs

    # Point at a real (empty) graph so the existence check + snapshot copy
    # succeed and the failure is forced at the substrate-open step specifically.
    tmpdir = tempfile.mkdtemp(prefix="cascade-wire-factory-")
    db_path = os.path.join(tmpdir, "t.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    from substrate.graph import ensure_initialized

    ensure_initialized(db_path)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated: vss load failed / model unavailable")

    monkeypatch.setattr(rs.DuckDbVssSubstrate, "open", classmethod(lambda cls, *a, **k: _boom()))

    # Must NOT raise; must return None.
    result = cr.build_prod_retrieval_substrate()
    assert result is None, (
        "build_prod_retrieval_substrate must degrade to None on an unopenable "
        "substrate (reuse disabled), never propagate the exception into the launch"
    )


def test_factory_returns_none_when_db_missing(monkeypatch):
    """A missing graph DB is the most common "reuse disabled" condition (fresh
    box, never ingested). The factory must return None without touching the
    substrate at all."""
    tmpdir = tempfile.mkdtemp(prefix="cascade-wire-missing-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "does-not-exist.duckdb"))
    result = cr.build_prod_retrieval_substrate()
    assert result is None


# ---------------------------------------------------------------------------
# ACV SPR-02 round-2 — the BLOCKER regression: per-launch snapshot temp-file
# leak. Each ``build_prod_retrieval_substrate()`` mkdtemp's a snapshot dir and
# copies the (≈86 MB in prod) graph into it; on the single Hetzner VM, without
# cleanup these accumulate continuously until the disk fills. The fix reclaims
# each launch's snapshot disk in two steps (eager unlink of the factory snapshot
# at open() time + close on session teardown). These tests FAIL on round-1's
# leaky factory and PASS after the fix.
# ---------------------------------------------------------------------------


def _count_temp_dirs(base: str, prefix: str) -> int:
    return len([d for d in os.listdir(base) if d.startswith(prefix)])


@pytest.fixture
def isolated_tmpbase(monkeypatch, tmp_path):
    """Pin tempfile's base dir to an empty per-test directory so the snapshot/
    index temp-dir counts are isolated from the rest of the machine. Both the
    factory's ``antiek-reuse-snapshot-`` dir and the vss path's ``antiek-vss-``
    dir mkdtemp into this base, so we can count what each launch leaves behind."""
    import tempfile as _tf

    base = str(tmp_path / "tmpbase")
    os.makedirs(base, exist_ok=True)
    monkeypatch.setenv("TMPDIR", base)
    monkeypatch.setattr(_tf, "tempdir", None)  # bust gettempdir() cache
    yield base


def _init_small_graph(monkeypatch, where: str) -> str:
    """A real, initialized (empty) graph DB the factory will snapshot — so the
    snapshot copy actually happens and the leak is exercised, not short-circuited
    by the missing-DB early return."""
    db_path = os.path.join(where, "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    from substrate.graph import ensure_initialized

    ensure_initialized(db_path)
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    return db_path


def test_factory_snapshot_dirs_do_not_accumulate(monkeypatch, isolated_tmpbase, tmp_path):
    """BLOCKER no-leak gate: N≥3 real factory calls must NOT leave N snapshot
    temp dirs behind. The eager-unlink step reclaims each ``antiek-reuse-snapshot``
    dir the instant open() returns.

    Round-1 (leaky): mkdtemp'd a snapshot dir per call and NEVER removed it →
    this asserts 3 accumulated dirs would be present, so it FAILS at
    ``after == 0``. Round-2: the factory unlinks + rmdir's its snapshot →
    ``after == 0``."""
    _init_small_graph(monkeypatch, str(tmp_path))

    before = _count_temp_dirs(isolated_tmpbase, "antiek-reuse-snapshot-")
    subs = []
    for _ in range(3):
        subs.append(cr.build_prod_retrieval_substrate())

    # Every launch must have produced a working (non-None) substrate — the leak
    # fix must not have quietly degraded reuse to None.
    assert all(s is not None for s in subs), (
        "factory returned None on a launch against a real graph — the cleanup "
        "must reclaim disk WITHOUT breaking the substrate"
    )

    after = _count_temp_dirs(isolated_tmpbase, "antiek-reuse-snapshot-")
    assert after == before == 0, (
        f"factory snapshot dirs accumulated: before={before} after={after} "
        f"(round-1 leaked one full-DB-copy temp dir per launch — disk exhaustion "
        f"on the single prod VM). Each launch's snapshot must be reclaimed."
    )

    # Close-half: closing each substrate must also reclaim the vss-internal index
    # copies (the ``antiek-vss-`` dirs the substrate's connection held open). After
    # close, those connections release their backing temp DB.
    for s in subs:
        cr.close_prod_retrieval_substrate(s)


def test_session_teardown_closes_substrate_freeing_disk():
    """The teardown half of the disk-reclamation fix: on completion,
    _run_to_completion must CLOSE the runner's retrieval substrate so the temp DB
    copy its connection held open (the vss-internal index copy / the pinned-inode
    fallback snapshot) is freed. A closed DuckDB connection holds no disk.

    Round-1: _run_to_completion only awaited join_and_merge — the substrate
    connection was never closed and its full-DB-copy temp file leaked for the
    process lifetime, so this FAILS at the close assertion. Round-2: teardown
    closes it.

    Deliberately does NOT assert eviction: the established contract
    (test_session_reconstructs_after_eviction simulates a RESTART; /cost + /steer
    are live-only) keeps a completed session live-and-steerable until a
    restart/explicit drop. Closing the substrate's connection (not evicting the
    session object) is what reclaims the disk."""
    import asyncio

    closed = {"n": 0}

    class _Sub:
        def close(self) -> None:
            closed["n"] += 1

    class _Runner:
        def __init__(self) -> None:
            self._retrieval_substrate = _Sub()

    class _Session:
        session_id = "session-teardown-probe"

        def __init__(self) -> None:
            self._runner = _Runner()

        async def join_and_merge(self) -> dict:
            return {"linked_findings": 0}

    sess = _Session()
    asyncio.run(cr._run_to_completion(sess))  # type: ignore[arg-type]

    assert closed["n"] == 1, (
        "_run_to_completion did not close the retrieval substrate on completion — "
        "its DuckDB connection (holding a full-DB-copy temp file) leaks disk for "
        "the process lifetime"
    )


def test_teardown_never_raises_when_substrate_close_fails():
    """Graceful degradation through cleanup: if the substrate's close() raises,
    teardown must swallow it (a teardown that propagated could wedge the
    completion task / crash the background loop). The disk is then reclaimed on
    GC instead — never at the cost of an exception."""
    import asyncio

    class _BadSub:
        def close(self) -> None:
            raise RuntimeError("simulated: connection already invalidated")

    class _Runner:
        def __init__(self) -> None:
            self._retrieval_substrate = _BadSub()

    class _Session:
        session_id = "session-bad-close-probe"

        def __init__(self) -> None:
            self._runner = _Runner()

        async def join_and_merge(self) -> dict:
            return {}

    # Must not raise.
    asyncio.run(cr._run_to_completion(_Session()))  # type: ignore[arg-type]


def test_factory_returns_substrate_even_if_eager_unlink_fails(monkeypatch, tmp_path):
    """Graceful degradation: if the eager-unlink cleanup step fails (e.g. the
    snapshot is already gone or perms deny it), the factory must STILL return the
    working substrate — cleanup failure must never break a launch. The disk is
    then reclaimed by the close-on-teardown half instead."""
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    db_path = os.path.join(str(tmp_path), "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    from substrate.graph import ensure_initialized

    ensure_initialized(db_path)

    real_unlink = os.unlink

    def _boom_unlink(path, *a, **k):
        if "antiek-reuse-snapshot-" in str(path):
            raise OSError("simulated: cannot unlink snapshot")
        return real_unlink(path, *a, **k)

    monkeypatch.setattr(os, "unlink", _boom_unlink)

    sub = cr.build_prod_retrieval_substrate()
    assert sub is not None, (
        "factory returned None because the eager-unlink cleanup raised — cleanup "
        "failure must degrade to 'snapshot reclaimed later', never a dead substrate"
    )
    cr.close_prod_retrieval_substrate(sub)
