"""Disposable PA02 chunk retrieval policy controls; no provider or production IO."""

from __future__ import annotations

import duckdb
import pytest

from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_read, connect_write
from substrate.graph import ensure_initialized
from substrate.graph.retrieval_adapters.turbopuffer import TurbopufferSubstrate
from substrate.graph.retrieval_gate import non_privileged_chunk_sql_clause
from substrate.graph.retrieval_substrate import (
    BruteForceSubstrate,
    DuckDbVssSubstrate,
    make_substrate,
)
from substrate.graph.search import search


@pytest.fixture
def corpus():
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE documents (document_id VARCHAR, content_class VARCHAR, "
        "owner_user_id VARCHAR)"
    )
    con.execute("CREATE TABLE book_assets (document_id VARCHAR, taken_down BOOLEAN)")
    rows = [
        ("public", "public_domain", None),
        ("contribution", "user_public_contribution", None),
        ("legacy-owned", "user_owned", "__operator__"),
        ("legacy-null", None, None),
        ("private-a", "user_authored_private", "owner-a"),
        ("private-b", "user_authored_private", "owner-b"),
        ("private-default", "user_authored_private", "__operator__"),
        ("private-upper-operator", "user_authored_private", "__OPERATOR__"),
        ("private-blank", "user_authored_private", ""),
        ("private-space", "user_authored_private", " "),
        ("private-padded", "user_authored_private", "owner-a "),
        ("private-shared", "user_authored_private", "shared"),
        ("private-upper-shared", "user_authored_private", "SHARED"),
        ("private-service", "user_authored_private", "service"),
        ("private-upper-service", "user_authored_private", "SERVICE"),
        ("private-local", "user_authored_private", "local"),
        ("private-upper-local", "user_authored_private", "LOCAL"),
        ("personal-a", "personal_reading", "owner-a"),
        ("personal-b", "personal_reading", "owner-b"),
        ("personal-default", "personal_reading", "__operator__"),
        ("personal-upper-operator", "personal_reading", "__OPERATOR__"),
        ("personal-blank", "personal_reading", ""),
        ("personal-space", "personal_reading", " "),
        ("personal-padded", "personal_reading", "owner-a "),
        ("personal-shared", "personal_reading", "shared"),
        ("personal-upper-shared", "personal_reading", "SHARED"),
        ("personal-service", "personal_reading", "service"),
        ("personal-upper-service", "personal_reading", "SERVICE"),
        ("personal-local", "personal_reading", "local"),
        ("personal-upper-local", "personal_reading", "LOCAL"),
        ("research", "research_only", None),
        ("restricted", "restricted_pending_opt_in", None),
        ("unknown-a", "unknown_future_class", "owner-a"),
        ("taken-public", "public_domain", None),
        ("taken-research", "research_only", None),
    ]
    con.executemany("INSERT INTO documents VALUES (?, ?, ?)", rows)
    con.executemany(
        "INSERT INTO book_assets VALUES (?, TRUE)",
        [("taken-public",), ("taken-research",)],
    )
    try:
        yield con
    finally:
        con.close()


def visible(con, policy_tag: str, owner_user_id: str | None) -> set[str]:
    sql, params = non_privileged_chunk_sql_clause(
        table_alias="d", policy_tag=policy_tag, owner_user_id=owner_user_id
    )
    return {
        row[0]
        for row in con.execute(
            "SELECT d.document_id FROM documents d WHERE TRUE" + sql, params
        ).fetchall()
    }


@pytest.mark.parametrize(
    ("tag", "owner", "expected"),
    [
        ("attribution_eligible", "owner-a", {"public", "contribution", "legacy-owned", "legacy-null"}),
        ("operator_only", "owner-a", {"public", "contribution", "legacy-owned", "legacy-null", "private-a", "personal-a", "restricted"}),
        ("private_research", "owner-a", {"public", "contribution", "legacy-owned", "legacy-null", "private-a", "personal-a", "restricted", "research"}),
        ("operator_only", None, {"public", "contribution", "legacy-owned", "legacy-null", "restricted"}),
        ("private_research", "owner-b", {"public", "contribution", "legacy-owned", "legacy-null", "private-b", "personal-b", "restricted", "research"}),
    ],
)
def test_canonical_gate_policies(corpus, tag, owner, expected):
    assert visible(corpus, tag, owner) == expected


@pytest.mark.parametrize("tag", ["operator_only", "private_research"])
@pytest.mark.parametrize("owner", [None, "", " ", "__operator__", " __operator__ ", "owner-a "])
def test_no_owner_authority_from_invalid_or_padded_identity(corpus, tag, owner):
    seen = visible(corpus, tag, owner)
    assert not {name for name in seen if name.startswith(("private-", "personal-"))}
    assert ("research" in seen) == (tag == "private_research")


