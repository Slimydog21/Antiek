"""Operator command for Turbopuffer shadow → SERVABLE promote/query."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Rebuild/promote/query the Turbopuffer SERVABLE hybrid index (DuckDB remains SoT; not the default talk-to-book mount).")
    p.add_argument("action", choices=("rebuild", "query", "benchmark", "promote", "status"))
    p.add_argument("--db", required=True, help="canonical graph DuckDB path")
    p.add_argument("--dry-run", action="store_true", help="count eligible rows; no SDK/network/write")
    p.add_argument("--query", help="query text for the query action")
    p.add_argument("--query-set", help="JSON list with query and relevant_ids (>=20)")
    p.add_argument("--manifest")
    p.add_argument("--confirm")
    p.add_argument("--output", help="non-content benchmark artifact path")
    p.add_argument("--include-result-ids", action="store_true",
                   help="include opaque result IDs (never text or query bodies)")
    p.add_argument("--region", default="gcp-us-central1")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.action == "query" and not args.query:
        parser().error("query action requires --query")
    if args.action == "benchmark" and (not args.query_set or not args.output):
        parser().error("benchmark requires --query-set and --output")
    if args.action == "promote" and (not args.manifest or not args.confirm):
        parser().error("promote requires --manifest and --confirm")
    from processing.embedding.embed import SentenceTransformerEmbedding
    from substrate.graph.retrieval_adapters.turbopuffer import TurbopufferSubstrate
    from substrate.graph.search import EmbeddingModel
    # status / dry-run never call encode(); avoid loading SentenceTransformer.
    if args.dry_run or args.action == "status":
        from runtime.db_lock import connect_read
        con = connect_read(args.db)
        try:
            dimension_row = con.execute(
                "SELECT dimension FROM embeddings_meta LIMIT 1").fetchone()
            if dimension_row is None:
                raise RuntimeError("canonical graph has no embedding identity")
            dim = int(dimension_row[0])
        finally:
            con.close()
        class DryModel:
            dimension = dim
            def encode(self, text: str) -> list[float]:
                raise RuntimeError("status/dry-run never embeds")
        model: EmbeddingModel = DryModel()
    else:
        from runtime.db_lock import connect_read
        con = connect_read(args.db)
        try:
            identities = con.execute(
                "SELECT provider,model_name,dimension,fingerprint FROM embeddings_meta GROUP BY ALL"
            ).fetchall()
        finally:
            con.close()
        if len(identities) != 1 or identities[0][0] != "sentence-transformers":
            raise RuntimeError("persisted embedding identity is not a supported sentence-transformer")
        model = SentenceTransformerEmbedding(str(identities[0][1]))
    sub = TurbopufferSubstrate.open(args.db, model=model,
                                    api_key=os.environ.get("TURBOPUFFER_API_KEY"),
                                    region=args.region)
    try:
        if args.action == "status":
            result = sub.readiness()
            try:
                result["embedding"] = sub.canonical_embedding_identity()
            except Exception as exc:  # noqa: BLE001 — operator snapshot
                result["embedding_error"] = type(exc).__name__
        elif args.action == "rebuild":
            result = sub.rebuild_shadow(dry_run=args.dry_run)
        elif args.action == "promote":
            result = sub.promote(args.manifest, confirmation=args.confirm)
        elif args.action == "benchmark":
            queries = json.loads(Path(args.query_set).read_text(encoding="utf-8"))
            if not isinstance(queries, list) or len(queries) < 20:
                raise SystemExit("benchmark query set must contain >=20 rows")
            rows: list[dict[str, Any]] = []
            for index, item in enumerate(queries):
                if not isinstance(item, dict) or set(item) != {
                        "query_id", "query", "expected_ids", "baseline_ids"}:
                    raise SystemExit("query rows require exact blinded benchmark schema")
                query = str(item["query"])
                query_id = str(item["query_id"])
                if query_id != __import__("hashlib").sha256(query.encode()).hexdigest():
                    raise SystemExit("query_id must be the SHA-256 of query")
                expected = item["expected_ids"]
                baseline_ids = item["baseline_ids"]
                if (not isinstance(expected, list) or not expected or len(expected) > 100 or
                        not isinstance(baseline_ids, list) or len(baseline_ids) > 10):
                    raise SystemExit("bounded expected_ids/baseline_ids required")
                started = time.perf_counter()
                outcome = sub.query(query, top_k=10, allow_fallback=False)
                ids = [r["chunk_id"] for r in outcome["results"]]
                relevant = set(map(str, expected))
                recall = len(set(ids) & relevant) / len(relevant) if relevant else 0.0
                baseline_recall = len(set(map(str, baseline_ids)) & relevant) / len(relevant)
                improvement = (recall - baseline_recall) * 100
                row = {"index": index, "query_id": query_id,
                       "status": outcome.get("status"),
                       "latency_ms": round((time.perf_counter()-started)*1000, 3),
                       "recall_at_10": recall, "baseline_recall_at_10": baseline_recall,
                       "delta_percentage_points": improvement}
                if args.include_result_ids:
                    row["result_ids"] = ids
                rows.append(row)
            wins = sum(1 for row in rows if row["status"] in {"shadow", "servable"} and
                       row["delta_percentage_points"] >= 15)
            passed = wins / len(rows) >= 0.70
            artifact = {"status": "measured", "namespace": sub._namespace_name,
                        "embedding": sub.canonical_embedding_identity(),
                        "query_count": len(rows), "rows": rows,
                        "ratchet": {"required_improvement_pct": 15,
                                    "required_query_fraction": 0.70,
                                    "operator_wins": wins,
                                    "passed": passed}}
            Path(args.output).write_text(json.dumps(artifact, sort_keys=True), encoding="utf-8")
            result = {"status": "artifact-written", "output": args.output,
                      "query_count": len(rows), "passed": passed}
        else:
            if args.dry_run:
                result = {"status": "dry-run", "action": "query", "network": False}
            else:
                raw = sub.query(args.query)
                result = {"status": raw.get("status")}
                if args.include_result_ids:
                    result["result_ids"] = [r["chunk_id"] for r in raw.get("results", [])]
        print(json.dumps(result, sort_keys=True))
    finally:
        sub.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
