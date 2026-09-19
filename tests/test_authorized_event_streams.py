from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from pathlib import Path

import pytest

import substrate.event_log.events as event_operations
from substrate.event_log import (
    append_event_once_authorized,
    prepare_typed_event,
    seal_investigation_authorized,
    trajectory_authorized,
)
from substrate.investigation_streams import (
    InvestigationStreamUnbound,
    resolve_investigation_stream,
)
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas.events import DispatchCallPayload


def _event(investigation_id: str, event_id: str, prompt_hash: str):
    payload = DispatchCallPayload(
        provider="provider",
        model="model",
        tier="flash",
        target_role="researcher",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.01,
        latency_ms=100,
        prompt_hash=prompt_hash,
    )
    return prepare_typed_event(investigation_id, payload, event_id=event_id)


def test_same_display_id_isolated_by_account_authority(tmp_path):
    alice = InvestigationAuthority("alice", "shared", root=tmp_path)
    bob = InvestigationAuthority("bob", "shared", root=tmp_path)
    append_event_once_authorized(alice, _event("shared", "evt-alice", "alice"))
    append_event_once_authorized(bob, _event("shared", "evt-bob", "bob"))

    assert [row["event_id"] for row in trajectory_authorized(alice)] == ["evt-alice"]
    assert [row["event_id"] for row in trajectory_authorized(bob)] == ["evt-bob"]
    assert resolve_investigation_stream(alice).jsonl_path != resolve_investigation_stream(
        bob
    ).jsonl_path
    assert not (tmp_path / "shared.jsonl").exists()


def test_authorized_append_rejects_display_id_mismatch_before_write(tmp_path):
    authority = InvestigationAuthority("alice", "expected", root=tmp_path)
    with pytest.raises(ValueError, match="crosses authorized"):
        append_event_once_authorized(authority, _event("foreign", "evt-1", "x"))
    with pytest.raises(InvestigationStreamUnbound):
        resolve_investigation_stream(authority)


def test_authorized_read_rejects_foreign_row_in_selected_stream(tmp_path):
    authority = InvestigationAuthority("alice", "expected", root=tmp_path)
    append_event_once_authorized(authority, _event("expected", "evt-1", "x"))
    path = resolve_investigation_stream(authority).jsonl_path
    row = json.loads(path.read_text().splitlines()[0])
    row["investigation_id"] = "foreign"
    path.write_text(json.dumps(row) + "\n")

    with pytest.raises(ValueError, match="crosses authorized"):
        trajectory_authorized(authority)


def test_authorized_read_rejects_conflicting_duplicate_event_id(tmp_path):
    authority = InvestigationAuthority("alice", "expected", root=tmp_path)
    append_event_once_authorized(authority, _event("expected", "evt-1", "first"))
    path = resolve_investigation_stream(authority).jsonl_path
    conflicting = _event("expected", "evt-1", "second").model_dump(mode="json")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(conflicting) + "\n")
    with pytest.raises(ValueError, match="event id collision"):
        trajectory_authorized(authority)


def test_append_stays_on_pinned_directory_during_namespace_replacement(
    tmp_path, monkeypatch
):
    authority = InvestigationAuthority("alice", "expected", root=tmp_path)
    append_event_once_authorized(authority, _event("expected", "evt-1", "first"))
    resolved = resolve_investigation_stream(authority)
    shard = resolved.jsonl_path.parent
    moved = shard.with_name(f"{shard.name}-moved")
    outside = tmp_path / "outside"
    outside.mkdir()
    original_lock = event_operations._authorized_event_lock
    replaced = False

    @contextmanager
    def replacing_lock(stream):
        nonlocal replaced
        if not replaced:
            shard.rename(moved)
            shard.symlink_to(outside, target_is_directory=True)
            replaced = True
        with original_lock(stream):
            yield

    monkeypatch.setattr(event_operations, "_authorized_event_lock", replacing_lock)
    append_event_once_authorized(authority, _event("expected", "evt-2", "second"))
    assert not list(outside.iterdir())
    rows = [json.loads(line) for line in (moved / resolved.jsonl_path.name).read_text().splitlines()]
    assert [row["event_id"] for row in rows] == ["evt-1", "evt-2"]


def test_authorized_read_rejects_hardlinked_stream_file(tmp_path):
    authority = InvestigationAuthority("alice", "expected", root=tmp_path)
    append_event_once_authorized(authority, _event("expected", "evt-1", "first"))
    path = resolve_investigation_stream(authority).jsonl_path
    (tmp_path / "hostile-hardlink").hardlink_to(path)
    with pytest.raises(RuntimeError, match="unsafe"):
        trajectory_authorized(authority)


def test_fresh_root_backup_restore_preserves_key_state_and_live_tail(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    authorities = {
        account: InvestigationAuthority(account, "shared", root=source)
        for account in ("alice", "bob")
    }
    for account, authority in authorities.items():
        append_event_once_authorized(
            authority, _event("shared", f"evt-{account}-prefix", account)
        )
        sealed = seal_investigation_authorized(authority)
        assert sealed is not None
        assert Path(sealed).is_file()
        append_event_once_authorized(
            authority, _event("shared", f"evt-{account}-tail", f"{account}-tail")
        )

    restored_root = tmp_path / "restored"
    shutil.copytree(source, restored_root, copy_function=shutil.copy2)
    restored = {
        account: InvestigationAuthority(account, "shared", root=restored_root)
        for account in ("alice", "bob")
    }

    for account, authority in restored.items():
        assert [row["event_id"] for row in trajectory_authorized(authority)] == [
            f"evt-{account}-prefix",
            f"evt-{account}-tail",
        ]
        append_event_once_authorized(
            authority, _event("shared", f"evt-{account}-restored", f"{account}-new")
        )
    assert resolve_investigation_stream(restored["alice"]).jsonl_path != (
        resolve_investigation_stream(restored["bob"]).jsonl_path
    )
    assert [row["event_id"] for row in trajectory_authorized(restored["alice"])] == [
        "evt-alice-prefix",
        "evt-alice-tail",
        "evt-alice-restored",
    ]
    assert [row["event_id"] for row in trajectory_authorized(restored["bob"])] == [
        "evt-bob-prefix",
        "evt-bob-tail",
        "evt-bob-restored",
    ]
