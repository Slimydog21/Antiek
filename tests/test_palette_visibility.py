"""Fixed-source palette admission, complete DTOs, ranking and failure contracts."""

from __future__ import annotations

import json
from dataclasses import asdict

import duckdb
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.multi_user.auth import mint_session_cookie, subject_owner_id
from substrate.write.block_search import search_blocks
from substrate.write.folders import ensure_folders_schema

ALICE = "alice-palette@example.test"
BOB = "bob-palette@example.test"
OWNER_A = subject_owner_id("magic_link", ALICE)
OWNER_B = subject_owner_id("magic_link", BOB)
PUBLIC_IDS = {"public", "licensed", "legacy", "direct", "both", "array", "edge"}


def _node(con, node_id, metadata, *, owner=None, label=None, node_type="claim", embedding=None):
    con.execute(
        "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, "
        "metadata, owner_user_id, embedding, created_at) "
        "VALUES (?, ?, ?, 'cross_domain', ?, ?, ?, TIMESTAMP '2020-01-01')",
        [node_id, label if label is not None else f"palette {node_id}", node_type,
         metadata if isinstance(metadata, str) else json.dumps(metadata), owner, embedding],
    )


def _edge(con, node_id, *, document_id=None, chunk_id=None):
    con.execute(
        "INSERT INTO edges (edge_id,source_node_id,target_node_id,relation, "
        "source_document_id,chunk_id,source_tier,extraction_confidence,graph_scope) "
        "VALUES (?, ?, ?, 'grounded', ?, ?, 2, 1, 'cross_domain')",
        [f"edge-{node_id}", node_id, node_id, document_id, chunk_id],
    )


@pytest.fixture
def graph(tmp_path, monkeypatch):
    path = str(tmp_path / "palette.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "synthetic-palette-secret-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "mock")
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    for key in ("ANTIEK_OPERATOR_TOKEN", "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
                "CF_ACCESS_CLIENT_SECRET", "ANTIEK_OPERATOR_EMAIL"):
        monkeypatch.delenv(key, raising=False)
    init_database_at_path(path)
    with connect_write(path, purpose="palette/synthetic-seed") as con:
        records = [
            ("public", "public_domain", None),
            ("licensed", "opt_in_licensed", None),
            ("legacy", None, None),
            ("private-a", "user_authored_private", OWNER_A),
            ("private-b", "user_authored_private", OWNER_B),
            ("personal-a", "personal_reading", OWNER_A),
            ("restricted", "restricted_pending_opt_in", None),
            ("research", "research_only", None),
            ("unknown", "unregistered_class", None),
            ("taken", "public_domain", None),
        ]
        for name, content_class, owner in records:
            con.execute(
                "INSERT INTO documents (document_id,title,source_tier,document_type, "
                "content_class,owner_user_id) VALUES (?, ?, 2, 'book', ?, ?)",
                [f"doc-{name}", f"Title {name}", content_class, owner or "__operator__"],
            )
            con.execute(
                "INSERT INTO chunks (chunk_id,document_id,chunk_index,text,token_count) "
                "VALUES (?, ?, 0, ?, 4)",
                [f"chunk-{name}", f"doc-{name}", f"raw body {name} never projected"],
            )
            _node(con, name, {"chunk_id": f"chunk-{name}"}, owner=owner)
        con.execute("INSERT INTO book_assets (document_id,taken_down) VALUES ('doc-taken',TRUE)")
        _node(con, "direct", {"source_document_id": "doc-public"}, node_type="insight")
        _node(con, "both", {"chunk_id": "chunk-public", "source_document_id": "doc-licensed"})
        _node(con, "array", {"source_chunk_ids": ["chunk-public", "chunk-licensed"]})
        _node(con, "edge", {})
        _edge(con, "edge", document_id="doc-public", chunk_id="chunk-licensed")
        _node(con, "foreign-node", {"chunk_id": "chunk-public"}, owner=OWNER_B)
        invalid = {
            "missing-chunk": {"chunk_id": "absent"},
            "missing-document": {"source_document_id": "absent"},
            "source-free": {},
            "malformed": "{broken",
            "non-object": "[]",
            "scalar": "42",
            "json-null": "null",
            "chunk-number": {"chunk_id": 7},
            "chunk-array": {"chunk_id": ["chunk-public"]},
            "chunk-null": {"chunk_id": None},
            "chunk-empty": {"chunk_id": ""},
            "doc-object": {"source_document_id": {"id": "doc-public"}},
            "doc-empty": {"source_document_id": " "},
            "contradict-private": {"chunk_id": "chunk-public", "source_document_id": "doc-private-b"},
            "contradict-missing": {"chunk_id": "chunk-public", "source_document_id": "missing"},
            "array-string": {"chunk_id": "chunk-public", "source_chunk_ids": "chunk-public"},
            "array-non-string": {"chunk_id": "chunk-public", "source_chunk_ids": [5]},
            "array-private": {"chunk_id": "chunk-public", "source_chunk_ids": ["chunk-private-b"]},
            "array-missing": {"source_chunk_ids": ["absent"]},
        }
        for name, metadata in invalid.items():
            _node(con, name, metadata)
        _node(con, "incident-private", {"chunk_id": "chunk-public"})
        _edge(con, "incident-private", document_id="doc-private-b")
        _node(con, "incident-taken", {"chunk_id": "chunk-public"})
        _edge(con, "incident-taken", chunk_id="chunk-taken")
    return path


