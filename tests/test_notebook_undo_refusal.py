"""Notebook undo stays unavailable until mutations issue server receipts."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runtime.db_lock import connect_write
from substrate.ai_actions import AIActionError, undo_ai_action
from substrate.ai_actions.handlers import HANDLERS
from substrate.auth.magic_link import mint_magic_link_token


@pytest.fixture
def signed_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "notebooks.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "undo-refusal-synthetic-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "undo-owner@example.test")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "mock")
    for key in (
        "ANTIEK_OPERATOR_TOKEN", "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET", "ANTIEK_DEV_LOGIN_TOKEN", "TURBOPUFFER_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    from interfaces.research.api.app import create_app
    from runtime.db_lock import connect_write
    from substrate.graph.schema import init_database

    with connect_write(str(tmp_path / "notebooks.duckdb"), purpose="test:notebook_undo_init") as con:
        init_database(con)

    with TestClient(create_app(register_wrestling=False, register_providers=False)) as client:
        callback = client.get(
            f"/auth/callback?token={mint_magic_link_token('undo-owner@example.test')}",
            follow_redirects=False,
        )
        assert callback.status_code == 302
        assert client.get("/auth/me").status_code == 200
        yield client, tmp_path


@pytest.mark.parametrize(
    ("target_kind", "deleted"),
    (("notebook", False), ("notebook_block", False), ("notebook_block", True)),
)
def test_signed_notebook_undo_refuses_before_writer_without_state_or_event_change(
    signed_client, monkeypatch, target_kind: str, deleted: bool
):
    client, tmp_path = signed_client
    created = client.post("/notebooks", json={"title": "Synthetic notebook"})
    assert created.status_code == 201, created.text
    notebook_id = created.json()["notebook_id"]
    appended = client.post(
        f"/notebooks/{notebook_id}/blocks",
        json={"block_type": "prose", "content": {"type": "paragraph"}},
    )
    assert appended.status_code == 201, appended.text
    block_id = appended.json()["blocks"][0]["block_id"]
    if deleted:
        removed = client.delete(f"/notebooks/{notebook_id}/blocks/{block_id}")
        assert removed.status_code == 200, removed.text

    target_id = notebook_id if target_kind == "notebook" else block_id
    applied = client.post(
        "/events/typed",
        json={
            "investigation_id": "inv-undo-refusal",
            "payload": {
                "action_type": "ai.action.applied",
                "target_kind": target_kind,
                "target_id": target_id,
                "operator_prompt": "synthetic notebook edit",
                "prev_state": {},
                "next_state": {},
                "prev_state_hash": "0" * 64,
            },
        },
    )
    assert applied.status_code == 201, applied.text
    event_file = tmp_path / "events" / "inv-undo-refusal.jsonl"
    events_before = event_file.read_bytes()
    db_path = str(tmp_path / "notebooks.duckdb")
    with connect_write(db_path, purpose="test:notebook_undo_before") as con:
        notebook_before = con.execute(
            "SELECT notebook_id,title,owner_user_id,content_class FROM notebooks WHERE notebook_id=?",
            [notebook_id],
        ).fetchone()
        blocks_before = con.execute(
            "SELECT block_id,notebook_id,block_index,block_type,ref_id,content_json "
            "FROM notebook_blocks WHERE notebook_id=? ORDER BY block_index,block_id",
            [notebook_id],
        ).fetchall()

    def forbidden_writer(*args, **kwargs):
        raise AssertionError("notebook undo acquired a writer")

    with monkeypatch.context() as patch:
        patch.setattr("runtime.db_lock.connect_write", forbidden_writer)
        refused = client.post(
            "/ai/undo",
            json={"event_id": applied.json()["event_id"], "investigation_id": "inv-undo-refusal"},
        )
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "notebook_undo_requires_server_receipt"
    assert target_id not in refused.text
    assert event_file.read_bytes() == events_before
    with connect_write(db_path, purpose="test:notebook_undo_after") as con:
        assert con.execute(
            "SELECT notebook_id,title,owner_user_id,content_class FROM notebooks WHERE notebook_id=?",
            [notebook_id],
        ).fetchone() == notebook_before
        assert con.execute(
            "SELECT block_id,notebook_id,block_index,block_type,ref_id,content_json "
            "FROM notebook_blocks WHERE notebook_id=? ORDER BY block_index,block_id",
            [notebook_id],
        ).fetchall() == blocks_before


@pytest.mark.parametrize("target_kind", ("notebook", "notebook_block"))
def test_direct_dispatch_refuses_before_handler_and_emitter(monkeypatch, target_kind: str):
    calls: list[str] = []

    def forbidden_handler(*args, **kwargs):
        calls.append("handler")

    monkeypatch.setitem(HANDLERS, target_kind, forbidden_handler)
    applied_event = {
        "event_id": "evt-synthetic",
        "investigation_id": "inv-synthetic",
        "payload": {
            "action_type": "ai.action.applied",
            "target_kind": target_kind,
            "target_id": "target-synthetic",
            "prev_state": {},
            "next_state": {},
        },
    }
    with pytest.raises(AIActionError, match="notebook undo requires a server receipt"):
        undo_ai_action(
            object(), applied_event=applied_event,
            emit_event_fn=lambda event: calls.append("emitter"),
        )
    assert calls == []


def test_signed_non_notebook_undo_still_emits_linked_event(signed_client):
    client, tmp_path = signed_client
    applied = client.post(
        "/events/typed",
        json={
            "investigation_id": "inv-layout-undo",
            "payload": {
                "action_type": "ai.action.applied",
                "target_kind": "ui_layout",
                "target_id": "panel-synthetic",
                "operator_prompt": "open synthetic panel",
                "prev_state": {"open": False},
                "next_state": {"open": True},
                "prev_state_hash": "0" * 64,
            },
        },
    )
    assert applied.status_code == 201, applied.text
    undone = client.post(
        "/ai/undo",
        json={"event_id": applied.json()["event_id"], "investigation_id": "inv-layout-undo"},
    )
    assert undone.status_code == 200, undone.text
    assert undone.json()["action_type"] == "ai.action.undone"
    events = [
        json.loads(line)
        for line in (tmp_path / "events" / "inv-layout-undo.jsonl").read_text().splitlines()
    ]
    assert len(events) == 2
    assert events[-1]["event_id"] == undone.json()["event_id"]
    assert events[-1]["payload"]["inverted_event_id"] == applied.json()["event_id"]
