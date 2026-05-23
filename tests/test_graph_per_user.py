"""Tests for substrate.graph_per_user — per-user DuckDB lifecycle."""

from __future__ import annotations

import os
import tempfile

import pytest

from substrate.ducklake import DuckLakeCatalog, HashPrefixSharding, InMemoryCatalogBackend, NoSharding
from substrate.graph_per_user import (
    InMemoryKeyProvider,
    KMSStubKeyProvider,
    KeyMaterial,
    KeyProviderError,
    PerUserStorageEvent,
    close_user_graph,
    create_user_graph,
    delete_user_graph,
    open_user_graph,
)
from substrate.graph_per_user.lifecycle import PerUserStorageEventKind


# ── KeyProvider ─────────────────────────────────────────────────


def test_inmemory_generates_unique_keys():
    p = InMemoryKeyProvider()
    k1 = p.generate_data_key(graph_id="u-1")
    k2 = p.generate_data_key(graph_id="u-2")
    assert k1.graph_id == "u-1"
    assert k2.graph_id == "u-2"
    assert k1.wrapped_data_key != k2.wrapped_data_key
    assert k1.algorithm == "AES_256_GCM"


def test_inmemory_refuses_duplicate_generate():
    p = InMemoryKeyProvider()
    p.generate_data_key(graph_id="u-1")
    with pytest.raises(KeyProviderError, match="already has a key"):
        p.generate_data_key(graph_id="u-1")


def test_inmemory_rotate_replaces_wrapped_key():
    p = InMemoryKeyProvider()
    orig = p.generate_data_key(graph_id="u-1")
    rotated = p.rotate(graph_id="u-1")
    assert rotated.key_id == orig.key_id
    assert rotated.wrapped_data_key != orig.wrapped_data_key


def test_inmemory_rotate_unknown_raises():
    p = InMemoryKeyProvider()
    with pytest.raises(KeyProviderError, match="cannot rotate"):
        p.rotate(graph_id="u-missing")


def test_inmemory_revoke_removes_key():
    p = InMemoryKeyProvider()
    p.generate_data_key(graph_id="u-1")
    p.revoke(graph_id="u-1")
    assert p.lookup(graph_id="u-1") is None


def test_inmemory_revoke_idempotent():
    p = InMemoryKeyProvider()
    p.revoke(graph_id="u-never-existed")  # no exception


def test_kms_stub_delegates_to_client():
    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def generate_data_key(self, *, KeyId, KeySpec):  # noqa: N803
            self.calls.append(("gen", KeyId, KeySpec))
            return {"CiphertextBlob": b"wrapped-" + KeyId.encode()}

        def disable_key(self, *, KeyId):  # noqa: N803
            self.calls.append(("disable", KeyId))

    client = FakeClient()
    p = KMSStubKeyProvider(client=client)
    material = p.generate_data_key(graph_id="u-1")
    assert material.key_id == "alias/antiek-graph-u-1"
    assert material.wrapped_data_key.startswith(b"wrapped-")
    p.revoke(graph_id="u-1")
    assert client.calls[-1][0] == "disable"


def test_kms_stub_propagates_client_failure():
    class BadClient:
        def generate_data_key(self, **kwargs):
            raise RuntimeError("KMS unavailable")

    p = KMSStubKeyProvider(client=BadClient())
    with pytest.raises(KeyProviderError, match="KMS generate_data_key failed"):
        p.generate_data_key(graph_id="u-1")


# ── Lifecycle ───────────────────────────────────────────────────


def _setup(tmp_path):
    catalog = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    key_provider = InMemoryKeyProvider()
    return catalog, key_provider, str(tmp_path)


def test_create_user_graph_registers_catalog_entry(tmp_path):
    catalog, kp, root = _setup(tmp_path)
    storage, event = create_user_graph(
        user_id="u-1", catalog=catalog, key_provider=kp,
        strategy=NoSharding(), root_dir=root,
    )
    assert storage.user_id == "u-1"
    assert event.kind == PerUserStorageEventKind.CREATED
    assert catalog.lookup("u-1") is not None
    assert catalog.lookup("u-1").db_path == storage.db_path
    assert os.path.isdir(os.path.dirname(storage.db_path))


def test_create_user_graph_idempotent_refusal(tmp_path):
    catalog, kp, root = _setup(tmp_path)
    create_user_graph(
        user_id="u-1", catalog=catalog, key_provider=kp,
        strategy=NoSharding(), root_dir=root,
    )
    with pytest.raises(KeyProviderError, match="already has a catalog entry"):
        create_user_graph(
            user_id="u-1", catalog=catalog, key_provider=kp,
            strategy=NoSharding(), root_dir=root,
        )


def test_create_user_graph_with_sharded_strategy(tmp_path):
    catalog, kp, root = _setup(tmp_path)
    storage, _ = create_user_graph(
        user_id="u-shardtest", catalog=catalog, key_provider=kp,
        strategy=HashPrefixSharding(hex_chars=1), root_dir=root,
    )
    # Path should include the shard hex dir.
    parts = storage.db_path.split(os.sep)
    assert parts[-1] == "u-shardtest.duckdb"
    # Hex-char shard between root and file.
    assert len(parts[-2]) == 1


def test_open_user_graph_returns_handle_when_exists(tmp_path):
    catalog, kp, root = _setup(tmp_path)
    created, _ = create_user_graph(
        user_id="u-1", catalog=catalog, key_provider=kp,
        strategy=NoSharding(), root_dir=root,
    )
    result = open_user_graph(user_id="u-1", catalog=catalog, key_provider=kp)
    assert result is not None
    storage, event = result
    assert storage.db_path == created.db_path
    assert event.kind == PerUserStorageEventKind.OPENED


def test_open_user_graph_returns_none_when_missing(tmp_path):
    catalog, kp, root = _setup(tmp_path)
    result = open_user_graph(user_id="u-missing", catalog=catalog, key_provider=kp)
    assert result is None


def test_close_user_graph_emits_event(tmp_path):
    catalog, kp, root = _setup(tmp_path)
    create_user_graph(
        user_id="u-1", catalog=catalog, key_provider=kp,
        strategy=NoSharding(), root_dir=root,
    )
    event = close_user_graph(user_id="u-1", catalog=catalog)
    assert event.kind == PerUserStorageEventKind.CLOSED
    assert event.user_id == "u-1"


def test_delete_user_graph_revokes_key_and_deregisters(tmp_path):
    catalog, kp, root = _setup(tmp_path)
    create_user_graph(
        user_id="u-1", catalog=catalog, key_provider=kp,
        strategy=NoSharding(), root_dir=root,
    )
    assert kp.lookup(graph_id="u-1") is not None
    assert catalog.lookup("u-1") is not None
    event = delete_user_graph(user_id="u-1", catalog=catalog, key_provider=kp)
    assert event.kind == PerUserStorageEventKind.DELETE_SCHEDULED
    assert kp.lookup(graph_id="u-1") is None
    assert catalog.lookup("u-1") is None


def test_delete_user_graph_idempotent_when_missing(tmp_path):
    catalog, kp, root = _setup(tmp_path)
    event = delete_user_graph(user_id="u-never", catalog=catalog, key_provider=kp)
    assert event.kind == PerUserStorageEventKind.DELETE_SCHEDULED


def test_invalid_user_id_rejected(tmp_path):
    catalog, kp, root = _setup(tmp_path)
    with pytest.raises(ValueError, match="invalid user_id"):
        create_user_graph(
            user_id="", catalog=catalog, key_provider=kp,
            strategy=NoSharding(), root_dir=root,
        )