def _api(monkeypatch, *, emails=""):
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", emails)
    return TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))


def _signed(client, email):
    client.cookies.set("ANTIEK_SESSION", mint_session_cookie("magic_link", email, email))


def _repository_hit(node_id, *, doc="public", score=0.0, node_type="claim"):
    return {
        "node_id": node_id, "label": f"palette {node_id}", "node_type": node_type,
        "source_tier": 2 if doc else None,
        "document_id": f"doc-{doc}" if doc else None,
        "document_title": f"Title {doc}" if doc else None, "score": score,
    }


def _app_hit(node_id, *, doc="public", label=None):
    label = label if label is not None else f"palette {node_id}"
    return {
        "block_id": node_id, "block_kind": "insight", "label": label,
        "body": label, "source_tier": 2 if doc else None,
        "document_title": f"Title {doc}" if doc else None,
    }


@pytest.mark.parametrize("policy", ["public", "attribution_eligible", "unknown", "owner_scoped",
                                     "operator_only", "private_research"])
@pytest.mark.parametrize("owner", [None, OWNER_A, OWNER_B])
def test_complete_reference_policy_matrix(graph, policy, owner):
    expected = set(PUBLIC_IDS)
    if owner == OWNER_B:
        expected.add("foreign-node")
    if policy in {"owner_scoped", "operator_only", "private_research"}:
        if owner == OWNER_A:
            expected |= {"private-a", "personal-a"}
        if owner == OWNER_B:
            expected |= {"private-b", "contradict-private", "array-private", "incident-private"}
    if policy in {"operator_only", "private_research"}:
        expected |= {"restricted", "research"}
    with connect_read(graph) as con:
        hits = search_blocks(con, policy_tag=policy, owner_user_id=owner, limit=100)
    assert {h.node_id for h in hits} == expected
    assert all(h.score == 0 for h in hits)


@pytest.mark.parametrize("route", ["/blocks/search", "/write/blocks/search"])
@pytest.mark.parametrize("email,own,foreign", [(ALICE, "private-a", "private-b"),
                                             (BOB, "private-b", "private-a")])
def test_http_verified_pair_full_owner_dto(graph, monkeypatch, route, email, own, foreign):
    client = _api(monkeypatch, emails=f"{ALICE},{BOB}")
    _signed(client, email)
    response = client.get(route, params={"q": own, "limit": 100})
    assert response.status_code == 200, response.text
    expected = (_app_hit(own, doc=own) if route == "/blocks/search"
                else _repository_hit(own, doc=own, score=1.0))
    if route == "/blocks/search":
        assert response.json() == {"count": 1, "hits": [expected]}
    else:
        hits = response.json()["hits"]
        assert response.json()["count"] == len(hits)
        assert hits[0] == expected
        assert foreign not in {h["node_id"] for h in hits}
        assert not {"restricted", "research", "unknown", "taken"} & {h["node_id"] for h in hits}
    assert "raw body" not in response.text


@pytest.mark.parametrize("route", ["/blocks/search", "/write/blocks/search"])
def test_http_no_principal_uses_public_admission(graph, monkeypatch, route):
    response = _api(monkeypatch).get(route, params={"limit": 100})
    assert response.status_code == 200, response.text
    hits = response.json()["hits"]
    key = "block_id" if route == "/blocks/search" else "node_id"
    assert {h[key] for h in hits} == PUBLIC_IDS
    assert response.json()["count"] == len(PUBLIC_IDS)
    by_id = {h[key]: h for h in hits}
    if key == "block_id":
        assert by_id["public"] == _app_hit("public")
        assert by_id["direct"] == _app_hit("direct", doc=None)
    else:
        assert by_id["public"] == _repository_hit("public")
        assert by_id["direct"] == _repository_hit("direct", node_type="insight")
    assert by_id["edge"] == (_app_hit("edge", doc=None) if key == "block_id"
                            else _repository_hit("edge", doc=None))
    assert "raw body" not in response.text


