"""Economics stays readable while a separate ingestion process owns DuckDB."""

from __future__ import annotations

import asyncio
import os
import select
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from interfaces.research.api import speak_routes
from interfaces.research.api.app import create_app

_ROOT = Path(__file__).resolve().parents[1]
_HOLD_WRITER = """
import sys
from runtime.db_lock import connect_write

with connect_write(sys.argv[1], purpose="test:economics-holder", timeout_s=5,
                   keepalive_s=0) as con:
    con.execute("SELECT 1")
    print("held", flush=True)
    sys.stdin.readline()
"""


def test_economics_retries_external_writer_without_blocking_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "speak.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)

    with TestClient(create_app(register_wrestling=False, register_providers=False,
                               cors_origins=[])) as client:
        created = client.post("/speak/projects", json={
            "title": "Economics under ingest", "publish_intent": "will_be_public",
        })
        missing = client.get("/speak/projects/missing/economics")
    assert created.status_code == 201, created.text
    assert missing.status_code == 404
    project_id = created.json()["project_id"]
    monkeypatch.setattr(speak_routes, "_WRITE_TIMEOUT_S", 2.0)

    proc = subprocess.Popen(
        [sys.executable, "-u", "-c", _HOLD_WRITER, str(db)],
        cwd=_ROOT,
        env=os.environ.copy(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        ready, _, _ = select.select([proc.stdout], [], [], 5)
        assert ready, "writer subprocess did not acquire the DB"
        assert proc.stdout.readline().strip() == "held"

        async def exercise() -> tuple[dict[str, object], bool]:
            task = asyncio.create_task(speak_routes.get_economics(project_id))
            await asyncio.sleep(0.2)
            loop_served_other_work = not task.done()
            assert proc.stdin is not None
            proc.stdin.write("release\n")
            proc.stdin.flush()
            return await asyncio.wait_for(task, 5), loop_served_other_work

        response, loop_served_other_work = asyncio.run(exercise())
        assert loop_served_other_work
        assert response["cell"]
        assert response["split_applies"] is True
    finally:
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)


def test_economics_does_not_retry_other_duckdb_io_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_read(_: str) -> None:
        raise duckdb.IOException("corrupt database")

    monkeypatch.setattr(speak_routes, "connect_read", fail_read)
    monkeypatch.setattr(speak_routes, "default_db_path", lambda: __file__)
    with pytest.raises(duckdb.IOException, match="corrupt database"):
        asyncio.run(speak_routes.get_economics("project"))


def test_economics_lock_retry_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_read(_: str) -> None:
        raise duckdb.IOException(
            "Could not set lock on file: Conflicting lock is held in another process"
        )

    monkeypatch.setattr(speak_routes, "connect_read", fail_read)
    monkeypatch.setattr(speak_routes, "default_db_path", lambda: __file__)
    monkeypatch.setattr(speak_routes, "_WRITE_TIMEOUT_S", 0.1)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(speak_routes.get_economics("project"))
    assert exc.value.status_code == 503
    assert exc.value.detail == "speak_writer_busy"
