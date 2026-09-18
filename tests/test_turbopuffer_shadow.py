from __future__ import annotations

import importlib
import json
import subprocess
import sys
from dataclasses import dataclass

import pytest

from benchmarks.retrieval_bench import HashEmbedding, seed_graph
from runtime.db_lock import connect_write
from substrate.graph.embedding_meta import _identity
from substrate.graph.retrieval_adapters.turbopuffer import TurbopufferSubstrate
from tools.turbopuffer_shadow import main


@dataclass
class Row:
    id: str
    vector: list[float] | None = None
    text: str | None = None
    document_id: str | None = None
    source_tier: int | None = None
    content_class: str | None = None


@dataclass
class Result:
    rows: list[Row]


@dataclass
class Response:
    results: list[Result]


class FakeNamespace:
    def __init__(self):
        self.writes = []
        self.queries = []
        self.ids: list[str] = []
        self.error: Exception | None = None
        self.upserted: list[str] = []
        self.upserted_rows = []
        self.corrupt_verification = False

    def write(self, **kwargs):
        self.writes.append(kwargs)
        self.upserted.extend(str(row["id"]) for row in kwargs.get("upsert_rows", []))
        self.upserted_rows.extend(kwargs.get("upsert_rows", []))

    def query(self, **kwargs):
        rows = [dict(r) for r in sorted(self.upserted_rows, key=lambda x: x["id"])]
        if self.corrupt_verification and rows:
            rows[0]["text"] = "tampered"
        return type("QueryResponse", (), {"rows": [Row(**r) for r in rows]})()

    def metadata(self, **kwargs):
        return type("Metadata", (), {"approx_row_count": len(self.upserted_rows),
                                     "schema_": {"text": {"type": "string",
                                                           "full_text_search": True}}})()

    def multi_query(self, **kwargs):
        self.queries.append(kwargs)
        if self.error:
            raise self.error
        return Response([Result([Row(i) for i in self.ids])])


@pytest.fixture
def graph(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    seed_graph(db, HashEmbedding())
    con = connect_write(db, purpose="tpuf-test-meta")
    try:
        rows = con.execute("SELECT chunk_id FROM chunks WHERE embedding IS NOT NULL").fetchall()
        provider, model, dim, fingerprint = _identity(HashEmbedding())
        con.executemany("INSERT OR REPLACE INTO embeddings_meta VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)",
                        [(r[0], provider, model, dim, fingerprint) for r in rows])
    finally:
        con.close()
    return db


def test_dry_rebuild_excludes_private_and_never_touches_vendor(graph):
    fake = FakeNamespace()
    sub = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x", namespace=fake)
    result = sub.rebuild_shadow(dry_run=True)
    assert result["eligible_rows"] > 0
    assert fake.writes == []
    sub.rebuild_shadow()
    serialized = json.dumps(fake.writes)
    assert "c-restricted-1" not in serialized
    assert "c-personal-1" not in serialized
    assert all("sharding" not in call for call in fake.writes)
    assert result["status"] == "dry-run"


def test_staging_manifest_and_explicit_local_promotion(graph, tmp_path):
    fake = FakeNamespace()
    sub = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x", namespace=fake,
                                    manifest_dir=tmp_path / "manifests")
    staged = sub.rebuild_shadow()
    assert staged["namespace"].startswith("antiek-shadow-chunks-v1-")
    assert staged["status"] == "staged"
    assert all("delete_by_filter" not in write for write in fake.writes)
    with pytest.raises(ValueError, match="confirmation"):
        sub.promote(staged["manifest_path"], confirmation="yes")
    promoted = sub.promote(staged["manifest_path"],
                           confirmation="PROMOTE-" + staged["content_hash"][:12])
    assert promoted["status"] == "promoted-local-pointer"


