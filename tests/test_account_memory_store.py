from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import substrate.memory.store as memory_store
from runtime.db_lock import LockedConnection, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.memory import MemoryItem, list_memory, write_memory_item


@pytest.fixture
def memory_con(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LockedConnection:
    db_path = str(tmp_path / "account-memory.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    init_database_at_path(db_path)
    con = connect_write(db_path, purpose="test-account-memory")
    try:
        yield con
    finally:
        con.close()


def _write(
    con: LockedConnection,
    *,
    owner: str,
    object: str,
    valid_from: datetime,
) -> MemoryItem:
    return write_memory_item(
        con,
        owner_user_id=owner,
        subject="operator",
        predicate="prefers_editor",
        object=object,
        provenance={
            "event_id": f"event-{owner}-{object}",
            "source_tier": 1,
            "extraction_confidence": 0.98,
        },
        valid_from=valid_from,
    )


def test_write_memory_item_projects_node_and_owner_edge(
    memory_con: LockedConnection,
) -> None:
    item = _write(
        memory_con,
        owner="user-a",
        object="vim",
        valid_from=datetime(2026, 8, 1, 9, 0),
    )

    node = memory_con.execute(
        "SELECT node_type, canonical_label, owner_user_id FROM nodes WHERE node_id = ?",
        [item.memory_id],
    ).fetchone()
    edge = memory_con.execute(
        "SELECT owner_user_id, valid_until FROM edges WHERE edge_id = ?",
        [item.edge_id],
    ).fetchone()

    assert node == ("memory", "vim", "user-a")
    assert edge == ("user-a", None)
    assert list_memory(memory_con, "user-a") == [item]


def test_supersede_invalidates_without_deleting(memory_con: LockedConnection) -> None:
    first_at = datetime(2026, 8, 1, 9, 0)
    second_at = first_at + timedelta(days=1)
    old = _write(memory_con, owner="user-a", object="vim", valid_from=first_at)
    new = _write(memory_con, owner="user-a", object="zed", valid_from=second_at)

    assert list_memory(memory_con, "user-a") == [new]
    history = list_memory(memory_con, "user-a", include_invalidated=True)
    assert [item.object for item in history] == ["zed", "vim"]
    preserved = history[1]
    assert preserved.memory_id == old.memory_id
    assert preserved.valid_to == second_at
    assert preserved.superseded_by == new.edge_id
    assert memory_con.execute(
        "SELECT count(*) FROM nodes WHERE node_type = 'memory' AND owner_user_id = 'user-a'"
    ).fetchone() == (2,)
    assert memory_con.execute(
        "SELECT count(*) FROM edges WHERE owner_user_id = 'user-a'"
    ).fetchone() == (2,)


def test_write_is_idempotent_for_current_value(memory_con: LockedConnection) -> None:
    at = datetime(2026, 8, 1, 9, 0)
    first = _write(memory_con, owner="user-a", object="vim", valid_from=at)
    repeated = _write(memory_con, owner="user-a", object="vim", valid_from=at)

    assert repeated == first
    assert len(list_memory(memory_con, "user-a", include_invalidated=True)) == 1


def test_list_memory_never_crosses_owner_scope(memory_con: LockedConnection) -> None:
    at = datetime(2026, 8, 1, 9, 0)
    item_a = _write(memory_con, owner="user-a", object="vim", valid_from=at)
    item_b = _write(memory_con, owner="user-b", object="emacs", valid_from=at)

    assert list_memory(memory_con, "user-a") == [item_a]
    assert list_memory(memory_con, "user-b") == [item_b]
    assert list_memory(memory_con, "user-c") == []


def test_list_memory_supports_point_in_time(memory_con: LockedConnection) -> None:
    first_at = datetime(2026, 8, 1, 9, 0)
    second_at = first_at + timedelta(days=1)
    old = _write(memory_con, owner="user-a", object="vim", valid_from=first_at)
    new = _write(memory_con, owner="user-a", object="zed", valid_from=second_at)

    at_first = list_memory(memory_con, "user-a", valid_at=first_at)
    at_second = list_memory(memory_con, "user-a", valid_at=second_at)
    assert [(item.memory_id, item.object) for item in at_first] == [
        (old.memory_id, "vim")
    ]
    assert [(item.memory_id, item.object) for item in at_second] == [
        (new.memory_id, "zed")
    ]


def test_future_supersession_preserves_present_interval(
    memory_con: LockedConnection,
) -> None:
    old = _write(
        memory_con,
        owner="user-a",
        object="vim",
        valid_from=datetime(2000, 1, 1),
    )
    future = _write(
        memory_con,
        owner="user-a",
        object="zed",
        valid_from=datetime(2099, 1, 1),
    )

    assert list_memory(memory_con, "user-a") == [
        old.model_copy(update={"valid_to": datetime(2099, 1, 1), "superseded_by": future.edge_id})
    ]
    assert list_memory(memory_con, "user-a", valid_at=datetime(2099, 1, 1)) == [
        future
    ]
    with pytest.raises(ValueError, match="later than the current"):
        _write(
            memory_con,
            owner="user-a",
            object="emacs",
            valid_from=datetime(2025, 1, 1),
        )
    assert len(list_memory(memory_con, "user-a", include_invalidated=True)) == 2


def test_write_rejects_caller_owned_transaction(memory_con: LockedConnection) -> None:
    memory_con.execute("BEGIN")
    try:
        with pytest.raises(RuntimeError, match="manages its own transaction"):
            _write(
                memory_con,
                owner="user-a",
                object="vim",
                valid_from=datetime(2026, 8, 1),
            )
        assert memory_con.execute(
            "SELECT count(*) FROM nodes WHERE node_type = 'memory'"
        ).fetchone() == (0,)
    finally:
        memory_con.execute("ROLLBACK")


def test_invalid_provenance_fails_before_graph_mutation(
    memory_con: LockedConnection,
) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        write_memory_item(
            memory_con,
            owner_user_id="user-a",
            subject="operator",
            predicate="prefers_editor",
            object="vim",
            provenance={"chunk_id": "missing-chunk"},
            valid_from=datetime(2026, 8, 1),
        )
    with pytest.raises(ValueError, match="source reference"):
        write_memory_item(
            memory_con,
            owner_user_id="user-a",
            subject="operator",
            predicate="prefers_editor",
            object="vim",
            provenance={"owner_user_id": "user-a"},
            valid_from=datetime(2026, 8, 1),
        )
    assert memory_con.execute("SELECT count(*) FROM nodes").fetchone() == (0,)


def test_write_enqueues_graph_events_atomically_then_dispatches_after_commit(
    memory_con: LockedConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatched: list[tuple[bool, str]] = []

    def capture_dispatch(
        _con: LockedConnection, investigation_id: str
    ) -> list[str]:
        dispatched.append((memory_con.in_explicit_transaction, investigation_id))
        return []

    monkeypatch.setattr(
        memory_store, "dispatch_pending_best_effort", capture_dispatch
    )
    item = _write(
        memory_con,
        owner="user-a",
        object="vim",
        valid_from=datetime(2026, 8, 1),
    )

    assert dispatched == [(False, "event-user-a-vim")]
    rows = memory_con.execute(
        "SELECT event_json,state FROM write_event_outbox ORDER BY outbox_sequence"
    ).fetchall()
    assert len(rows) == 3
    assert {str(row[1]) for row in rows} == {"pending"}
    edge_payload = json.loads(str(rows[-1][0]))["payload"]
    assert edge_payload["edge_id"] == item.edge_id
    assert edge_payload["owner_user_id"] == "user-a"


def test_outbox_failure_rolls_back_graph_and_event_intents(
    memory_con: LockedConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = memory_store.enqueue_event
    calls = 0

    def fail_second_enqueue(*args: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected outbox failure")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(memory_store, "enqueue_event", fail_second_enqueue)
    with pytest.raises(RuntimeError, match="injected outbox failure"):
        _write(
            memory_con,
            owner="user-a",
            object="vim",
            valid_from=datetime(2026, 8, 1),
        )

    assert memory_con.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
    assert memory_con.execute("SELECT count(*) FROM edges").fetchone() == (0,)
    assert memory_con.execute(
        "SELECT count(*) FROM write_event_outbox"
    ).fetchone() == (0,)
