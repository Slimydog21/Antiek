"""Synthetic-load latency benchmark for ``get_cross_doc_links`` (SPR-07 M1).

The SPR-07 spec asks for P99 < 200ms against "production-shape data".
We do not have a production substrate in CI, so this test seeds a
synthetic graph (10k chunks across 100 documents with embeddings,
+ ~500 edges) and runs ``get_cross_doc_links`` 100 times against
random highlights — reporting P50/P95/P99 in milliseconds.

This is what "synthetic load test" means in the rigor-3 framing: a
measurement we can defend, not a single localhost call. The number
the test asserts on is the P99 — we mark the test as ``slow`` so CI
can opt-in, but local runs can fire ``pytest -m slow tests/
test_cross_doc_latency.py`` to verify.

If the measured P99 exceeds 200ms the test FAILS LOUDLY. Closing the
gap is then a profiling exercise — the failing number is the honest
report SPR-07 ships.

What's deliberately NOT covered here:
- A real sentence-transformers model. We use the deterministic stub
  to keep CI hermetic; the embedding-encode time isn't on the
  hot path of ``get_cross_doc_links`` (one encode per call, not per
  candidate). A follow-up sprint can plumb a true model into a slow
  bench.
- The TS-side call overhead (HTTP, JSON encode/decode). The 200ms
  budget is for the Python query, not the round-trip; the TS side
  has its own budget (M2 "pills within 300ms of highlight finalize")
  which includes the HTTP component.
"""

from __future__ import annotations

import os
import random
import sys
import time

import duckdb
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from runtime.db_lock import connect_write  # noqa: E402
from services.cross_doc.query import Highlight, get_cross_doc_links  # noqa: E402
from substrate.graph import (  # noqa: E402
    ensure_initialized,
    insert_chunk,
    insert_document,
    insert_edge,
    insert_node,
)


# Synthetic-graph dimensions. Picked so the embedding cosine SQL has to
# scan a non-trivial number of rows — production substrates today (5–
# 10k chunks per active operator) sit in this range. Doubling these
# numbers shows the slope without retesting; the assertion below is
# the stop-loss.
NUM_DOCUMENTS = 100
CHUNKS_PER_DOC = 100  # → 10_000 total chunks
NUM_EDGES = 500
EMBEDDING_DIM = 8  # matches the StubEmbedding


class StubEmbedding:
    dimension = EMBEDDING_DIM

    def encode(self, text: str) -> list[float]:
        v = [0.0] * self.dimension
        for i, ch in enumerate(text):
            v[i % self.dimension] += float(ord(ch))
        return v


def _make_random_vec(rng: random.Random) -> list[float]:
    return [rng.uniform(-1.0, 1.0) for _ in range(EMBEDDING_DIM)]


