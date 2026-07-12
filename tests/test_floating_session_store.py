"""Owner-wide durable session discovery index."""

from __future__ import annotations

import json

import pytest

from substrate.floating_session.store import FileSessionStore, InMemorySessionStore


def _row(session_id: str, owner_id: str, asset_id: str) -> dict[str, str]:
    return {
        "session_id": session_id,
        "owner_id": owner_id,
        "parent_asset_id": asset_id,
        "spawn_id": f"spn_{session_id[-4:]}",
        "investigation_id": f"inv_{session_id[-4:]}",
        "status": "reserved",
        "view_mode": "floating",
        "selection_text": "passage",
    }


@pytest.mark.parametrize("store_kind", ["memory", "file"])
def test_owner_index_crosses_assets_without_crossing_owners(tmp_path, store_kind):
    store = (
        InMemorySessionStore()
        if store_kind == "memory"
        else FileSessionStore(tmp_path / "sessions")
    )
    alice_rows = [
        _row("fsess_1111111111111111", "alice", "asset-a"),
        _row("fsess_2222222222222222", "alice", "asset-b"),
    ]
    for row in [*alice_rows, _row("fsess_3333333333333333", "bob", "asset-a")]:
        store.put_session(row)

    assert store.list_owner_sessions(
        "alice", after_session_id=None, limit=10
    ) == alice_rows
    assert [
        row["owner_id"]
        for row in store.list_owner_sessions("bob", after_session_id=None, limit=10)
    ] == ["bob"]
    first = store.list_owner_sessions("alice", after_session_id=None, limit=1)
    second = store.list_owner_sessions(
        "alice", after_session_id=first[0]["session_id"], limit=1
    )
    assert [first[0]["session_id"], second[0]["session_id"]] == [
        row["session_id"] for row in alice_rows
    ]
    with pytest.raises(ValueError, match="cursor is not available"):
        store.list_owner_sessions(
            "alice", after_session_id="fsess_9999999999999999", limit=1
        )

    if store_kind == "file":
        reopened = FileSessionStore(tmp_path / "sessions")
        assert len(
            reopened.list_owner_sessions("alice", after_session_id=None, limit=10)
        ) == 2


def test_durable_owner_index_fails_closed_on_missing_or_owner_drift(tmp_path):
    store = FileSessionStore(tmp_path / "sessions")
    row = _row("fsess_4444444444444444", "alice", "asset-a")
    store.put_session(row)
    session_path = store.root / "sessions" / f"{row['session_id']}.json"
    session_path.unlink()
    with pytest.raises(ValueError, match="requires reconciliation"):
        store.list_owner_sessions("alice", after_session_id=None, limit=10)

    store.put_session(row)
    session_path.write_text(json.dumps({**row, "owner_id": "bob"}), encoding="utf-8")
    with pytest.raises(ValueError, match="requires reconciliation"):
        store.list_owner_sessions("alice", after_session_id=None, limit=10)


def test_durable_store_backfills_owner_index_for_existing_rows(tmp_path):
    root = tmp_path / "sessions"
    # Establish a prior clean startup, then simulate a crash after the
    # canonical row write but before either index append.
    FileSessionStore(root)
    sessions = root / "sessions"
    row = _row("fsess_5555555555555555", "alice", "legacy-indexed-asset")
    (sessions / f"{row['session_id']}.json").write_text(
        json.dumps(row), encoding="utf-8"
    )

    reopened = FileSessionStore(root)
    assert reopened.list_owner_sessions(
        "alice", after_session_id=None, limit=10
    ) == [row]
