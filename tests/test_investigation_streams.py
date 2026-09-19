from __future__ import annotations

import json
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import substrate.investigation_streams as stream_codec
from substrate.investigation_streams import (
    StreamStorageState,
    initialize_composite_stream,
    list_authorized_investigation_ids,
    list_composite_investigation_ids,
    list_operator_investigation_authorities,
    resolve_investigation_stream,
)
from substrate.investigation_tenancy import (
    InvestigationAuthority,
    InvestigationOwnershipConflict,
    bind_legacy_stream_lease,
    mark_legacy_lease_composite,
)


def test_two_accounts_same_display_id_get_distinct_opaque_paths(tmp_path):
    alice = InvestigationAuthority("alice@example.test", "same-display", root=tmp_path)
    bob = InvestigationAuthority("bob@example.test", "same-display", root=tmp_path)
    a = initialize_composite_stream(alice)
    b = initialize_composite_stream(bob)
    assert a.jsonl_path != b.jsonl_path
    assert a.state_path != b.state_path
    for path in (a.jsonl_path, b.jsonl_path, a.state_path, b.state_path):
        rendered = str(path)
        assert "alice" not in rendered
        assert "bob" not in rendered
        assert "same-display" not in rendered
    assert resolve_investigation_stream(alice).state is StreamStorageState.COMPOSITE
    assert resolve_investigation_stream(bob).state is StreamStorageState.COMPOSITE
    assert list_composite_investigation_ids("alice@example.test", root=tmp_path) == [
        "same-display"
    ]
    assert list_composite_investigation_ids("bob@example.test", root=tmp_path) == [
        "same-display"
    ]


def test_legacy_resolution_requires_exact_owner(tmp_path):
    alice = InvestigationAuthority("alice", "legacy", root=tmp_path)
    bob = InvestigationAuthority("bob", "legacy", root=tmp_path)
    bind_legacy_stream_lease(alice)
    resolved = resolve_investigation_stream(alice)
    assert resolved.state is StreamStorageState.LEGACY
    assert resolved.jsonl_path == tmp_path / "legacy.jsonl"
    with pytest.raises(InvestigationOwnershipConflict):
        resolve_investigation_stream(bob)


def test_account_enumeration_unions_composite_and_exact_legacy_owner(tmp_path):
    alice_legacy = InvestigationAuthority("alice", "legacy", root=tmp_path)
    alice_composite = InvestigationAuthority("alice", "composite", root=tmp_path)
    bob_composite = InvestigationAuthority("bob", "composite", root=tmp_path)
    bind_legacy_stream_lease(alice_legacy)
    (tmp_path / "legacy.jsonl").write_text("", encoding="utf-8")
    initialize_composite_stream(alice_composite)
    initialize_composite_stream(bob_composite)

    assert list_authorized_investigation_ids("alice", root=tmp_path) == [
        "composite",
        "legacy",
    ]
    assert list_authorized_investigation_ids("bob", root=tmp_path) == ["composite"]


