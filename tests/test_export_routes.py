"""P1 §6 — ``GET /export/my-graph`` (full-graph export bundle, read half).

Builds a temp DuckDB (real Antiek schema + rows), a temp events dir (one
sealed parquet written via DuckDB COPY + one live jsonl through the
substrate event log), and a temp home, then asserts:

- 200 + ``application/zip`` content type + attachment filename
- the zip carries ``graph/`` + ``events/`` + ``manifest.json``
- manifest counts match reality (tables, table_rows, event files, master 0)
- the exported ``graph/schema.sql`` is normalized (no self-ref-FK stray
  commas) and the events parquet round-trips
- the source DB file checksum is UNCHANGED (export never mutates the graph)
- the temp bundle dir is cleaned up after streaming (no leftover dirs)
- 503 (value-free body) when the db path is invalid (empty home)
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile

import duckdb
from fastapi.testclient import TestClient

from interfaces.research.api import export_routes
from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.event_log import default_events_dir, log_event
from substrate.graph.schema import init_database_at_path


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def _build_store(monkeypatch, tmp_path) -> dict[str, str]:
    """Temp home + real-schema DB with rows + events dir with parquet+jsonl."""
    home = tmp_path / "home"
    events = tmp_path / "events"
    events.mkdir()
    db = tmp_path / "graph.duckdb"

    monkeypatch.setenv("ANTIEK_HOME", str(home))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))

    init_database_at_path(str(db))
    with connect_write(str(db), purpose="test:export-fixture") as con:
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, document_type) "
            "VALUES ('d1', 'a', 1, 'url'), ('d2', 'b', 2, 'url')"
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('n1', 'x', 'entity', 'depth')"
        )

    # One sealed parquet: written via DuckDB COPY (pyarrow is an optional
    # dependency; duckdb writes a real parquet either way).
    con = duckdb.connect(str(db))
    try:
        con.execute(
            f"COPY (SELECT 'evt-1' AS event_id, 'research.started' AS action_type) "
            f"TO '{events / 'inv-sealed.parquet'}' (FORMAT PARQUET)"
        )
    finally:
        con.close()
    # One live jsonl via the substrate event log (append-only, unsealed).
    log_event("inv-live", "research.started", events_dir=str(events))
    return {"home": str(home), "events": str(events), "db": str(db)}


def test_export_my_graph_bundle(monkeypatch, tmp_path):
    paths = _build_store(monkeypatch, tmp_path)
    db = paths["db"]
    # Events resolution honors ANTIEK_RESEARCH_EVENTS_DIR (fallback: ANTIEK_HOME).
    assert default_events_dir() == paths["events"]

    before = _sha256(db)

    created_dirs: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def tracked_mkdtemp(*args, **kwargs):
        d = real_mkdtemp(*args, **kwargs)
        created_dirs.append(d)
        return d

    monkeypatch.setattr(export_routes.tempfile, "mkdtemp", tracked_mkdtemp)

    resp = _client().get("/export/my-graph")
    assert resp.status_code == 200, resp.text[:500]
    assert resp.headers["content-type"].startswith("application/zip")
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment; filename=")
    assert "antiek-graph-export-" in disposition
    assert disposition.rstrip('"').endswith(".zip")

    # The export must not mutate the source DB file.
    assert _sha256(db) == before, "source DuckDB file changed during export"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert "manifest.json" in names
    graph_entries = [n for n in names if n.startswith("graph/")]
    event_entries = [n for n in names if n.startswith("events/")]
    assert graph_entries, "zip missing graph/ contents"
    assert event_entries, "zip missing events/ contents"

    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["source_db_path"] == "graph.duckdb"
    assert manifest["generated_at"]
    assert manifest["graph_not_mutated"] is True
    # The real Antiek schema (init_database_at_path) carries dozens of
    # tables; the two we seeded must be counted at their exact row counts.
    assert manifest["counts"]["tables"] >= 2
    assert manifest["counts"]["table_rows"]["documents"] == 2
    assert manifest["counts"]["table_rows"]["nodes"] == 1
    assert manifest["counts"]["event_files"] == 2
    assert manifest["counts"]["event_parquet_files"] == 1
    assert manifest["counts"]["event_jsonl_files"] == 1
    assert manifest["counts"]["master_files"] == 0
    assert manifest["master_md"]["status"].startswith("n/a")
    assert manifest["event_schema_version"] >= 1

    # graph/schema.sql is normalized: no self-ref-FK stray commas.
    schema = zf.read("graph/schema.sql").decode("utf-8")
    assert ", ," not in schema
    assert ", )" not in schema
    assert "CREATE TABLE" in schema

    # events copied verbatim and the parquet round-trips.
    assert "events/inv-sealed.parquet" in names
    assert "events/inv-live.jsonl" in names
    pq_path = tmp_path / "roundtrip.parquet"
    pq_path.write_bytes(zf.read("events/inv-sealed.parquet"))
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{pq_path}')"
        ).fetchone()[0]
    finally:
        con.close()
    assert rows == 1

    # The temp bundle is cleaned up after streaming completes.
    assert created_dirs, "mkdtemp was not called by the route"
    assert all(not os.path.exists(d) for d in created_dirs), (
        f"export temp dirs not cleaned up: {[d for d in created_dirs if os.path.exists(d)]}"
    )

    # The only DB-named sibling files are the DB and the writer-coordination
    # sidecar (house protocol; created by connect_write during setup).
    db_siblings = sorted(
        p.name for p in tmp_path.iterdir() if p.name.startswith("graph.duckdb")
    )
    assert db_siblings == ["graph.duckdb", "graph.duckdb.write.lock"]


def test_export_my_graph_503_when_db_path_invalid(monkeypatch, tmp_path):
    home = tmp_path / "empty-home"
    home.mkdir()
    monkeypatch.setenv("ANTIEK_HOME", str(home))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(home / "research_graph.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "no-events"))

    resp = _client().get("/export/my-graph")
    assert resp.status_code == 503
    body = json.dumps(resp.json())
    assert str(home) not in body, "503 body leaks the db path"
    assert "traceback" not in body.lower()
    assert "research_graph" not in body
    assert "graph database unavailable" in body


INVITE_TOKEN = "invite-bearer-credential-7f3a9c"
PARTNER_SECRET = "a1" * 32


def _seed_credentials(db: str) -> str:
    """Seed the three credential stores the graph DB carries; return the
    operator's live signing key."""
    from services.antiek_format.signature import ensure_keypair
    from substrate.speak.schema import ensure_speak_schema

    private_key = ensure_keypair("__operator__", db_path=db).private_key_b64
    with connect_write(db, purpose="test:export-credentials") as con:
        ensure_speak_schema(con)
        con.execute(
            "INSERT INTO speak_invites (invite_id, interview_id, project_id, token, "
            "required_consent_scopes) VALUES ('i1', 'iv1', 'p1', ?, '[\"record\"]'), "
            "('i2', 'iv2', 'p1', 'second-invite-credential', '[]')",
            [INVITE_TOKEN],
        )
        con.execute(
            "INSERT INTO federation_partners (attempt_id, partner_id, display_name, "
            "substrate_url, shared_secret_hex, state, registered_at, "
            "last_state_change_at) VALUES ('a1', 'partner-1', 'Partner', "
            "'https://partner.example', ?, 'trusted', now(), now())",
            [PARTNER_SECRET],
        )
    return private_key


