"""Signed HTTP regressions for discovery failure headers and cleanup precedence."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from runtime import db_lock

EMAIL = "timeout-discovery@example.test"
SECRET = "timeout-discovery-synthetic-secret-" + "x" * 40
PATHS = ("/books", "/library", "/documents")
FAILURES = (db_lock.ReadLockTimeout, RuntimeError)


@pytest.fixture
def discovery(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "catalog.duckdb"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", EMAIL)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "mock")
    from substrate.multi_user.auth import mint_session_cookie
    from substrate.graph.schema import init_database

    db_path = str(tmp_path / "catalog.duckdb")
    with db_lock.connect_write(
        db_path,
        purpose="test-private-discovery-timeout-headers-init",
        keepalive_s=0,
    ) as con:
        init_database(con)
    from interfaces.research.api import app as app_module

    client = TestClient(app_module.create_app(
        register_wrestling=False, register_providers=False,
    ))
    client.cookies.set("ANTIEK_SESSION", mint_session_cookie("magic_link", EMAIL, EMAIL))
    yield client, app_module._READ_LOCK_RETRY_AFTER_S
    client.close()


def _assert_failure(response, path, failure_type, retry_after):
    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    if path == "/documents":
        assert detail == {"error": {
            "code": "read_unavailable",
            "message": (
                "The underlying store could not be read. This is "
                "NOT a statement that no records exist."
            ),
        }}
    else:
        assert detail == "read_unavailable"
    if failure_type is db_lock.ReadLockTimeout:
        assert response.headers["Retry-After"] == retry_after
    else:
        assert "Retry-After" not in response.headers


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("failure_type", FAILURES)
def test_open_failure_preserves_body_and_typed_header(
    discovery, monkeypatch, path, failure_type,
):
    client, retry_after = discovery
    calls = []

    def fail_open(db_path, *, external_lock_timeout_s=0.0):
        assert external_lock_timeout_s == (2.0 if path == "/books" else 0.0)
        calls.append(db_path)
        raise failure_type("synthetic open failure")

    monkeypatch.setattr(db_lock, "connect_read", fail_open)
    _assert_failure(client.get(path), path, failure_type, retry_after)
    assert len(calls) == 1


@pytest.mark.parametrize("stage", ("query", "close", "response"))
@pytest.mark.parametrize("failure_type", FAILURES)
def test_library_remaining_wrappers_preserve_body_and_typed_header(
    discovery, monkeypatch, stage, failure_type,
):
    client, retry_after = discovery
    from interfaces.research.api import library

    real_connect = db_lock.connect_read
    calls = []

    class FailingConnection:
        def __init__(self, con):
            self.con = con

        def execute(self, sql, *args):
            calls.append(sql)
            if stage == "query" and sql == "COMMIT":
                raise failure_type("synthetic query failure")
            return self.con.execute(sql, *args)

        def close(self):
            calls.append("close")
            self.con.close()
            if stage == "close":
                raise failure_type("synthetic close failure")

    def connect_with_failure(db_path):
        return FailingConnection(real_connect(db_path))

    def fail_response(*args, **kwargs):
        calls.append("response")
        raise failure_type("synthetic response failure")

    monkeypatch.setattr(db_lock, "connect_read", connect_with_failure)
    if stage == "response":
        monkeypatch.setattr(library, "build_library_page", fail_response)
    _assert_failure(client.get("/library"), "/library", failure_type, retry_after)
    assert calls.count("close") == 1
    if stage == "query":
        assert "ROLLBACK" in calls
    elif stage == "response":
        assert calls.index("close") < calls.index("response")


@pytest.mark.parametrize("primary_type,cleanup_type", (
    (RuntimeError, db_lock.ReadLockTimeout),
    (db_lock.ReadLockTimeout, RuntimeError),
))
def test_library_primary_failure_controls_header_when_both_cleanup_steps_fail(
    discovery, monkeypatch, primary_type, cleanup_type,
):
    client, retry_after = discovery
    real_connect = db_lock.connect_read
    calls = []

    class FailingCleanup:
        def __init__(self, con):
            self.con = con

        def execute(self, sql, *args):
            calls.append(sql)
            if sql == "COMMIT":
                raise primary_type("synthetic primary failure")
            if sql == "ROLLBACK":
                raise cleanup_type("synthetic rollback failure")
            return self.con.execute(sql, *args)

        def close(self):
            calls.append("close")
            self.con.close()
            raise cleanup_type("synthetic close failure")

    def connect_with_failure(db_path):
        return FailingCleanup(real_connect(db_path))

    monkeypatch.setattr(db_lock, "connect_read", connect_with_failure)
    _assert_failure(client.get("/library"), "/library", primary_type, retry_after)
    assert calls[-3:] == ["COMMIT", "ROLLBACK", "close"]
    assert calls.count("close") == 1
