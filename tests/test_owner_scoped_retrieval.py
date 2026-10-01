"""Owner-scoped retrieval keeps private value separate from rights privilege."""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.retrieval_gate import (
    _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES,
    OWNER_SCOPED_POLICY_TAG,
    PRIVILEGED_POLICY_TAGS,
    non_privileged_chunk_sql_clause,
)
from substrate.graph.schema import init_database
from substrate.graph.search import search
from substrate.rights.register import VALID_CONTENT_CLASSES


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        value = sum((idx + 1) * ord(char) for idx, char in enumerate(text)) or 1
        return [float(value % n) / n for n in (7, 11, 13, 17)]


@pytest.fixture
def db_path():
    root = tempfile.mkdtemp(prefix="antiek-owner-scoped-")
    path = os.path.join(root, "graph.duckdb")
    con = connect_write(path, purpose="owner-scoped-test-init")
    try:
        init_database(con)
    finally:
        con.close()
    return path


def _seed(
    path: str, document_id: str, content_class: str | None, owner: str, body: str,
) -> None:
    con = connect_write(path, purpose="owner-scoped-test-seed")
    try:
        insert_document(
            con, document_id=document_id, source_tier=2, document_type="paper",
            title=document_id, content_class=content_class,
        )
        con.execute(
            "UPDATE documents SET owner_user_id = ? WHERE document_id = ?",
            [owner, document_id],
        )
        insert_chunk(
            con, document_id=document_id, chunk_index=0, text=body,
            section_path="Page 1", token_count=6,
            embedding=StubEmbedding().encode(body),
        )
    finally:
        con.close()


def _search(path: str, policy: str, owner: str | None):
    con = connect_write(path, purpose="owner-scoped-test-search")
    try:
        return search(
            con, "quantum optics", model=StubEmbedding(), top_k=20,
            policy_tag=policy, owner_user_id=owner,
        )
    finally:
        con.close()


def test_owner_scoped_is_not_a_privileged_policy():
    assert OWNER_SCOPED_POLICY_TAG == "owner_scoped"
    assert OWNER_SCOPED_POLICY_TAG not in PRIVILEGED_POLICY_TAGS


def test_owner_scoped_preserves_public_and_legacy_null_classes(db_path):
    _seed(db_path, "public", "public_domain", "__operator__", "quantum optics public")
    _seed(db_path, "legacy-null", None, "__operator__", "quantum optics legacy")
    results = _search(db_path, OWNER_SCOPED_POLICY_TAG, None)["results"]
    assert {row["document_id"] for row in results} == {"public", "legacy-null"}


@pytest.mark.parametrize("content_class", ["personal_reading", "user_authored_private"])
def test_owner_scoped_admits_only_exact_owner_personal_classes(db_path, content_class):
    _seed(db_path, "private-a", content_class, "account-a", "quantum optics personal passage A")
    _seed(db_path, "private-b", content_class, "account-b", "quantum optics personal passage B")

    own = _search(db_path, OWNER_SCOPED_POLICY_TAG, "account-a")["results"]
    foreign = _search(db_path, OWNER_SCOPED_POLICY_TAG, "account-c")["results"]
    assert {row["document_id"] for row in own} == {"private-a"}
    assert "private-b" not in {row["document_id"] for row in foreign}


@pytest.mark.parametrize("content_class", ["restricted_pending_opt_in", "research_only"])
def test_owner_scoped_does_not_grant_other_policy_classes(db_path, content_class):
    _seed(db_path, "gated", content_class, "account-a", "quantum optics restricted passage")
    results = _search(db_path, OWNER_SCOPED_POLICY_TAG, "account-a")["results"]
    assert "gated" not in {row["document_id"] for row in results}


def test_owner_scoped_fails_closed_for_unknown_persisted_class(db_path):
    _seed(db_path, "unknown", "unknown_future_class", "account-a", "quantum optics unknown")
    results = _search(db_path, OWNER_SCOPED_POLICY_TAG, "account-a")["results"]
    assert "unknown" not in {row["document_id"] for row in results}


@pytest.mark.parametrize(
    "policy,owner",
    [
        ("attribution_eligible", "account-a"),
        (OWNER_SCOPED_POLICY_TAG, None),
        (OWNER_SCOPED_POLICY_TAG, ""),
        (OWNER_SCOPED_POLICY_TAG, " account-a"),
        (OWNER_SCOPED_POLICY_TAG, "__OPERATOR__"),
    ],
)
def test_private_needs_owner_scoped_exact_usable_owner(db_path, policy, owner):
    _seed(db_path, "private-a", "personal_reading", "account-a", "quantum optics private")
    results = _search(db_path, policy, owner)["results"]
    assert "private-a" not in {row["document_id"] for row in results}


