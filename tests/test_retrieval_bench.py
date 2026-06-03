"""SPR-05 M2 — benchmark harness tests.

Asserts:
  - recall@k is REAL arithmetic over the labeled set (known-answer: 2/3 →
    0.667), and a stub that returns nothing yields recall 0.0 (non-vacuity —
    the harness measures, it does not rubber-stamp),
  - the fixture-size guard refuses (non-zero exit / raises) on a <20-query
    fixture,
  - per-domain + load-bearing/non-load-bearing recall splits are computed,
  - the operator fixture loads and carries label_provenance per query,
  - the full driver emits an artifact with the candidate comparison + the
    single-writer assertion + the embedder caveat.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from benchmarks import retrieval_bench as rb
from substrate.graph import retrieval_substrate as _rs

# Hang-proof probe (LOAD-only, memoized, NO network install unless the operator
# opts in via ANTIEK_VSS_ALLOW_INSTALL). False on a network-restricted CI runner.
_VSS_LOADABLE = _rs._vss_loadable_probe()


# ---------------------------------------------------------------------------
# Known-answer recall arithmetic (non-vacuity)
# ---------------------------------------------------------------------------


def test_recall_at_k_known_answer():
    """2 of 3 relevant ids in the top-k → 0.667 (exact arithmetic)."""
    retrieved = ["a", "b", "x", "y"]
    relevant = ("a", "b", "c")
    r = rb.recall_at_k(retrieved, relevant, k=4)
    assert round(r, 3) == 0.667


def test_recall_at_k_full_and_zero():
    assert rb.recall_at_k(["a", "b"], ("a", "b"), k=2) == 1.0
    # non-vacuity: a substrate that returns nothing scores 0.0, not a pass.
    assert rb.recall_at_k([], ("a", "b"), k=5) == 0.0
    # ranked out of the window: relevant id below k is NOT counted.
    assert rb.recall_at_k(["x", "y", "z", "a"], ("a",), k=3) == 0.0


def test_recall_at_k_none_for_empty_relevant():
    """Negative / gate controls have no relevant set — scored separately, not
    by recall. recall_at_k returns None so they don't dilute the mean."""
    assert rb.recall_at_k(["a"], (), k=5) is None


def test_known_answer_via_aggregate_stub_substrate():
    """End-to-end: a stub substrate with a hand-set top-k flows through the
    aggregate path and reports the exact arithmetic recall. A broken stub that
    returns nothing makes recall 0.0 — proving the harness measures."""
    # Two load-bearing queries: one with 2/3 relevant retrieved, one with 0/1.
    qresults = [
        rb.QueryResult(id="A", domain="d1", load_bearing=True,
                       label_provenance="fixture",
                       recall=rb.recall_at_k(["a", "b", "x"], ("a", "b", "c"), 5)),
        rb.QueryResult(id="B", domain="d2", load_bearing=True,
                       label_provenance="fixture",
                       recall=rb.recall_at_k([], ("z",), 5)),
    ]
    agg = rb._aggregate("stub", qresults, [1.0, 2.0, 3.0], 5.0,
                        vss_active=None, gate_leak=None, neg_control_violations=[])
    # mean of {0.667, 0.0} = 0.3333
    assert agg["recall_at_5"]["load_bearing"] == pytest.approx(0.3333, abs=1e-3)
    assert agg["recall_at_5"]["per_domain"]["d1"] == pytest.approx(0.6667, abs=1e-3)
    assert agg["recall_at_5"]["per_domain"]["d2"] == 0.0


# ---------------------------------------------------------------------------
# Fixture-size guard (seed-and-catch)
# ---------------------------------------------------------------------------


def _write_fixture(tmp: Path, n: int) -> Path:
    qs = "\n".join(
        f"  - id: Q{i}\n    type: exact-fact\n    query: q{i}\n    target: chunks\n"
        f"    domain: d\n    relevant: [c-{i}]\n    label_provenance: fixture\n"
        f"    load_bearing: true"
        for i in range(n)
    )
    p = tmp / "small.yaml"
    p.write_text(f"meta:\n  default_top_k: 5\nqueries:\n{qs}\n", encoding="utf-8")
    return p


def test_fixture_too_small_refuses():
    """A 5-query fixture must be refused (raises FixtureTooSmall)."""
    tmp = Path(tempfile.mkdtemp(prefix="antiek-spr05-fixsmall-"))
    p = _write_fixture(tmp, 5)
    with pytest.raises(rb.FixtureTooSmall, match="5 queries, need >=20"):
        rb._load_fixture(p)


