"""Backfill embeddings_meta for chunks that already have vectors.

TurboPuffer SERVABLE export requires embeddings_meta to exactly cover the
export allowlist. Older book ingests stored floats without pinning provider
identity; this operator tool fills the gap without re-embedding.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Backfill embeddings_meta from live SentenceTransformer identity")
    p.add_argument("--db", required=True, help="canonical graph DuckDB path")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--only-export-classes", action="store_true",
        help="limit to TURBOPUFFER_INDEX_CONTENT_CLASSES documents",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from processing.embedding.embed import SentenceTransformerEmbedding
    from runtime.db_lock import connect_read, connect_write
    from substrate.constants import TURBOPUFFER_INDEX_CONTENT_CLASSES
    from substrate.graph.embedding_meta import _identity, record_chunk_embedding_meta

    con = connect_read(args.db)
    try:
        if args.only_export_classes:
            allowed = sorted(TURBOPUFFER_INDEX_CONTENT_CLASSES)
            placeholders = ",".join("?" for _ in allowed)
            missing = con.execute(
                "SELECT c.chunk_id FROM chunks c "
                "JOIN documents d ON d.document_id=c.document_id "
                "LEFT JOIN embeddings_meta em ON em.chunk_id=c.chunk_id "
                f"WHERE c.embedding IS NOT NULL AND em.chunk_id IS NULL "
                f"AND d.content_class IN ({placeholders}) "
                "ORDER BY c.chunk_id",
                allowed,
            ).fetchall()
        else:
            missing = con.execute(
                "SELECT c.chunk_id FROM chunks c "
                "LEFT JOIN embeddings_meta em ON em.chunk_id=c.chunk_id "
                "WHERE c.embedding IS NOT NULL AND em.chunk_id IS NULL "
                "ORDER BY c.chunk_id"
            ).fetchall()
        # Prefer existing identity if present
        existing = con.execute(
            "SELECT provider,model_name,dimension,fingerprint "
            "FROM embeddings_meta GROUP BY ALL"
        ).fetchall()
    finally:
        con.close()

    if len(existing) > 1:
        raise SystemExit("canonical graph has multiple embedding identities; refuse backfill")
    if existing:
        provider_name, model_name, dimension, fingerprint = existing[0]
        if provider_name != "sentence-transformers":
            raise SystemExit(f"unsupported provider {provider_name!r}")
        model = SentenceTransformerEmbedding(str(model_name))
        live = _identity(model)
        if live != (provider_name, model_name, int(dimension), fingerprint):
            raise SystemExit("live SentenceTransformer identity mismatches embeddings_meta")
    else:
        model = SentenceTransformerEmbedding("all-MiniLM-L6-v2")

    result: dict[str, Any] = {
        "missing": len(missing),
        "dry_run": bool(args.dry_run),
        "identity": {
            "provider": _identity(model)[0],
            "model": _identity(model)[1],
            "dimension": _identity(model)[2],
            "fingerprint": _identity(model)[3],
        },
    }
    if args.dry_run or not missing:
        print(json.dumps(result, sort_keys=True))
        return 0

    written = 0
    with connect_write(args.db, purpose="backfill-embeddings-meta") as wcon:
        for (chunk_id,) in missing:
            record_chunk_embedding_meta(wcon, chunk_id=chunk_id, provider=model)
            written += 1
    result["written"] = written
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
