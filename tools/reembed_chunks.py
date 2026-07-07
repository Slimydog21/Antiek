"""Re-embed every ``chunks`` row with the LIVE embedding provider.

DOGFOOD SPR-02 — the research-pillar root-cause fix. The substrate's chunk
vectors are hash-derived by default (M1 proof: ``stored == HashEmbedding(text)``
within float32 precision), so retrieval finds lexical/hash collisions, not
meaning. This tool rewrites every ``chunks.embedding`` with
``default_embedding_provider()`` so retrieval is semantic.

Invariants (mirror tools/merge_staging + tools/backfill_cc0_remap):

- **Single-writer.** One ``runtime.db_lock.connect_write`` transaction wraps
  every UPDATE. The live-writer flock opens once and commits or rolls back
  atomically — an interruption mid-run leaves the store at its pre-run state,
  resumable by re-running.
- **Idempotent.** Re-running with the SAME provider recomputes identical
  vectors (a given model + text is deterministic). Count is preserved — no
  chunk row is added or lost, only its vector column rewritten.
- **Column-explicit.** Only ``chunks.embedding`` is touched; ``chunk_id`` /
  ``text`` / ``document_id`` are read, never written.
- **Honest.** ``--apply`` REFUSES when the resolved provider is
  ``HashEmbedding`` (re-embedding with the hash stub is a silent no-op that
  masquerades as an upgrade) unless ``--force-hash`` is passed for testing.
- **Deliberate on prod.** ``--allow-prod-write`` is required when ``--db-path``
  resolves to the prod substrate default (re-embedding prod is an operator
  step; the default is a dry-run that writes nothing).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from processing.embedding.embed import (  # noqa: E402
    HashEmbedding,
    default_embedding_provider,
)
from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph import default_db_path  # noqa: E402
from substrate.graph.embedding_meta import record_chunk_embedding_meta  # noqa: E402
from substrate.graph.schema import init_database  # noqa: E402


@dataclass(frozen=True)
class ReembedReport:
    """Outcome of a re-embed run (dry-run or applied)."""

    db_path: str
    provider: str
    provider_is_hash: bool
    applied: bool
    total_chunks: int
    embedded_chunks: int  # chunks with a non-null embedding
    before_dim: int | None
    after_dim: int | None
    vectors_rewritten: int
    count_preserved: bool
    ran_at: str


def _is_prod_db(db_path: str) -> bool:
    """True when ``db_path`` resolves to the prod substrate default. Mirrors
    tools/ingest_open_access._is_prod_db / tools/backfill_cc0_remap._is_prod_db."""
    try:
        return os.path.abspath(db_path) == os.path.abspath(default_db_path())
    except Exception:
        return False


def _vector_dim(vec: object) -> int | None:
    if vec is None:
        return None
    if not isinstance(vec, Iterable):
        return None
    try:
        return len(list(vec))
    except TypeError:
        return None


def _l2norm(vec: Sequence[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in vec))


def run(
    db_path: str,
    *,
    apply: bool,
    force_hash: bool = False,
    limit: int | None = None,
) -> ReembedReport:
    """Re-embed (or dry-run-report) every chunk. Public entry for tests.

    ``apply=False`` is a read-only dry run that writes nothing. ``apply=True``
    opens the single writer, rewrites each ``chunks.embedding``, and asserts
    the chunk COUNT is preserved before/after.
    """
    provider = default_embedding_provider()
    provider_is_hash = isinstance(provider, HashEmbedding)

    # ── BEFORE: counts + a sample vector's dimension (read-only) ──────────
    import duckdb

    con_ro = duckdb.connect(db_path, read_only=True)
    try:
        total_row = con_ro.execute("SELECT count(*) FROM chunks").fetchone()
        embedded_row = con_ro.execute(
            "SELECT count(*) FROM chunks WHERE embedding IS NOT NULL"
        ).fetchone()
        if total_row is None or embedded_row is None:
            raise RuntimeError("DuckDB count query unexpectedly returned no rows")
        total = int(total_row[0])
        embedded = int(embedded_row[0])
        sample = con_ro.execute(
            "SELECT embedding FROM chunks WHERE embedding IS NOT NULL LIMIT 1"
        ).fetchone()
        before_dim = _vector_dim(sample[0]) if sample else None
    finally:
        con_ro.close()

    if apply and provider_is_hash and not force_hash:
        raise RuntimeError(
            "Refusing to --apply: the resolved provider is HashEmbedding, so "
            "re-embedding is a silent no-op (the very failure mode SPR-02 "
            "kills). Install sentence-transformers (pip install -e '.[embedding]') "
            "and/or set ANTIEK_EMBEDDING_PROVIDER=sentence-transformers, then "
            "re-run. Pass --force-hash only for testing."
        )

    if not apply:
        return ReembedReport(
            db_path=os.path.abspath(db_path),
            provider=type(provider).__name__,
            provider_is_hash=provider_is_hash,
            applied=False,
            total_chunks=total,
            embedded_chunks=embedded,
            before_dim=before_dim,
            after_dim=before_dim,
            vectors_rewritten=0,
            count_preserved=True,
            ran_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    # ── APPLY: single-writer transaction, rewrite every embedding ─────────
    rows = duckdb.connect(db_path, read_only=True).execute(
        "SELECT chunk_id, text FROM chunks"
        + (f" LIMIT {int(limit)}" if limit else "")
    ).fetchall()

    vectors_rewritten = 0
    with connect_write(db_path, purpose="reembed_chunks") as con:
        init_database(con)
        for chunk_id, text in rows:
            vec = provider.encode(text or "")
            con.execute(
                "UPDATE chunks SET embedding = ? WHERE chunk_id = ?",
                [list(vec), chunk_id],
            )
            record_chunk_embedding_meta(con, chunk_id=chunk_id, provider=provider)
            vectors_rewritten += 1
        after_total = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
        sample_after = con.execute(
            "SELECT embedding FROM chunks WHERE embedding IS NOT NULL LIMIT 1"
        ).fetchone()
        after_dim = _vector_dim(sample_after[0]) if sample_after else None

    return ReembedReport(
        db_path=os.path.abspath(db_path),
        provider=type(provider).__name__,
        provider_is_hash=provider_is_hash,
        applied=True,
        total_chunks=after_total,
        embedded_chunks=after_total,
        before_dim=before_dim,
        after_dim=after_dim,
        vectors_rewritten=vectors_rewritten,
        count_preserved=(after_total == total),
        ran_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _print_report(report: ReembedReport) -> None:
    print(json.dumps(asdict(report), indent=2, default=str))
    tag = "APPLIED" if report.applied else "DRY RUN (nothing written)"
    print(
        f"\nreembed_chunks [{tag}]: provider={report.provider} | "
        f"chunks={report.total_chunks} | dim {report.before_dim}→{report.after_dim} | "
        f"vectors_rewritten={report.vectors_rewritten} | "
        f"count_preserved={report.count_preserved}"
    )
    if report.provider_is_hash and not report.applied:
        print(
            "WARNING: provider is HashEmbedding — --apply would refuse "
            "(install sentence-transformers for a real semantic re-embed).",
            file=sys.stderr,
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="reembed_chunks",
        description="Re-embed every chunk with the live embedding provider (DOGFOOD SPR-02).",
    )
    p.add_argument("--db-path", help="target DuckDB (defaults to the substrate default)")
    p.add_argument(
        "--apply", action="store_true",
        help="rewrite the vectors (default is a dry-run that writes nothing)",
    )
    p.add_argument(
        "--allow-prod-write", action="store_true",
        help="required when --db-path is the prod substrate default",
    )
    p.add_argument(
        "--force-hash", action="store_true",
        help="allow --apply under HashEmbedding (testing only)",
    )
    p.add_argument(
        "--limit", type=int, default=None,
        help="re-embed only the first N chunks (testing/witness)",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = args.db_path or default_db_path()

    if args.apply and _is_prod_db(db_path) and not args.allow_prod_write:
        print(
            "error: --db-path resolves to the prod substrate default. Re-embedding "
            "prod is an operator step: re-run with --allow-prod-write after a "
            "backup (the old hash vectors are overwritten in place).",
            file=sys.stderr,
        )
        return 2

    report = run(db_path, apply=args.apply, force_hash=args.force_hash, limit=args.limit)
    _print_report(report)
    if args.apply and not report.count_preserved:
        print("error: chunk count changed during re-embed — investigate.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
