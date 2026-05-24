"""Tests for substrate/conversation — event, event_log, checkpoint, branch, CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.conversation import (
    Checkpoint,
    CheckpointVerifyFailed,
    ConversationLogCorrupted,
    Event,
    EventLog,
    create_branch,
    create_checkpoint,
    list_branches,
    list_checkpoints,
    verify_checkpoint,
)
from substrate.conversation.cli import main as branch_cli_main


def test_event_hash_is_deterministic() -> None:
    e1 = Event(position=1, ts="2026-05-24T00:00:00+00:00", kind="user_message", payload={"text": "hi"})
    e2 = Event(position=1, ts="2026-05-24T00:00:00+00:00", kind="user_message", payload={"text": "hi"})
    assert e1.hash() == e2.hash()
    e3 = Event(position=2, ts="2026-05-24T00:00:00+00:00", kind="user_message", payload={"text": "hi"})
    assert e1.hash() != e3.hash()


def test_event_canonical_json_is_key_order_stable() -> None:
    e = Event(
        position=1, ts="2026-05-24T00:00:00+00:00", kind="user_message",
        payload={"z": 1, "a": 2, "m": 3},
    )
    cj = e.canonical_json()
    assert cj.index('"kind"') < cj.index('"parent_checkpoint"')
    assert cj.index('"a"') < cj.index('"m"') < cj.index('"z"')


def test_event_pinned_hash_value() -> None:
    e = Event(position=1, ts="2026-01-01T00:00:00+00:00", kind="user_message", payload={"x": 1})
    assert e.hash() == "629c4e19aaafd23e29a1e4b6523612620823042db1dc594967f26f3bf89463e9"


def test_event_rejects_invalid_kind() -> None:
    with pytest.raises(ValueError, match="unknown EventKind"):
        Event(position=1, ts="2026-01-01T00:00:00+00:00", kind="bogus", payload={})  # type: ignore[arg-type]


def test_event_rejects_zero_position() -> None:
    with pytest.raises(ValueError, match="position must be >= 1"):
        Event(position=0, ts="2026-01-01T00:00:00+00:00", kind="user_message", payload={})


def _ev(pos: int, kind: str = "user_message", payload: dict | None = None) -> Event:
    return Event(
        position=pos,
        ts=f"2026-05-24T00:00:0{pos}+00:00",
        kind=kind,  # type: ignore[arg-type]
        payload=payload or {"i": pos},
    )


def test_event_log_append_and_iter(tmp_path: Path) -> None:
    log = EventLog("s1", tmp_path, fsync_on_append=False)
    for i in range(1, 6):
        log.append(_ev(i))
    events = list(log.iter_events())
    assert [e.position for e in events] == [1, 2, 3, 4, 5]
    assert log.position() == 5


def test_event_log_out_of_order_position_raises(tmp_path: Path) -> None:
    log = EventLog("s1", tmp_path, fsync_on_append=False)
    log.append(_ev(1))
    with pytest.raises(ConversationLogCorrupted, match="expected position 2, got 5"):
        log.append(_ev(5))


def test_event_log_repeated_position_raises(tmp_path: Path) -> None:
    log = EventLog("s1", tmp_path, fsync_on_append=False)
    log.append(_ev(1))
    log.append(_ev(2))
    with pytest.raises(ConversationLogCorrupted, match="expected position 3, got 2"):
        log.append(_ev(2))


def test_event_log_session_id_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        EventLog("../escape", tmp_path)
    with pytest.raises(ValueError):
        EventLog("dir/sub", tmp_path)


def test_event_log_iter_slice(tmp_path: Path) -> None:
    log = EventLog("s1", tmp_path, fsync_on_append=False)
    for i in range(1, 11):
        log.append(_ev(i))
    sliced = list(log.iter_events(from_position=4, to_position=6))
    assert [e.position for e in sliced] == [4, 5, 6]


def test_event_log_corrupted_final_line(tmp_path: Path) -> None:
    log = EventLog("s1", tmp_path, fsync_on_append=False)
    log.append(_ev(1))
    log.path.write_text(log.path.read_text() + "not-valid-json\n")
    with pytest.raises(ConversationLogCorrupted):
        log.position()


def test_checkpoint_create_and_verify(tmp_path: Path) -> None:
    log = EventLog("s1", tmp_path, fsync_on_append=False)
    for i in range(1, 6):
        log.append(_ev(i))
    cp = create_checkpoint("s1", tmp_path, position=3, label="point-A")
    assert cp.position == 3
    assert cp.label == "point-A"
    assert len(cp.hash) == 64
    verify_checkpoint("s1", tmp_path, 3, cp.hash)


def test_checkpoint_verify_detects_log_mutation(tmp_path: Path) -> None:
    log = EventLog("s1", tmp_path, fsync_on_append=False)
    for i in range(1, 6):
        log.append(_ev(i))
    cp = create_checkpoint("s1", tmp_path, position=3)
    lines = log.path.read_text().splitlines()
    tampered = Event(position=2, ts="2099-01-01T00:00:00+00:00", kind="system_marker", payload={"hack": True})
    lines[1] = tampered.canonical_json()
    log.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(CheckpointVerifyFailed):
        verify_checkpoint("s1", tmp_path, 3, cp.hash)


def test_checkpoint_at_invalid_position_raises(tmp_path: Path) -> None:
    log = EventLog("s1", tmp_path, fsync_on_append=False)
    log.append(_ev(1))
    with pytest.raises(ValueError, match="has only 1 events"):
        create_checkpoint("s1", tmp_path, position=5)


def test_list_checkpoints_round_trip(tmp_path: Path) -> None:
    log = EventLog("s1", tmp_path, fsync_on_append=False)
    for i in range(1, 6):
        log.append(_ev(i))
    create_checkpoint("s1", tmp_path, 2, label="A")
    create_checkpoint("s1", tmp_path, 4, label="B")
    cps = list_checkpoints("s1", tmp_path)
    assert [c.position for c in cps] == [2, 4]


def test_create_branch_copies_events_up_to_position(tmp_path: Path) -> None:
    parent = EventLog("parent", tmp_path, fsync_on_append=False)
    for i in range(1, 11):
        parent.append(_ev(i))
    cp = create_checkpoint("parent", tmp_path, position=4)
    child_id = create_branch("parent", cp, "retry", tmp_path)
    child = EventLog(child_id, tmp_path, fsync_on_append=False)
    assert child.position() == 4
    assert [e.position for e in child.iter_events()] == [1, 2, 3, 4]


def test_create_branch_independence_child_does_not_affect_parent(tmp_path: Path) -> None:
    parent = EventLog("parent", tmp_path, fsync_on_append=False)
    for i in range(1, 6):
        parent.append(_ev(i))
    cp = create_checkpoint("parent", tmp_path, position=3)
    child_id = create_branch("parent", cp, "retry", tmp_path)
    child = EventLog(child_id, tmp_path, fsync_on_append=False)
    child.append(_ev(4, payload={"divergent": True}))
    child.append(_ev(5, payload={"divergent": True}))
    assert parent.position() == 5
    parent_evs = list(parent.iter_events(from_position=4))
    assert parent_evs[0].payload == {"i": 4}
    child_evs = list(child.iter_events(from_position=4))
    assert child_evs[0].payload == {"divergent": True}


def test_create_branch_records_lineage(tmp_path: Path) -> None:
    parent = EventLog("parent", tmp_path, fsync_on_append=False)
    for i in range(1, 4):
        parent.append(_ev(i))
    cp = create_checkpoint("parent", tmp_path, position=2)
    child_id = create_branch("parent", cp, "alt", tmp_path)
    branches = list_branches(tmp_path)
    assert len(branches) == 1
    assert branches[0].child_session_id == child_id
    assert branches[0].name == "alt"


def test_create_branch_rejects_tampered_checkpoint(tmp_path: Path) -> None:
    parent = EventLog("parent", tmp_path, fsync_on_append=False)
    for i in range(1, 5):
        parent.append(_ev(i))
    cp = create_checkpoint("parent", tmp_path, position=3)
    bad = Checkpoint(session_id="parent", position=3, hash="0" * 64, created_at=cp.created_at, label=None)
    with pytest.raises(CheckpointVerifyFailed):
        create_branch("parent", bad, "wont-make-it", tmp_path)
    assert list_branches(tmp_path) == []


def test_branch_of_branch(tmp_path: Path) -> None:
    parent = EventLog("p", tmp_path, fsync_on_append=False)
    for i in range(1, 6):
        parent.append(_ev(i))
    cp1 = create_checkpoint("p", tmp_path, position=3)
    child1 = create_branch("p", cp1, "child1", tmp_path)
    child1_log = EventLog(child1, tmp_path, fsync_on_append=False)
    child1_log.append(_ev(4, payload={"a": 1}))
    cp2 = create_checkpoint(child1, tmp_path, position=4)
    child2 = create_branch(child1, cp2, "child2", tmp_path)
    assert EventLog(child2, tmp_path, fsync_on_append=False).position() == 4


def _seed_session(project_root: Path, session_id: str, n: int = 5) -> None:
    log = EventLog(session_id, project_root, fsync_on_append=False)
    for i in range(1, n + 1):
        log.append(_ev(i))


def test_cli_from_creates_branch(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _seed_session(tmp_path, "orig", n=5)
    rc = branch_cli_main(["--project-root", str(tmp_path), "from", "orig:3", "--name", "retry"])
    assert rc == 0
    branches = list_branches(tmp_path)
    assert len(branches) == 1
    assert branches[0].branch_position == 3


def test_cli_list_renders_tree(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _seed_session(tmp_path, "root", n=4)
    cp = create_checkpoint("root", tmp_path, 2)
    create_branch("root", cp, "a", tmp_path)
    create_branch("root", cp, "b", tmp_path)
    branch_cli_main(["--project-root", str(tmp_path), "list"])
    out = capsys.readouterr().out
    assert "root" in out and "name='a'" in out and "name='b'" in out


def test_cli_switch_writes_active_marker(tmp_path: Path) -> None:
    _seed_session(tmp_path, "orig", n=2)
    rc = branch_cli_main(["--project-root", str(tmp_path), "switch", "orig"])
    assert rc == 0
    assert (tmp_path / ".antiek" / "active_session_id").read_text() == "orig"


def test_cli_switch_unknown_session_errors(tmp_path: Path) -> None:
    rc = branch_cli_main(["--project-root", str(tmp_path), "switch", "no-such"])
    assert rc == 2


def test_cli_delete_removes_directory(tmp_path: Path) -> None:
    _seed_session(tmp_path, "doomed", n=2)
    rc = branch_cli_main(["--project-root", str(tmp_path), "delete", "doomed"])
    assert rc == 0
    assert not (tmp_path / ".antiek" / "conversation" / "doomed").exists()


def test_cli_delete_cascade(tmp_path: Path) -> None:
    _seed_session(tmp_path, "root", n=3)
    cp = create_checkpoint("root", tmp_path, 2)
    child = create_branch("root", cp, "child", tmp_path)
    grand_cp = create_checkpoint(child, tmp_path, 2)
    grandchild = create_branch(child, grand_cp, "grand", tmp_path)
    branch_cli_main(["--project-root", str(tmp_path), "delete", "root", "--cascade"])
    assert not (tmp_path / ".antiek" / "conversation" / "root").exists()
    assert not (tmp_path / ".antiek" / "conversation" / child).exists()
    assert not (tmp_path / ".antiek" / "conversation" / grandchild).exists()


def test_cli_list_json_output(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _seed_session(tmp_path, "root", n=3)
    cp = create_checkpoint("root", tmp_path, 2)
    create_branch("root", cp, "alt", tmp_path)
    rc = branch_cli_main(["--project-root", str(tmp_path), "list", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 1
    assert data[0]["name"] == "alt"