@pytest.mark.parametrize("tag", ["operator_only", "private_research"])
def test_reserved_owner_ids_never_unlock_private_or_personal_rows(corpus, tag):
    reserved = (
        "__operator__", "__OPERATOR__",
        "shared", "SHARED",
        "service", "SERVICE",
        "local", "LOCAL",
    )
    seen = visible(corpus, tag, None)
    for owner_id in reserved:
        seen.update(visible(corpus, tag, owner_id))

    assert not {
        document_id for document_id in seen
        if document_id.startswith(("private-", "personal-"))
    }
    assert {"private-a", "personal-a"} <= visible(corpus, tag, "owner-a")
    assert {"private-b", "personal-b"} <= visible(corpus, tag, "owner-b")


def test_omitted_owner_cannot_match_stored_default(corpus):
    for tag in ("operator_only", "private_research"):
        sql, params = non_privileged_chunk_sql_clause(policy_tag=tag)
        rows = corpus.execute(
            "SELECT document_id FROM documents d WHERE TRUE" + sql, params
        ).fetchall()
        assert "private-default" not in {row[0] for row in rows}
        assert "personal-default" not in {row[0] for row in rows}


def test_canonical_vocabulary_includes_agent_only_with_explicit_derivation_refusal():
    from substrate.constants import RESEARCH_ONLY_CONTENT_CLASS
    from substrate.rights.register import (
        DERIVED_CONTENT_CLASS_TABLE,
        VALID_CONTENT_CLASSES,
    )

    assert RESEARCH_ONLY_CONTENT_CLASS == "research_only"
    assert RESEARCH_ONLY_CONTENT_CLASS in VALID_CONTENT_CLASSES
    assert DERIVED_CONTENT_CLASS_TABLE[RESEARCH_ONLY_CONTENT_CLASS] is None
    assert set(VALID_CONTENT_CLASSES) == set(DERIVED_CONTENT_CLASS_TABLE)