def test_account_enumeration_ignores_unbound_raw_and_foreign_lease(tmp_path):
    alice = InvestigationAuthority("alice", "owned", root=tmp_path)
    bind_legacy_stream_lease(alice)
    (tmp_path / "owned.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "unbound.jsonl").write_text("", encoding="utf-8")

    assert list_authorized_investigation_ids("alice", root=tmp_path) == ["owned"]
    assert list_authorized_investigation_ids("bob", root=tmp_path) == []


def test_operator_global_enumeration_includes_every_composite_account(tmp_path):
    for account_id, investigation_id in (
        ("alice", "same-display"),
        ("bob", "same-display"),
        ("bob", "other"),
    ):
        initialize_composite_stream(
            InvestigationAuthority(account_id, investigation_id, root=tmp_path)
        )
    operator = InvestigationAuthority("__operator__", "__global__", root=tmp_path)

    assert [
        (authority.account_id, authority.investigation_id)
        for authority in list_operator_investigation_authorities(operator)
    ] == [
        ("alice", "same-display"),
        ("bob", "other"),
        ("bob", "same-display"),
    ]


def test_non_operator_cannot_enumerate_global_stream_domain(tmp_path):
    initialize_composite_stream(InvestigationAuthority("alice", "inv", root=tmp_path))
    with pytest.raises(InvestigationOwnershipConflict, match="requires operator"):
        list_operator_investigation_authorities(
            InvestigationAuthority("alice", "__global__", root=tmp_path)
        )


def test_operator_global_enumeration_refuses_partial_legacy_domain(tmp_path):
    initialize_composite_stream(InvestigationAuthority("alice", "new", root=tmp_path))
    (tmp_path / "historic.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(InvestigationOwnershipConflict, match="legacy migration"):
        list_operator_investigation_authorities(
            InvestigationAuthority("__operator__", "__global__", root=tmp_path)
        )


def test_operator_global_enumeration_refuses_legacy_only_domain(tmp_path):
    operator = InvestigationAuthority("__operator__", "__global__", root=tmp_path)
    (tmp_path / "historic.parquet").write_text("", encoding="utf-8")
    with pytest.raises(InvestigationOwnershipConflict, match="legacy migration"):
        list_operator_investigation_authorities(operator)


def test_composite_state_tamper_never_falls_back_to_legacy(tmp_path):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    resolved = initialize_composite_stream(authority)
    data = json.loads(resolved.state_path.read_text())
    data["account_digest"] = "0" * 64
    resolved.state_path.write_text(json.dumps(data))
    (tmp_path / "inv.jsonl").write_text('{"legacy":"must-not-read"}\n')
    with pytest.raises(InvestigationOwnershipConflict):
        resolve_investigation_stream(authority)


def test_state_symlink_fails_closed(tmp_path):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    resolved = initialize_composite_stream(authority)
    resolved.state_path.unlink()
    target = tmp_path / "target.json"
    target.write_text("{}")
    resolved.state_path.symlink_to(target)
    with pytest.raises((InvestigationOwnershipConflict, RuntimeError)):
        resolve_investigation_stream(authority)


def test_state_only_tamper_is_rejected(tmp_path):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    resolved = initialize_composite_stream(authority)
    data = json.loads(resolved.state_path.read_text())
    data["state"] = "legacy"
    resolved.state_path.write_text(json.dumps(data))
    with pytest.raises(InvestigationOwnershipConflict, match="state"):
        resolve_investigation_stream(authority)


def test_deleted_composite_state_never_revives_legacy(tmp_path):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    resolved = initialize_composite_stream(authority)
    (tmp_path / "inv.jsonl").write_text('{"legacy":"must-not-read"}\n')
    resolved.state_path.unlink()
    with pytest.raises(InvestigationOwnershipConflict, match="state"):
        resolve_investigation_stream(authority)


def test_deleted_all_composite_markers_never_revives_raw_legacy(tmp_path):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    resolved = initialize_composite_stream(authority)
    bind_legacy_stream_lease(authority)
    mark_legacy_lease_composite(authority)
    (tmp_path / "inv.jsonl").write_text('{"legacy":"must-not-read"}\n')
    resolved.state_path.unlink()
    resolved.allocation_path.unlink()
    with pytest.raises(InvestigationOwnershipConflict):
        resolve_investigation_stream(authority)


def test_owned_legacy_stream_requires_explicit_migration(tmp_path):
    authority = InvestigationAuthority("alice", "legacy", root=tmp_path)
    bind_legacy_stream_lease(authority)
    with pytest.raises(InvestigationOwnershipConflict, match="explicit composite migration"):
        initialize_composite_stream(authority)


def test_interrupted_state_creation_resumes_from_allocation(tmp_path):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    first = initialize_composite_stream(authority)
    first.state_path.unlink()
    resumed = initialize_composite_stream(authority)
    assert resumed.state_path.is_file()
    assert resolve_investigation_stream(authority).state is StreamStorageState.COMPOSITE


def test_publish_crash_after_link_is_recovered(tmp_path):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    resolved = initialize_composite_stream(authority)
    temp = resolved.state_path.with_name(f".{resolved.state_path.name}.crash.tmp")
    temp.hardlink_to(resolved.state_path)
    assert resolved.state_path.stat().st_nlink == 2
    assert resolve_investigation_stream(authority).state is StreamStorageState.COMPOSITE
    assert resolved.state_path.stat().st_nlink == 1
    assert not temp.exists()


def test_publish_crash_before_link_discards_orphan_temp(tmp_path):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    resolved = initialize_composite_stream(authority)
    resolved.state_path.unlink()
    temp = resolved.state_path.with_name(f".{resolved.state_path.name}.crash.tmp")
    temp.write_bytes(b"incomplete")
    assert initialize_composite_stream(authority).state is StreamStorageState.COMPOSITE
    assert not temp.exists()


def test_unrelated_publish_temp_fails_closed(tmp_path):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    resolved = initialize_composite_stream(authority)
    temp = resolved.state_path.with_name(f".{resolved.state_path.name}.hostile.tmp")
    temp.write_bytes(b"unrelated")
    with pytest.raises(RuntimeError, match="remnant is unsafe"):
        resolve_investigation_stream(authority)


def test_empty_allocation_is_not_claimed_or_repaired(tmp_path):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    resolved = initialize_composite_stream(authority)
    resolved.allocation_path.write_bytes(b"")
    with pytest.raises(InvestigationOwnershipConflict, match="allocation"):
        initialize_composite_stream(authority)


def test_hardlinked_state_is_rejected(tmp_path):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    resolved = initialize_composite_stream(authority)
    second_link = tmp_path / "state-hardlink"
    second_link.hardlink_to(resolved.state_path)
    with pytest.raises(RuntimeError, match="unsafe"):
        resolve_investigation_stream(authority)


def test_tenancy_key_rotation_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_INVESTIGATION_TENANCY_KEY_SECRET", "first-secret")
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    initialize_composite_stream(authority)
    monkeypatch.setenv("ANTIEK_INVESTIGATION_TENANCY_KEY_SECRET", "second-secret")
    with pytest.raises(RuntimeError, match="rotation requires migration"):
        InvestigationAuthority("alice", "inv", root=tmp_path)


def test_concurrent_initialization_converges_on_one_exact_marker(tmp_path):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _index: initialize_composite_stream(authority), range(24)))
    assert {result.state_path for result in results} == {results[0].state_path}
    assert resolve_investigation_stream(authority).state is StreamStorageState.COMPOSITE