def test_query_ann_bm25_rrf_and_canonical_hydration_drops_vendor_injection(graph):
    fake = FakeNamespace()
    fake.ids = ["c-restricted-1", "foreign", "c-quera-1"]
    sub = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x", namespace=fake)
    result = sub.query("neutral atom", top_k=4, source_tier_max=2,
                       document_ids=["doc-quera"])
    assert [r["chunk_id"] for r in result["results"]] == ["c-quera-1"]
    call = fake.queries[0]
    assert call["rerank_by"] == ("RRF",)
    assert call["consistency"] == {"level": "strong"}
    assert call["queries"][0]["rank_by"][1] == "ANN"
    assert call["queries"][1]["rank_by"][1] == "BM25"


def test_vendor_failure_falls_back_explicitly(graph):
    fake = FakeNamespace()
    fake.error = RuntimeError("outage")
    sub = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x", namespace=fake)
    result = sub.query("quantum")
    assert result["status"] == "degraded — brute_force"
    assert result["degraded_reason"] == "RuntimeError"
    assert result["results"]


def test_benchmark_mode_never_falls_back(graph):
    fake = FakeNamespace()
    fake.error = RuntimeError("outage")
    sub = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x", namespace=fake)
    result = sub.query("quantum", allow_fallback=False)
    assert result["status"] == "benchmark-failed"
    assert result["results"] == []


def test_private_policy_and_namespace_derivation_rejected(graph):
    sub = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x",
                                    namespace=FakeNamespace())
    with pytest.raises(ValueError, match="attribution_eligible"):
        sub.query("x", policy_tag="operator_only")
    with pytest.raises(ValueError, match="shadow namespace"):
        TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x",
                                  namespace=FakeNamespace(), namespace_name="users.1")


def test_rebuild_refuses_embedding_identity_mismatch(graph):
    class WrongModel(HashEmbedding):
        model_name = "wrong-model"

    sub = TurbopufferSubstrate.open(graph, model=WrongModel(), api_key="x",
                                    namespace=FakeNamespace())
    with pytest.raises(RuntimeError, match="provider/model/version/dimension mismatch"):
        sub.rebuild_shadow()


def test_rebuild_detects_vendor_content_corruption(graph):
    fake = FakeNamespace()
    fake.corrupt_verification = True
    sub = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x", namespace=fake)
    with pytest.raises(RuntimeError, match="content-hash"):
        sub.rebuild_shadow()


def test_external_allowlist_excludes_null_content_class(graph):
    con = connect_write(graph, purpose="tpuf-test-null-class")
    try:
        con.execute("UPDATE documents SET content_class=NULL WHERE document_id='doc-quera'")
    finally:
        con.close()
    fake = FakeNamespace()
    sub = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x", namespace=fake)
    sub.rebuild_shadow()
    assert all(row["document_id"] != "doc-quera" for row in fake.upserted_rows)


def test_cli_help_and_dry_run_are_reachable_without_credentials(graph):
    help_run = subprocess.run([sys.executable, "-m", "tools.turbopuffer_shadow", "--help"],
                              text=True, capture_output=True, check=False)
    assert help_run.returncode == 0
    assert "DuckDB remains SoT" in help_run.stdout or "SERVABLE" in help_run.stdout
    run = subprocess.run([sys.executable, "-m", "tools.turbopuffer_shadow", "rebuild",
                          "--db", graph, "--dry-run"], text=True, capture_output=True,
                         check=False)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["status"] == "dry-run"