def _shard_rows(zf: zipfile.ZipFile, name: str, tmp_path) -> list[dict]:
    path = tmp_path / name.replace("/", "_")
    path.write_bytes(zf.read(name))
    con = duckdb.connect()
    try:
        cur = con.execute(f"SELECT * FROM read_parquet('{path}')")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    finally:
        con.close()


def test_export_my_graph_keeps_credentials_on_the_host(monkeypatch, tmp_path):
    """The bundle is built to leave the host, so it must not carry the
    Ed25519 signing key ("NEVER leaves substrate-resident storage"), a live
    Speak invite bearer token, or a federation partner's shared secret."""
    paths = _build_store(monkeypatch, tmp_path)
    private_key = _seed_credentials(paths["db"])
    secrets = (private_key, INVITE_TOKEN, "second-invite-credential", PARTNER_SECRET)

    resp = _client().get("/export/my-graph")
    assert resp.status_code == 200, resp.text[:500]
    zf = zipfile.ZipFile(io.BytesIO(resp.content))

    shards: dict[str, list[dict]] = {}
    for name in zf.namelist():
        if name.startswith("graph/") and name.endswith(".parquet"):
            rows = _shard_rows(zf, name, tmp_path)
            shards[name.removeprefix("graph/").removesuffix(".parquet")] = rows
            flat = repr(rows)
        else:
            flat = zf.read(name).decode("utf-8", errors="replace")
        # Index only: the assertion must not echo key material into the log.
        leaked = [i for i, secret in enumerate(secrets) if secret in flat]
        assert leaked == [], f"credential #{leaked} exported in {name}"

    # The signing key's rows stay home; the non-secret rows keep their data
    # with the credential replaced by a fresh value nobody holds.
    assert shards["antiek_user_keypairs"] == []
    invites = {r["invite_id"]: r for r in shards["speak_invites"]}
    assert set(invites) == {"i1", "i2"}
    assert invites["i1"]["required_consent_scopes"] == '["record"]'
    tokens = [r["token"] for r in invites.values()]
    assert all(tokens) and len(set(tokens)) == 2, "restore needs NOT NULL UNIQUE tokens"
    (partner,) = shards["federation_partners"]
    assert partner["partner_id"] == "partner-1"
    assert partner["shared_secret_hex"]

    manifest = json.loads(zf.read("manifest.json"))
    withheld = manifest["credentials_withheld"]
    assert withheld["antiek_user_keypairs"]["policy"] == "rows_withheld"
    assert withheld["antiek_user_keypairs"]["source_rows"] == 1
    assert withheld["speak_invites.token"]["policy"] == "values_replaced"
    assert withheld["federation_partners.shared_secret_hex"]["policy"] == "values_replaced"
    # Counts describe the bundle, not the source.
    assert manifest["counts"]["table_rows"]["antiek_user_keypairs"] == 0
    assert manifest["counts"]["table_rows"]["speak_invites"] == 2


