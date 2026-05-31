"""Measure the connect_write-held merge window at production scale (SPR-01 M6).

The keystone claim is "the API stays up; the merge is seconds." A toy 6-book
batch can only *regression-guard* that claim; it cannot *evidence* it at the
scale the keystone will actually run. The first prod ingest (2026-05-29) landed
31 documents and 5,017 embedded chunks — so this measures the real
``connect_write``-held window on a 5,017-chunk batch, and the slope of that
window across batch sizes, so the recorded number is a defensible production
figure rather than a hoped-for one.

What it does NOT measure: the ingest (download/extract/chunk/embed) duration.
That happens off the live writer in staging by design; the keystone is the
copy window, not the ingest. Staging here is populated by a fast bulk insert
because the merge's ``INSERT … SELECT`` across the ATTACHed DB is identical
regardless of how staging's rows got there — the cost is the row count and the
``FLOAT[]`` materialization, not the ingest path. (One honest caveat is
recorded by ``--note``: the embedding dim here is 16, matching the project's
stub embedder; a larger production embedding dim widens each chunk row and
would scale the chunk-copy term linearly in dim. The slope below is reported
in chunks; multiply by the dim ratio for a different embedder.)

Re-runnable on the box against temp DBs (needs no prod env):

    .venv/bin/python -m tools.measure_merge_window
    .venv/bin/python -m tools.measure_merge_window --sizes 500,2000,5017 --dim 16
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph.schema import init_database  # noqa: E402
from tools.merge_staging import merge_staging  # noqa: E402

# Shape of the first prod ingest (2026-05-29): 31 docs, 5,017 chunks.
PROD_DOCS = 31
PROD_CHUNKS = 5017


def _populate_staging(staging_path: str, *, n_docs: int, n_chunks: int, dim: int) -> None:
    """Bulk-fill a staging DB with ``n_docs`` documents and ``n_chunks`` chunks,
    each chunk carrying a ``dim``-element FLOAT[] vector, plus one node per doc.
    Mirrors the columns the real ingest populates; the merge copies the same
    rows whether they arrived this way or via the connector path."""
    con = connect_write(staging_path, purpose="measure-populate")
    try:
        init_database(con)
        con.execute("BEGIN")
        for d in range(n_docs):
            con.execute(
                "INSERT INTO documents "
                "(document_id, source_tier, document_type, content_class) "
                "VALUES (?, 2, 'book', 'public_domain')",
                [f"doc-{d:05d}"],
            )
            con.execute(
                "INSERT INTO nodes "
                "(node_id, canonical_label, node_type, embedding, graph_scope) "
                "VALUES (?, ?, 'claim', ?, 'depth')",
                [f"node-{d:05d}", f"label-{d}", [float(d % 7)] * dim],
            )
        # Spread the chunks across the documents, each with a distinct vector.
        rows = []
        for c in range(n_chunks):
            vec = [float((c + i) % 13) for i in range(dim)]
            rows.append((f"chunk-{c:06d}", f"doc-{c % n_docs:05d}", c, f"text-{c}", vec, 10))
        con.executemany(
            "INSERT INTO chunks "
            "(chunk_id, document_id, chunk_index, text, embedding, token_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.execute("COMMIT")
    finally:
        con.close()


def measure_one(*, n_docs: int, n_chunks: int, dim: int) -> float:
    """Return the connect_write-held merge window (seconds) for one batch."""
    tmp = tempfile.mkdtemp(prefix="antiek-merge-measure-")
    live = os.path.join(tmp, "live.duckdb")
    staging = os.path.join(tmp, "staging.duckdb")
    con = connect_write(live, purpose="measure-init-live")
    try:
        init_database(con)
    finally:
        con.close()
    _populate_staging(staging, n_docs=n_docs, n_chunks=n_chunks, dim=dim)
    result = merge_staging(live_db=live, staging_db=staging)
    assert result.total_inserted >= n_chunks, "measurement merged fewer rows than staged"
    return result.window_s


def _slope(points: list[tuple[int, float]]) -> float:
    """Least-squares slope (seconds per chunk) of window vs chunk-count."""
    n = len(points)
    if n < 2:
        return 0.0
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    sxx = sum(x * x for x, _ in points)
    sxy = sum(x * y for x, y in points)
    denom = n * sxx - sx * sx
    return (n * sxy - sx * sy) / denom if denom else 0.0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m tools.measure_merge_window",
        description="Measure the SPR-01 merge window at production scale + its slope.",
    )
    p.add_argument(
        "--sizes",
        default=f"500,2000,{PROD_CHUNKS}",
        help="comma-separated chunk counts to measure (slope is fit across them)",
    )
    p.add_argument("--dim", type=int, default=16, help="embedding dimensionality")
    p.add_argument("--docs", type=int, default=PROD_DOCS, help="document count per batch")
    args = p.parse_args(argv)

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    print(f"merge-window measurement (docs={args.docs}, dim={args.dim})")
    print(f"{'chunks':>8}  {'window_s':>10}  {'µs/chunk':>10}")
    points: list[tuple[int, float]] = []
    for n_chunks in sizes:
        w = measure_one(n_docs=args.docs, n_chunks=n_chunks, dim=args.dim)
        points.append((n_chunks, w))
        print(f"{n_chunks:>8}  {w:>10.4f}  {w / n_chunks * 1e6:>10.2f}")
    slope = _slope(points)
    prod = next((w for n, w in points if n == PROD_CHUNKS), None)
    print(f"\nslope: {slope * 1e6:.3f} µs/chunk ({slope:.3e} s/chunk)")
    if prod is not None:
        print(f"production-scale ({PROD_CHUNKS} chunks) window: {prod:.4f}s  ← the keystone number")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