def test_benchmark_artifact_requires_twenty_and_redacts_content(graph, tmp_path, monkeypatch):
    embed_module = importlib.import_module("processing.embedding.embed")

    monkeypatch.setattr(embed_module, "SentenceTransformerEmbedding", lambda _name: HashEmbedding())
    con = connect_write(graph, purpose="tpuf-cli-model-identity")
    try:
        con.execute("UPDATE embeddings_meta SET provider='sentence-transformers'")
    finally:
        con.close()
    query_set = tmp_path / "queries.json"
    secret = "private-query-body-must-not-leak"
    query_set.write_text(json.dumps([
        {"query": f"{secret}-{index}",
         "query_id": __import__("hashlib").sha256(f"{secret}-{index}".encode()).hexdigest(),
         "expected_ids": ["c-quera-1"], "baseline_ids": ["c-quera-1"]}
        for index in range(20)
    ]), encoding="utf-8")
    output = tmp_path / "artifact.json"
    assert main(["benchmark", "--db", graph, "--query-set", str(query_set),
                 "--output", str(output)]) == 0
    artifact_text = output.read_text(encoding="utf-8")
    artifact = json.loads(artifact_text)
    assert secret not in artifact_text
    assert artifact["query_count"] == 20
    assert artifact["embedding"]["dimension"] == HashEmbedding.dimension
    assert all("result_ids" not in row for row in artifact["rows"])
    assert artifact["ratchet"]["passed"] is False


def test_promoted_pointer_context_drives_vendor_namespace(graph, tmp_path, monkeypatch):
    fake = FakeNamespace()
    sub = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x", namespace=fake,
                                    manifest_dir=tmp_path)
    staged = sub.rebuild_shadow()
    sub.promote(staged["manifest_path"],
                confirmation="PROMOTE-" + staged["content_hash"][:12])
    made = []
    monkeypatch.setattr(
        "substrate.graph.retrieval_adapters.turbopuffer.make_namespace",
        lambda **kwargs: made.append(kwargs["namespace"]) or FakeNamespace())
    active = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x",
                                       manifest_dir=tmp_path)
    active._ns()
    assert made == [staged["namespace"]]


def test_promoted_query_reports_servable_status(graph, tmp_path, monkeypatch):
    fake = FakeNamespace()
    sub = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x", namespace=fake,
                                    manifest_dir=tmp_path)
    staged = sub.rebuild_shadow()
    assert staged["row_count"] >= 1
    fake.ids = [str(row["id"]) for row in fake.upserted_rows]
    assert sub.query_status_label() == "shadow"
    pre = sub.query("government", top_k=1, allow_fallback=False)
    assert pre["status"] == "shadow"
    assert pre["results"], "vendor ids must hydrate from DuckDB SoT"
    sub.promote(staged["manifest_path"],
                confirmation="PROMOTE-" + staged["content_hash"][:12])
    assert sub.query_status_label() == "servable"
    post = sub.query("government", top_k=1, allow_fallback=False)
    assert post["status"] == "servable"
    assert post["results"]



def test_servable_env_enables_without_shadow_flag(graph, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTIEK_TURBOPUFFER_SHADOW_ENABLED", raising=False)
    monkeypatch.setenv("ANTIEK_TURBOPUFFER_SERVABLE", "1")
    sub = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x",
                                    manifest_dir=tmp_path)
    assert not sub.skipped
    ready = sub.readiness()
    assert ready["servable_enabled"] is True
    assert ready["duckdb_is_sot"] is True
    assert ready["production_default_mount"] is False
    assert "public_domain" in ready["export_classes"]


def test_max_rows_env_bounds_rebuild(graph, tmp_path, monkeypatch):
    fake = FakeNamespace()
    monkeypatch.setenv("ANTIEK_TURBOPUFFER_MAX_ROWS", "1")
    from substrate.graph.retrieval_adapters import turbopuffer as mod
    assert mod._max_export_rows() == 1
    sub = TurbopufferSubstrate.open(graph, model=HashEmbedding(), api_key="x", namespace=fake,
                                    manifest_dir=tmp_path)
    dry = sub.rebuild_shadow(dry_run=True)
    if dry["eligible_rows"] > 1:
        with pytest.raises(RuntimeError, match="bounded"):
            sub.rebuild_shadow()



def test_cli_status_action(graph, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTIEK_TURBOPUFFER_SERVABLE", "1")
    fake = FakeNamespace()
    # status does not need network; open with key via env
    monkeypatch.setenv("TURBOPUFFER_API_KEY", "x")
    assert main(["status", "--db", graph]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["duckdb_is_sot"] is True
    assert out["adapter"] == "turbopuffer"
