"""Speak read routes survive short DuckDB writer leases in another process."""

from __future__ import annotations

import asyncio
import json
import os
import select
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import duckdb
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from interfaces.research.api import speak_routes
from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.speak import async_interview
from substrate.speak.async_interview import resume as original_resume

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


def _seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, str, str]:
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
        project_id = created.json()["project_id"]
        invite = client.post(
            f"/speak/projects/{project_id}/invites",
            json={"informant_email": "reader@example.org"},
        )
        assert invite.status_code == 201, invite.text
    assert missing.status_code == 404
    return db, project_id, invite.json()["interview_id"], invite.json()["token"]


def _hold_writer(db: Path) -> subprocess.Popen[str]:
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
    except BaseException:
        _close_writer(proc)
        raise
    return proc


def _release_writer(proc: subprocess.Popen[str]) -> None:
    if proc.stdin is not None and not proc.stdin.closed:
        proc.stdin.write("release\n")
        proc.stdin.flush()


def _close_writer(proc: subprocess.Popen[str]) -> None:
    if proc.stdin is not None and not proc.stdin.closed:
        proc.stdin.close()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=5)


def test_economics_retries_external_writer_without_blocking_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, project_id, _, _ = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(speak_routes, "_WRITE_TIMEOUT_S", 2.0)
    proc = _hold_writer(db)
    try:
        async def exercise() -> tuple[dict[str, object], bool]:
            task = asyncio.create_task(speak_routes.get_economics(project_id))
            await asyncio.sleep(0.2)
            loop_served_other_work = not task.done()
            _release_writer(proc)
            return await asyncio.wait_for(task, 5), loop_served_other_work

        response, loop_served_other_work = asyncio.run(exercise())
        assert loop_served_other_work
        assert response["cell"]
        assert response["split_applies"] is True
    finally:
        _close_writer(proc)


def test_other_speak_reads_and_voice_precheck_wait_off_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, project_id, interview_id, token = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(speak_routes, "_WRITE_TIMEOUT_S", 3.0)
    proc = _hold_writer(db)
    request = Request({
        "type": "http", "method": "POST", "path": f"/speak/invite/{token}/voice",
        "headers": [(b"content-length", b"invalid")],
    })

    async def voice_precheck() -> int:
        with pytest.raises(HTTPException) as exc:
            await speak_routes.invitee_voice(token, request, question_id="q1")
        return exc.value.status_code

    try:
        async def exercise() -> list[Any]:
            tasks = [
                asyncio.create_task(speak_routes.public_feed()),
                asyncio.create_task(speak_routes.resolve_invite(token)),
                asyncio.create_task(speak_routes.public_opportunities(interest=None)),
                asyncio.create_task(speak_routes.list_pushes()),
                asyncio.create_task(speak_routes.get_interview(interview_id)),
                asyncio.create_task(voice_precheck()),
            ]
            await asyncio.sleep(0.2)
            assert all(not task.done() for task in tasks)
            _release_writer(proc)
            return await asyncio.wait_for(asyncio.gather(*tasks), 8)

        feed, invite, opportunities, pushes, interview, voice_status = asyncio.run(exercise())
        assert feed["projects"][0]["project_id"] == project_id
        assert invite.interview_id == interview_id
        assert opportunities["public_opportunities"]
        assert pushes["public_opportunities"]
        assert interview["interview_id"] == interview_id
        assert voice_status == 400
    finally:
        _close_writer(proc)


def test_invite_landing_retries_its_second_read_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, _, interview_id, token = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(speak_routes, "_WRITE_TIMEOUT_S", 3.0)
    ready = threading.Event()
    holder: list[subprocess.Popen[str]] = []

    def resume_after_writer_starts(
        db_path: str, iid: str, *, external_lock_timeout_s: float = 0.0
    ) -> object:
        holder.append(_hold_writer(db))
        ready.set()
        return original_resume(
            db_path, iid, external_lock_timeout_s=external_lock_timeout_s
        )

    monkeypatch.setattr(speak_routes, "resume", resume_after_writer_starts)
    try:
        async def exercise() -> tuple[dict[str, object], bool]:
            task = asyncio.create_task(speak_routes.invitee_landing(token))
            assert await asyncio.wait_for(asyncio.to_thread(ready.wait, 5), 6)
            await asyncio.sleep(0.2)
            loop_served_other_work = not task.done()
            _release_writer(holder[0])
            return await asyncio.wait_for(task, 5), loop_served_other_work

        landing, loop_served_other_work = asyncio.run(exercise())
        assert loop_served_other_work
        assert landing["interview_id"] == interview_id
    finally:
        for proc in holder:
            _close_writer(proc)


