"""The companion GET serves the last build and never writes (THREAD-CONTRACT
§1.12: "Its GET routes never write. A refresh is a POST").

Ported from lane A's executed probes on #3514 (C2 rebuild-on-read, C1 the
document-only export path, C4(a) a cached build served after takedown).
Real DuckDB + a real event log per test; the router is mounted alone behind
a test identity middleware (header ``x-test-owner`` becomes the owner), plus
one create_app check that the refresh POST is mounted.

The pinned wire shapes, each asserted with its exact key set:

  GET json, built + servable now  200 payload + ``state: built``,
                                  ``x-antiek-serving: last-build``
  GET json, no build              200 ``{document_id, state: not_built}``
  GET json, withheld now          200 ``{document_id, state: withheld, reason}``
  GET html, no build / withheld   404 ``companion_not_built`` / ``companion_withheld``
  POST refresh, success           200, identical to the next GET
  POST refresh, rebuild fails     503 ``{detail, error_type, has_last_build}``
  foreign or missing document     404 ``book_not_found`` on every route
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import interfaces.research.api.companion_routes as companion_routes
import runtime.db_lock as db_lock
import substrate.companions.evidence_index as evidence_index
import substrate.companions.projector as projector
import substrate.graph as graph
import substrate.graph.schema as graph_schema
import substrate.research_artifact.paths as artifact_paths
from runtime.db_lock import connect_read, connect_write
from substrate.books.highlights.schema import init_highlights_schema
from substrate.books.reading_state import ReadingStateStore
from substrate.graph.ops import insert_document, update_document_gate_columns
from substrate.graph.schema import init_database_at_path

BODY = "The companion probe book opens with a sentence worth keeping."
CLAIM = "SECRET-CLAIM-TEXT the probe finding"

BUILT_KEYS = {
    "document_id",
    "exists",
    "title",
    "servable",
    "rebuilt_at",
    "claims",
    "anchors",
    "processes",
    "state",
}

#: The tables the companion code writes (the index + the SPR-03 wiring).
COMPANION_TABLES = (
    "evidence_index",
    "companion_rebuild_receipts",
    "companion_seen_triggers",
    "companion_seen_triggers_by_owner",
    "companion_watcher_state",
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "probe.duckdb"
    events = tmp_path / "events"
    arts = tmp_path / "artifacts"
    events.mkdir()
    arts.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(arts))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    init_database_at_path(str(db))
    return {"db": str(db), "events": str(events), "arts": str(arts)}


def _seed(
    db: str,
    *,
    document_id: str = "doc-1",
    doc_owner: str = "owner-a",
    content_class: str = "public_domain",
    with_book_asset: bool = False,
    anchor_owner: str | None = None,
    reading_owner: str | None = None,
) -> None:
    with connect_write(db, purpose="test/seed") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title="The Probe Book",
            raw_text=BODY,
            content_class=content_class,
            owner_user_id=doc_owner,
            on_conflict="ignore",
        )
        if with_book_asset:
            con.execute("INSERT INTO book_assets (document_id) VALUES (?)", [document_id])
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, section_path, "
            "text, token_count) VALUES (?, ?, 0, 'Page 1', ?, 9)",
            [f"c-{document_id}", document_id, BODY],
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES (?, ?, 'insight', 'depth')",
            [f"n-1-{document_id}", CLAIM],
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, source_document_id, source_tier, extraction_confidence, "
            "investigation_id, graph_scope) VALUES "
            "(?, ?, ?, 'supported_by', ?, ?, 2, 0.9, 'inv-1', 'depth')",
            [
                f"e-1-{document_id}",
                f"n-1-{document_id}",
                f"n-1-{document_id}",
                f"c-{document_id}",
                document_id,
            ],
        )
        if anchor_owner:
            init_highlights_schema(con)
            con.execute(
                "INSERT INTO anchored_highlights (anchor_id, owner_user_id, document_id, "
                "normalization, anchor_node_id, anchor_node_text_sha256, "
                "anchor_start_scalar, anchor_end_scalar, servable_at_pin, anchor_quote, "
                "anchor_prefix, anchor_suffix, selection_text_sha256, page_index_hint, "
                "source, status, investigation_id) VALUES (?, ?, ?, 'unicode-nfc-v1', ?, ?, "
                "0, 11, TRUE, 'the opening', '', '', ?, 0, 'pin', 'active', 'inv-1')",
                [
                    f"ahl-{anchor_owner}-{document_id}",
                    anchor_owner,
                    document_id,
                    f"c-{document_id}",
                    hashlib.sha256(BODY.encode()).hexdigest(),
                    hashlib.sha256(b"the opening").hexdigest(),
                ],
            )
        if reading_owner:
            ReadingStateStore().put(
                con,
                owner_user_id=reading_owner,
                document_id=document_id,
                page_index=41,
                anchor_ref=None,
                prefs_json="{}",
                expected_revision=0,
            )


def _identity_app() -> FastAPI:
    """The companion router alone behind a test identity middleware: header
    x-test-owner becomes request.state.user_id (what _reader_owner_id reads)."""
    app = FastAPI()
    companion_routes.register_companion_routes(app)

    @app.middleware("http")
    async def _identity(request: Request, call_next: Any) -> Any:
        request.state.user_id = request.headers.get("x-test-owner") or "owner-a"
        request.state.auth_method = "antiek_session_cookie"
        return await call_next(request)

    return app


def _client() -> TestClient:
    return TestClient(_identity_app(), raise_server_exceptions=False)


def _as(owner: str) -> dict[str, str]:
    return {"x-test-owner": owner}


def _get_json(client: TestClient, owner: str = "owner-a", doc: str = "doc-1") -> Any:
    return client.get(f"/documents/{doc}/companion?format=json", headers=_as(owner))


def _get_html(client: TestClient, owner: str = "owner-a", doc: str = "doc-1") -> Any:
    return client.get(f"/documents/{doc}/companion", headers=_as(owner))


def _refresh(client: TestClient, owner: str = "owner-a", doc: str = "doc-1") -> Any:
    return client.post(f"/documents/{doc}/companion/refresh", headers=_as(owner))


def _snapshot(env: dict[str, str]) -> dict[str, Any]:
    """Every row the companion code writes + every file under the artifacts
    and events directories (bytes hashed)."""
    con = connect_read(env["db"])
    try:
        present = {
            str(r[0])
            for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()
        }
        tables = {
            t: sorted(con.execute(f"SELECT * FROM {t}").fetchall(), key=repr)
            for t in COMPANION_TABLES
            if t in present
        }
    finally:
        con.close()
    files: dict[str, str] = {}
    for root in (env["arts"], env["events"]):
        for p in sorted(Path(root).rglob("*")):
            key = str(p)
            files[key] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir"
    return {"tables": tables, "files": files}


def _spy_every_writer(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace every write seam the companion code reaches with a recorder
    that also raises: a GET that touches one fails loudly, and the list
    says which."""
    calls: list[str] = []

    def spy(name: str) -> Any:
        def _boom(*_a: Any, **_kw: Any) -> Any:
            calls.append(name)
            raise AssertionError(f"GET reached a write seam: {name}")

        return _boom

    monkeypatch.setattr(db_lock, "connect_write", spy("db_lock.connect_write"))
    monkeypatch.setattr(projector, "connect_write", spy("projector.connect_write"))
    monkeypatch.setattr(graph_schema, "connect_write", spy("graph_schema.connect_write"))
    # Schema init takes the writer lock on a cold probe; the GET never calls it.
    monkeypatch.setattr(graph, "ensure_initialized", spy("graph.ensure_initialized"))
    monkeypatch.setattr(
        graph_schema, "init_database_at_path", spy("graph_schema.init_database_at_path")
    )
    for name in ("rebuild_document_full", "export_document_companion", "rebuild_document"):
        monkeypatch.setattr(projector, name, spy(f"projector.{name}"))
        monkeypatch.setattr(companion_routes, name, spy(f"routes.{name}"), raising=False)
    monkeypatch.setattr(projector, "rebuild_scope", spy("projector.rebuild_scope"))
    monkeypatch.setattr(evidence_index, "rebuild_scope", spy("evidence_index.rebuild_scope"))
    monkeypatch.setattr(
        artifact_paths, "atomic_write_nofollow", spy("paths.atomic_write_nofollow")
    )
    monkeypatch.setattr(pathlib.Path, "write_text", spy("Path.write_text"))
    monkeypatch.setattr(pathlib.Path, "write_bytes", spy("Path.write_bytes"))
    return calls