@pytest.fixture
def retrieval_db(tmp_path, monkeypatch):
    db = str(tmp_path / "retrieval.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("ANTIEK_VSS_ALLOW_INSTALL", raising=False)
    monkeypatch.delenv("TURBOPUFFER_API_KEY", raising=False)
    model = HashEmbedding(dimension=8)
    ensure_initialized(db)
    rows = [
        ("open", "public_domain", None, False),
        ("private-a", "user_authored_private", "owner-a", False),
        ("private-b", "user_authored_private", "owner-b", False),
        ("research", "research_only", None, False),
        ("unknown", "unknown_future_class", "owner-a", False),
        ("taken", "public_domain", None, True),
    ]
    with connect_write(db, purpose="pa02-retrieval-fixture") as con:
        for doc, cls, owner, taken in rows:
            body = f"retrieval sentinel {doc} body"
            con.execute(
                "INSERT INTO documents (document_id,title,source_tier,document_type,"
                "content_class,owner_user_id) VALUES (?,?,2,'book',?,?)",
                [doc, doc, cls, owner or "__operator__"],
            )
            con.execute(
                "INSERT INTO chunks (chunk_id,document_id,chunk_index,text,embedding) "
                "VALUES (?, ?, 0, ?, ?)",
                [f"chunk-{doc}", doc, body, model.encode(body)],
            )
            if taken:
                con.execute(
                    "INSERT INTO book_assets (document_id,taken_down) VALUES (?,TRUE)",
                    [doc],
                )
    return db, model


def _ids(result):
    return {row["document_id"] for row in result["results"]}


def test_search_passes_absent_identity_without_operator_substitution(
    retrieval_db, monkeypatch
):
    import importlib

    search_module = importlib.import_module("substrate.graph.search")
    original = search_module.non_privileged_chunk_sql_clause
    observed = []

    def traced_gate(**kwargs):
        observed.append(kwargs["owner_user_id"])
        return original(**kwargs)

    monkeypatch.setattr(search_module, "non_privileged_chunk_sql_clause", traced_gate)
    db, model = retrieval_db
    with connect_read(db) as con:
        assert _ids(search(con, "retrieval", model=model, top_k=20,
                           policy_tag="private_research")) == {"open", "research"}
    assert observed == [None]


def test_unknown_best_candidate_is_removed_before_rank_limit(retrieval_db):
    db, model = retrieval_db
    with connect_write(db, purpose="pa02-rank-limit-probe") as con:
        con.execute(
            "UPDATE chunks SET embedding=? WHERE document_id='unknown'",
            [model.encode("retrieval")],
        )
    with connect_read(db) as con:
        result = search(
            con, "retrieval", model=model, top_k=1,
            policy_tag="private_research", owner_user_id="owner-a",
        )
    assert len(result["results"]) == 1
    assert result["results"][0]["document_id"] != "unknown"


@pytest.mark.parametrize("kind", ["brute", "vss_fallback"])
def test_substrate_forwards_owner_to_canonical_gate(retrieval_db, kind):
    db, model = retrieval_db
    with connect_read(db) as con:
        sub = (
            BruteForceSubstrate.from_con(con, model=model)
            if kind == "brute" else DuckDbVssSubstrate.from_con(con, model=model)
        )
        try:
            owner = sub.query(
                "retrieval", top_k=20, policy_tag="private_research",
                owner_user_id="owner-a",
            )
            absent = sub.query(
                "retrieval", top_k=20, policy_tag="private_research",
                owner_user_id=None,
            )
            assert "private-a" in _ids(owner)
            assert "private-b" not in _ids(owner)
            assert "private-a" not in _ids(absent)
            assert any("private-a body" in row["chunk_text"] for row in owner["results"])
            assert all("private-b body" not in row["chunk_text"] for row in owner["results"])
            assert all("private-a body" not in row["chunk_text"] for row in absent["results"])
            assert "research" in _ids(owner) & _ids(absent)
            assert "unknown" not in _ids(owner) | _ids(absent)
            assert "taken" not in _ids(owner) | _ids(absent)
        finally:
            sub.close()


class _OfflineNamespace:
    def __init__(self, ids=None):
        self.ids = ids if ids is not None else (
            "open", "private-a", "private-b", "research", "unknown", "taken"
        )
        self.queries = []

    def multi_query(self, **kwargs):
        self.queries.append(kwargs)
        rows = [type("Row", (), {"id": f"chunk-{doc}"})() for doc in self.ids]
        return type("Response", (), {"results": [type("Block", (), {"rows": rows})()]})()


def test_turbopuffer_hydration_and_privileged_fallback(retrieval_db, tmp_path):
    db, model = retrieval_db
    with connect_read(db) as con:
        namespace = _OfflineNamespace()
        sub = TurbopufferSubstrate(
            con, model=model, api_key="offline", namespace=namespace,
            manifest_dir=tmp_path,
        )
        public = sub.query("retrieval", top_k=20, owner_user_id="owner-a")
        assert _ids(public) == {"open"}
        assert [row["chunk_text"] for row in public["results"]] == [
            "retrieval sentinel open body"
        ]
        assert len(namespace.queries) == 1
        rankers = [query["rank_by"][1] for query in namespace.queries[0]["queries"]]
        assert rankers == ["ANN", "BM25"]
        owner = sub.query(
            "retrieval", top_k=20, policy_tag="private_research",
            owner_user_id="owner-a",
        )
        assert "private-a" in _ids(owner)
        assert "private-b" not in _ids(owner)
        assert "research" in _ids(owner)
        assert "unknown" not in _ids(owner)
        assert any("private-a body" in row["chunk_text"] for row in owner["results"])
        assert all("private-b body" not in row["chunk_text"] for row in owner["results"])


def test_turbopuffer_empty_candidate_fallback_uses_public_gate(retrieval_db, tmp_path):
    db, model = retrieval_db
    with connect_read(db) as con:
        sub = TurbopufferSubstrate(
            con, model=model, api_key="offline", namespace=_OfflineNamespace(ids=[]),
            manifest_dir=tmp_path,
        )
        result = sub.query("retrieval", top_k=20, owner_user_id="owner-a")
        assert result["status"] == "degraded — brute_force"
        assert _ids(result) == {"open"}
        assert all("private-a body" not in row["chunk_text"] for row in result["results"])


def test_vss_open_reports_actual_engine_and_keeps_body_gate(retrieval_db):
    db, model = retrieval_db
    sub = DuckDbVssSubstrate.open(db, model=model)
    try:
        print(f"PA02_VSS_ACTIVE={sub.vss_active}")
        result = sub.query(
            "retrieval", top_k=20, policy_tag="private_research",
            owner_user_id="owner-a",
        )
        assert "private-a" in _ids(result)
        assert "private-b" not in _ids(result)
        assert "unknown" not in _ids(result)
        assert "taken" not in _ids(result)
        assert any("private-a body" in row["chunk_text"] for row in result["results"])
    finally:
        sub.close()


def test_vss_active_sql_branch_forwards_owner_without_claiming_hnsw(retrieval_db):
    db, model = retrieval_db
    # Exercise the active query code path with a sized vector column. No HNSW
    # index is built here; native-index availability is reported separately.
    with connect_write(db, purpose="pa02-vss-sql-branch") as con:
        con.execute("ALTER TABLE chunks ADD COLUMN embedding_vss FLOAT[8]")
        con.execute("UPDATE chunks SET embedding_vss=embedding::FLOAT[8]")
    with connect_read(db) as con:
        sub = DuckDbVssSubstrate(con, model=model, vss_active=True)
        owner = sub.query(
            "retrieval", top_k=20, policy_tag="private_research",
            owner_user_id="owner-a",
        )
        absent = sub.query(
            "retrieval", top_k=20, policy_tag="private_research",
            owner_user_id=None,
        )
        assert "private-a" in _ids(owner)
        assert "private-b" not in _ids(owner)
        assert "private-a" not in _ids(absent)
        assert "research" in _ids(owner) & _ids(absent)
        assert "unknown" not in _ids(owner) | _ids(absent)
        assert "taken" not in _ids(owner) | _ids(absent)


def test_ducklake_skipped_adapter_accepts_optional_owner(retrieval_db):
    db, model = retrieval_db
    sub = make_substrate("ducklake", db, model=model, has_creds=False)
    try:
        result = sub.query(
            "retrieval", top_k=20, policy_tag="private_research",
            owner_user_id="owner-a",
        )
        assert result["results"] == []
        assert result["status"] == "skipped — no credentials"
    finally:
        sub.close()
