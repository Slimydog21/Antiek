"""Single-namespace Turbopuffer SERVABLE hybrid index (shadow → promote).

DuckDB/graph remains source of truth. TurboPuffer holds a SERVABLE-only
secondary hybrid retrieval index for rights-clean external chunks
(``TURBOPUFFER_INDEX_CONTENT_CLASSES``). Rebuild is explicit; promote writes
a local active pointer; successful queries report ``status: "servable"``
when that pointer is active, else ``status: "shadow"``. Query always
hydrates/gates via DuckDB and falls back to canonical search on vendor
failure. Not the default talk-to-book mount — enable via
``ANTIEK_TURBOPUFFER_SERVABLE`` / ``ANTIEK_TURBOPUFFER_SHADOW_ENABLED``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from runtime.db_lock import connect_read
from substrate.constants import TURBOPUFFER_INDEX_CONTENT_CLASSES
from substrate.graph.embedding_meta import _identity
from substrate.graph.retrieval_adapters.turbopuffer_client import (
    ShadowNamespace,
    make_namespace,
    response_rows,
)
from substrate.graph.retrieval_gate import non_privileged_chunk_sql_clause
from substrate.graph.search import EmbeddingModel, search

_SKIPPED = "skipped — no credentials"
_ENABLE_ENV = "ANTIEK_TURBOPUFFER_SHADOW_ENABLED"
_SERVABLE_ENABLE_ENV = "ANTIEK_TURBOPUFFER_SERVABLE"
_MAX_ROWS_ENV = "ANTIEK_TURBOPUFFER_MAX_ROWS"
_DEFAULT_MAX_ROWS = 50_000
DEFAULT_NAMESPACE = "antiek-shadow-chunks-v1"
_FORBIDDEN_NAMESPACE_PARTS = ("user", "investigation", "shard")


def _fts_enabled(value: Any) -> bool:
    """Official SDK returns True on write schema and a config object on metadata."""
    return value is not False and value is not None


def _content_digest_row(row: dict[str, Any]) -> dict[str, Any]:
    """Hash identity without float vectors (TurboPuffer stores float32)."""
    return {
        "id": row["id"],
        "text": row["text"],
        "document_id": row["document_id"],
        "source_tier": int(row["source_tier"]) if row.get("source_tier") is not None else None,
        "content_class": row["content_class"],
    }


def _vectors_close(a: Sequence[float] | None, b: Sequence[float] | None, *, tol: float = 1e-5) -> bool:
    if a is None or b is None or len(a) != len(b):
        return False
    return max(abs(float(x) - float(y)) for x, y in zip(a, b, strict=True)) <= tol



def _validate_namespace(value: str) -> str:
    staging = value.startswith(DEFAULT_NAMESPACE + "-") and len(value) == len(DEFAULT_NAMESPACE) + 13
    if (value != DEFAULT_NAMESPACE and not staging) or any(part in value.lower() for part in _FORBIDDEN_NAMESPACE_PARTS):
        raise ValueError(f"shadow namespace must be {DEFAULT_NAMESPACE} or its digest staging form")
    return value



def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes"}


def _max_export_rows() -> int:
    raw = os.environ.get(_MAX_ROWS_ENV, "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return _DEFAULT_MAX_ROWS


class TurbopufferSubstrate:
    name = "turbopuffer"

    def __init__(self, con: Any, *, model: EmbeddingModel, api_key: str | None,
                 namespace: ShadowNamespace | None = None,
                 namespace_name: str = DEFAULT_NAMESPACE, region: str = "gcp-us-central1",
                 manifest_dir: str | Path | None = None, db_identity: str = "injected"):
        self._con, self._model, self._api_key = con, model, api_key
        self._namespace = namespace
        self._namespace_name = _validate_namespace(namespace_name)
        self._region = region
        self._manifest_dir = Path(manifest_dir or ".antiek/turbopuffer-shadow")
        self._context = {"region": region, "db_identity": db_identity,
                         "account_identity": hashlib.sha256((api_key or "").encode()).hexdigest()[:16]}
        enabled = _env_truthy(_ENABLE_ENV) or _env_truthy(_SERVABLE_ENABLE_ENV)
        self.status: str | None = None if api_key and (namespace is not None or enabled) else _SKIPPED

    @classmethod
    def open(cls, db_path: str, *, model: EmbeddingModel, api_key: str | None = None,
             namespace: ShadowNamespace | None = None,
             namespace_name: str = DEFAULT_NAMESPACE,
             region: str = "gcp-us-central1", manifest_dir: str | Path | None = None) -> TurbopufferSubstrate:
        key = api_key if api_key is not None else os.environ.get("TURBOPUFFER_API_KEY")
        db_identity = hashlib.sha256(str(Path(db_path).resolve()).encode()).hexdigest()
        return cls(connect_read(db_path), model=model, api_key=key, namespace=namespace,
                   namespace_name=namespace_name, region=region, manifest_dir=manifest_dir,
                   db_identity=db_identity)

    @property
    def skipped(self) -> bool:
        return self.status == _SKIPPED

    def active_pointer(self) -> dict[str, Any] | None:
        """Return the local promote pointer if present and context-matched."""
        pointer = self._manifest_dir / "active.json"
        if not pointer.exists():
            return None
        active = json.loads(pointer.read_text(encoding="utf-8"))
        if active.get("context") != self._context:
            return None
        return active

    def query_status_label(self) -> str:
        """``servable`` when a promote pointer is active; else ``shadow``."""
        return "servable" if self.active_pointer() is not None else "shadow"

    def readiness(self) -> dict[str, Any]:
        """Operator-facing SERVABLE readiness snapshot (no network)."""
        pointer = self.active_pointer()
        return {
            "adapter": self.name,
            "skipped": self.skipped,
            "api_key_present": bool(self._api_key),
            "shadow_enabled": _env_truthy(_ENABLE_ENV),
            "servable_enabled": _env_truthy(_SERVABLE_ENABLE_ENV),
            "namespace_default": self._namespace_name,
            "active_namespace": None if pointer is None else pointer.get("active_namespace"),
            "content_hash": None if pointer is None else pointer.get("content_hash"),
            "query_status_if_live": self.query_status_label(),
            "export_classes": sorted(TURBOPUFFER_INDEX_CONTENT_CLASSES),
            "max_export_rows": _max_export_rows(),
            "duckdb_is_sot": True,
            "production_default_mount": False,
        }

    def eligible_stats(self) -> dict[str, Any]:
        """Count DuckDB SoT rows eligible for the TurboPuffer SERVABLE index."""
        allowed = sorted(TURBOPUFFER_INDEX_CONTENT_CLASSES)
        placeholders = ",".join("?" for _ in allowed)
        docs = self._con.execute(
            f"SELECT count(*) FROM documents WHERE content_class IN ({placeholders})",
            allowed,
        ).fetchone()[0]
        chunks = self._con.execute(
            "SELECT count(*) FROM chunks c JOIN documents d ON d.document_id=c.document_id "
            f"WHERE d.content_class IN ({placeholders})",
            allowed,
        ).fetchone()[0]
        with_emb = self._con.execute(
            "SELECT count(*) FROM chunks c JOIN documents d ON d.document_id=c.document_id "
            f"WHERE c.embedding IS NOT NULL AND d.content_class IN ({placeholders})",
            allowed,
        ).fetchone()[0]
        with_meta = self._con.execute(
            "SELECT count(*) FROM embeddings_meta em "
            "JOIN chunks c USING(chunk_id) "
            "JOIN documents d ON d.document_id=c.document_id "
            f"WHERE d.content_class IN ({placeholders})",
            allowed,
        ).fetchone()[0]
        return {
            "export_classes": allowed,
            "documents": int(docs),
            "chunks": int(chunks),
            "chunks_with_embedding": int(with_emb),
            "chunks_with_embeddings_meta": int(with_meta),
            "export_ready": int(with_emb) == int(with_meta),
        }

    def _ns(self) -> ShadowNamespace:
        if self._namespace is None:
            if not self._api_key:
                raise RuntimeError(_SKIPPED)
            pointer = self._manifest_dir / "active.json"
            namespace = self._namespace_name
            if pointer.exists():
                active = json.loads(pointer.read_text(encoding="utf-8"))
                if active.get("context") != self._context:
                    raise RuntimeError("active namespace pointer context mismatch")
                namespace = _validate_namespace(active["active_namespace"])
            self._namespace = make_namespace(api_key=self._api_key, region=self._region,
                                             namespace=namespace)
        return self._namespace

    def rebuild_shadow(self, *, dry_run: bool = False, batch_size: int = 500) -> dict[str, Any]:
        meta = self._con.execute(
            "SELECT provider,model_name,dimension,fingerprint,count(*) FROM embeddings_meta "
            "GROUP BY ALL"
        ).fetchall()
        if len(meta) != 1:
            raise RuntimeError("canonical graph must have one complete embedding identity")
        provider, model_name, dimension, fingerprint, _meta_count = meta[0]
        live_identity = _identity(self._model)
        if (not dry_run and
                (provider, model_name, int(dimension), fingerprint) != live_identity):
            raise RuntimeError("embedding provider/model/version/dimension mismatch")
        if dry_run and int(dimension) != int(self._model.dimension):
            raise RuntimeError("embedding dimension mismatch")
        allowed = sorted(TURBOPUFFER_INDEX_CONTENT_CLASSES)
        placeholders = ",".join("?" for _ in allowed)
        rows = self._con.execute(
            "SELECT c.chunk_id,c.embedding,c.text,c.document_id,d.source_tier,"
            "d.content_class FROM chunks c JOIN documents d ON d.document_id=c.document_id "
            f"WHERE c.embedding IS NOT NULL AND d.content_class IN ({placeholders}) ORDER BY c.chunk_id",
            allowed,
        ).fetchall()
        payload = [{"id": r[0], "vector": list(r[1]), "text": r[2],
                    "document_id": r[3], "source_tier": r[4],
                    "content_class": r[5] or "legacy_null"} for r in rows]
        digest_rows = [_content_digest_row(row) for row in payload]
        digest_input = json.dumps({"rows": digest_rows, "fingerprint": fingerprint,
                                   "model": model_name, "dimension": int(dimension)},
                                  sort_keys=True, separators=(",", ":")).encode()
        content_hash = hashlib.sha256(digest_input).hexdigest()
        staging = f"{DEFAULT_NAMESPACE}-{content_hash[:12]}"
        manifest = {"namespace": staging, "row_count": len(payload), "content_hash": content_hash,
                    "embedding": {"provider": provider, "model": model_name,
                                  "version": fingerprint, "dimension": dimension},
                    "context": self._context,
                    "status": "dry-run" if dry_run else "staged"}
        covered = self._con.execute(
            f"SELECT count(*) FROM embeddings_meta em JOIN chunks c USING(chunk_id) "
            f"JOIN documents d ON d.document_id=c.document_id WHERE d.content_class IN ({placeholders})",
            allowed).fetchone()[0]
        if int(covered) != len(payload):
            raise RuntimeError("embedding metadata does not exactly cover export allowlist")
        if dry_run:
            return {"status": "dry-run", "namespace": self._namespace_name,
                    "staging_namespace": staging, "eligible_rows": len(payload),
                    "content_hash": content_hash, "batches": math.ceil(len(payload) / batch_size),
                    "embedding": manifest["embedding"]}
        # Incremental: skip vendor rewrite when active SERVABLE pointer already
        # matches this exact rights-clean export digest (cron-friendly no-op).
        active = self.active_pointer()
        if active and active.get("content_hash") == content_hash:
            return {
                "status": "unchanged",
                "namespace": active.get("active_namespace"),
                "row_count": len(payload),
                "content_hash": content_hash,
                "eligible_rows": len(payload),
                "embedding": manifest["embedding"],
                "incremental": True,
            }
        ns = self._namespace or make_namespace(api_key=self._api_key or "", region=self._region,
                                               namespace=staging)
        max_rows = _max_export_rows()
        if len(payload) > max_rows:
            raise RuntimeError(
                f"Turbopuffer export verification is bounded to {max_rows} rows "
                f"(set {_MAX_ROWS_ENV} to raise for SERVABLE-scale rebuilds)"
            )
        for start in range(0, len(payload), batch_size):
            ns.write(upsert_rows=payload[start:start + batch_size],
                     distance_metric="cosine_distance",
                     schema={"text": {"type": "string", "full_text_search": True}},
                     timeout=30.0)
        verified = ns.query(rank_by=("id", "asc"), limit=max(1, len(payload)),
                            include_attributes=True,
                            consistency={"level": "strong"}, timeout=30.0)
        verified_payload = []
        for row in getattr(verified, "rows", ()):
            verified_payload.append({key: getattr(row, key) for key in
                                     ("id", "vector", "text", "document_id", "source_tier",
                                      "content_class")})
        verified_rows = [_content_digest_row(row) for row in verified_payload]
        verified_hash = hashlib.sha256(json.dumps(
            {"rows": verified_rows, "fingerprint": fingerprint, "model": model_name,
             "dimension": int(dimension)}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        by_id = {row["id"]: row for row in payload}
        vectors_ok = all(
            rid in by_id and _vectors_close(by_id[rid]["vector"], row.get("vector"))
            for rid, row in ((r["id"], r) for r in verified_payload)
        )
        metadata = ns.metadata(timeout=30.0)
        schema = getattr(metadata, "schema_", {})
        text_schema = schema.get("text") if isinstance(schema, dict) else None
        text_fts = getattr(text_schema, "full_text_search", None)
        if isinstance(text_schema, dict):
            text_fts = text_schema.get("full_text_search")
        if (len(verified_payload) != len(payload) or verified_hash != content_hash or
                not vectors_ok or
                getattr(metadata, "approx_row_count", len(payload)) != len(payload) or
                not _fts_enabled(text_fts)):
            raise RuntimeError("staging namespace row-count/content-hash verification failed")
        self._manifest_dir.mkdir(parents=True, exist_ok=True)
        path = self._manifest_dir / f"{content_hash}.json"
        path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        return {**manifest, "manifest_path": str(path)}

    def promote(self, manifest_path: str | Path, *, confirmation: str) -> dict[str, Any]:
        path = Path(manifest_path)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        expected = "PROMOTE-" + manifest["content_hash"][:12]
        if confirmation != expected or manifest.get("status") != "staged":
            raise ValueError(f"explicit confirmation token required: {expected}")
        if manifest.get("context") != self._context:
            raise ValueError("manifest account/region/database context mismatch")
        if manifest.get("namespace") != f"{DEFAULT_NAMESPACE}-{manifest['content_hash'][:12]}":
            raise ValueError("manifest namespace digest mismatch")
        self._manifest_dir.mkdir(parents=True, exist_ok=True)
        pointer = self._manifest_dir / "active.json"
        prior = json.loads(pointer.read_text()) if pointer.exists() else None
        pointer.write_text(json.dumps({"active_namespace": manifest["namespace"],
                                      "content_hash": manifest["content_hash"],
                                      "context": self._context,
                                      "rollback": prior}, sort_keys=True), encoding="utf-8")
        return {"status": "promoted-local-pointer", "namespace": manifest["namespace"],
                "rollback_available": prior is not None}

    def canonical_embedding_identity(self) -> dict[str, Any]:
        rows = self._con.execute(
            "SELECT provider,model_name,dimension,fingerprint FROM embeddings_meta GROUP BY ALL"
        ).fetchall()
        if len(rows) != 1:
            raise RuntimeError("canonical graph must have one complete embedding identity")
        provider, model, dimension, version = rows[0]
        return {"provider": provider, "model": model, "version": version,
                "dimension": int(dimension)}

    def query(self, text: str, *, top_k: int = 5, source_tier_max: int | None = None,
              document_ids: Sequence[str] | None = None,
              policy_tag: str = "attribution_eligible",
              allow_fallback: bool = True) -> dict[str, Any]:
        if policy_tag != "attribution_eligible":
            raise ValueError("Turbopuffer SERVABLE index supports attribution_eligible only")
        if self.skipped:
            return {"query": text, "top_k": top_k, "results": [], "node_matches": [],
                    "status": _SKIPPED}
        def fallback(reason: str) -> dict[str, Any]:
            if not allow_fallback:
                return {"query": text, "top_k": top_k, "results": [], "node_matches": [],
                        "status": "benchmark-failed", "failure_reason": reason}
            return {
                **search(self._con, text, model=self._model, top_k=top_k,
                         source_tier_max=source_tier_max, document_ids=document_ids,
                         policy_tag=policy_tag),
                "status": "degraded — brute_force", "degraded_reason": reason,
            }
        if document_ids is not None and not document_ids:
            return fallback("empty document scope")
        query_vec = list(self._model.encode(text))
        filters: list[Any] = []
        if source_tier_max is not None:
            filters.append(("source_tier", "Lte", int(source_tier_max)))
        if document_ids is not None:
            filters.append(("document_id", "In", list(document_ids)))
        filter_arg: Any = ("And", filters) if len(filters) > 1 else (filters[0] if filters else None)
        try:
            response = self._ns().multi_query(
                queries=[{"rank_by": ("vector", "ANN", query_vec), "limit": top_k,
                          **({"filters": filter_arg} if filter_arg else {})},
                         {"rank_by": ("text", "BM25", text), "limit": top_k,
                          **({"filters": filter_arg} if filter_arg else {})}],
                rerank_by=("RRF",), consistency={"level": "strong"}, timeout=30.0)
            ids = [str(getattr(row, "id", "")) for row in response_rows(response) if getattr(row, "id", None)]
            if not ids:
                return fallback("vendor returned no candidates")
            placeholders = ",".join("?" for _ in ids)
            gate_sql, gate_params = non_privileged_chunk_sql_clause(
                table_alias="d", policy_tag=policy_tag, owner_user_id="__operator__")
            sql = (
                "SELECT c.chunk_id,c.section_path,c.text,c.token_count,c.document_id,c.chunk_index,"
                "d.title,d.source_tier,d.document_type,c.embedding FROM chunks c JOIN documents d "
                f"ON d.document_id=c.document_id WHERE c.chunk_id IN ({placeholders})" + gate_sql
            )
            params: list[Any] = ids + gate_params
            if source_tier_max is not None:
                sql += " AND d.source_tier <= ?"
                params.append(int(source_tier_max))
            if document_ids is not None:
                doc_placeholders = ",".join("?" for _ in document_ids)
                sql += f" AND c.document_id IN ({doc_placeholders})"
                params.extend(document_ids)
            rows = self._con.execute(sql, params).fetchall()
            by_id = {r[0]: r for r in rows}
            results = []
            for cid in ids:
                r = by_id.get(cid)
                if r is None:
                    continue
                dot = sum(float(a) * float(b) for a, b in zip(r[9], query_vec, strict=True))
                denom = math.sqrt(sum(float(a) ** 2 for a in r[9])) * math.sqrt(sum(float(b) ** 2 for b in query_vec))
                results.append({"chunk_id": r[0], "section_path": r[1], "chunk_text": r[2],
                                "token_count": r[3], "document_id": r[4], "chunk_index": r[5],
                                "document_title": r[6], "source_tier": r[7], "document_type": r[8],
                                "similarity": dot / denom if denom else 0.0})
            return {"query": text, "top_k": top_k, "results": results[:top_k],
                    "node_matches": [], "status": self.query_status_label()}
        except Exception as exc:
            return fallback(type(exc).__name__)

    def sync_servable(
        self,
        *,
        dry_run: bool = False,
        batch_size: int = 500,
        auto_promote: bool = False,
        confirm: str | None = None,
    ) -> dict[str, Any]:
        """Rebuild if the eligible export digest changed; optionally promote.

        DuckDB remains SoT. This is the cron entrypoint for incremental
        TurboPuffer refresh (no-op when ``content_hash`` matches active pointer).
        """
        stats = self.eligible_stats()
        staged = self.rebuild_shadow(dry_run=dry_run, batch_size=batch_size)
        out: dict[str, Any] = {"eligible": stats, "rebuild": staged}
        if dry_run or staged.get("status") in {"unchanged", "dry-run"}:
            out["status"] = staged.get("status")
            return out
        if not auto_promote:
            out["status"] = "staged"
            return out
        promoted = self.promote(staged["manifest_path"], confirmation=confirm or "")
        out["promote"] = promoted
        out["status"] = "synced"
        return out

    def close(self) -> None:
        self._con.close()
