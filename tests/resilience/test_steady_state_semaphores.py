"""nygard SPR-07 M3 — semaphore steady-state (the Phase-A loky regression).

HONEST SCOPE (per the SPR-07 M3 acceptance clause "if the leak can only be
reproduced with real parallelism, state that limitation honestly and cover what
you can"):

The Phase-A failure (tests/regression/agent_failures/loky-semaphore-parameter-
extractor.yaml) was a leaked loky/multiprocessing OS semaphore on an external-
kill of the parameter-extractor worker pool. That leak class is ARCHITECTURALLY
ELIMINATED, not merely reaped: the research runner was migrated to an in-process
``asyncio.Semaphore`` (runtime/research_runner/host_local.py lines 4-10 + 287,
``async with self._semaphore``). loky is not even installed, and no code under
runtime/ or roles/parameter_extractor/ creates an OS semaphore anymore.

So this covers two things faithfully:
  1. The OS-semaphore count (the ORIGINAL leak metric) stays at its baseline
     across the fault loops — nothing creates or leaks an OS semaphore.
  2. The MODERN teardown guarantee that replaced the loky pool: the exact
     ``async with asyncio.Semaphore`` pattern host_local uses releases its permit
     on EVERY exit path, including an exception ("external-kill analogue"), so a
     repeated fault never leaks a permit and never wedges the bound. A leaked
     permit is the modern equivalent of the wedged loky pool.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.resilience.resource_probe import (
    active_semaphore_count,
    asyncio_semaphore_permits,
)


def test_os_semaphore_count_stays_at_baseline_under_faults(tmp_path, monkeypatch):
    """No OS semaphore is created or leaked by the resilience harness / retriever
    seam — the loky leak class is gone (asyncio runner)."""
    import tempfile

    import duckdb

    import substrate.graph.retrieval_substrate as rs
    from substrate.errors import RetrieverInfraError
    from tools.faultinject import readonly_fs

    baseline = active_semaphore_count()

    db = tmp_path / "graph.duckdb"
    duckdb.connect(str(db)).close()
    scratch = tmp_path / "s"
    scratch.mkdir()
    copy_target = scratch / "vss_index.duckdb"
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: str(scratch))

    class _StubModel:
        dimension = 8

        def encode(self, xs):  # pragma: no cover
            return [[0.0] * 8 for _ in xs]

    for _ in range(20):
        with readonly_fs(copy_target), pytest.raises(RetrieverInfraError):
            rs.DuckDbVssSubstrate.open(str(db), model=_StubModel())

    assert active_semaphore_count() == baseline


def test_asyncio_semaphore_releases_permit_on_repeated_fault():
    """The modern loky-leak fix: `async with asyncio.Semaphore` (the exact
    host_local.py:287 pattern) releases the permit on every exit including an
    exception, so N faulting tasks leave the bound at full capacity."""

    async def _run() -> None:
        max_concurrency = 3
        sem = asyncio.Semaphore(max_concurrency)
        assert asyncio_semaphore_permits(sem) == max_concurrency

        class _ExternalKill(RuntimeError):
            pass

        for _ in range(50):  # N>=20 abnormal teardowns
            with pytest.raises(_ExternalKill):
                async with sem:  # bounded concurrency — the host_local pattern
                    assert asyncio_semaphore_permits(sem) == max_concurrency - 1
                    raise _ExternalKill("abnormal teardown analogue")
            # Permit released on the exception path — no leak, bound not wedged.
            assert asyncio_semaphore_permits(sem) == max_concurrency

    asyncio.run(_run())


def test_host_local_runner_uses_asyncio_semaphore_not_a_process_pool():
    """Guard the architectural decision that eliminates the loky leak: the runner
    binds concurrency with asyncio.Semaphore, not loky/multiprocessing."""
    from runtime.research_runner import host_local

    src = host_local.__file__
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    assert "asyncio.Semaphore(" in text
    assert "async with self._semaphore" in text
    # No process-pool / loky resurrection sneaking back in (the leak came from a
    # process pool killed out-of-band; asyncio has no external process to kill).
    assert "import loky" not in text
    assert "get_reusable_executor" not in text
    assert "ProcessPoolExecutor" not in text
    assert "multiprocessing.Pool" not in text
