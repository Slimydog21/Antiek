"""nygard SPR-07 M2 — file-handle steady-state under repeated read-only-FS fault.

Loops SPR-01's readonly_fs injector over the REAL retriever write path
(DuckDbVssSubstrate.open's shutil.copy) N>=50 times. Each cycle the injected
EROFS surfaces as a typed RetrieverInfraError (SPR-02 invariant), and the fd
count must return to baseline — no monotonic growth. A file opened before the
write fault that is not closed on the exception path would show up here as a leak.
"""

from __future__ import annotations

import tempfile

import pytest

from tests.resilience.resource_probe import open_fd_count


def test_fd_steady_state_under_repeated_readonly_fs_fault(tmp_path, monkeypatch):
    import duckdb

    import substrate.graph.retrieval_substrate as rs
    from substrate.errors import RetrieverInfraError
    from tools.faultinject import readonly_fs

    db = tmp_path / "graph.duckdb"
    duckdb.connect(str(db)).close()
    scratch = tmp_path / "vss-scratch"
    scratch.mkdir()
    copy_target = scratch / "vss_index.duckdb"
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: str(scratch))

    class _StubModel:
        dimension = 8

        def encode(self, xs):  # pragma: no cover - copy fails first
            return [[0.0] * 8 for _ in xs]

    def drive_one_fault():
        with readonly_fs(copy_target), pytest.raises(RetrieverInfraError):
            rs.DuckDbVssSubstrate.open(str(db), model=_StubModel())

    # Warm up so lazy imports / module caches settle before the baseline.
    drive_one_fault()
    baseline = open_fd_count()

    n = 60
    for _ in range(n):
        drive_one_fault()

    final = open_fd_count()
    # Small tolerance for interpreter/runtime jitter; the point is NO monotonic
    # growth across 60 faults (a per-fault leak would add ~60 fds).
    assert final <= baseline + 2, (
        f"fd leak under repeated RO-FS fault: baseline={baseline} final={final} "
        f"after {n} faults"
    )