def test_unclassified_credential_shaped_column_is_replaced(monkeypatch, tmp_path):
    """Fail closed: a credential-shaped column nobody classified yet is
    replaced, and the manifest names it, rather than exported verbatim."""
    paths = _build_store(monkeypatch, tmp_path)
    with connect_write(paths["db"], purpose="test:export-new-secret") as con:
        con.execute("CREATE TABLE future_oauth (id TEXT PRIMARY KEY, refresh_token TEXT)")
        con.execute("INSERT INTO future_oauth VALUES ('o1', 'refresh-credential-99')")

    resp = _client().get("/export/my-graph")
    assert resp.status_code == 200, resp.text[:500]
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    (row,) = _shard_rows(zf, "graph/future_oauth.parquet", tmp_path)
    assert row["id"] == "o1"
    assert row["refresh_token"] and row["refresh_token"] != "refresh-credential-99"
    withheld = json.loads(zf.read("manifest.json"))["credentials_withheld"]
    assert withheld["future_oauth.refresh_token"]["policy"] == "values_replaced"
    assert "unclassified" in withheld["future_oauth.refresh_token"]["reason"]


def test_every_credential_shaped_column_in_the_schema_is_classified(tmp_path):
    """Tripwire: a new table with a key/token/secret column must be classified
    (credential or not) in export_routes, not left to the fail-closed default."""
    from services.antiek_format.signature import ensure_keypair
    from substrate.speak.schema import ensure_speak_schema

    db = str(tmp_path / "schema.duckdb")
    init_database_at_path(db)
    ensure_keypair("__operator__", db_path=db)
    with connect_write(db, purpose="test:export-schema-scan") as con:
        ensure_speak_schema(con)
    con = duckdb.connect(db, read_only=True)
    try:
        columns = con.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'main'"
        ).fetchall()
    finally:
        con.close()
    unclassified = [
        (t, c)
        for t, c, dtype in columns
        if export_routes._credential_shaped(c, dtype)
        and t not in export_routes.CREDENTIAL_TABLES_WITHHELD
        and (t, c) not in export_routes.CREDENTIAL_COLUMNS_REPLACED
        and (t, c) not in export_routes.NON_CREDENTIAL_COLUMNS
    ]
    assert unclassified == []
    assert ("speak_invites", "token") in export_routes.CREDENTIAL_COLUMNS_REPLACED
