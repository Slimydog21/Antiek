"""Backfill embeddings_meta for chunks that already have vectors.

TurboPuffer SERVABLE export requires embeddings_meta to exactly cover the
export allowlist. Older book ingests stored floats without pinning provider
identity; this operator tool fills the gap without re-embedding.
"""

from __future__ import annotations

import argparse
import json
import sys
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
                "SELECT c.chunk_id, c.text, c.embedding FROM chunks c "
                "JOIN documents d ON d.document_id=c.document_id "
                "LEFT JOIN embeddings_meta em ON em.chunk_id=c.chunk_id "
                f"WHERE c.embedding IS NOT NULL AND em.chunk_id IS NULL "
                f"AND d.content_class IN ({placeholders}) "
                "ORDER BY c.chunk_id",
                allowed,
            ).fetchall()
        else:
            missing = con.execute(
                "SELECT c.chunk_id, c.text, c.embedding FROM chunks c "
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

    # VERIFY before stamping. This tool used to assert the live model's
    # identity onto every unpinned chunk without looking at the vector — so a
    # chunk whose floats were HASH-derived (the silent-fallback case this
    # backfill exists to repair) got stamped "MiniLM", and the search-time
    # compatibility gate then vouched for a lie. A pin is a claim about
    # provenance; the only honest way to make it after the fact is to
    # re-derive the vector and check it matches.
    written = 0
    unverified: list[str] = []
    with connect_write(args.db, purpose="backfill-embeddings-meta") as wcon:
        for chunk_id, text, stored in missing:
            if _vector_matches(model, text, stored):
                record_chunk_embedding_meta(wcon, chunk_id=chunk_id, provider=model)
                written += 1
            else:
                unverified.append(chunk_id)
    result["written"] = written
    result["unverified"] = unverified
    print(json.dumps(result, sort_keys=True))
    if unverified:
        print(
            f"backfill: {len(unverified)} chunk(s) whose stored vector does NOT "
            "match this model's encoding were left UNPINNED (not stamped). They "
            "were produced by a different provider — re-embed them with "
            "tools/reembed_chunks.py rather than claiming an identity they lack.",
            file=sys.stderr,
        )
        return 2
    return 0


def _vector_matches(model: Any, text: str, stored: Any, *, min_cos: float = 0.999) -> bool:
    """True iff re-encoding ``text`` reproduces ``stored`` (cosine >= min_cos)."""
    import math
    if stored is None or text is None:
        return False
    fresh = [float(x) for x in model.encode(text)]
    got = [float(x) for x in stored]
    if len(fresh) != len(got) or not fresh:
        return False
    dot = sum(a * b for a, b in zip(fresh, got, strict=True))
    na = math.sqrt(sum(a * a for a in fresh))
    nb = math.sqrt(sum(b * b for b in got))
    if na == 0 or nb == 0:
        return False
    return bool(dot / (na * nb) >= min_cos)


if __name__ == "__main__":
    raise SystemExit(main())
