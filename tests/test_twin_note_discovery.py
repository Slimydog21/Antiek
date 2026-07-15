from __future__ import annotations

import hashlib
import inspect
import json
import threading

import pytest
import duckdb
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import twin_note_routes
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from substrate.twin_note_taker.compression import (
    TwinNoteCompressionError,
    build_window_admission,
    validate_window_evidence,
)
from substrate.twin_note_taker.discovery import (
    TwinNoteDiscoveryService,
    TwinNoteDiscoveryUnavailable,
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _seed_document(con, asset, owner, title="Shared title"):
    con.execute(
        "INSERT INTO documents(document_id,title,source_tier,document_type,owner_user_id) "
        "VALUES (?,?,?,?,?)", [asset, title, 1, "text", owner]
    )


def _seed_binding(con, notebook, asset, investigation, owner):
    con.execute(
        "INSERT INTO notebooks(notebook_id,title,document_id,investigation_id,owner_user_id) "
        "VALUES (?,?,?,?,?)", [notebook, "Notebook", asset, investigation, owner]
    )


def _seed_window(con, window, investigation, ordinal=0):
    sources = [f"evt-{window}"]
    source_json = _canonical(sources)
    request_json = _canonical({
        "investigation_id": investigation,
        "source_event_ids": sources,
    })
    raw = _canonical({"notes": [{
        "text": f"Note {window}", "confidence": "high",
        "source_event_ids": sources,
    }]})
    con.execute(
        "INSERT INTO note_taker_windows(window_id,consumer_version,investigation_id,"
        "threshold,ordinal,first_event_id,last_event_id,source_event_ids_json,source_digest,"
        "request_json,request_sha256,provider_idempotency_key,state,raw_result,raw_result_sha256) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [window, 2, investigation, 5, ordinal, sources[0], sources[-1], source_json,
         _sha(source_json), request_json, _sha(request_json), window, "completed", raw, _sha(raw)],
    )


@pytest.fixture
def database(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    return db


def test_owner_join_deduplicates_and_is_not_a_foreign_oracle(database):
    with connect_write(database, purpose="test/discovery-seed") as con:
        _seed_document(con, "asset-a", "owner-a")
        _seed_document(con, "asset-b", "owner-b")
        _seed_binding(con, "n-a-1", "asset-a", "inv-shared", "owner-a")
        _seed_binding(con, "n-a-2", "asset-a", "inv-shared", "owner-a")
        _seed_binding(con, "n-b", "asset-b", "inv-shared", "owner-b")
        _seed_window(con, "window-shared", "inv-shared")
    service = TwinNoteDiscoveryService(db_path=database)
    owner = service.candidates("owner-a")
    assert [asset["asset_id"] for asset in owner["assets"]] == ["asset-a"]
    assert [row["window_id"] for row in owner["assets"][0]["windows"]] == ["window-shared"]
    assert type(owner["assets"][0]["windows"][0]["consumer_version"]) is int
    assert service.candidates("nobody") == service.candidates("empty-owner")


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("UPDATE note_taker_windows SET state='materialized'", "evidence_incomplete"),
        ("UPDATE note_taker_windows SET raw_result='changed'", "evidence_digest_mismatch"),
        ("UPDATE note_taker_windows SET source_event_ids_json='[ ]', source_digest=sha256('[ ]')",
         "evidence_noncanonical"),
        ("UPDATE note_taker_windows SET "
         "request_json='{\"investigation_id\":\"other\",\"source_event_ids\":[\"evt-window\"]}', "
         "request_sha256=sha256('{\"investigation_id\":\"other\",\"source_event_ids\":[\"evt-window\"]}')",
         "evidence_binding_mismatch"),
        ("UPDATE note_taker_windows SET raw_result='{\"notes\":[{\"text\":\"bad\"}]}', "
         "raw_result_sha256=sha256('{\"notes\":[{\"text\":\"bad\"}]}')",
         "evidence_output_invalid"),
    ],
)
def test_candidate_corruption_maps_to_closed_reason(database, sql, reason):
    with connect_write(database, purpose="test/discovery-corruption") as con:
        _seed_document(con, "asset", "owner")
        _seed_binding(con, "notebook", "asset", "inv", "owner")
        _seed_window(con, "window", "inv")
        con.execute(sql)
    window = TwinNoteDiscoveryService(db_path=database).candidates("owner")["assets"][0]["windows"][0]
    assert window["eligibility"] == "excluded"
    assert window["exclusion_reason"] == reason
    assert window["note_count"] == window["source_count"] == 0