def test_existing_operator_and_agent_rights_policies_are_preserved(db_path):
    _seed(db_path, "restricted", "restricted_pending_opt_in", "account-a", "quantum optics gated")
    _seed(db_path, "research", "research_only", "account-a", "quantum optics agent")

    operator_ids = {
        row["document_id"]
        for row in _search(db_path, "operator_only", "account-a")["results"]
    }
    agent_ids = {
        row["document_id"]
        for row in _search(db_path, "private_research", None)["results"]
    }
    assert "restricted" in operator_ids
    assert "research" not in operator_ids
    assert {"restricted", "research"} <= agent_ids


def test_owner_scoped_sql_binds_outer_vocabulary_then_class_arm_then_owner():
    sql, params = non_privileged_chunk_sql_clause(
        table_alias="d", policy_tag=OWNER_SCOPED_POLICY_TAG,
        owner_user_id="account-a",
    )
    known = sorted(VALID_CONTENT_CLASSES)
    excluded = sorted(_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES)
    personal = sorted({"personal_reading", "user_authored_private"})
    assert params == [*known, *excluded, *personal, "account-a"]
    assert "NOT EXISTS (SELECT 1 FROM book_assets td" in sql
    assert "IN (?,?) AND d.owner_user_id = ?" in sql


def test_owner_scoped_excludes_taken_down_book_even_if_private_class_remains(db_path):
    from substrate.books import ingest as book_ingest

    body = "quantum optics taken down private body"
    _seed(db_path, "taken", "personal_reading", "account-a", body)
    con = connect_write(db_path, purpose="owner-scoped-test-takedown")
    try:
        book_ingest.register_book(
            con, document_id="taken", content_class="personal_reading",
            provenance="synthetic D1 control",
        )
        # Isolate D1's outer retrieval predicate from rights reclassification.
        con.execute("UPDATE book_assets SET taken_down = TRUE WHERE document_id = ?", ["taken"])
    finally:
        con.close()
    results = _search(db_path, OWNER_SCOPED_POLICY_TAG, "account-a")["results"]
    assert "taken" not in {row["document_id"] for row in results}


def test_turbopuffer_keeps_owner_scoped_query_on_duckdb(db_path, tmp_path):
    from runtime.db_lock import connect_read
    from substrate.graph.retrieval_adapters.turbopuffer import TurbopufferSubstrate

    class Namespace:
        def __init__(self) -> None:
            self.calls = 0

        def multi_query(self, **kwargs):
            self.calls += 1
            raise AssertionError("private owner-scoped query reached TurboPuffer")

    _seed(db_path, "private-a", "personal_reading", "account-a", "quantum optics private A")
    _seed(db_path, "private-b", "personal_reading", "account-b", "quantum optics private B")
    namespace = Namespace()
    con = connect_read(db_path)
    try:
        substrate = TurbopufferSubstrate(
            con, model=StubEmbedding(), api_key="synthetic", namespace=namespace,
            manifest_dir=tmp_path,
        )
        result = substrate.query(
            "quantum optics", top_k=10, policy_tag=OWNER_SCOPED_POLICY_TAG,
            owner_user_id="account-a",
        )
        assert {row["document_id"] for row in result["results"]} == {"private-a"}
        assert namespace.calls == 0
    finally:
        con.close()


def test_vss_open_owner_scoped_gate_without_network_install(db_path, monkeypatch):
    from substrate.graph.retrieval_substrate import DuckDbVssSubstrate

    monkeypatch.setenv("ANTIEK_VSS_ALLOW_INSTALL", "0")
    _seed(db_path, "private-a", "user_authored_private", "account-a", "quantum optics private A")
    _seed(db_path, "private-b", "user_authored_private", "account-b", "quantum optics private B")
    substrate = DuckDbVssSubstrate.open(db_path, model=StubEmbedding())
    try:
        result = substrate.query(
            "quantum optics", top_k=10, policy_tag=OWNER_SCOPED_POLICY_TAG,
            owner_user_id="account-a",
        )
        assert {row["document_id"] for row in result["results"]} == {"private-a"}
        print(f"OWNER_SCOPED_VSS_ACTIVE={substrate.vss_active}")
        if substrate.vss_active:
            indexes = substrate._con.execute(
                "SELECT index_name, sql FROM duckdb_indexes() "
                "WHERE table_name = 'chunks' ORDER BY index_name"
            ).fetchall()
            plan = substrate._con.execute(
                "EXPLAIN SELECT chunk_id FROM chunks WHERE embedding_vss IS NOT NULL "
                "ORDER BY array_cosine_distance(embedding_vss, "
                "[0.1,0.2,0.3,0.4]::FLOAT[4]) ASC LIMIT 10"
            ).fetchall()
            print(f"OWNER_SCOPED_VSS_INDEXES={indexes}")
            print(f"OWNER_SCOPED_VSS_EXPLAIN={plan}")
    finally:
        substrate.close()