@pytest.mark.parametrize("expire", [False, True])
def test_pushes_second_resume_never_fabricates_zero_pending_under_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, expire: bool
) -> None:
    db, _, interview_id, _ = _seed(tmp_path, monkeypatch)
    turns = [{"role": "interviewer", "question_id": "q1", "text": "What happened?"}]
    with connect_write(str(db), purpose="test:pending-question", keepalive_s=0) as con:
        con.execute(
            "UPDATE interviews SET transcript_turns = ? WHERE interview_id = ?",
            [json.dumps(turns), interview_id],
        )
    baseline = asyncio.run(speak_routes.list_pushes())
    assert baseline["private_repings"][0]["pending_question_count"] == 1

    monkeypatch.setattr(speak_routes, "_WRITE_TIMEOUT_S", 0.1 if expire else 2.0)
    ready = threading.Event()
    holder: list[subprocess.Popen[str]] = []

    def resume_after_writer_starts(
        db_path: str, iid: str, *, external_lock_timeout_s: float = 0.0
    ) -> object:
        holder.append(_hold_writer(db))
        ready.set()
        return original_resume(
            db_path, iid, external_lock_timeout_s=external_lock_timeout_s
        )

    monkeypatch.setattr(async_interview, "resume", resume_after_writer_starts)
    try:
        async def exercise() -> tuple[dict[str, Any] | None, bool]:
            task = asyncio.create_task(speak_routes.list_pushes())
            assert await asyncio.wait_for(asyncio.to_thread(ready.wait, 5), 6)
            if expire:
                with pytest.raises(HTTPException) as exc:
                    await asyncio.wait_for(task, 5)
                assert exc.value.status_code == 503
                assert exc.value.detail == "speak_writer_busy"
                return None, True
            await asyncio.sleep(0.2)
            loop_served_other_work = not task.done()
            _release_writer(holder[0])
            return await asyncio.wait_for(task, 5), loop_served_other_work

        pushes, loop_served_other_work = asyncio.run(exercise())
        assert loop_served_other_work
        if not expire:
            assert pushes is not None
            assert pushes["private_repings"][0]["pending_question_count"] == 1
    finally:
        for proc in holder:
            _close_writer(proc)


def test_pushes_keeps_zero_fallback_for_unrelated_session_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, interview_id, _ = _seed(tmp_path, monkeypatch)

    def bad_session(*_args: object, **_kwargs: object) -> None:
        raise ValueError("malformed interview state")

    monkeypatch.setattr(async_interview, "resume", bad_session)
    pushes = asyncio.run(speak_routes.list_pushes())
    row = next(r for r in pushes["private_repings"] if r["interview_id"] == interview_id)
    assert row["pending_question_count"] == 0


def test_economics_does_not_retry_other_duckdb_io_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_read(_: str, *, read_only: bool = False) -> None:
        raise duckdb.IOException("corrupt database")

    monkeypatch.setattr(duckdb, "connect", fail_read)
    monkeypatch.setattr(speak_routes, "default_db_path", lambda: __file__)
    with pytest.raises(duckdb.IOException, match="corrupt database"):
        asyncio.run(speak_routes.get_economics("project"))


def test_economics_lock_retry_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_read(_: str, *, read_only: bool = False) -> None:
        raise duckdb.IOException(
            "Could not set lock on file: Conflicting lock is held in another process"
        )

    monkeypatch.setattr(duckdb, "connect", fail_read)
    monkeypatch.setattr(speak_routes, "default_db_path", lambda: __file__)
    monkeypatch.setattr(speak_routes, "_WRITE_TIMEOUT_S", 0.1)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(speak_routes.get_economics("project"))
    assert exc.value.status_code == 503
    assert exc.value.detail == "speak_writer_busy"