@pytest.mark.parametrize("route", ["/blocks/search", "/write/blocks/search"])
def test_single_operator_preserves_privileged_derived_labels(graph, monkeypatch, route):
    client = _api(monkeypatch, emails=ALICE)
    _signed(client, ALICE)
    response = client.get(route, params={"limit": 100})
    assert response.status_code == 200, response.text
    key = "block_id" if route == "/blocks/search" else "node_id"
    ids = {h[key] for h in response.json()["hits"]}
    assert ids == PUBLIC_IDS | {"private-a", "personal-a", "restricted", "research"}
    assert "raw body" not in response.text


def test_app_admission_before_newest_limit_and_ilike_wildcards(graph, monkeypatch):
    with connect_write(graph, purpose="palette/recent-denied-seed") as con:
        for i in range(6):
            _node(con, f"recent-{i}", {"chunk_id": "chunk-private-b"}, label="wild X result")
            con.execute("UPDATE nodes SET created_at=TIMESTAMP '2025-01-01' WHERE node_id=?",
                        [f"recent-{i}"])
        _node(con, "older-visible", {"chunk_id": "chunk-public"}, label="wild Y result")
        _node(con, "newer-visible", {"chunk_id": "chunk-licensed"}, label="wild Z result")
        con.execute("UPDATE nodes SET created_at=TIMESTAMP '2021-01-01' WHERE node_id='newer-visible'")
    client = _api(monkeypatch)
    response = client.get("/blocks/search", params={"q": "WiLd _%", "limit": 2})
    assert response.status_code == 200, response.text
    assert response.json() == {"count": 2, "hits": [
        _app_hit("newer-visible", doc="licensed", label="wild Z result"),
        _app_hit("older-visible", label="wild Y result"),
    ]}
    limited = client.get("/blocks/search", params={"q": "wild", "limit": 1})
    assert limited.json() == {"count": 1, "hits": [
        _app_hit("newer-visible", doc="licensed", label="wild Z result"),
    ]}


def test_repository_one_select_chunk_precedence_and_filters(graph):
    class RecordingRead:
        def __init__(self, con):
            self.con = con
            self.statements = []

        def execute(self, sql, params=None):
            self.statements.append((sql, params))
            return self.con.execute(sql, params)

    with connect_write(graph, purpose="palette/folder-seed") as con:
        ensure_folders_schema(con)
        con.execute("INSERT INTO write_folders(folder_id,name) VALUES ('folder-a','Synthetic')")
        con.executemany("INSERT INTO write_folder_members(folder_id,node_id) VALUES ('folder-a',?)",
                        [[n] for n in ("both", "direct", "private-a", "private-b")])
    with connect_read(graph) as con:
        recording = RecordingRead(con)
        both = search_blocks(recording, source_document_id="doc-public", node_types=["claim"],
                             owner_user_id=OWNER_A, policy_tag="owner_scoped", limit=100)
        assert len(recording.statements) == 1
        by_id = {h.node_id: asdict(h) for h in both}
        assert by_id["both"] == _repository_hit("both")
        assert "direct" not in by_id
        assert "both" not in {h.node_id for h in search_blocks(con, source_document_id="doc-licensed")}
        scoped = search_blocks(con, folder_id="folder-a", source_document_id="doc-private-a",
                               node_types=["claim"], owner_user_id=OWNER_A,
                               policy_tag="owner_scoped")
        assert [asdict(h) for h in scoped] == [_repository_hit("private-a", doc="private-a")]
        direct = search_blocks(con, folder_id="folder-a", source_document_id="doc-public",
                               node_types=["insight"], owner_user_id=OWNER_A,
                               policy_tag="owner_scoped")
        assert [asdict(h) for h in direct] == [_repository_hit("direct", node_type="insight")]


def test_repository_score_embedding_tie_and_limit_after_admission(graph):
    with connect_write(graph, purpose="palette/rank-seed") as con:
        for node_id, label, embedding, chunk in [
            ("rank-a", "quantum other", [0.0, 1.0], "chunk-public"),
            ("rank-b", "quantum other", [0.0, 1.0], "chunk-public"),
            ("rank-z", "quantum", [1.0, 0.0], "chunk-public"),
            ("rank-denied", "quantum", [1.0, 0.0], "chunk-private-b"),
        ]:
            _node(con, node_id, {"chunk_id": chunk}, label=label, embedding=embedding)
    with connect_read(graph) as con:
        hits = search_blocks(con, query="quantum", query_embedding=[1.0, 0.0], limit=3)
        repeat = search_blocks(con, query="quantum", query_embedding=[1.0, 0.0], limit=3)
        assert hits == repeat
        assert [(h.node_id, h.score) for h in hits] == [("rank-z", 2.0), ("rank-a", 1.0), ("rank-b", 1.0)]
        assert search_blocks(con, query="quantum", query_embedding=[1.0, 0.0], limit=1) == hits[:1]
        browse = search_blocks(con, limit=100)
        assert [h.node_id for h in browse] == sorted(h.node_id for h in browse)


