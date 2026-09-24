"""Tests for ``tools.migrate_owner_namespace`` — the Option A one-way migration.

Builds a synthetic single-operator deployment (legacy ``__operator__`` rows in
every store the 24 ``request_owner_user_id`` call sites write) through the REAL
writers — the bare-app settings routes mint legacy rows exactly as pre-Option-A
production did — then proves:

  * dry-run (the default) lists every move and writes nothing;
  * ``apply=True`` re-owns every store to the derived owner, re-seals the BYOK
    credential (same plaintext, new owner binding), and re-namespaces record
    ids — after which the migrated model is visible to that operator's session
    and to no one else;
  * the tool REFUSES when more than one legacy owner is present, when the
    target owner already holds conflicting rows, or when the e-mail does not
    derive.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import settings_lineup
from interfaces.research.api.account_memory_identity import (
    derive_owner_from_verified_email,
)
from interfaces.research.api.settings_budget import register_settings_budget_routes
from interfaces.research.api.settings_models_admin import _load_registry
from runtime.byok.store import list_credentials, load_credential
from runtime.connectors import registry as tool_registry
from runtime.connectors.registry import (
    ToolConnectionUnavailable,
    connect_tool,
    resolve_tool_connection,
)
from runtime.db_lock import connect_write
from substrate.byot_usage.ledger import ByotUsageLedger
from substrate.compute_capacity import set_capacity
from substrate.compute_capacity.acu_meter import ensure_acu_ledger
from substrate.dispatch.router import reset_provider_registry
from substrate.telemetry_preferences import SqlitePreferenceStore, set_preference
from tools import migrate_owner_namespace
from tools.migrate_owner_namespace import (
    LEGACY_OWNER,
    MigrationRefused,
    run_migration,
)

OPERATOR = "operator@example.test"
TARGET = derive_owner_from_verified_email(OPERATOR)
assert TARGET is not None

_SECRET = "sk-legacy-super-secret-model-key-1234567890"
_MODEL_ID = "user-legacy-deepseek"
_TOOL_SECRET = "AIza" + "LegacyTool" * 3
_ADD_BODY = {
    "provider_kind": "openai_compat",
    "model_id": "deepseek-chat",
    "display_name": "Legacy DeepSeek",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": _SECRET,
}


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(tmp_path / "settings" / "user_models.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "byok" / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "byok" / "master.key"))
    monkeypatch.setenv("ANTIEK_BYOT_USAGE_DB", str(tmp_path / "byot-usage.sqlite3"))
    monkeypatch.setenv("ANTIEK_LINEUP_PATH", str(tmp_path / "settings" / "lineup.json"))
    monkeypatch.setenv("ANTIEK_TELEMETRY_DB", str(tmp_path / "telemetry" / "preferences.sqlite"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv(
        "ANTIEK_TOOL_CONNECTIONS_PATH", str(tmp_path / "settings" / "tool_connections.json")
    )
    monkeypatch.setenv("ANTIEK_CONNECTOR_QUOTA_DIR", str(tmp_path / "quota"))
    reset_provider_registry()
    yield tmp_path
    reset_provider_registry()


def _seed_legacy_state(env: Path) -> None:
    """Write one legacy-owned row into every affected store, via real writers."""
    # 1. user-model registry + model_provider credential. On THIS branch the
    #    bare app (no auth middleware) fails closed with 401 — that is Option
    #    A working. To simulate the pre-Option-A production posture that
    #    created the legacy rows, the owner predicate is pinned to the legacy
    #    sentinel for the seeding POST only; everything downstream (registry
    #    shape, BYOK v3 sealing, id scheme) is the real writer.
    from unittest.mock import patch

    from interfaces.research.api import settings_models_admin as models_admin

    app = FastAPI()
    register_settings_budget_routes(app)
    with (
        patch.object(models_admin, "request_owner_user_id", lambda request: LEGACY_OWNER),
        TestClient(app) as client,
    ):
        assert client.post("/settings/models/user", json=_ADD_BODY).status_code == 201
    assert _load_registry()[_MODEL_ID].owner_user_id == LEGACY_OWNER

    # 2. an oauth credential owned by the sentinel (the shape oauth_routes writes)
    from runtime.byok.store import store_credential

    store_credential(
        "oauth:openai",
        json.dumps({"access_token": "tok", "provider": "openai"}),
        pipeline_kind="oauth_openai",
        owner_user_id=LEGACY_OWNER,
    )

    # 3. BYOT usage ledger: one key-usage row + one journal row
    ledger = ByotUsageLedger(db_path=env / "byot-usage.sqlite3")
    ledger.set_limit(_MODEL_ID, LEGACY_OWNER, 500)
    con = sqlite3.connect(str(env / "byot-usage.sqlite3"))
    con.execute(
        "INSERT INTO byot_operation_journal ("
        " api_key_id, owner_user_id, operation_id, state, reserved_cents,"
        " actual_cents, authority_digest, created_at, updated_at)"
        " VALUES (?, ?, ?, 'settled', 10, 9, 'digest', 't', 't')",
        (_MODEL_ID, LEGACY_OWNER, "op-1"),
    )
    con.commit()
    con.close()

    # 4. lineup sidecar
    settings_lineup._write_registry_unlocked(
        {"owners": {LEGACY_OWNER: {"general": {}, "advanced": {}, "updated_at": "t"}}}
    )

    # 5. telemetry preferences
    store = SqlitePreferenceStore(db_path=str(env / "telemetry" / "preferences.sqlite"))
    set_preference(
        store, user_id=LEGACY_OWNER, surface_name="skill_invocation_frequency", enabled=False
    )

    # 6. graph DuckDB: capacity row, ACU ledger row, tier-override audit row
    #    (the full graph schema is applied by the app startup above; seed a
    #    document + chunk so the override row's foreign keys hold)
    from substrate.graph.schema import init_database

    with connect_write(str(env / "graph.duckdb"), purpose="test-seed", timeout_s=10) as con:
        init_database(con)
        set_capacity(con, owner_user_id=LEGACY_OWNER, tier="standard")
        ensure_acu_ledger(con)
        con.execute(
            "INSERT INTO owner_compute_acu_ledger "
            "(investigation_id, owner_user_id, acu_units, reason) VALUES ('inv-1', ?, 1, 'test')",
            [LEGACY_OWNER],
        )
        con.execute(
            "INSERT INTO documents (document_id, source_tier, document_type) "
            "VALUES ('doc-1', 1, 'test')"
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
            "VALUES ('chunk-1', 'doc-1', 0, 'text')"
        )
        con.execute(
            "INSERT INTO chunk_tier_overrides (chunk_id, original_tier, override_tier, reason, set_by) "
            "VALUES ('chunk-1', 1, 3, 'test', ?)",
            [LEGACY_OWNER],
        )

    # 7. a connected BYO tool, written by the registry writer the pre-fix
    #    Settings route called with the sentinel
    connect_tool(LEGACY_OWNER, "youtube", _TOOL_SECRET)


def _owners_everywhere(env: Path) -> dict[str, list[str]]:
    """Snapshot every owner key in every store, for change assertions."""
    registry = _load_registry()
    out: dict[str, list[str]] = {
        "registry": sorted({r.owner_user_id for r in registry.values()}),
        "byok": sorted({m.owner_user_id or "<none>" for m in list_credentials()}),
    }
    con = sqlite3.connect(str(env / "byot-usage.sqlite3"))
    out["byot_usage"] = sorted(
        row[0]
        for row in con.execute(
            "SELECT DISTINCT owner_user_id FROM byot_key_usage "
            "UNION SELECT DISTINCT owner_user_id FROM byot_operation_journal"
        )
    )
    con.close()
    out["lineup"] = sorted(settings_lineup._load_registry().get("owners", {}))
    con = sqlite3.connect(str(env / "telemetry" / "preferences.sqlite"))
    out["telemetry"] = sorted(
        row[0]
        for row in con.execute("SELECT DISTINCT user_id FROM user_telemetry_preferences")
    )
    con.close()
    tool_rows, _pending = tool_registry._load_unlocked()
    out["tools"] = sorted({r.owner_user_id for r in tool_rows.values()})
    import duckdb

    con = duckdb.connect(str(env / "graph.duckdb"), read_only=True)
    try:
        out["duckdb"] = sorted(
            row[0]
            for row in con.execute(
                "SELECT owner_user_id FROM owner_compute_capacity "
                "UNION SELECT owner_user_id FROM owner_compute_acu_ledger "
                "UNION SELECT set_by FROM chunk_tier_overrides"
            ).fetchall()
        )
    finally:
        con.close()
    return out


# ---------------------------------------------------------------------------
# dry-run (the default) writes nothing
# ---------------------------------------------------------------------------


def test_dry_run_lists_every_move_and_writes_nothing(env: Path) -> None:
    _seed_legacy_state(env)
    before = _owners_everywhere(env)

    report = run_migration(OPERATOR)  # apply=False is the default

    assert report.target_owner == TARGET
    assert report.applied is False
    stores = {(m.store, m.table) for m in report.moves}
    assert ("user_models.json", "registry") in stores
    assert ("byok artifact", "oauth_openai") in stores
    assert any(table == "byot_key_usage" for _, table in stores)
    assert any(table == "byot_operation_journal" for _, table in stores)
    assert ("lineup.json", "owners") in stores
    assert any(table == "owner_compute_capacity" for _, table in stores)
    assert any(table == "owner_compute_acu_ledger" for _, table in stores)
    assert any(table == "chunk_tier_overrides.set_by" for _, table in stores)
    assert any(table == "user_telemetry_preferences" for _, table in stores)
    assert ("tool_connections.json", "registry") in stores
    assert _owners_everywhere(env) == before


# ---------------------------------------------------------------------------
# apply re-owns everything, one way, auditable
# ---------------------------------------------------------------------------


def test_apply_reowns_every_store_and_reseals_credentials(env: Path, caplog) -> None:  # noqa: ANN001
    _seed_legacy_state(env)
    old_cred_ref = _load_registry()[_MODEL_ID].cred_ref

    with caplog.at_level("INFO", logger="tools.migrate_owner_namespace"):
        report = run_migration(OPERATOR, apply=True)

    assert report.applied is True
    owners = _owners_everywhere(env)
    for store, owner_set in owners.items():
        assert owner_set == [TARGET], f"{store}: {owner_set}"

    # The registry record was re-namespaced to the derived owner's id prefix.
    registry = _load_registry()
    assert list(registry) != [_MODEL_ID]
    (record,) = registry.values()
    assert record.owner_user_id == TARGET
    assert record.id.startswith("user-") and record.id != _MODEL_ID
    assert record.id.endswith("legacy-deepseek")

    # The credential was re-sealed: new ref, new owner binding, SAME plaintext,
    # and the old ciphertext is gone.
    assert record.cred_ref != old_cred_ref
    creds = list_credentials()
    assert {m.cred_id for m in creds}.isdisjoint({old_cred_ref})
    model_cred = next(m for m in creds if m.pipeline_kind == "model_provider")
    assert model_cred.owner_user_id == TARGET
    assert model_cred.account_handle == record.id
    assert load_credential(record.cred_ref).reveal() == _SECRET
    oauth_cred = next(m for m in creds if m.pipeline_kind == "oauth_openai")
    assert oauth_cred.owner_user_id == TARGET

    # The audit log names every row moved, with store, table and key.
    assert _MODEL_ID in caplog.text
    assert "byot_key_usage" in caplog.text
    assert "owner_compute_capacity" in caplog.text
    assert "oauth_openai" in caplog.text
    assert any("user-legacy-deepseek" in m.key for m in report.moves)

    # Post-migration, the operator's SESSION sees the migrated model through
    # the aligned predicate — the end-to-end point of Option A.
    app = FastAPI()
    register_settings_budget_routes(app)

    @app.middleware("http")
    async def _stamp(request, call_next):  # noqa: ANN001, ANN202
        request.state.auth_method = "antiek_session_cookie"
        request.state.user_id = LEGACY_OWNER
        request.state.user_email = request.headers.get("X-Test-Email")
        return await call_next(request)

    with TestClient(app) as client:
        mine = client.get("/settings/models/user", headers={"X-Test-Email": OPERATOR}).json()
        assert [row["id"] for row in mine["models"]] == [record.id]
        stranger = client.get(
            "/settings/models/user", headers={"X-Test-Email": "stranger@example.test"}
        ).json()
        assert stranger["count"] == 0


def test_apply_is_idempotent_noop_when_nothing_legacy_remains(env: Path) -> None:
    _seed_legacy_state(env)
    run_migration(OPERATOR, apply=True)
    second = run_migration(OPERATOR, apply=True)
    assert second.moves == []
    assert _owners_everywhere(env)["registry"] == [TARGET]


# ---------------------------------------------------------------------------
# refusals — fail closed, nothing written
# ---------------------------------------------------------------------------


def test_refuses_when_more_than_one_legacy_owner(env: Path) -> None:
    _seed_legacy_state(env)
    # A second person wrote rows under a genuine per-user id.
    ledger = ByotUsageLedger(db_path=env / "byot-usage.sqlite3")
    ledger.set_limit("user-other", "usr_someone_else", 100)
    before = _owners_everywhere(env)
    with pytest.raises(MigrationRefused, match="more than one legacy owner"):
        run_migration(OPERATOR)
    with pytest.raises(MigrationRefused, match="more than one legacy owner"):
        run_migration(OPERATOR, apply=True)
    assert _owners_everywhere(env) == before


def test_refuses_when_target_owner_already_conflicts(env: Path) -> None:
    _seed_legacy_state(env)
    # The target owner already holds a row for the same telemetry surface.
    store = SqlitePreferenceStore(db_path=str(env / "telemetry" / "preferences.sqlite"))
    set_preference(
        store, user_id=TARGET, surface_name="skill_invocation_frequency", enabled=True
    )
    with pytest.raises(MigrationRefused, match="conflicting"):
        run_migration(OPERATOR, apply=True)


def test_refuses_an_address_that_does_not_derive(env: Path) -> None:
    _seed_legacy_state(env)
    with pytest.raises(MigrationRefused, match="does not derive"):
        run_migration("not-an-email", apply=True)


# ---------------------------------------------------------------------------
# Connected BYO tools
# ---------------------------------------------------------------------------

_STRANGER = derive_owner_from_verified_email("stranger@example.test")
assert _STRANGER is not None


def _tool_state(env: Path) -> tuple[bytes, list[tuple[str, str | None, str | None]]]:
    """Registry bytes plus (cred_id, owner, kind) of every stored credential."""
    return (
        (env / "settings" / "tool_connections.json").read_bytes(),
        sorted((m.cred_id, m.owner_user_id, m.pipeline_kind) for m in list_credentials()),
    )


def _tool_row(owner: str, vendor: tool_registry.ToolVendor) -> tool_registry.ToolConnectionRecord:
    rows, _pending = tool_registry._load_unlocked()
    return rows[tool_registry._record_key(owner, vendor)]


def test_dry_run_leaves_tool_connections_and_credentials_untouched(env: Path) -> None:
    connect_tool(LEGACY_OWNER, "youtube", _TOOL_SECRET)
    before = _tool_state(env)

    report = run_migration(OPERATOR)

    assert [m.table for m in report.moves if m.store == "tool_connections.json"] == ["registry"]
    assert _tool_state(env) == before


def test_apply_moves_a_legacy_tool_to_the_derived_owner_with_its_secret(env: Path) -> None:
    connect_tool(LEGACY_OWNER, "youtube", _TOOL_SECRET)
    old_cred_id = _tool_row(LEGACY_OWNER, "youtube").cred_id
    with pytest.raises(ToolConnectionUnavailable):  # the live defect: invisible to its owner
        resolve_tool_connection(TARGET, "youtube")

    run_migration(OPERATOR, apply=True)

    row = _tool_row(TARGET, "youtube")
    assert load_credential(row.cred_id).reveal() == _TOOL_SECRET
    resolve_tool_connection(TARGET, "youtube").close()  # the search/ingest spend path
    with pytest.raises(ToolConnectionUnavailable):
        resolve_tool_connection(LEGACY_OWNER, "youtube")
    assert old_cred_id not in {m.cred_id for m in list_credentials()}
    assert tool_registry._load_unlocked()[1] == []  # no pending deletions left behind


def test_second_apply_is_a_noop_for_tools(env: Path) -> None:
    connect_tool(LEGACY_OWNER, "youtube", _TOOL_SECRET)
    run_migration(OPERATOR, apply=True)
    after_first = _tool_state(env)

    second = run_migration(OPERATOR, apply=True)

    assert second.moves == []
    assert _tool_state(env) == after_first


def test_another_owners_tool_rows_are_untouched(env: Path) -> None:
    connect_tool(_STRANGER, "youtube", "AIza" + "StrangerKey" * 3)
    connect_tool(LEGACY_OWNER, "youtube", _TOOL_SECRET)
    theirs = _tool_row(_STRANGER, "youtube")
    their_meta = {m.cred_id: m for m in list_credentials()}[theirs.cred_id]

    run_migration(OPERATOR, apply=True)

    assert _tool_row(_STRANGER, "youtube") == theirs
    assert {m.cred_id: m for m in list_credentials()}[theirs.cred_id] == their_meta
    assert load_credential(theirs.cred_id).reveal() == "AIza" + "StrangerKey" * 3
    assert _tool_row(TARGET, "youtube").cred_id != theirs.cred_id


def test_refuses_when_the_target_already_has_that_tool(env: Path) -> None:
    connect_tool(LEGACY_OWNER, "youtube", _TOOL_SECRET)
    connect_tool(TARGET, "youtube", "AIza" + "ReconnectedKey" * 2)
    before = _tool_state(env)

    for apply in (False, True):
        with pytest.raises(MigrationRefused, match="conflicting"):
            run_migration(OPERATOR, apply=apply)

    assert _tool_state(env) == before


def test_refuses_a_legacy_row_bound_to_someone_elses_credential(env: Path) -> None:
    """Re-sealing whatever the row points at could hand a stranger's key to the target."""
    connect_tool(_STRANGER, "youtube", "AIza" + "StrangerKey" * 3)
    connect_tool(LEGACY_OWNER, "youtube", _TOOL_SECRET)
    theirs = _tool_row(_STRANGER, "youtube")
    with tool_registry._guard(exclusive=True):
        rows, pending = tool_registry._load_unlocked()
        key = tool_registry._record_key(LEGACY_OWNER, "youtube")
        rows[key] = replace(
            rows[key], cred_id=theirs.cred_id, credential_fingerprint=theirs.credential_fingerprint
        )
        tool_registry._write_unlocked(rows, pending)
    before = _tool_state(env)

    with pytest.raises(MigrationRefused, match="cannot be proven"):
        run_migration(OPERATOR, apply=True)

    assert _tool_state(env) == before


def test_a_failed_reseal_leaves_tools_as_they_were(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect_tool(LEGACY_OWNER, "youtube", _TOOL_SECRET)
    connect_tool(LEGACY_OWNER, "polygon", "pk" + "PolygonKey" * 2)
    before = _tool_state(env)
    real = migrate_owner_namespace.store_credential_with_metadata
    calls: list[str] = []

    def fail_second(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs["pipeline_kind"])
        if len(calls) == 2:
            raise RuntimeError("disk full")
        return real(*args, **kwargs)

    monkeypatch.setattr(migrate_owner_namespace, "store_credential_with_metadata", fail_second)

    with pytest.raises(RuntimeError, match="disk full"):
        run_migration(OPERATOR, apply=True)

    assert len(calls) == 2
    assert _tool_state(env) == before