def test_discovery_order_is_deterministic_and_admission_shares_validator(database, monkeypatch):
    with connect_write(database, purpose="test/discovery-order") as con:
        _seed_document(con, "asset", "owner", title="")
        _seed_binding(con, "notebook", "asset", "z-investigation", "owner")
        _seed_binding(con, "notebook-2", "asset", "a-investigation", "owner")
        _seed_window(con, "window-z", "z-investigation", 0)
        _seed_window(con, "window-a", "a-investigation", 9)
    service = TwinNoteDiscoveryService(db_path=database)
    first = service.candidates("owner")
    second = service.candidates("owner")
    assert first == second
    assert first["assets"][0]["asset_label"] == "Untitled document"
    assert [w["window_id"] for w in first["assets"][0]["windows"]] == ["window-a", "window-z"]

    calls = []
    original = validate_window_evidence
    monkeypatch.setattr("substrate.twin_note_taker.compression.validate_window_evidence",
                        lambda row: calls.append(row[0]) or original(row))
    service.candidates("owner")
    admission = build_window_admission(
        db_path=database, ownership_resolver=lambda *_: True,
        account_id="owner", asset_id="asset", window_ids=("window-a",),
    )
    assert admission.window_ids == ("window-a",)
    assert calls == ["window-a", "window-z", "window-a"]


def test_parameter_free_route_is_private_and_value_free(database, monkeypatch):
    monkeypatch.setattr(twin_note_routes, "default_db_path", lambda: database)
    app = FastAPI()

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        request.state.user_id = request.headers.get("x-test-user", "owner")
        return await call_next(request)

    app.include_router(twin_note_routes.twin_note_router)
    client = TestClient(app)
    response = client.get("/research/twin-notes/revision-candidates?asset_id=secret")
    assert response.status_code == 422
    assert response.headers["cache-control"] == "private, no-store"
    assert "secret" not in response.text and "asset_id" not in response.text

    body_response = client.request("GET", "/research/twin-notes/revision-candidates",
                                   content='{"window_id":"secret"}')
    assert body_response.status_code == 422
    assert body_response.headers["cache-control"] == "private, no-store"
    assert "secret" not in body_response.text and "window_id" not in body_response.text

    unauthenticated = FastAPI()
    unauthenticated.include_router(twin_note_routes.twin_note_router)
    auth_response = TestClient(unauthenticated).get(
        "/research/twin-notes/revision-candidates")
    assert auth_response.status_code == 401
    assert auth_response.headers["cache-control"] == "private, no-store"

    with connect_write(database, purpose="test/discovery-foreign-only") as con:
        _seed_document(con, "foreign-asset", "foreign")
        _seed_binding(con, "foreign-notebook", "foreign-asset", "foreign-inv", "foreign")
        _seed_window(con, "foreign-window", "foreign-inv")
    empty_one = client.get("/research/twin-notes/revision-candidates",
                           headers={"x-test-user": "owner"})
    empty_two = client.get("/research/twin-notes/revision-candidates",
                           headers={"x-test-user": "nobody"})
    assert empty_one.content == empty_two.content


def test_validator_output_failure_is_shared_with_admission(database):
    with connect_write(database, purpose="test/discovery-output") as con:
        _seed_window(con, "window", "inv")
        raw = _canonical({"notes": [{"text": "missing attribution"}]})
        con.execute("UPDATE note_taker_windows SET raw_result=?, raw_result_sha256=?",
                    [raw, _sha(raw)])
    with pytest.raises(TwinNoteCompressionError, match="output is invalid"):
        build_window_admission(
            db_path=database, ownership_resolver=lambda *_: True,
            account_id="owner", asset_id="asset", window_ids=("window",),
        )


