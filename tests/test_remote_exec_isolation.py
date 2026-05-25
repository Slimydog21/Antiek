"""SPR-02 M4 — single-writer isolation across remote researches.

The invariant DRW SPR-02 holds host-local, now proven across off-host
execution with a FAKE provider:

  * each remote leaf appends only to its own per-investigation JSONL — 20
    concurrent leaves → 20 independent, uncorrupted logs, zero interleaving;
  * no remote-exec path opens a graph write connection — the *only*
    ``connect_write`` caller in ``runtime/remote_exec/`` is ``funnel.py``
    (greppable + tested);
  * the promotion funnel is single-threaded through ``db_lock`` — 20
    near-simultaneous completions produce zero ``WriteLockTimeout`` and no
    double-write.

Rigor #5: the single-writer proof is mechanical — one ``grep`` for
``connect_write`` over the package returns exactly ``funnel.py``.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import pathlib
import tempfile

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from runtime.db_lock import connect_read
from runtime.remote_exec import RemotePromotionFunnel, RemoteResearchRunner
from runtime.research_runner import BudgetCap, ResearchPlan, RunState
from substrate.event_log import trajectory
from substrate.graph.schema import init_database_at_path
from tests.remote_exec_fakes import FakeProvider


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
    monkeypatch.setenv("ANTIEK_EVENTS_DIR", ev)
    return ev


def _plan(i: int) -> ResearchPlan:
    return ResearchPlan(investigation_id=f"inv-{i}", sub_question=f"q{i}?",
                        budget=BudgetCap(cost_usd=1.0, max_steps=50))


REMOTE_EXEC_DIR = pathlib.Path(__file__).resolve().parents[1] / "runtime" / "remote_exec"


def test_connect_write_only_in_funnel():
    """The mechanical single-writer proof. Search the package source for any
    *use* of ``connect_write`` (an import binding or a call) — the only file
    that uses the graph writer is ``funnel.py``. Prose mentions of the symbol
    in other modules' docstrings (which document the invariant) are not uses
    and are excluded; the test keys on ``import`` and ``connect_write(`` so a
    reviewer can verify "remote research never writes the graph" mechanically.

    Equivalent one-liner a reviewer can run:

        grep -rnE 'import connect_write|connect_write\\(' runtime/remote_exec/

    which returns only ``funnel.py``.
    """
    import re as _re

    use_pattern = _re.compile(r"import connect_write|connect_write\s*\(")
    offenders = []
    for py in REMOTE_EXEC_DIR.glob("*.py"):
        if py.name == "funnel.py":
            continue
        if use_pattern.search(py.read_text()):
            offenders.append(py.name)
    assert offenders == [], (
        f"connect_write used outside funnel.py: {offenders}. Remote research "
        f"must never write the graph directly — only the host funnel does."
    )
    # And funnel.py DOES bind it (the single writer is real, not absent).
    funnel_src = (REMOTE_EXEC_DIR / "funnel.py").read_text()
    assert "import connect_write" in funnel_src


async def test_twenty_concurrent_leaves_isolated_logs(events_dir):
    prov = FakeProvider(steps=3)
    r = RemoteResearchRunner(prov, max_concurrency=20, events_dir=events_dir,
                             seal_on_complete=False)
    handles = [await r.start(f"inv-{i}", _plan(i)) for i in range(20)]
    # drain every stream concurrently
    async def _drain(h):
        return [ev async for ev in r.stream(h)]
    results = await asyncio.gather(*(_drain(h) for h in handles))
    await r.join()

    # 20 sandboxes provisioned + 20 torn down — no leak across the fan-out
    assert sorted(prov.provisioned) == sorted(f"inv-{i}" for i in range(20))
    assert sorted(prov.torn_down) == sorted(f"inv-{i}" for i in range(20))

    # 20 isolated, uncorrupted JSONL trajectories
    files = sorted(f for f in os.listdir(events_dir) if f.endswith(".jsonl"))
    assert len(files) == 20
    for i in range(20):
        rows = trajectory(f"inv-{i}", events_dir=events_dir)
        assert rows, f"inv-{i} empty trajectory"
        # every row belongs to this investigation — no cross-file interleaving
        assert all(row["investigation_id"] == f"inv-{i}" for row in rows)
    # every leaf reached DONE
    for res in results:
        assert res[-1].state == RunState.DONE


async def test_promotion_funnel_serialized_no_lock_timeout(events_dir):
    db = os.path.join(tempfile.mkdtemp(), "graph.duckdb")
    init_database_at_path(db)
    funnel = RemotePromotionFunnel(db_path=db)
    await funnel.start()

    r = RemoteResearchRunner(
        FakeProvider(steps=2), max_concurrency=20, events_dir=events_dir,
        seal_on_complete=False, on_emit=funnel.submit,
    )
    handles = [await r.start(f"inv-{i}", _plan(i)) for i in range(20)]

    async def _drain(h):
        return [ev async for ev in r.stream(h)]
    await asyncio.gather(*(_drain(h) for h in handles))
    await r.join()
    await funnel.drain_and_stop()

    # one note + one question per leaf, all promoted through the single funnel
    assert funnel.errors == []
    assert funnel.promoted_insights == 20
    assert funnel.promoted_questions == 20
    con = connect_read(db)
    try:
        n_insight = con.execute(
            "SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0]
        n_question = con.execute(
            "SELECT count(*) FROM nodes WHERE node_type='question'").fetchone()[0]
        assert n_insight == 20
        assert n_question == 20
        # no double-write: exactly 40 distinct node ids promoted
        assert len(set(funnel.promoted_node_ids)) == 40
    finally:
        con.close()


async def test_no_double_write_under_concurrent_submit(events_dir):
    # Submit the same fan-out's events from 20 leaves; assert each promoted
    # node id is unique (the serialized worker means no two promotions race
    # the same write).
    db = os.path.join(tempfile.mkdtemp(), "graph.duckdb")
    init_database_at_path(db)
    funnel = RemotePromotionFunnel(db_path=db)
    await funnel.start()
    r = RemoteResearchRunner(
        FakeProvider(steps=1), max_concurrency=20, events_dir=events_dir,
        seal_on_complete=False, on_emit=funnel.submit,
    )
    handles = [await r.start(f"inv-{i}", _plan(i)) for i in range(20)]

    async def _drain(h):
        return [ev async for ev in r.stream(h)]
    await asyncio.gather(*(_drain(h) for h in handles))
    await r.join()
    await funnel.drain_and_stop()

    assert len(funnel.promoted_node_ids) == len(set(funnel.promoted_node_ids))
    assert funnel.errors == []
