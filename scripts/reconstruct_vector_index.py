#!/usr/bin/env python3
"""Reconstruct missing chunk embeddings.

DDIA-execution SPR-06. Anchors philosophy P8 (vector indexes are
secondary, derived data over substrate-owned truth; rebuildable from
the underlying chunks).

Antiek's vector store is the ``embedding FLOAT[]`` column on the
``chunks`` table (DuckDB-native cosine similarity, see
``substrate/graph/search.py``). The reconstruction path is exactly the
forward path: for chunks where ``embedding IS NULL`` (or all chunks
when ``--rebuild`` is set), the script calls the embedding model and
writes the vector back.

Properties this script preserves:

- **Idempotent.** Running twice on a fully-embedded namespace makes
  zero writes. Use ``--rebuild`` to force re-embedding.
- **Bounded.** ``--max-chunks N`` caps the work per invocation; the
  script can be resumed safely.
- **Cost-aware.** ``--cost-budget USD`` stops cleanly when the
  estimated spend exceeds the budget, emitting a resume hint.
- **Single-writer.** Acquires the substrate's flock via
  ``runtime.db_lock.connect_write`` — never touches DuckDB directly.

If the vector store is ever lost (turbopuffer wiped, namespace deleted,
pgvector schema migration breaks), this script is the recovery path.
That's the entire point of P8 — vector indexes are recoverable from
the chunks they index.

Usage::

    # Dry run: report what would be done
    .venv/bin/python scripts/reconstruct_vector_index.py --db PATH --dry-run

    # Embed missing only (default, idempotent)
    .venv/bin/python scripts/reconstruct_vector_index.py --db PATH

    # Force re-embed everything (use after embedding-model upgrade)
    .venv/bin/python scripts/reconstruct_vector_index.py --db PATH --rebuild

    # Bounded
    .venv/bin/python scripts/reconstruct_vector_index.py --db PATH --max-chunks 1000

The script is operator-invoked, not part of the request path. Cost
telemetry rows are written to the substrate via the existing burn
ledger when ``ANTIEK_DISABLE_BURN_TELEMETRY`` is unset.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional, Protocol

# Repo-relative imports
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import (  # noqa: E402
    WriteLockTimeout,
    connect_read,
    connect_write,
)


class EmbeddingModel(Protocol):
    """Same shape as ``substrate.graph.search.EmbeddingModel`` — kept
    duplicated here so the script can be imported by tests without
    pulling the substrate's graph module (which transitively imports
    sentence-transformers in production).
    """

    dimension: int

    def encode(self, text: str) -> list[float]: ...


def _count_chunks_missing_embedding(con) -> int:
    """How many chunks in the DB still have ``embedding IS NULL``?"""
    result = con.execute(
        "SELECT COUNT(*) FROM chunks WHERE embedding IS NULL"
    ).fetchone()
    return int(result[0]) if result else 0


def _count_chunks_total(con) -> int:
    result = con.execute("SELECT COUNT(*) FROM chunks").fetchone()
    return int(result[0]) if result else 0


def _fetch_chunks_to_embed(
    con,
    *,
    rebuild: bool,
    limit: int,
) -> list[tuple[str, str]]:
    """Return (chunk_id, text) tuples for chunks that need embedding."""
    where_clause = "" if rebuild else "WHERE embedding IS NULL"
    sql = f"""
        SELECT chunk_id, text
        FROM chunks
        {where_clause}
        ORDER BY chunk_id
        LIMIT {int(limit)}
    """
    return [(r[0], r[1]) for r in con.execute(sql).fetchall()]


def _write_embedding(con, chunk_id: str, vector: list[float]) -> None:
    """Write the computed embedding to the substrate. Inside a flocked
    write context — caller owns the lock.
    """
    con.execute(
        "UPDATE chunks SET embedding = ? WHERE chunk_id = ?",
        [vector, chunk_id],
    )


def reconstruct(
    db_path: str,
    *,
    model: EmbeddingModel,
    rebuild: bool = False,
    max_chunks: int = 10_000,
    cost_per_chunk_usd: float = 0.0,
    cost_budget_usd: Optional[float] = None,
    dry_run: bool = False,
) -> dict[str, int | float | bool | str]:
    """Reconstruct embeddings. Returns a result dict for ops reporting.

    Result shape::

        {
            "db_path": str,
            "rebuild": bool,
            "dry_run": bool,
            "total_chunks": int,
            "missing_before": int,
            "embedded_this_run": int,
            "skipped_by_budget": int,
            "estimated_cost_usd": float,
            "elapsed_s": float,
        }
    """
    t0 = time.monotonic()
    result: dict[str, int | float | bool | str] = {
        "db_path": db_path,
        "rebuild": rebuild,
        "dry_run": dry_run,
        "embedded_this_run": 0,
        "skipped_by_budget": 0,
        "estimated_cost_usd": 0.0,
        "elapsed_s": 0.0,
    }

    # Read-side: count what needs doing. Read-only is safe to interleave
    # with a writer; only the actual UPDATEs need the flock.
    with connect_read(db_path) as read_con:
        result["total_chunks"] = _count_chunks_total(read_con)
        result["missing_before"] = _count_chunks_missing_embedding(read_con)
        candidates = _fetch_chunks_to_embed(
            read_con, rebuild=rebuild, limit=max_chunks
        )

    if dry_run:
        result["elapsed_s"] = time.monotonic() - t0
        return result

    if not candidates:
        result["elapsed_s"] = time.monotonic() - t0
        return result

    # Acquire the flock for the duration of the embedding writes.
    # Embedding compute happens inside the write block; on a typical
    # ingest this can be 30+ seconds. The single-writer invariant
    # (P1, db_lock invariants) is preserved because we own the lock.
    try:
        with connect_write(db_path, purpose="reconstruct_vector_index") as con:
            for chunk_id, text in candidates:
                # Check budget BEFORE incurring spend.
                projected = result["estimated_cost_usd"] + cost_per_chunk_usd
                if (
                    cost_budget_usd is not None
                    and projected > cost_budget_usd
                ):
                    # Stop cleanly; remaining work is the resume target.
                    result["skipped_by_budget"] = (
                        len(candidates) - int(result["embedded_this_run"])
                    )
                    break
                vector = model.encode(text)
                _write_embedding(con, chunk_id, vector)
                result["embedded_this_run"] = (
                    int(result["embedded_this_run"]) + 1
                )
                result["estimated_cost_usd"] = projected
    except WriteLockTimeout:
        # Surface to caller; the script's exit code reflects this.
        result["elapsed_s"] = time.monotonic() - t0
        raise

    result["elapsed_s"] = time.monotonic() - t0
    return result


def _format_result(result: dict[str, int | float | bool | str]) -> str:
    """Human-readable summary suitable for ops + logs."""
    lines = [
        f"reconstruct_vector_index: {result['db_path']}",
        f"  total_chunks:       {result['total_chunks']}",
        f"  missing_before:     {result['missing_before']}",
        f"  embedded_this_run:  {result['embedded_this_run']}"
        + ("  (DRY RUN)" if result["dry_run"] else ""),
    ]
    if result["skipped_by_budget"]:
        lines.append(
            f"  skipped_by_budget:  {result['skipped_by_budget']}  "
            "(resume by re-running with the same flags)"
        )
    lines.append(
        f"  estimated_cost:     ${float(result['estimated_cost_usd']):.4f}"
    )
    lines.append(f"  elapsed:            {float(result['elapsed_s']):.2f}s")
    return "\n".join(lines)


def _default_model() -> EmbeddingModel:
    """Best-effort default: load Antiek's production embedding model.

    Imports are deferred so the script can run in dry-run mode without
    sentence-transformers being installed.
    """
    from substrate.graph.search import SentenceTransformerEmbedding

    return SentenceTransformerEmbedding()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reconstruct_vector_index",
        description=(
            "Recompute missing embeddings on the ``chunks`` table. "
            "Idempotent. Cost-bounded. Use --rebuild to force-recompute "
            "everything (e.g., after an embedding-model upgrade)."
        ),
        epilog=(
            "Why this exists: P8 of the philosophy doc — vector "
            "indexes are derived data, rebuildable from chunks. This "
            "script IS the rebuild path. See "
            "docs/decisions/vector_index_as_derived_data.md."
        ),
    )
    parser.add_argument("--db", required=True, help="Path to the DuckDB file")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Re-embed EVERY chunk (not just missing). Use after an "
        "embedding-model upgrade.",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=10_000,
        help="Maximum chunks to embed in this run (default 10000). "
        "Bounded so a single invocation can't run away.",
    )
    parser.add_argument(
        "--cost-per-chunk",
        type=float,
        default=0.0,
        help="Estimated USD cost per embedding call. Used to enforce "
        "--cost-budget. Default 0 (assumes local model; no per-call "
        "USD cost).",
    )
    parser.add_argument(
        "--cost-budget",
        type=float,
        default=None,
        help="Stop cleanly when projected spend exceeds this USD. "
        "Remaining work is reported so the operator can resume.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be done; make no writes. Read-only.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the human-readable summary on success.",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(
            f"reconstruct_vector_index: --db {args.db} does not exist",
            file=sys.stderr,
        )
        return 2

    # Late-load the model so --dry-run can run without
    # sentence-transformers installed.
    model: EmbeddingModel | None = None
    if not args.dry_run:
        try:
            model = _default_model()
        except ImportError as exc:
            print(
                f"reconstruct_vector_index: embedding model unavailable: "
                f"{exc}. Install with: pip install -e '.[embedding]'",
                file=sys.stderr,
            )
            return 3

    try:
        result = reconstruct(
            args.db,
            model=model,  # type: ignore[arg-type]
            rebuild=args.rebuild,
            max_chunks=args.max_chunks,
            cost_per_chunk_usd=args.cost_per_chunk,
            cost_budget_usd=args.cost_budget,
            dry_run=args.dry_run,
        )
    except WriteLockTimeout as exc:
        print(
            f"reconstruct_vector_index: write lock busy: {exc}",
            file=sys.stderr,
        )
        return 4

    if not args.quiet:
        print(_format_result(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