@pytest.mark.parametrize("column", ["source_event_ids_json", "request_json", "raw_result"])
def test_evidence_size_ceiling_is_shared_with_admission(database, column):
    from substrate.twin_note_taker import compression

    with connect_write(database, purpose="test/discovery-evidence-size") as con:
        _seed_document(con, "asset", "owner")
        _seed_binding(con, "notebook", "asset", "inv", "owner")
        _seed_window(con, "window", "inv")
        oversized = "x" * (compression.MAX_WINDOW_EVIDENCE_FIELD_BYTES + 1)
        digest_column = {
            "source_event_ids_json": "source_digest",
            "request_json": "request_sha256",
            "raw_result": "raw_result_sha256",
        }[column]
        con.execute(
            f"UPDATE note_taker_windows SET {column}=?, {digest_column}=?",
            [oversized, _sha(oversized)],
        )

    candidate = TwinNoteDiscoveryService(db_path=database).candidates("owner")["assets"][0]["windows"][0]
    assert candidate["exclusion_reason"] == "evidence_output_invalid"
    with pytest.raises(TwinNoteCompressionError, match="output is invalid"):
        build_window_admission(
            db_path=database, ownership_resolver=lambda *_: True,
            account_id="owner", asset_id="asset", window_ids=("window",),
        )


def test_parser_exception_is_closed(monkeypatch):
    sources = _canonical(["evt"])
    request = _canonical({"investigation_id": "inv", "source_event_ids": ["evt"]})
    raw = _canonical({"notes": []})
    row = ("window", 2, "inv", 0, sources, _sha(sources), request, _sha(request),
           "completed", raw, _sha(raw))
    monkeypatch.setattr("substrate.twin_note_taker.compression.parse_notes_response",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("secret")))
    assert validate_window_evidence(row).exclusion_reason == "evidence_output_invalid"


def test_connection_failure_is_availability_not_integrity(monkeypatch):
    monkeypatch.setattr("substrate.twin_note_taker.discovery.connect_read",
                        lambda _path: (_ for _ in ()).throw(OSError("secret path")))
    with pytest.raises(TwinNoteDiscoveryUnavailable, match="unavailable"):
        TwinNoteDiscoveryService(db_path="secret path").candidates("owner")


def test_complete_join_rejects_null_and_owner_mismatch(database):
    with connect_write(database, purpose="test/discovery-complete-join") as con:
        _seed_document(con, "good", "owner")
        _seed_document(con, "wrong", "other")
        _seed_binding(con, "good-binding", "good", "inv", "owner")
        _seed_binding(con, "wrong-notebook-owner", "good", "inv", "other")
        _seed_binding(con, "wrong-document-owner", "wrong", "inv", "owner")
        con.execute("INSERT INTO notebooks(notebook_id,title,document_id,investigation_id,owner_user_id) "
                    "VALUES ('null-document','N',NULL,'inv','owner'),"
                    "('null-investigation','N','good',NULL,'owner')")
        _seed_window(con, "window", "inv")
    result = TwinNoteDiscoveryService(db_path=database).candidates("owner")
    assert [asset["asset_id"] for asset in result["assets"]] == ["good"]
    assert len(result["assets"][0]["windows"]) == 1


def test_sql_bounds_foreign_capacity_and_validation_cap(database, monkeypatch):
    from substrate.twin_note_taker import discovery

    monkeypatch.setattr(discovery, "MAX_DISCOVERY_ASSETS", 2)
    monkeypatch.setattr(discovery, "MAX_WINDOWS_PER_ASSET", 2)
    monkeypatch.setattr(discovery, "MAX_TOTAL_WINDOWS", 2)
    with connect_write(database, purpose="test/discovery-bounds") as con:
        for owner, prefix, count in (("foreign", "foreign", 8), ("owner", "owned", 3)):
            for index in range(count):
                asset = f"{prefix}-asset-{index}"
                investigation = f"{prefix}-inv-{index}"
                _seed_document(con, asset, owner)
                _seed_binding(con, f"{prefix}-notebook-{index}", asset, investigation, owner)
                _seed_window(con, f"{prefix}-window-{index}", investigation)
    calls = []
    original = validate_window_evidence
    monkeypatch.setattr("substrate.twin_note_taker.compression.validate_window_evidence",
                        lambda row: calls.append(row[0]) or original(row))
    result = TwinNoteDiscoveryService(db_path=database).candidates("owner")
    assert [asset["asset_id"] for asset in result["assets"]] == [
        "owned-asset-0", "owned-asset-1"]
    assert result["truncated"] is True
    assert len(calls) == 2
    assert all("foreign" not in json.dumps(asset) for asset in result["assets"])


