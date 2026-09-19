"""ANT-AHT account authority and private filesystem boundary."""

from __future__ import annotations

import json
import os
import stat
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from substrate.research_artifact.authority import ArtifactAuthority
from substrate.research_artifact.storage import FilesystemArtifactStore, UnsafeArtifactState


@pytest.fixture(autouse=True)
def isolated_authority_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path))


@pytest.mark.parametrize(
    "account_id,investigation_id",
    [
        ("alice", "same"),
        ("alice/../bob", "../../same"),
        ("Ａ", "A"),
        ("e\u0301", "é"),
        ("back\\slash", ".hidden"),
        ("line\nbreak", "dot..dot"),
    ],
)
def test_opaque_keys_never_expose_raw_ids(tmp_path, account_id, investigation_id):
    authority = ArtifactAuthority(account_id, investigation_id)
    path = authority.artifact_path(tmp_path)
    assert account_id not in str(path)
    assert investigation_id not in str(path)
    assert path.is_relative_to(tmp_path / "accounts")


def test_same_investigation_is_disjoint_and_sidecars_bind_owner(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    alice = ArtifactAuthority("alice", "same-id")
    bob = ArtifactAuthority("bob", "same-id")
    alice_path = store.write(alice, "<p>Alice private</p>")
    bob_path = store.write(bob, "<p>Bob private</p>")

    assert alice_path != bob_path
    assert store.read(alice) == "<p>Alice private</p>"
    assert store.read(bob) == "<p>Bob private</p>"
    assert stat.S_IMODE(alice_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(alice_path.parent.stat().st_mode) == 0o700
    sidecar = json.loads(alice.sidecar_path(tmp_path).read_text())
    assert sidecar["account_id_digest"] == alice.account_digest
    assert "alice" not in alice.sidecar_path(tmp_path).read_text()


def test_tamper_and_nonregular_files_fail_closed(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    authority = ArtifactAuthority("alice", "paper")
    path = store.write(authority, "original")
    path.write_text("tampered")
    with pytest.raises(UnsafeArtifactState, match="mismatch"):
        store.read(authority)

    path.unlink()
    os.symlink(tmp_path / "foreign", path)
    with pytest.raises(UnsafeArtifactState, match="regular file"):
        store.write(authority, "replacement")


def test_invalid_identity_rejected():
    for value in ("", "   ", " alice", "alice ", "bad\x00id", "x" * 513):
        with pytest.raises(ValueError):
            ArtifactAuthority(value, "inv")


def test_interrupted_pair_publish_recovers_last_valid_bytes(tmp_path, monkeypatch):
    from substrate.research_artifact import storage as storage_module

    store = FilesystemArtifactStore(tmp_path)
    authority = ArtifactAuthority("alice", "paper")
    store.write(authority, "last committed")
    original_atomic_write = storage_module._atomic_write

    def crash_after_artifact(root, path, data):
        original_atomic_write(root, path, data)
        if path == authority.artifact_path(tmp_path):
            raise RuntimeError("injected publish crash")

    monkeypatch.setattr(storage_module, "_atomic_write", crash_after_artifact)
    with pytest.raises(RuntimeError, match="injected publish crash"):
        store.write(authority, "uncommitted replacement")
    monkeypatch.setattr(storage_module, "_atomic_write", original_atomic_write)
    assert store.read(authority) == "last committed"


def test_first_write_crash_after_html_recovers_from_marker(tmp_path, monkeypatch):
    from substrate.research_artifact import storage as storage_module

    store = FilesystemArtifactStore(tmp_path)
    authority = ArtifactAuthority("alice", "first-write")
    original_atomic_write = storage_module._atomic_write

    def crash_after_artifact(root, path, data):
        original_atomic_write(root, path, data)
        if path == authority.artifact_path(tmp_path):
            raise RuntimeError("injected first publish crash")

    monkeypatch.setattr(storage_module, "_atomic_write", crash_after_artifact)
    with pytest.raises(RuntimeError, match="first publish"):
        store.write(authority, "first committed bytes")
    monkeypatch.setattr(storage_module, "_atomic_write", original_atomic_write)
    assert store.read(authority) == "first committed bytes"


def test_concurrent_writers_leave_one_complete_valid_pair(tmp_path):
    authority = ArtifactAuthority("alice", "contended")
    FilesystemArtifactStore(tmp_path).write(authority, "seed")

    def publish(value: str) -> None:
        FilesystemArtifactStore(tmp_path).write(authority, value)

    values = [f"writer-{index}" for index in range(20)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(publish, values))
    assert FilesystemArtifactStore(tmp_path).read(authority) in values
    assert not authority.artifact_path(tmp_path).with_suffix(".write-in-progress").exists()


def test_same_store_does_not_treat_another_thread_as_reentrant(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    authority = ArtifactAuthority("alice", "thread-ownership")
    first_holds_lock = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def first() -> None:
        with store.mutation_lock(authority):
            first_holds_lock.set()
            assert release_first.wait(timeout=2)

    def second() -> None:
        assert first_holds_lock.wait(timeout=2)
        with store.mutation_lock(authority):
            second_entered.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(first)
        second_future = pool.submit(second)
        assert first_holds_lock.wait(timeout=2)
        assert not second_entered.wait(timeout=0.1)
        release_first.set()
        first_future.result(timeout=2)
        second_future.result(timeout=2)
    assert second_entered.is_set()


def test_write_refuses_incomplete_existing_pair_without_overwriting_bytes(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    authority = ArtifactAuthority("alice", "damaged")
    path = store.write(authority, "only surviving bytes")
    authority.sidecar_path(tmp_path).unlink()
    before = path.read_bytes()
    with pytest.raises(UnsafeArtifactState, match="pair is incomplete"):
        store.write(authority, "replacement")
    assert path.read_bytes() == before


def test_event_stream_keys_are_owner_bound_and_opaque():
    alice = ArtifactAuthority("alice@example.test", "shared-investigation")
    bob = ArtifactAuthority("bob@example.test", "shared-investigation")
    assert alice.event_stream_id != bob.event_stream_id
    assert alice.account_id not in alice.event_stream_id
    assert alice.investigation_id not in alice.event_stream_id


def test_install_key_rotation_fails_closed_until_authenticated_migration(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("ANTIEK_ARTIFACT_KEY_SECRET", "a" * 32)
    first = ArtifactAuthority("alice", "paper")
    frozen_path = first.artifact_path()
    monkeypatch.setenv("ANTIEK_ARTIFACT_KEY_SECRET", "b" * 32)
    with pytest.raises(RuntimeError, match="authenticated migration"):
        ArtifactAuthority("alice", "paper")
    assert first.artifact_path() == frozen_path