def test_fixture_too_small_nonzero_exit():
    """The CLI driver exits non-zero on a thin fixture (gate: non-silent)."""
    tmp = Path(tempfile.mkdtemp(prefix="antiek-spr05-fixexit-"))
    p = _write_fixture(tmp, 5)
    rc = rb.main(["--substrate", "vss", "--fixture", str(p)])
    assert rc == 2


def test_exactly_20_passes_guard():
    tmp = Path(tempfile.mkdtemp(prefix="antiek-spr05-fix20-"))
    p = _write_fixture(tmp, 20)
    queries, _ = rb._load_fixture(p)
    assert len(queries) == 20


# ---------------------------------------------------------------------------
# Operator fixture integrity
# ---------------------------------------------------------------------------


def test_operator_fixture_loads_with_provenance():
    queries, meta = rb._load_fixture(rb._default_fixture_path())
    assert len(queries) >= 20
    provs = {q.label_provenance for q in queries}
    assert provs <= {"fixture", "author-asserted", "structural"}
    assert "fixture" in provs and "author-asserted" in provs and "structural" in provs
    # paraphrase/conceptual queries are flagged non-load-bearing under the stub.
    paraphrase = [q for q in queries if q.type == "paraphrase"]
    assert paraphrase and all(not q.load_bearing for q in paraphrase)
    # the §9.0 gate-control query carries must_not_return.
    gate = [q for q in queries if q.type == "gate-control"]
    assert gate and gate[0].must_not_return == ("c-restricted-1",)
    assert "OPERATOR_INPUTS" in meta.get("source", "")


# ---------------------------------------------------------------------------
# Full driver smoke — artifact shape + single-writer + gate
# ---------------------------------------------------------------------------


def test_run_benchmark_emits_artifact():
    out = Path(tempfile.mkdtemp(prefix="antiek-spr05-art-")) / "spike.json"
    artifact = rb.run_benchmark(
        ["vss", "brute_force", "turbopuffer", "ducklake"],
        out_path=out,
        latency_repeats=3,
        prefer_real_embedder=False,  # deterministic: force the stub in CI
    )
    assert out.exists()
    saved = json.loads(out.read_text())
    kinds = {c["substrate"] for c in saved["candidates"]}
    assert kinds == {"vss", "brute_force", "turbopuffer", "ducklake"}

    by = {c["substrate"]: c for c in saved["candidates"]}
    # vendor adapters skipped, not crashed
    assert by["turbopuffer"]["status"] == "skipped — no credentials"
    assert by["ducklake"]["status"] == "skipped — no credentials"
    # vss measured, gate held, latency recorded — UNCONDITIONAL (the bench runs
    # and the artifact is well-formed whether vss is active or falls back to
    # brute force). vss_active is True only where the extension is loadable;
    # on a network-restricted CI runner the bench records vss_active=False and
    # falls back to brute force — that is the safe, expected behaviour.
    assert by["vss"]["status"] == "measured"
    if _VSS_LOADABLE:
        assert by["vss"]["vss_active"] is True
    else:
        assert by["vss"]["vss_active"] is False  # hang-proof fallback in no-network env
    assert by["vss"]["gate_9_0"]["held"] is True
    assert by["vss"]["latency_ms"]["p95"] >= 0.0
    assert by["vss"]["index_build_ms"] >= 0.0
    # §16 single-writer held across the whole run
    assert saved["single_writer_held"] is True
    # honesty: the stub embedder caveat is recorded
    assert saved["embedder"]["semantic"] is False
    assert "NON-LOAD-BEARING" in saved["embedder"]["caveat"]


def test_vss_and_bruteforce_identical_recall_in_artifact():
    """On the same seeded graph, VSS and brute-force must report identical
    pooled recall — they rank identically (HNSW is exact at this scale)."""
    out = Path(tempfile.mkdtemp(prefix="antiek-spr05-art2-")) / "spike.json"
    artifact = rb.run_benchmark(
        ["vss", "brute_force"], out_path=out, latency_repeats=2,
        prefer_real_embedder=False,
    )
    by = {c["substrate"]: c for c in artifact["candidates"]}
    assert by["vss"]["recall_at_5"]["pooled"] == by["brute_force"]["recall_at_5"]["pooled"]
    assert by["vss"]["recall_at_5"]["load_bearing"] == \
           by["brute_force"]["recall_at_5"]["load_bearing"]