def test_response_forbidden_field_audit(database):
    with connect_write(database, purpose="test/discovery-field-audit") as con:
        _seed_document(con, "asset", "owner")
        _seed_binding(con, "notebook", "asset", "inv", "owner")
        _seed_window(con, "window", "inv")
    encoded = json.dumps(TwinNoteDiscoveryService(db_path=database).candidates("owner"))
    for forbidden in ("raw_result", "source_event_ids", "sha256", "provider", "model",
                      "policy", "attempt", "created_at", "updated_at", "owner_user_id",
                      "hidden_total"):
        assert forbidden not in encoded


def test_discovery_is_read_only_and_has_no_service_construction_seams(database, monkeypatch):
    from substrate.twin_note_taker import compression, workflow

    before = open(database, "rb").read()
    monkeypatch.setattr(compression.DurableTwinNoteCompression, "__init__",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("compressor")))
    monkeypatch.setattr(workflow.TwinNoteWorkflow, "__init__",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("workflow")))
    TwinNoteDiscoveryService(db_path=database).candidates("owner")
    assert open(database, "rb").read() == before
    from substrate.twin_note_taker import discovery
    source = inspect.getsource(discovery)
    for forbidden in ("connect_write", "init_database_at_path", "publication_root",
                      "events_dir", "provider", "background", "dispatch_aggregate_pending"):
        assert forbidden not in source


@pytest.mark.parametrize(
    ("asset_limit", "window_limit", "total_limit", "asset_count", "windows_each",
     "expected_assets", "expected_windows", "truncated"),
    [
        (2, 2, 4, 2, 2, 2, 4, False),
        (2, 2, 4, 3, 2, 2, 4, True),
        (2, 2, 4, 1, 3, 1, 2, True),
        (3, 3, 2, 2, 2, 1, 2, True),
    ],
)
def test_exact_and_plus_one_bound_matrix(
    database, monkeypatch, asset_limit, window_limit, total_limit,
    asset_count, windows_each, expected_assets, expected_windows, truncated,
):
    from substrate.twin_note_taker import discovery

    monkeypatch.setattr(discovery, "MAX_DISCOVERY_ASSETS", asset_limit)
    monkeypatch.setattr(discovery, "MAX_WINDOWS_PER_ASSET", window_limit)
    monkeypatch.setattr(discovery, "MAX_TOTAL_WINDOWS", total_limit)
    with connect_write(database, purpose="test/discovery-bound-matrix") as con:
        # Reverse insertion order and identical labels prove PK ordering.
        for asset_index in reversed(range(asset_count)):
            asset = f"asset-{asset_index}"
            investigation = f"inv-{asset_index}"
            _seed_document(con, asset, "owner", title="Equal label")
            _seed_binding(con, f"notebook-{asset_index}", asset, investigation, "owner")
            for window_index in reversed(range(windows_each)):
                _seed_window(con, f"window-{asset_index}-{window_index}",
                             investigation, window_index)
    result = TwinNoteDiscoveryService(db_path=database).candidates("owner")
    assert len(result["assets"]) == expected_assets
    assert sum(len(asset["windows"]) for asset in result["assets"]) == expected_windows
    assert result["truncated"] is truncated
    assert [asset["asset_id"] for asset in result["assets"]] == sorted(
        asset["asset_id"] for asset in result["assets"])


def test_raw_byte_ceiling_excludes_without_parser(database, monkeypatch):
    from substrate.twin_note_taker import compression

    with connect_write(database, purpose="test/discovery-raw-bound") as con:
        _seed_document(con, "asset", "owner")
        _seed_binding(con, "notebook", "asset", "inv", "owner")
        _seed_window(con, "window", "inv")
    monkeypatch.setattr(compression, "MAX_WINDOW_EVIDENCE_FIELD_BYTES", 1)
    monkeypatch.setattr(compression, "parse_notes_response",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("parser called")))
    window = TwinNoteDiscoveryService(db_path=database).candidates("owner")["assets"][0]["windows"][0]
    assert window["exclusion_reason"] == "evidence_output_invalid"


