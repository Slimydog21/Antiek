"""nygard SPR-02 M2 — regression fixture for the 2026-05-17 read-only-FS class.

Provenance: memory `project_researchmaxx_arxiv.md` + the 2026-05-17 incident —
an infra fault on a read-only filesystem was silently converted into a benign
degradation, erasing the cause. The retriever analogue lives at
`substrate/graph/retrieval_substrate.py`: `DuckDbVssSubstrate.open` copies the
graph to a scratch dir before building an HNSW index (`shutil.copy`, line ~336),
and an `OSError` there is caught and SILENTLY downgraded to a brute-force
fallback (line ~337-339, `# pragma: no cover`). That silent swallow is the exact
I-LOUD violation this sprint fixes.

This fixture arms SPR-01's REAL read-only-FS injector at the copy target and
drives the REAL `DuckDbVssSubstrate.open`, then asserts the outcome is a TYPED
infra failure (`RetrieverInfraError`) — NOT a silent brute-force fallback.

FAILS-BEFORE: on the pre-SPR-02(M4) tree, `open` swallows the OSError and returns
a brute-force substrate, so no `RetrieverInfraError` is raised and this test
FAILS. That failing run is the point (name the bug before fixing it).
PASSES-AFTER: once the M4 boundary raises `RetrieverInfraError` from the copy
OSError, this passes.

(The spec named this file `retriever-readonly-fs-2026-05-17.py`; renamed to a
`test_`-prefixed, underscore form so pytest's default `python_files` actually
collects it — a regression fixture that never runs is worse than none.)
"""

from __future__ import annotations

import tempfile

import pytest


def test_readonly_fs_at_retriever_copy_surfaces_typed_not_silent(tmp_path, monkeypatch):
    import duckdb

    import substrate.graph.retrieval_substrate as rs
    from substrate.errors import RetrieverInfraError
    from tools.faultinject import readonly_fs

    db = tmp_path / "graph.duckdb"
    duckdb.connect(str(db)).close()  # a real, readable graph to copy FROM
    scratch = tmp_path / "vss-scratch"
    scratch.mkdir()
    copy_target = scratch / "vss_index.duckdb"
    # Pin the retriever's internal scratch so we can arm on the copy target.
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: str(scratch))

    class _StubModel:
        dimension = 8

        def encode(self, xs):  # pragma: no cover - copy fails before encode
            return [[0.0] * 8 for _ in xs]

    # An infra fault (read-only FS) at the vss-index copy site MUST surface as a
    # typed RetrieverInfraError — not be silently masked as "vss unavailable,
    # using brute-force". Expected degradations (the vss EXTENSION being
    # unavailable) keep their benign brute-force fallback; an OSError does not.
    with readonly_fs(copy_target):
        with pytest.raises(RetrieverInfraError) as ei:
            rs.DuckDbVssSubstrate.open(str(db), model=_StubModel())

    import errno

    assert ei.value.errno == errno.EROFS
    assert "retrieval" in ei.value.seam
