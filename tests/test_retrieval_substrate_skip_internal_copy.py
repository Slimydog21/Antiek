"""ACV SPR-03 — the double-copy de-dup gate for DuckDbVssSubstrate.

SPR-02's ``build_prod_retrieval_substrate`` already mkdtemp's a per-launch
throwaway snapshot of the graph and unlinks it eagerly. Without de-dup, the vss
path then copies that snapshot AGAIN internally (``shutil.copy`` →
``antiek-vss-*`` temp dir), so each launch pays TWO full-DB (≈86 MB in prod)
copies. SPR-03 adds ``DuckDbVssSubstrate.open(skip_internal_copy=True)`` so a
caller that already owns an isolated snapshot drops the second copy — the
substrate indexes that snapshot IN PLACE.

These tests prove:

  * ``skip_internal_copy=True`` makes ZERO ``antiek-vss-*`` temp dirs (the
    second copy is gone) on BOTH the vss-active and the fallback path;
  * the substrate still queries correctly over the in-place snapshot;
  * OWNERSHIP: the substrate NEVER deletes the caller's ``db_path`` snapshot —
    the caller owns its lifecycle (so cascade_routes' eager unlink + the
    close-on-teardown remain the only deleters);
  * (positive control, vss-loadable only) the DEFAULT path DOES create an
    ``antiek-vss-`` dir — so the zero-count above is the FLAG's effect, not a
    test that would pass vacuously.

A second module exercises the de-dup THROUGH the real
``build_prod_retrieval_substrate`` factory and re-asserts the SPR-02 no-leak
invariant (no double-unlink / use-after-unlink, snapshot dirs do not accumulate)
so the de-dup did not break the snapshot lifecycle.
"""

from __future__ import annotations

import os

import pytest

from benchmarks.retrieval_bench import HashEmbedding, seed_graph
from substrate.graph import retrieval_substrate as _rs
from substrate.graph.retrieval_substrate import DuckDbVssSubstrate, make_substrate

_VSS_LOADABLE = _rs._vss_loadable_probe()
_requires_vss = pytest.mark.skipif(
    not _VSS_LOADABLE,
    reason="vss extension not loadable without a network install",
)


def _count_vss_dirs(base: str) -> int:
    return len([d for d in os.listdir(base) if d.startswith("antiek-vss-")])


@pytest.fixture
def isolated_tmpbase(monkeypatch, tmp_path):
    """Pin tempfile's base dir to an empty per-test directory so the
    ``antiek-vss-`` temp-dir count is isolated from the rest of the machine.
    Mirrors test_cascade_substrate_wire.isolated_tmpbase."""
    import tempfile as _tf

    base = str(tmp_path / "tmpbase")
    os.makedirs(base, exist_ok=True)
    monkeypatch.setenv("TMPDIR", base)
    monkeypatch.setattr(_tf, "tempdir", None)  # bust gettempdir() cache
    return base


@pytest.fixture
def isolated_snapshot(tmp_path):
    """A throwaway isolated snapshot the caller owns — exactly the shape
    ``build_prod_retrieval_substrate`` passes (its own mkdtemp'd copy)."""
    emb = HashEmbedding()
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir()
    db = str(snap_dir / "reuse_snapshot.duckdb")
    seed_graph(db, emb)
    return db, emb


# ──────────────────────────────────────────────────────────────────────────────
# skip_internal_copy=True → ZERO second copies (the de-dup), on either path.
# ──────────────────────────────────────────────────────────────────────────────


def test_skip_internal_copy_makes_no_second_copy(isolated_tmpbase, isolated_snapshot):
    """The headline acceptance: with skip_internal_copy=True, the substrate
    makes NO ``antiek-vss-*`` temp dir (no second full-DB copy). True on BOTH the
    vss-active path (indexes the snapshot in place) and the fallback path (opens
    the snapshot read-only directly)."""
    db, emb = isolated_snapshot
    before = _count_vss_dirs(isolated_tmpbase)
    sub = DuckDbVssSubstrate.open(db, model=emb, skip_internal_copy=True)
    try:
        after = _count_vss_dirs(isolated_tmpbase)
        assert after == before == 0, (
            f"skip_internal_copy=True still made a second copy: "
            f"antiek-vss- dirs before={before} after={after}. The de-dup must "
            f"index the caller's snapshot IN PLACE, never copy it again."
        )
        # And it still works: a query returns the search() shape.
        res = sub.query("QuEra neutral-atom gate error rate", top_k=3)
        assert set(res.keys()) == {"query", "top_k", "results", "node_matches"}
    finally:
        sub.close()


def test_skip_internal_copy_via_make_substrate_factory(isolated_tmpbase, isolated_snapshot):
    """The flag threads through the ``make_substrate("vss", ...)`` seam (the
    call site cascade_routes uses), not just the direct .open() — same zero
    second copy."""
    db, emb = isolated_snapshot
    sub = make_substrate("vss", db, model=emb, skip_internal_copy=True)
    try:
        assert _count_vss_dirs(isolated_tmpbase) == 0, (
            "make_substrate('vss', ..., skip_internal_copy=True) must forward the "
            "flag so no second copy is made"
        )
        assert sub.name == "vss"
    finally:
        sub.close()


def test_substrate_does_not_delete_callers_snapshot(isolated_snapshot):
    """OWNERSHIP CONTRACT: under skip_internal_copy=True the substrate operates
    on the caller's db_path directly, but it must NEVER unlink/delete that file —
    the caller owns the snapshot lifecycle. Opening then closing must leave the
    caller's file exactly where the caller put it."""
    db, emb = isolated_snapshot
    assert os.path.exists(db)
    sub = DuckDbVssSubstrate.open(db, model=emb, skip_internal_copy=True)
    sub.close()
    assert os.path.exists(db), (
        "the substrate deleted the caller's snapshot — it must not. The caller "
        "(cascade_routes) owns the snapshot's lifecycle; the substrate only "
        "closes its connection."
    )


def test_default_path_does_make_a_second_copy(isolated_tmpbase, isolated_snapshot):
    """Positive control (vss-loadable only): the DEFAULT (skip_internal_copy
    omitted) path DOES create an ``antiek-vss-`` dir — so the zero-count proofs
    above are the FLAG's effect, not a vacuous pass. Skipped when vss is not
    loadable (the fallback never copies, so there is nothing to contrast)."""
    if not _VSS_LOADABLE:
        pytest.skip("vss not loadable — the default path also falls back, no copy")
    db, emb = isolated_snapshot
    sub = DuckDbVssSubstrate.open(db, model=emb)  # default: skip_internal_copy=False
    try:
        assert sub.vss_active, "expected vss active in this environment"
        assert _count_vss_dirs(isolated_tmpbase) == 1, (
            "the default (no-flag) vss path must make exactly one internal copy "
            "(antiek-vss- dir) — this is the second copy the flag eliminates"
        )
    finally:
        sub.close()


def test_default_behaviour_unchanged_when_flag_omitted(isolated_snapshot):
    """Regression safety: omitting the flag preserves the prior behaviour exactly
    (the substrate opens and queries; no signature break for existing callers
    like the benchmark + the interface tests)."""
    db, emb = isolated_snapshot
    sub = make_substrate("vss", db, model=emb)  # no skip_internal_copy
    try:
        res = sub.query("phased-array radar gain sidelobe", top_k=3)
        assert isinstance(res["results"], list)
        # The caller's snapshot is untouched on the default path too.
        assert os.path.exists(db)
    finally:
        sub.close()