def test_each_eligible_singleton_really_previews_without_mutation(database, tmp_path):
    from runtime.db_lock import connect_read
    from substrate.twin_note_taker.workflow import TwinNoteWorkflow

    with connect_write(database, purpose="test/discovery-preview") as con:
        _seed_document(con, "asset", "owner")
        _seed_binding(con, "notebook", "asset", "inv", "owner")
        _seed_window(con, "window", "inv")
    candidate = TwinNoteDiscoveryService(db_path=database).candidates("owner")["assets"][0]["windows"][0]
    workflow = TwinNoteWorkflow(
        lambda account, asset, investigation: (account, asset, investigation)
        == ("owner", "asset", "inv"),
        db_path=database,
        publication_root=tmp_path / "published",
    )
    preview = workflow.preview(account_id="owner", asset_id="asset",
                               window_ids=[candidate["window_id"]])
    assert preview.asset_id == "asset"
    with connect_read(database) as con:
        assert con.execute("SELECT COUNT(*) FROM twin_note_revisions").fetchone() == (0,)


def test_identity_fetches_obey_remaining_global_plus_one(database, monkeypatch):
    from substrate.twin_note_taker import discovery

    monkeypatch.setattr(discovery, "MAX_DISCOVERY_ASSETS", 3)
    monkeypatch.setattr(discovery, "MAX_WINDOWS_PER_ASSET", 10)
    monkeypatch.setattr(discovery, "MAX_TOTAL_WINDOWS", 3)
    with connect_write(database, purpose="test/discovery-staged-limits") as con:
        for asset_index in range(2):
            asset = f"asset-{asset_index}"
            investigation = f"inv-{asset_index}"
            _seed_document(con, asset, "owner")
            _seed_binding(con, f"notebook-{asset_index}", asset, investigation, "owner")
            for window_index in range(2):
                _seed_window(con, f"window-{asset_index}-{window_index}",
                             investigation, window_index)

    real_connect = discovery.connect_read
    fetches = []

    class Buffered:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class RecordingConnection:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.connection.close()

        def execute(self, sql, params=None):
            cursor = self.connection.execute(sql, params or [])
            if "SELECT DISTINCT w.window_id" in sql:
                rows = cursor.fetchall()
                fetches.append((params[-1], len(rows)))
                return Buffered(rows)
            return cursor

    monkeypatch.setattr(discovery, "connect_read",
                        lambda path: RecordingConnection(real_connect(path)))
    result = TwinNoteDiscoveryService(db_path=database).candidates("owner")
    assert sum(len(asset["windows"]) for asset in result["assets"]) == 3
    assert result["truncated"] is True
    assert fetches == [(4, 2), (2, 2)]
    assert all(fetched <= requested for requested, fetched in fetches)


def test_explicit_snapshot_prevents_cross_phase_hybrid(database, monkeypatch):
    from substrate.twin_note_taker import discovery

    with connect_write(database, purpose="test/discovery-snapshot-seed") as con:
        _seed_document(con, "asset", "owner")
        _seed_binding(con, "notebook", "asset", "inv", "owner")
        _seed_window(con, "window-old", "inv", 0)

    asset_read = threading.Event()
    writer_done = threading.Event()
    writer_errors = []

    def writer():
        assert asset_read.wait(5)
        try:
            with connect_write(database, purpose="test/discovery-concurrent-writer") as con:
                _seed_window(con, "window-new", "inv", 1)
        except Exception as exc:  # pragma: no cover - asserted below
            writer_errors.append(exc)
        finally:
            writer_done.set()

    thread = threading.Thread(target=writer)
    thread.start()

    class BarrierConnection:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.connection.close()

        def execute(self, sql, params=None):
            cursor = self.connection.execute(sql, params or [])
            if "SELECT DISTINCT d.document_id" in sql:
                rows = cursor.fetchall()
                asset_read.set()
                assert writer_done.wait(5)
                return type("Buffered", (), {"fetchall": lambda self: rows})()
            return cursor

    monkeypatch.setattr(discovery, "connect_read",
                        lambda path: BarrierConnection(duckdb.connect(path)))
    snapshot = TwinNoteDiscoveryService(db_path=database).candidates("owner")
    thread.join(5)
    assert not thread.is_alive() and not writer_errors
    assert [row["window_id"] for row in snapshot["assets"][0]["windows"]] == ["window-old"]
    monkeypatch.setattr(discovery, "connect_read", lambda path: duckdb.connect(path))
    refreshed = TwinNoteDiscoveryService(db_path=database).candidates("owner")
    assert [row["window_id"] for row in refreshed["assets"][0]["windows"]] == [
        "window-old", "window-new"]
