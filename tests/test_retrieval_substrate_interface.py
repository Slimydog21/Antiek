"""SPR-05 M1/M3 — RetrievalSubstrate interface + §9.0 gate + §16 read-only tests.

Asserts:
  - the DuckDB-VSS impl returns BYTE-FOR-BYTE the search() shape and IDENTICAL
    ordering to the brute-force reference on the same seeded graph (M1),
  - the §9.0 retrieval-time gate is preserved across the seam for BOTH the
    reference and VSS impls (restricted content excluded under
    attribution_eligible, included under private_research),
  - every adapter (vss, brute_force, turbopuffer, ducklake) opens the graph DB
    read-only and changes no chunks/nodes/edges row count (§16 single-writer),
  - the credential-gated adapters self-report skipped without crashing,
  - the factory rejects unknown kinds and never imports a vendor on the default
    path.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from benchmarks.retrieval_bench import HashEmbedding, row_counts, seed_graph
from runtime.db_lock import connect_write
from substrate.graph import retrieval_substrate as _rs
from substrate.graph.retrieval_substrate import (
    RetrievalSubstrate,
    make_substrate,
)
from substrate.graph.search import search

# Hang-proof probe (LOAD-only, memoized, NO network install unless the operator
# opts in via ANTIEK_VSS_ALLOW_INSTALL). On a network-restricted CI runner this
# returns False instantly, so vss-active-only tests SKIP rather than fail/hang.
_VSS_LOADABLE = _rs._vss_loadable_probe()
_requires_vss = pytest.mark.skipif(
    not _VSS_LOADABLE,
    reason="vss extension not loadable without a network install "
           "(set ANTIEK_VSS_ALLOW_INSTALL=1 on a networked box to install it)",
)


@pytest.fixture(autouse=True)
def _no_turbopuffer_credentials(monkeypatch):
    """Pin the credential-free adapter contracts at the test boundary."""
    monkeypatch.delenv("TURBOPUFFER_API_KEY", raising=False)
    monkeypatch.delenv("ANTIEK_TURBOPUFFER_SERVABLE", raising=False)
    monkeypatch.delenv("DUCKLAKE_CATALOG", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)


@pytest.fixture
def seeded_db():
    emb = HashEmbedding()
    d = tempfile.mkdtemp(prefix="antiek-spr05-iface-")
    db = os.path.join(d, "graph.duckdb")
    counts = seed_graph(db, emb)
    with connect_write(db, purpose="pa02-interface-owner-fixture") as con:
        con.execute(
            "UPDATE documents SET owner_user_id='owner-a' "
            "WHERE document_id='doc-personal'"
        )
    yield db, emb, counts


# ---------------------------------------------------------------------------
# M1 — shape + ordering parity
# ---------------------------------------------------------------------------


def test_protocol_runtime_checkable(seeded_db):
    db, emb, _ = seeded_db
    vss = make_substrate("vss", db, model=emb)
    bf = make_substrate("brute_force", db, model=emb)
    try:
        assert isinstance(vss, RetrievalSubstrate)
        assert isinstance(bf, RetrievalSubstrate)
        assert vss.name == "vss"
        assert bf.name == "brute_force"
    finally:
        vss.close()
        bf.close()


def test_query_returns_search_shape(seeded_db):
    db, emb, _ = seeded_db
    sub = make_substrate("vss", db, model=emb)
    try:
        res = sub.query("QuEra neutral-atom gate error rate", top_k=5)
        assert set(res.keys()) == {"query", "top_k", "results", "node_matches"}
        assert res["query"] == "QuEra neutral-atom gate error rate"
        assert res["top_k"] == 5
        assert isinstance(res["results"], list)
        if res["results"]:
            item = res["results"][0]
            # same per-item schema as search()
            assert set(item.keys()) == {
                "chunk_id", "section_path", "chunk_text", "token_count",
                "document_id", "chunk_index", "document_title", "source_tier",
                "document_type", "similarity",
            }
    finally:
        sub.close()


@_requires_vss
def test_vss_matches_bruteforce_ordering_and_similarity(seeded_db):
    """The DuckDB-VSS impl must rank IDENTICALLY to the brute-force reference
    on the seeded graph — the HNSW index is exact-equivalent at this scale, so
    a swap is correctness-preserving (M1 acceptance).

    Skipped when the vss extension is not loadable (e.g. network-restricted CI
    with ANTIEK_VSS_ALLOW_INSTALL unset): the brute-force-parity tests below
    keep the correctness coverage; the impl falls back to brute force there."""
    db, emb, _ = seeded_db
    vss = make_substrate("vss", db, model=emb)
    bf = make_substrate("brute_force", db, model=emb)
    try:
        assert vss.vss_active, "VSS extension should be active in this environment"
        for q in (
            "QuEra neutral-atom gate error rate",
            "phased-array radar gain sidelobe",
            "LiFePO4 capacity retention cycling",
            "superconducting decoherence mechanism",
        ):
            rv = vss.query(q, top_k=10)["results"]
            rb = bf.query(q, top_k=10)["results"]
            assert [r["chunk_id"] for r in rv] == [r["chunk_id"] for r in rb], q
            assert [r["similarity"] for r in rv] == [r["similarity"] for r in rb], q
    finally:
        vss.close()
        bf.close()


def test_vss_parity_with_raw_search(seeded_db):
    """The reference impl is a faithful wrapper of the existing search() —
    identical results to calling search() directly."""
    db, emb, _ = seeded_db
    from runtime.db_lock import connect_read

    con = connect_read(db)
    try:
        raw = search(con, "fault tolerance threshold", model=emb, top_k=5)
    finally:
        con.close()
    sub = make_substrate("brute_force", db, model=emb)
    try:
        wrapped = sub.query("fault tolerance threshold", top_k=5)
        assert [r["chunk_id"] for r in wrapped["results"]] == \
               [r["chunk_id"] for r in raw["results"]]
        assert wrapped["query"] == raw["query"]
    finally:
        sub.close()


# ---------------------------------------------------------------------------
# §9.0 gate preservation — both impls
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["vss", "brute_force"])
def test_gate_excludes_restricted_under_attribution_eligible(seeded_db, kind):
    """The seeded graph carries c-restricted-1 (content_class=
    restricted_pending_opt_in). It MUST NOT appear under the default
    attribution_eligible policy, for BOTH impls."""
    db, emb, _ = seeded_db
    sub = make_substrate(kind, db, model=emb)
    try:
        res = sub.query("quantum computing milestones", top_k=20,
                        policy_tag="attribution_eligible")
        ids = {r["chunk_id"] for r in res["results"]}
        assert "c-restricted-1" not in ids, f"{kind} leaked restricted content"
    finally:
        sub.close()


@pytest.mark.parametrize("kind", ["vss", "brute_force"])
def test_gate_includes_restricted_under_private_research(seeded_db, kind):
    """Restricted content IS retrievable under the privileged
    private_research tag — for BOTH impls."""
    db, emb, _ = seeded_db
    sub = make_substrate(kind, db, model=emb)
    try:
        res = sub.query("quantum computing milestones", top_k=20,
                        policy_tag="private_research")
        ids = {r["chunk_id"] for r in res["results"]}
        assert "c-restricted-1" in ids, f"{kind} withheld restricted under private_research"
    finally:
        sub.close()


@pytest.mark.parametrize("kind", ["vss", "brute_force"])
def test_gate_excludes_personal_reading_under_attribution_eligible(seeded_db, kind):
    """The seeded graph carries c-personal-1 (content_class=personal_reading).
    It MUST NOT appear under the default attribution_eligible policy, for BOTH
    impls — same non-privileged gate as search()."""
    db, emb, _ = seeded_db
    sub = make_substrate(kind, db, model=emb)
    try:
        res = sub.query("quantum computing milestones", top_k=20,
                        policy_tag="attribution_eligible")
        ids = {r["chunk_id"] for r in res["results"]}
        assert "c-personal-1" not in ids, f"{kind} leaked personal_reading content"
    finally:
        sub.close()


@pytest.mark.parametrize("kind", ["vss", "brute_force"])
def test_gate_includes_personal_reading_under_operator_only(seeded_db, kind):
    """Owner-only personal_reading IS retrievable under operator_only — for
    BOTH impls."""
    db, emb, _ = seeded_db
    sub = make_substrate(kind, db, model=emb)
    try:
        res = sub.query("quantum computing milestones", top_k=20,
                        policy_tag="operator_only", owner_user_id="owner-a")
        ids = {r["chunk_id"] for r in res["results"]}
        assert "c-personal-1" in ids, f"{kind} withheld personal_reading under operator_only"
    finally:
        sub.close()


def test_unknown_policy_tag_fails_closed(seeded_db):
    """A typo'd policy_tag must default to safe-exclude (the gate fails
    closed) — same posture as search()."""
    db, emb, _ = seeded_db
    sub = make_substrate("vss", db, model=emb)
    try:
        res = sub.query("quantum computing milestones", top_k=20,
                        policy_tag="typo_should_not_unlock")
        ids = {r["chunk_id"] for r in res["results"]}
        assert "c-restricted-1" not in ids
    finally:
        sub.close()


# ---------------------------------------------------------------------------
# §16 single-writer — read-only, no row-count change
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["vss", "brute_force", "turbopuffer", "ducklake"])
def test_read_only_no_row_count_change(seeded_db, kind):
    """Each adapter must change no chunks/nodes/edges row count across a full
    query run (§16 single-writer). The credential-gated adapters skip cleanly."""
    db, emb, before = seeded_db
    sub = make_substrate(kind, db, model=emb)
    try:
        for q in ("quantum", "radar gain", "battery capacity", "bridge load"):
            sub.query(q, top_k=5)
    finally:
        sub.close()
    after = row_counts(db)
    assert after == before, f"{kind} changed row counts: {before} -> {after}"


@pytest.mark.parametrize("kind", ["turbopuffer", "ducklake"])
def test_credential_gated_adapters_skip(seeded_db, kind):
    """Without credentials, vendor adapters self-report skipped.

    DuckLake returns the honest-empty shape. TurboPuffer (SERVABLE hybrid)
    falls back to DuckDB SoT ``search()`` so cascade/reuse still works when
    the env gate is on but the key is absent — dual structure, never crash.
    """
    db, emb, _ = seeded_db
    sub = make_substrate(kind, db, model=emb)
    try:
        assert sub.status == "skipped — no credentials"
        assert sub.skipped is True
        res = sub.query("anything", top_k=5)
        if kind == "turbopuffer":
            assert res["status"] == "degraded — brute_force"
            assert res.get("degraded_reason") == "no credentials"
            # DuckDB SoT may return rows; vendor was not required.
            assert "results" in res
            empty = sub.query("anything", top_k=5, allow_fallback=False)
            assert empty["results"] == []
            assert empty["status"] == "skipped — no credentials"
        else:
            assert res["results"] == []
            assert res["status"] == "skipped — no credentials"
    finally:
        sub.close()


def test_adapters_open_connection_read_only(seeded_db):
    """The adapters open via connect_read — a write through that connection
    raises (read-only enforcement at the DuckDB layer)."""
    db, emb, _ = seeded_db
    sub = make_substrate("turbopuffer", db, model=emb)
    try:
        with pytest.raises(Exception):  # noqa: B017
            sub._con.execute(
                "INSERT INTO documents (document_id, title, source_tier, document_type) "
                "VALUES ('x','x',3,'paper')"
            )
    finally:
        sub.close()


# ---------------------------------------------------------------------------
# Factory hygiene
# ---------------------------------------------------------------------------


def test_factory_rejects_unknown_kind(seeded_db):
    db, emb, _ = seeded_db
    with pytest.raises(ValueError, match="unknown substrate kind"):
        make_substrate("pinecone", db, model=emb)


def test_default_factory_path_imports_no_vendor(tmp_path):
    """Cold default import does not import either vendor adapter."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    private = tmp_path / "cold-import"
    private.mkdir()
    paths = {
        "HOME": private / "home",
        "ANTIEK_HOME": private / "antiek-home",
        "TMPDIR": private / "tmp",
        "ANTIEK_RESEARCH_EVENTS_DIR": private / "events",
        "ANTIEK_RESEARCH_ARTIFACTS_DIR": private / "artifacts",
        "HF_HOME": private / "hf-home",
        "XDG_CACHE_HOME": private / "cache",
    }
    for path in paths.values():
        path.mkdir()
    # Mirrors boot_providers candidates with no explicit ANTIEK_ENV_FILE.
    candidates = [
        root / "platform" / ".env",
        root.parent / "platform" / ".env",
        paths["HOME"] / ".antiek" / ".env",
        root / ".env",
    ]
    assert all(not p.exists() and not p.is_symlink() for p in candidates)
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "en_US.UTF-8",
        "PYTHONPATH": str(root),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "ANTIEK_DUCKDB_PATH": str(private / "graph.duckdb"),
        "ANTIEK_PASSKEY_STORE": str(private / "passkeys.json"),
        "ANTIEK_EMAIL_PROVIDER": "mock",
        "ANTIEK_EMBEDDING_PROVIDER": "hash",
        "ANTIEK_VSS_ALLOW_INSTALL": "0",
        "HF_HUB_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    env.update({name: str(path) for name, path in paths.items()})
    code = """
import hashlib
import json
import os
import sys
from pathlib import Path
import substrate.graph.retrieval_substrate as rs
root = Path(sys.argv[1]).resolve()
origin = Path(rs.__file__).resolve()
assert origin == root / 'substrate/graph/retrieval_substrate.py'
assert 'substrate.graph.retrieval_adapters.turbopuffer' not in sys.modules
assert 'substrate.graph.retrieval_adapters.ducklake' not in sys.modules
proof = {'origin': str(origin), 'sha256': hashlib.sha256(origin.read_bytes()).hexdigest(),
         'vendor_adapters_imported': False}
Path(os.environ['HOME']).parent.joinpath('cold-import-proof.json').write_text(json.dumps(proof))
print(json.dumps(proof))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(root)],
        cwd=root, env=env, capture_output=True, text=True, timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["vendor_adapters_imported"] is False