@pytest.fixture(scope="module")
def populated_db(tmp_path_factory):
    """Build the synthetic graph once, share across test runs."""
    tmp = tmp_path_factory.mktemp("cross_doc_bench")
    db_path = str(tmp / "graph.duckdb")
    ensure_initialized(db_path)
    rng = random.Random(0x5EED)
    con = connect_write(db_path, purpose="bench_seed")
    try:
        chunk_ids: list[str] = []
        # Map each chunk_id to its owning document_id so the edge
        # seeding step doesn't have to parse the synthetic id format.
        chunk_doc: dict[str, str] = {}
        for d in range(NUM_DOCUMENTS):
            doc_id = f"doc-{d:04d}"
            insert_document(
                con,
                document_id=doc_id,
                source_tier=rng.choice([1, 2, 3, 4, 5]),
                document_type="peer_reviewed_paper",
                title=f"Document {d}",
                on_conflict="ignore",
            )
            for c in range(CHUNKS_PER_DOC):
                cid = insert_chunk(
                    con,
                    chunk_id=f"ch-{d:04d}-{c:04d}",
                    document_id=doc_id,
                    chunk_index=c,
                    text=f"document {d} chunk {c} — synthetic content for benchmark",
                    embedding=_make_random_vec(rng),
                )
                chunk_ids.append(cid)
                chunk_doc[cid] = doc_id

        # Seed user-asserted + citation edges across random chunk
        # pairs. The graph layer's edges table is the substrate truth;
        # we attach edges to specific chunks (chunk_id column).
        node_ids: list[str] = []
        for n in range(50):
            nid = insert_node(
                con,
                canonical_label=f"concept-{n}",
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id="bench-inv",
                on_conflict="ignore",
            )
            node_ids.append(nid)
        for _ in range(NUM_EDGES):
            src_node = rng.choice(node_ids)
            tgt_node = rng.choice(node_ids)
            if src_node == tgt_node:
                continue
            relation = rng.choice(["user_asserted_link", "cites", "related"])
            chunk_for_edge = rng.choice(chunk_ids)
            insert_edge(
                con,
                source_node_id=src_node,
                target_node_id=tgt_node,
                relation=relation,
                chunk_id=chunk_for_edge,
                source_document_id=chunk_doc[chunk_for_edge],
                source_tier=2,
                extraction_confidence=0.9,
                graph_scope="cross_domain",
                investigation_id="bench-inv",
                on_conflict="ignore",
            )
    finally:
        con.close()
    return db_path


def _percentile(values: list[float], pct: float) -> float:
    """Tiny percentile helper. NumPy would do but the bench is cheap
    enough to avoid the dep."""
    if not values:
        return float("nan")
    s = sorted(values)
    k = int(round(pct / 100.0 * (len(s) - 1)))
    return s[k]


def test_get_cross_doc_links_p99_under_budget(populated_db, capsys):
    """Run ``get_cross_doc_links`` 100x on randomly-chosen source docs
    and assert P99 stays under the 200ms budget.

    Honesty hook (rigor #3): if this fails, the test prints P50/P95/
    P99 so the handoff can include the actual measurement. Do NOT
    quiet the test by raising the budget — that's the wrong fix.
    """
    rng = random.Random(0xC0FFEE)
    con = duckdb.connect(populated_db, read_only=True)
    model = StubEmbedding()
    timings_ms: list[float] = []

    # Warm pass — JIT/cache the first read. Per-call cold timing isn't
    # what we measure; we measure steady-state which is what the gutter
    # surface experiences (the operator highlights many regions per
    # session).
    _ = get_cross_doc_links(
        Highlight(
            document_id="doc-0000",
            page=1,
            bbox=(0, 0, 10, 10),
            selected_text="warm up",
        ),
        con=con,
        model=model,
    )

    for _ in range(100):
        d = rng.randrange(NUM_DOCUMENTS)
        highlight = Highlight(
            document_id=f"doc-{d:04d}",
            page=1,
            bbox=(0, 0, 10, 10),
            selected_text=f"selection in doc {d}",
        )
        start = time.perf_counter()
        get_cross_doc_links(highlight, con=con, model=model)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        timings_ms.append(elapsed_ms)

    p50 = _percentile(timings_ms, 50)
    p95 = _percentile(timings_ms, 95)
    p99 = _percentile(timings_ms, 99)
    avg = sum(timings_ms) / len(timings_ms)

    # Always emit the numbers — they go into the SPR-07 handoff.
    with capsys.disabled():
        print(
            f"\n[cross_doc latency] N={len(timings_ms)} runs over "
            f"{NUM_DOCUMENTS}×{CHUNKS_PER_DOC}={NUM_DOCUMENTS * CHUNKS_PER_DOC} "
            f"chunks + {NUM_EDGES} edges: "
            f"avg={avg:.1f}ms  P50={p50:.1f}ms  P95={p95:.1f}ms  "
            f"P99={p99:.1f}ms  budget=200ms"
        )

    assert p99 < 200.0, (
        f"P99 latency {p99:.1f}ms exceeds the 200ms budget. "
        f"Full distribution: P50={p50:.1f}ms P95={p95:.1f}ms P99={p99:.1f}ms"
    )