# ── C2: the GET never writes ────────────────────────────────────────────────


def test_get_json_and_html_never_write_with_a_build_on_disk(env, monkeypatch) -> None:
    _seed(env["db"], anchor_owner="owner-a", reading_owner="owner-a")
    # The build comes from the substrate export (the refresh's work), so this
    # test isolates the GET: whatever it does after this line must be a read.
    projector.export_document_companion(
        env["db"], owner_user_id="owner-a", document_id="doc-1", events_dir=env["events"]
    )
    before = _snapshot(env)
    calls = _spy_every_writer(monkeypatch)
    client = _client()

    rj = _get_json(client)
    rh = _get_html(client)

    assert calls == []
    assert rj.status_code == 200, rj.text
    assert rh.status_code == 200, rh.text
    assert rj.json()["state"] == "built"
    assert rj.headers["x-antiek-serving"] == "last-build"
    assert rh.headers["x-antiek-serving"] == "last-build"
    assert _snapshot(env) == before


def test_get_never_writes_before_any_build(env, monkeypatch) -> None:
    _seed(env["db"])
    before = _snapshot(env)
    calls = _spy_every_writer(monkeypatch)
    client = _client()

    rj = _get_json(client)
    rh = _get_html(client)

    assert calls == []
    assert rj.status_code == 200
    assert rh.status_code == 404
    assert _snapshot(env) == before


