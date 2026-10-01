"""Document-fork route proofs (thread-merge + document fork SPR-01).

FastAPI TestClient against a REAL DuckDB fixture (the api_env shape from
tests/test_reading_state_routes.py). The spec's five proofs, plus the adopt
mode the reformat-provenance spec contracts ("officially fork" promotes a
provisional derived document, the lineage row carrying the generation
record):

  1. fork → forks-of-this lists it → detail incl. parent → lineage both
     directions → the fork opens and reads as its own document → the
     parent's body hash is byte-identical before and after;
  2. rights inheritance: the fork's class is the derivation rule's output
     (public_domain → user_owned; an opt_in_licensed parent keeps its class
     AND its rights holder), served through the EXISTING gates on the fork's
     own id; a gated parent (personal_reading — the stack's non-servable
     lane) is REFUSED (422), strictly stronger than "stays owner-only":
     the laundering path cannot exist. Route-table diff: the only fork
     routes are the four this module registers — no fork-specific body
     fetch exists to test;
  3. idempotency: same operation id → same fork, one row; a distinct
     operation → a second fork, both listed;
  4. depth-1: fork-of-fork is a 409 naming the limit;
  5. capture audit: the lineage row's hashes recompute against the stored
     bodies.

The auth middleware's enforcement-disabled default stamps the
single-operator identity, so the requesting owner is "__operator__" unless
a test re-keys rows at the store layer.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_document


@pytest.fixture
def api_env(monkeypatch):
    # This is a substrate-free route fixture: ambient operator credentials on
    # a development workstation must not turn the hermetic TestClient into a
    # 401-only suite.
    for variable in (
        "ANTIEK_AUTH_SECRET",
        "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
    ):
        monkeypatch.delenv(variable, raising=False)
    tmpdir = tempfile.mkdtemp(prefix="forks-api-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    arts = os.path.join(tmpdir, "artifacts")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", arts)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "events": events, "arts": arts}


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False))


def _seed_book(
    db: str,
    document_id: str = "doc-parent",
    *,
    title: str = "Parent Book",
    raw_text: str = "The parent's full body.\n\nSecond page of it.",
    content_class: str = "public_domain",
    ip_holder_id: str | None = None,
) -> None:
    from substrate.books.model import upsert_book_asset

    with connect_write(db, purpose="test/seed-fork-book") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title=title,
            raw_text=raw_text,
            content_class=content_class,
            ip_holder_id=ip_holder_id,
            on_conflict="ignore",
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
            "section_path, text, token_count) VALUES (?, ?, 0, 'Page 1', ?, 6)",
            [f"chunk-{document_id}", document_id, raw_text],
        )
        upsert_book_asset(con, document_id=document_id, page_count=2)


def _body(db: str, document_id: str) -> str:
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ? LIMIT 1",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    return str(row[0])


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fork_rows(db: str) -> list[tuple]:
    con = connect_read(db)
    try:
        return con.execute(
            "SELECT fork_id, parent_document_id, fork_document_id, "
            "operation_id, parent_body_sha256, fork_body_sha256 "
            "FROM document_forks ORDER BY created_at, fork_id"
        ).fetchall()
    finally:
        con.close()


# ── Proof 1: the round trip; the original is byte-identical ────────────────


def test_fork_round_trip_and_original_immutable(api_env) -> None:
    db = api_env["db"]
    _seed_book(db)
    parent_hash_before = _sha(_body(db, "doc-parent"))
    client = _client()

    created = client.post(
        "/books/doc-parent/forks",
        json={"operation_id": "op-1", "note": "my working copy",
              "fork_point_locator": "page:1"},
    )
    assert created.status_code == 201, created.text
    fork = created.json()
    assert fork["parent_document_id"] == "doc-parent"
    assert fork["fork_document_id"] != "doc-parent"
    assert fork["note"] == "my working copy"
    assert fork["fork_point_locator"] == "page:1"
    assert fork["parent_title"] == "Parent Book"
    fork_doc = fork["fork_document_id"]

    # forks-of-this lists it.
    listed = client.get("/books/doc-parent/forks")
    assert listed.status_code == 200
    assert [row["fork_id"] for row in listed.json()["forks"]] == [fork["fork_id"]]
    assert listed.json()["forked_from"] is None

    # The fork's own read of the same route answers the parent direction.
    reverse = client.get(f"/books/{fork_doc}/forks")
    assert reverse.status_code == 200
    assert reverse.json()["forks"] == []
    assert reverse.json()["forked_from"]["fork_id"] == fork["fork_id"]
    assert reverse.json()["forked_from"]["parent_title"] == "Parent Book"

    # Detail, incl. parent.
    detail = client.get(f"/forks/{fork['fork_id']}")
    assert detail.status_code == 200
    assert detail.json()["parent_document_id"] == "doc-parent"
    assert detail.json()["fork_document_id"] == fork_doc

    # Lineage, both directions, one row per hop.
    lineage = client.get(f"/forks/{fork['fork_id']}/lineage")
    assert lineage.status_code == 200
    body = lineage.json()
    assert body["parent"]["document_id"] == "doc-parent"
    assert body["parent"]["title"] == "Parent Book"
    assert body["parent"]["fork_id"] == fork["fork_id"]
    assert body["children"] == []  # depth-1: a fork's children are honestly empty

    # The fork opens and reads as its own document: the book detail route
    # (book_assets copied) and the gated full-text route both serve it.
    book = client.get(f"/books/{fork_doc}")
    assert book.status_code == 200, book.text
    assert book.json()["title"] == "Parent Book"
    assert book.json()["page_count"] == 2
    text = client.get(f"/books/{fork_doc}/full-text")
    assert text.status_code == 200, text.text
    assert text.json()["full_text"] == "The parent's full body.\n\nSecond page of it."

    # The body copy included the chunks, re-keyed to the fork.
    con = connect_read(db)
    try:
        chunks = con.execute(
            "SELECT chunk_id, text FROM chunks WHERE document_id = ?",
            [fork_doc],
        ).fetchall()
    finally:
        con.close()
    assert len(chunks) == 1
    assert chunks[0][0].startswith(f"{fork_doc}-c")
    assert chunks[0][1] == "The parent's full body.\n\nSecond page of it."

    # The original is byte-identical after the whole flow (asserted, not
    # reviewed).
    assert _sha(_body(db, "doc-parent")) == parent_hash_before


# ── Proof 2: rights inheritance + the rights-trust gate ────────────────────


def test_fork_rights_inheritance_and_refusal(api_env) -> None:
    db = api_env["db"]
    _seed_book(db, "doc-pd", content_class="public_domain")
    _seed_book(db, "doc-lic", content_class="opt_in_licensed", ip_holder_id="iph-1")
    _seed_book(db, "doc-gated", content_class="personal_reading")
    client = _client()

    # public_domain rebases to user_owned (the derivation table): the fork
    # is the operator's own expression, servable under the existing gates.
    pd = client.post("/books/doc-pd/forks", json={"operation_id": "op-pd"})
    assert pd.status_code == 201, pd.text
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT content_class, ip_holder_id FROM documents "
            "WHERE document_id = ? LIMIT 1",
            [pd.json()["fork_document_id"]],
        ).fetchone()
    finally:
        con.close()
    assert tuple(row) == ("user_owned", None)

    # opt_in_licensed is a fixed point: class AND rights holder follow the
    # derivative (the publisher's licence, attribution and rev-share).
    lic = client.post("/books/doc-lic/forks", json={"operation_id": "op-lic"})
    assert lic.status_code == 201, lic.text
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT content_class, ip_holder_id FROM documents "
            "WHERE document_id = ? LIMIT 1",
            [lic.json()["fork_document_id"]],
        ).fetchone()
    finally:
        con.close()
    assert tuple(row) == ("opt_in_licensed", "iph-1")

    # A gated (non-servable) parent is REFUSED — the derivation rule grants
    # no transformation right, so no fork of it ever exists to serve.
    gated = client.post("/books/doc-gated/forks", json={"operation_id": "op-g"})
    assert gated.status_code == 422
    assert "fork_rights_refused" in gated.json()["detail"]
    assert _fork_rows(db) == _fork_rows(db)  # no row for the refusal
    assert all(r[1] != "doc-gated" for r in _fork_rows(db))


def test_no_fork_specific_fetch_route(api_env) -> None:
    """Route-table diff: the only fork paths are the four this module
    registers — no fork-specific body fetch exists to test."""
    app = create_app(register_wrestling=False)
    fork_routes = sorted(
        {
            (route.path, method)
            for route in app.routes
            for method in getattr(route, "methods", set()) or set()
            if "fork" in route.path
        }
    )
    assert fork_routes == [
        ("/books/{document_id}/forks", "GET"),
        ("/books/{document_id}/forks", "POST"),
        ("/forks/{fork_id}", "GET"),
        ("/forks/{fork_id}/lineage", "GET"),
        # SPR-02: the fork-merge family — preview/commit receipts, never a
        # body fetch. The diff's point stands: no fork route serves bodies.
        ("/research/artifacts/fork-merge/commit", "POST"),
        ("/research/artifacts/fork-merge/preview", "POST"),
    ]


# ── Proof 3: idempotency on the client operation id ─────────────────────────


def test_fork_idempotency(api_env) -> None:
    db = api_env["db"]
    _seed_book(db)
    client = _client()

    first = client.post("/books/doc-parent/forks", json={"operation_id": "op-1"})
    replay = client.post("/books/doc-parent/forks", json={"operation_id": "op-1"})
    assert first.status_code == 201
    assert replay.status_code == 200  # a replay, honestly not "created"
    assert replay.json()["fork_id"] == first.json()["fork_id"]
    assert len(_fork_rows(db)) == 1

    second = client.post("/books/doc-parent/forks", json={"operation_id": "op-2"})
    assert second.status_code == 201
    assert second.json()["fork_id"] != first.json()["fork_id"]
    assert len(_fork_rows(db)) == 2

    listed = client.get("/books/doc-parent/forks")
    assert {row["fork_id"] for row in listed.json()["forks"]} == {
        first.json()["fork_id"],
        second.json()["fork_id"],
    }


# ── Proof 4: depth-1 refusal ────────────────────────────────────────────────


def test_fork_of_fork_refused_409(api_env) -> None:
    _seed_book(api_env["db"])
    client = _client()
    fork = client.post("/books/doc-parent/forks", json={"operation_id": "op-1"})
    assert fork.status_code == 201
    fork_doc = fork.json()["fork_document_id"]

    refused = client.post(f"/books/{fork_doc}/forks", json={"operation_id": "op-2"})
    assert refused.status_code == 409
    assert "fork_depth_limit" in refused.json()["detail"]


# ── Proof 5: the capture hashes recompute against the stored bodies ─────────


def test_capture_audit_hashes(api_env) -> None:
    db = api_env["db"]
    _seed_book(db)
    client = _client()
    fork = client.post("/books/doc-parent/forks", json={"operation_id": "op-1"})
    assert fork.status_code == 201

    (row,) = _fork_rows(db)
    _, parent_id, fork_id, _, parent_hash, fork_hash = row
    assert parent_hash == _sha(_body(db, parent_id))
    assert fork_hash == _sha(_body(db, fork_id))
    # A copy fork's body is byte-identical at capture — the hashes agree.
    assert parent_hash == fork_hash


# ── The owner boundary ───────────────────────────────────────────────────────


def test_fork_owner_boundary(api_env) -> None:
    """Another owner's fork never crosses the line: the reads 404 / list
    empty after the rows are re-keyed at the store layer."""
    db = api_env["db"]
    _seed_book(db)
    client = _client()
    fork = client.post("/books/doc-parent/forks", json={"operation_id": "op-1"})
    assert fork.status_code == 201

    with connect_write(db, purpose="test/rekey-owner") as con:
        con.execute(
            "UPDATE document_forks SET owner_user_id = 'someone-else'"
        )
        con.execute(
            "UPDATE documents SET owner_user_id = 'someone-else' "
            "WHERE document_id = ?",
            [fork.json()["fork_document_id"]],
        )

    assert client.get(f"/forks/{fork.json()['fork_id']}").status_code == 404
    assert (
        client.get(f"/forks/{fork.json()['fork_id']}/lineage").status_code == 404
    )
    listed = client.get("/books/doc-parent/forks")
    assert listed.status_code == 200
    assert listed.json()["forks"] == []


# ── Adopt mode: the reformat flow's "officially fork" ────────────────────────


def _seed_generation(
    db: str,
    generation_id: str,
    source_document_id: str,
    derived_document_id: str,
) -> None:
    from substrate.provenance.store import GenerationRecordRow, ProvenanceStore

    with connect_write(db, purpose="test/seed-generation") as con:
        ProvenanceStore().record_generation(
            con,
            record=GenerationRecordRow(
                generation_id=generation_id,
                owner_user_id="__operator__",
                source_document_id=source_document_id,
                derived_document_id=derived_document_id,
                prompt="the 20-minute version",
                model="fixture-model",
                params_json="{}",
                mostly_generated=False,
                created_at="2026-10-01T00:00:00Z",
            ),
            bites=[],
        )


def test_adopt_fork_promotes_derived_document(api_env) -> None:
    db = api_env["db"]
    _seed_book(db, "doc-source", title="Source Book")
    _seed_book(db, "doc-derived", title="Source Book (20-minute version)",
               raw_text="A generated condensation.", content_class="public_domain")
    _seed_generation(db, "gen-1", "doc-source", "doc-derived")
    client = _client()

    adopted = client.post(
        "/books/doc-source/forks",
        json={
            "operation_id": "reformat-fork:gen-1",
            "derived_document_id": "doc-derived",
            "generation_id": "gen-1",
        },
    )
    assert adopted.status_code == 201, adopted.text
    row = adopted.json()
    # The fork IS the derived document — promoted, not copied.
    assert row["fork_document_id"] == "doc-derived"
    assert row["generation_id"] == "gen-1"
    assert row["fork_body_sha256"] == _sha("A generated condensation.")
    assert row["parent_body_sha256"] == _sha(_body(db, "doc-source"))

    # Idempotent on the operation id AND naturally on the derived document.
    replay = client.post(
        "/books/doc-source/forks",
        json={
            "operation_id": "reformat-fork:gen-1",
            "derived_document_id": "doc-derived",
            "generation_id": "gen-1",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["fork_id"] == row["fork_id"]
    assert len(_fork_rows(db)) == 1

    # A dangling generation ref is a 422, never stored (a FRESH derived
    # document — re-adopting the already-promoted one is a lawful replay).
    _seed_book(db, "doc-derived-2", title="Another condensation",
               raw_text="A second generated condensation.",
               content_class="public_domain")
    dangling = client.post(
        "/books/doc-source/forks",
        json={
            "operation_id": "op-dangling",
            "derived_document_id": "doc-derived-2",
            "generation_id": "gen-nope",
        },
    )
    assert dangling.status_code == 422

    # The derived document cannot become a fork of a DIFFERENT parent.
    _seed_book(db, "doc-other", title="Other Book")
    conflict = client.post(
        "/books/doc-other/forks",
        json={"operation_id": "op-conflict", "derived_document_id": "doc-derived"},
    )
    assert conflict.status_code == 409
    assert "fork_conflict" in conflict.json()["detail"]


# ── Schema is additive and idempotent ────────────────────────────────────────


def test_forks_ddl_is_additive_and_idempotent(api_env) -> None:
    """The schema init runs on every write entry; applying it twice on one
    connection is a no-op, and the table's constraints hold at the DB."""
    from substrate.documents.forks import init_forks_schema

    with connect_write(api_env["db"], purpose="test/ddl-idempotent") as con:
        init_forks_schema(con)
        init_forks_schema(con)
        # The note cap is a DB-layer CHECK, not only API validation.
        import duckdb

        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO document_forks (fork_id, owner_user_id, "
                "parent_document_id, fork_document_id, operation_id, note, "
                "parent_body_sha256, fork_body_sha256) VALUES (?, ?, ?, ?, "
                "?, ?, ?, ?)",
                [
                    "fork-x", "__operator__", "doc-a", "doc-b", "op-x",
                    "n" * 501, "h" * 64, "h" * 64,
                ],
            )