def test_resolver_cannot_observe_half_published_initialization(tmp_path, monkeypatch):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    allocation_published = threading.Event()
    release_initializer = threading.Event()
    original = stream_codec._atomic_create_at
    calls = 0

    def paused_publish(directory_fd, name, payload):
        nonlocal calls
        result = original(directory_fd, name, payload)
        calls += 1
        if calls == 2:
            allocation_published.set()
            assert release_initializer.wait(timeout=5)
        return result

    monkeypatch.setattr(stream_codec, "_atomic_create_at", paused_publish)
    with ThreadPoolExecutor(max_workers=2) as pool:
        initializing = pool.submit(initialize_composite_stream, authority)
        assert allocation_published.wait(timeout=5)
        resolving = pool.submit(resolve_investigation_stream, authority)
        assert not resolving.done()
        release_initializer.set()
        assert initializing.result(timeout=5).state is StreamStorageState.COMPOSITE
        assert resolving.result(timeout=5).state is StreamStorageState.COMPOSITE


def test_replaced_parent_symlink_is_rejected(tmp_path):
    parent = tmp_path / "parent"
    root = parent / "events"
    authority = InvestigationAuthority("alice", "inv", root=root)
    moved = tmp_path / "moved"
    parent.rename(moved)
    outside = tmp_path / "outside"
    outside.mkdir()
    parent.symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="root is unsafe"):
        initialize_composite_stream(authority)
    assert not (outside / "events" / "streams").exists()


def test_copied_root_replacement_with_valid_markers_is_rejected(tmp_path):
    root = tmp_path / "events"
    authority = InvestigationAuthority("alice", "inv", root=root)
    initialize_composite_stream(authority)
    moved = tmp_path / "original"
    root.rename(moved)
    shutil.copytree(moved, root)
    with pytest.raises(RuntimeError, match="root identity changed"):
        resolve_investigation_stream(authority)


def test_failed_second_directory_open_does_not_leak_fd(tmp_path):
    if not os.path.isdir("/dev/fd"):
        pytest.skip("descriptor census unavailable")
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    state_dir = tmp_path / ".tenancy" / "stream-state"
    state_dir.symlink_to(outside, target_is_directory=True)
    before = len(os.listdir("/dev/fd"))
    with pytest.raises(RuntimeError, match="directory is unsafe"):
        initialize_composite_stream(authority)
    assert len(os.listdir("/dev/fd")) == before


def test_failed_directory_fsync_does_not_leak_child_fd(tmp_path, monkeypatch):
    if not os.path.isdir("/dev/fd"):
        pytest.skip("descriptor census unavailable")
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    before = len(os.listdir("/dev/fd"))

    def fail_fsync(_fd):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(stream_codec.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="injected fsync failure"):
        initialize_composite_stream(authority)
    assert len(os.listdir("/dev/fd")) == before