def test_repository_absent_optional_folder_and_partial_schema(graph):
    with connect_read(graph) as con:
        assert search_blocks(con, folder_id="missing") == []
    with connect_write(graph, purpose="palette/partial-folder-schema") as con:
        con.execute("CREATE TABLE write_folders(folder_id TEXT)")
    with connect_read(graph) as con, pytest.raises(duckdb.CatalogException, match="write_folder_members"):
        search_blocks(con, folder_id="missing")


@pytest.mark.parametrize("phase", ["probe", "candidate"])
def test_repository_sql_failures_propagate(graph, phase):
    class FailingRead:
        def __init__(self, con):
            self.con = con

        def execute(self, sql, params=None):
            if phase == "probe" and "sqlite_master" in sql:
                raise RuntimeError("synthetic folder probe failure")
            if phase == "candidate" and "FROM nodes n" in sql:
                raise RuntimeError("synthetic candidate failure")
            return self.con.execute(sql, params)

    with connect_read(graph) as con, pytest.raises(RuntimeError, match=f"synthetic .*{phase}.*failure"):
        search_blocks(FailingRead(con), folder_id="f" if phase == "probe" else None)


@pytest.mark.parametrize("table", ["documents", "chunks", "edges", "book_assets"])
def test_actual_rights_and_source_query_errors_are_not_empty_success(graph, table):
    class MissingTableRead:
        def __init__(self, con):
            self.con = con

        def execute(self, sql, params=None):
            failed_sql = sql.replace(f"JOIN {table} ", f"JOIN unavailable_{table} ")
            failed_sql = failed_sql.replace(f"FROM {table} ", f"FROM unavailable_{table} ")
            assert failed_sql != sql
            return self.con.execute(failed_sql, params)

    with connect_read(graph) as con, pytest.raises(duckdb.CatalogException, match=f"unavailable_{table}"):
        search_blocks(MissingTableRead(con))


@pytest.mark.parametrize("route", ["/blocks/search", "/write/blocks/search"])
def test_http_database_failure_propagates_and_closes_handle(graph, monkeypatch, route):
    class FailedRead:
        closed = False

        def execute(self, sql, params=None):
            raise RuntimeError("synthetic palette read failure")

        def close(self):
            self.closed = True

    failed = FailedRead()
    module = "runtime.db_lock.connect_read" if route == "/blocks/search" else "interfaces.research.api.write_routes.connect_read"
    monkeypatch.setattr(module, lambda path: failed)
    with pytest.raises(RuntimeError, match="synthetic palette read failure"):
        _api(monkeypatch).get(route)
    assert failed.closed


def test_empty_label_retains_distinct_app_body_contract(graph, monkeypatch):
    with connect_write(graph, purpose="palette/empty-label") as con:
        _node(con, "empty-label", {"chunk_id": "chunk-public"}, label="")
        con.execute("UPDATE nodes SET created_at=TIMESTAMP '2025-01-01' WHERE node_id='empty-label'")
    response = _api(monkeypatch).get("/blocks/search", params={"limit": 1})
    assert response.status_code == 200, response.text
    assert response.json() == {"count": 1, "hits": [{
        "block_id": "empty-label", "block_kind": "insight", "label": "(no label)",
        "body": "", "source_tier": 2, "document_title": "Title public",
    }]}


def test_http_folder_and_source_filters_do_not_confer_owner_authority(graph, monkeypatch):
    with connect_write(graph, purpose="palette/foreign-folder-filter") as con:
        ensure_folders_schema(con)
        con.execute("INSERT INTO write_folders(folder_id,name,owner_user_id) VALUES ('foreign','Synthetic',?)",
                    [OWNER_B])
        con.executemany("INSERT INTO write_folder_members(folder_id,node_id) VALUES ('foreign',?)",
                        [["public"], ["private-b"]])
    client = _api(monkeypatch, emails=f"{ALICE},{BOB}")
    _signed(client, ALICE)
    response = client.get("/write/blocks/search", params={"folder_id": "foreign"})
    assert response.status_code == 200, response.text
    assert response.json() == {"count": 1, "hits": [_repository_hit("public")]}
    denied = client.get("/write/blocks/search", params={
        "folder_id": "foreign", "source_document_id": "doc-private-b",
    })
    assert denied.status_code == 200, denied.text
    assert denied.json() == {"count": 0, "hits": []}