def test_get_serves_the_last_build_not_a_fresh_projection(env) -> None:
    """After a refresh the sources move on; the GET keeps serving the build
    it has (same stamp, same claims) until the next POST."""
    _seed(env["db"])
    client = _client()
    first = _refresh(client)
    assert first.status_code == 200, first.text

    with connect_write(env["db"], purpose="test/new-claim") as con:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('n-late', 'a later finding', 'insight', 'depth')"
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, source_document_id, source_tier, extraction_confidence, "
            "investigation_id, graph_scope) VALUES ('e-late', 'n-late', 'n-late', "
            "'supported_by', 'c-doc-1', 'doc-1', 2, 0.9, 'inv-1', 'depth')"
        )

    served = _get_json(client)
    assert served.json() == first.json()
    assert served.headers["x-antiek-rebuilt-at"] == first.headers["x-antiek-rebuilt-at"]
    assert "a later finding" not in _get_html(client).text

    again = _refresh(client)
    assert again.status_code == 200
    assert "a later finding" in [c["text"] for c in again.json()["claims"]]
    assert "a later finding" in [c["text"] for c in _get_json(client).json()["claims"]]


# ── The pinned shapes ───────────────────────────────────────────────────────


def test_before_any_refresh_json_is_not_built_and_html_is_404(env) -> None:
    _seed(env["db"])
    client = _client()

    rj = _get_json(client)
    assert rj.status_code == 200
    assert rj.json() == {"document_id": "doc-1", "state": "not_built"}

    rh = _get_html(client)
    assert rh.status_code == 404
    assert rh.json() == {"detail": "companion_not_built"}


def test_refresh_returns_the_build_and_the_get_serves_the_same_one(env) -> None:
    _seed(env["db"], anchor_owner="owner-a", reading_owner="owner-a")
    client = _client()

    posted = _refresh(client)
    assert posted.status_code == 200, posted.text
    body = posted.json()
    assert set(body) == BUILT_KEYS
    assert body["state"] == "built"
    assert body["document_id"] == "doc-1"
    assert body["servable"] is True
    assert [c["text"] for c in body["claims"]] == [CLAIM]
    stamp = posted.headers["x-antiek-rebuilt-at"]
    assert stamp == body["rebuilt_at"]

    rj = _get_json(client)
    assert rj.status_code == 200
    assert rj.json() == body
    assert rj.headers["x-antiek-rebuilt-at"] == stamp
    assert rj.headers["x-antiek-serving"] == "last-build"
    assert rj.headers["x-antiek-companion-generated"] == "true"
    assert rj.headers["x-antiek-document-id"] == "doc-1"

    rh = _get_html(client)
    assert rh.status_code == 200
    assert rh.headers["x-antiek-rebuilt-at"] == stamp
    assert rh.headers["x-antiek-serving"] == "last-build"
    assert rh.headers["x-antiek-companion-generated"] == "true"
    assert rh.headers["x-antiek-document-id"] == "doc-1"
    assert rh.text.startswith("<!-- generated: never authored")
    assert CLAIM in rh.text
    assert _get_html(client).text == rh.text  # the stored export, byte-stable


def test_failed_refresh_is_503_with_the_type_only_and_keeps_the_last_build(
    env, monkeypatch
) -> None:
    _seed(env["db"])
    _seed(env["db"], document_id="doc-2")
    client = _client()
    good = _refresh(client)
    assert good.status_code == 200

    def failing_rebuild(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("SECRET-FAILURE-TEXT /var/lib/antiek/graph.duckdb")

    monkeypatch.setattr(projector, "rebuild_document_full", failing_rebuild)

    failed = _refresh(client)
    assert failed.status_code == 503
    assert failed.json() == {
        "detail": "companion_rebuild_failed",
        "error_type": "RuntimeError",
        "has_last_build": True,
    }
    assert "SECRET-FAILURE-TEXT" not in failed.text

    # The previous build keeps serving, untouched.
    served = _get_json(client)
    assert served.json() == good.json()
    assert served.headers["x-antiek-rebuilt-at"] == good.headers["x-antiek-rebuilt-at"]

    # A document that never built says so.
    never = _refresh(client, doc="doc-2")
    assert never.status_code == 503
    assert never.json() == {
        "detail": "companion_rebuild_failed",
        "error_type": "RuntimeError",
        "has_last_build": False,
    }
    assert _get_json(client, doc="doc-2").json() == {"document_id": "doc-2", "state": "not_built"}


# ── C1: one owner's build never reaches another ─────────────────────────────


def test_rekeyed_document_never_serves_the_previous_owners_build(env) -> None:
    _seed(env["db"], anchor_owner="owner-a", reading_owner="owner-a")
    client = _client()
    a_build = _refresh(client, owner="owner-a")
    assert a_build.status_code == 200, a_build.text
    assert a_build.json()["anchors"], "A's own anchor is in A's build"
    assert "page 42" in json.dumps(a_build.json()["processes"])

    with connect_write(env["db"], purpose="test/rekey") as con:
        con.execute("UPDATE documents SET owner_user_id = 'owner-b' WHERE document_id = 'doc-1'")

    # B has no build of its own: nothing of A's is served.
    rj = _get_json(client, owner="owner-b")
    assert rj.status_code == 200
    assert rj.json() == {"document_id": "doc-1", "state": "not_built"}
    rh = _get_html(client, owner="owner-b")
    assert rh.status_code == 404
    assert rh.json() == {"detail": "companion_not_built"}

    # A no longer owns the document: every route is the owner-boundary 404.
    for resp in (
        _get_json(client, owner="owner-a"),
        _get_html(client, owner="owner-a"),
        _refresh(client, owner="owner-a"),
    ):
        assert resp.status_code == 404
        assert resp.json() == {"detail": "book_not_found"}

    # B's refresh builds B's own view: A's anchor and reading position are absent.
    b_build = _refresh(client, owner="owner-b")
    assert b_build.status_code == 200, b_build.text
    assert b_build.json()["state"] == "built"
    assert b_build.json()["anchors"] == []
    assert "page 42" not in json.dumps(b_build.json()["processes"])
    assert _get_json(client, owner="owner-b").json() == b_build.json()
    assert "page 42" not in _get_html(client, owner="owner-b").text


def test_each_owner_keeps_its_own_build(env) -> None:
    """Builds live side by side per (owner, document): B's refresh never
    overwrites A's build, so when the document returns to A, A's GET serves
    A's own build (never B's, never nothing)."""
    _seed(env["db"], anchor_owner="owner-a", reading_owner="owner-a")
    client = _client()
    a_build = _refresh(client, owner="owner-a").json()
    for new_owner in ("owner-b", "owner-a"):
        with connect_write(env["db"], purpose="test/rekey") as con:
            con.execute(
                "UPDATE documents SET owner_user_id = ? WHERE document_id = 'doc-1'",
                [new_owner],
            )
        if new_owner == "owner-b":
            assert _refresh(client, owner="owner-b").status_code == 200

    served = _get_json(client, owner="owner-a")
    assert served.status_code == 200
    assert served.json() == a_build
    assert "page 42" in _get_html(client, owner="owner-a").text


def test_another_owners_or_a_legacy_export_on_disk_is_never_served(env) -> None:
    """The persisted build is keyed by (owner, document): a build written
    for owner A (and a legacy document-only file) is never what B's GET
    serves after a re-key, even when the files sit on disk."""
    _seed(env["db"], anchor_owner="owner-a", reading_owner="owner-a")
    legacy = Path(env["arts"]) / "companions" / "doc-1.html"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("<!-- LEGACY-EXPORT --><p>page 42</p>", encoding="utf-8")
    projector.export_document_companion(
        env["db"], owner_user_id="owner-a", document_id="doc-1", events_dir=env["events"]
    )
    with connect_write(env["db"], purpose="test/rekey") as con:
        con.execute("UPDATE documents SET owner_user_id = 'owner-b' WHERE document_id = 'doc-1'")
    client = _client()

    rh = _get_html(client, owner="owner-b")
    assert rh.status_code == 404
    assert rh.json() == {"detail": "companion_not_built"}
    assert "page 42" not in rh.text and "LEGACY-EXPORT" not in rh.text
    rj = _get_json(client, owner="owner-b")
    assert rj.json() == {"document_id": "doc-1", "state": "not_built"}


# ── C4(a): a withheld document's cached build is not served ────────────────


def test_takedown_withholds_the_cached_build(env) -> None:
    from substrate.books.takedown import take_down

    _seed(env["db"], with_book_asset=True)
    client = _client()
    assert _refresh(client).status_code == 200
    assert CLAIM in _get_html(client).text

    with connect_write(env["db"], purpose="test/takedown") as con:
        assert take_down(con, "doc-1", reason="test") is True

    rj = _get_json(client)
    assert rj.status_code == 200
    assert rj.json() == {"document_id": "doc-1", "state": "withheld", "reason": "taken_down"}
    rh = _get_html(client)
    assert rh.status_code == 404
    assert rh.json() == {"detail": "companion_withheld"}
    assert CLAIM not in rj.text and CLAIM not in rh.text


def test_takedown_withholds_even_when_every_rebuild_fails(env, monkeypatch) -> None:
    """The probe's lock-timeout shape: after take_down, a rebuild that can
    never take the writer lock must not surface the pre-takedown build."""
    from runtime.db_lock import WriteLockTimeout
    from substrate.books.takedown import take_down

    _seed(env["db"], with_book_asset=True)
    projector.export_document_companion(
        env["db"], owner_user_id="owner-a", document_id="doc-1", events_dir=env["events"]
    )
    with connect_write(env["db"], purpose="test/takedown") as con:
        take_down(con, "doc-1", reason="test")

    def timeout_write(*_a: Any, **_kw: Any) -> Any:
        raise WriteLockTimeout("writer lock held past timeout")

    monkeypatch.setattr(projector, "connect_write", timeout_write)
    client = _client()
    rh = _get_html(client)
    assert rh.status_code == 404
    assert rh.json() == {"detail": "companion_withheld"}
    assert CLAIM not in rh.text


def test_taken_down_flag_alone_withholds(env) -> None:
    """book_assets.taken_down=TRUE with the class untouched: the reader's
    predicate (servability_of with the flag) honours it, so the companion
    does too."""
    _seed(env["db"], with_book_asset=True)
    client = _client()
    assert _refresh(client).status_code == 200
    with connect_write(env["db"], purpose="test/flag-only") as con:
        con.execute("UPDATE book_assets SET taken_down = TRUE WHERE document_id = 'doc-1'")

    assert _get_json(client).json() == {
        "document_id": "doc-1",
        "state": "withheld",
        "reason": "taken_down",
    }
    assert _get_html(client).json() == {"detail": "companion_withheld"}


def test_a_document_that_stopped_being_servable_is_withheld(env) -> None:
    _seed(env["db"], with_book_asset=True)
    client = _client()
    assert _refresh(client).status_code == 200
    with connect_write(env["db"], purpose="test/gate") as con:
        update_document_gate_columns(
            con, "doc-1", content_class="restricted_pending_opt_in", set_content_class=True
        )

    rj = _get_json(client)
    assert rj.status_code == 200
    assert rj.json() == {"document_id": "doc-1", "state": "withheld", "reason": "not_servable"}
    assert CLAIM not in rj.text
    rh = _get_html(client)
    assert rh.status_code == 404
    assert rh.json() == {"detail": "companion_withheld"}


# ── The owner boundary ──────────────────────────────────────────────────────


def test_foreign_and_missing_documents_are_the_same_404_on_every_route(env) -> None:
    _seed(env["db"], doc_owner="owner-a")
    before = _snapshot(env)
    client = _client()
    cases = [
        ("owner-b", "doc-1"),  # foreign
        ("owner-a", "doc-missing"),  # missing
    ]
    for owner, doc in cases:
        for resp in (
            _get_json(client, owner=owner, doc=doc),
            _get_html(client, owner=owner, doc=doc),
            _refresh(client, owner=owner, doc=doc),
        ):
            assert resp.status_code == 404, (owner, doc, resp.text)
            assert resp.json() == {"detail": "book_not_found"}
    assert _snapshot(env) == before  # a refused refresh wrote nothing


def test_refresh_is_mounted_in_the_app(env) -> None:
    from interfaces.research.api.app import create_app

    _seed(env["db"], doc_owner="__operator__")
    client = TestClient(create_app(register_wrestling=False))
    posted = client.post("/documents/doc-1/companion/refresh")
    assert posted.status_code == 200, posted.text
    assert posted.json()["state"] == "built"
    served = client.get("/documents/doc-1/companion?format=json")
    assert served.json() == posted.json()
