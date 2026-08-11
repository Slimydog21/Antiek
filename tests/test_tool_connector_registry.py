from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from runtime.byok.store import list_credentials
from runtime.connectors.registry import (
    ToolConnectionIntegrityError,
    ToolConnectionUnavailable,
    connect_tool,
    disconnect_tool,
    list_tool_connections,
    resolve_tool_connection,
)

KEY_BYTES = b"k" * 32
YOUTUBE_KEY_A = "AIza" + "a" * 24
YOUTUBE_KEY_B = "AIza" + "b" * 24


@pytest.fixture
def paths(tmp_path, monkeypatch):
    registry = tmp_path / "tool_connections.json"
    artifact = tmp_path / "credentials.enc"
    monkeypatch.setenv("ANTIEK_TOOL_CONNECTIONS_PATH", str(registry))
    return str(registry), str(artifact)


def _rows(owner: str, artifact: str):
    return {row.vendor: row for row in list_tool_connections(owner, artifact_path=artifact)}


def test_connect_list_resolve_replace_and_disconnect_are_owner_bound(paths) -> None:
    registry, artifact = paths
    created = connect_tool(
        "user-a",
        "youtube",
        YOUTUBE_KEY_A,
        artifact_path=artifact,
        key_bytes=KEY_BYTES,
    )
    assert created.status == "configured_unverified"
    assert created.credential_present is True
    assert not hasattr(created, "cred_id")

    metadata = list_credentials(artifact_path=artifact)
    assert len(metadata) == 1
    first_cred_id = metadata[0].cred_id
    assert metadata[0].owner_user_id == "user-a"
    assert metadata[0].pipeline_kind == "connector_youtube"
    assert metadata[0].binding_version == 3

    connector = resolve_tool_connection(
        "user-a",
        "youtube",
        artifact_path=artifact,
        key_bytes=KEY_BYTES,
    )
    assert connector.cred_id == first_cred_id
    assert YOUTUBE_KEY_A not in repr(connector)

    connect_tool(
        "user-a",
        "youtube",
        YOUTUBE_KEY_B,
        artifact_path=artifact,
        key_bytes=KEY_BYTES,
    )
    replaced = list_credentials(artifact_path=artifact)
    assert len(replaced) == 1
    assert replaced[0].cred_id != first_cred_id
    assert os.stat(registry).st_mode & 0o777 == 0o600

    assert disconnect_tool("user-a", "youtube", artifact_path=artifact) is True
    assert _rows("user-a", artifact)["youtube"].status == "unconfigured"
    assert list_credentials(artifact_path=artifact) == []
    with pytest.raises(ToolConnectionUnavailable):
        resolve_tool_connection("user-a", "youtube", artifact_path=artifact)


def test_same_vendor_is_isolated_between_owners(paths) -> None:
    _, artifact = paths
    connect_tool(
        "user-a", "youtube", YOUTUBE_KEY_A,
        artifact_path=artifact, key_bytes=KEY_BYTES,
    )
    connect_tool(
        "user-b", "youtube", YOUTUBE_KEY_B,
        artifact_path=artifact, key_bytes=KEY_BYTES,
    )
    assert _rows("user-a", artifact)["youtube"].credential_present is True
    assert _rows("user-b", artifact)["youtube"].credential_present is True
    assert disconnect_tool("user-b", "youtube", artifact_path=artifact) is True
    assert _rows("user-a", artifact)["youtube"].credential_present is True
    assert _rows("user-b", artifact)["youtube"].credential_present is False


def test_list_and_keyed_resolve_do_not_decrypt(paths, monkeypatch) -> None:
    _, artifact = paths
    connect_tool(
        "user-a", "youtube", YOUTUBE_KEY_A,
        artifact_path=artifact, key_bytes=KEY_BYTES,
    )
    monkeypatch.setattr(
        "runtime.byok.store.load_credential",
        lambda *args, **kwargs: pytest.fail("listing/keyed construction decrypted a key"),
    )
    assert _rows("user-a", artifact)["youtube"].credential_present is True
    connector = resolve_tool_connection(
        "user-a", "youtube", artifact_path=artifact, key_bytes=KEY_BYTES,
    )
    assert connector.cred_id is not None


def test_edgar_contact_is_encrypted_and_resolved_without_public_echo(paths) -> None:
    _, artifact = paths
    contact = "researcher@example.test"
    snapshot = connect_tool(
        "user-a", "edgar", contact,
        artifact_path=artifact, key_bytes=KEY_BYTES,
    )
    assert snapshot.credential_kind == "contact"
    assert contact not in repr(snapshot)
    connector = resolve_tool_connection(
        "user-a", "edgar", artifact_path=artifact, key_bytes=KEY_BYTES,
    )
    assert contact not in repr(connector)


def test_tampered_fingerprint_degrades_and_refuses_resolution(paths) -> None:
    registry, artifact = paths
    connect_tool(
        "user-a", "youtube", YOUTUBE_KEY_A,
        artifact_path=artifact, key_bytes=KEY_BYTES,
    )
    with open(registry, encoding="utf-8") as handle:
        data = json.load(handle)
    record = next(value for key, value in data.items() if not key.startswith("__"))
    record["credential_fingerprint"] = "0" * 64
    with open(registry, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.chmod(registry, 0o600)

    row = _rows("user-a", artifact)["youtube"]
    assert row.status == "degraded"
    assert row.credential_present is False
    with pytest.raises(ToolConnectionUnavailable):
        resolve_tool_connection(
            "user-a", "youtube", artifact_path=artifact, key_bytes=KEY_BYTES,
        )


def test_corrupt_or_nonregular_registry_fails_closed(paths) -> None:
    registry, artifact = paths
    with open(registry, "w", encoding="utf-8") as handle:
        handle.write("not-json")
    os.chmod(registry, stat.S_IRUSR | stat.S_IWUSR)
    with pytest.raises(ToolConnectionIntegrityError):
        list_tool_connections("user-a", artifact_path=artifact)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("record_version", True),
        ("owner_user_id", "x" * 257),
        ("credential_fingerprint", "nope"),
        ("updated_at", "yesterday"),
    ],
)
def test_registry_records_are_parsed_strictly(paths, field, bad) -> None:
    registry, artifact = paths
    connect_tool("user-a", "youtube", YOUTUBE_KEY_A, artifact_path=artifact, key_bytes=KEY_BYTES)
    data = json.loads(Path(registry).read_text(encoding="utf-8"))
    record = next(value for key, value in data.items() if not key.startswith("__"))
    record[field] = bad
    with open(registry, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.chmod(registry, 0o600)
    with pytest.raises(ToolConnectionIntegrityError):
        list_tool_connections("user-a", artifact_path=artifact)


def test_registry_and_lock_symlinks_fail_closed(paths, tmp_path) -> None:
    registry, artifact = paths
    target = tmp_path / "target"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, 0o600)
    os.symlink(target, registry)
    with pytest.raises((OSError, ToolConnectionIntegrityError)):
        list_tool_connections("user-a", artifact_path=artifact)
    os.unlink(registry)
    os.unlink(f"{registry}.lock")
    os.symlink(target, f"{registry}.lock")
    with pytest.raises((OSError, ToolConnectionIntegrityError)):
        list_tool_connections("user-a", artifact_path=artifact)


def test_failed_old_delete_is_durably_retried(paths, monkeypatch) -> None:
    registry, artifact = paths
    connect_tool("user-a", "youtube", YOUTUBE_KEY_A, artifact_path=artifact, key_bytes=KEY_BYTES)
    real_delete = __import__("runtime.connectors.registry", fromlist=["delete_credential"]).delete_credential
    calls = 0
    def flaky(cred_id, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected delete failure")
        return real_delete(cred_id, **kwargs)
    monkeypatch.setattr("runtime.connectors.registry.delete_credential", flaky)
    with pytest.raises(OSError):
        connect_tool("user-a", "youtube", YOUTUBE_KEY_B, artifact_path=artifact, key_bytes=KEY_BYTES)
    data = json.loads(Path(registry).read_text(encoding="utf-8"))
    assert data["__pending_deletions__"]
    rows = _rows("user-a", artifact)
    assert rows["youtube"].credential_present is True
    assert json.loads(Path(registry).read_text(encoding="utf-8"))["__pending_deletions__"] == []
    assert len(list_credentials(artifact_path=artifact)) == 1


def test_initial_connect_does_not_depend_on_fallible_metadata_listing(paths, monkeypatch) -> None:
    _, artifact = paths
    monkeypatch.setattr(
        "runtime.connectors.registry.list_credentials",
        lambda **kwargs: pytest.fail("post-store metadata listing must not be required"),
    )
    created = connect_tool(
        "user-a", "youtube", YOUTUBE_KEY_A, artifact_path=artifact, key_bytes=KEY_BYTES
    )
    assert created.credential_present is True


def test_pending_journal_refuses_active_and_cross_owner_authority(paths) -> None:
    registry, artifact = paths
    connect_tool("user-a", "youtube", YOUTUBE_KEY_A, artifact_path=artifact, key_bytes=KEY_BYTES)
    data = json.loads(Path(registry).read_text(encoding="utf-8"))
    record = next(value for key, value in data.items() if not key.startswith("__"))
    pending = {
        "cred_id": record["cred_id"],
        "owner_user_id": record["owner_user_id"],
        "vendor": record["vendor"],
        "pipeline_kind": "connector_youtube",
        "account_handle": record["account_handle"],
        "credential_fingerprint": record["credential_fingerprint"],
    }
    data["__pending_deletions__"] = [pending]
    Path(registry).write_text(json.dumps(data), encoding="utf-8")
    os.chmod(registry, 0o600)
    with pytest.raises(ToolConnectionIntegrityError, match="active"):
        list_tool_connections("user-a", artifact_path=artifact)
    assert len(list_credentials(artifact_path=artifact)) == 1

    del data[next(key for key in data if not key.startswith("__"))]
    pending["owner_user_id"] = "user-b"
    Path(registry).write_text(json.dumps(data), encoding="utf-8")
    os.chmod(registry, 0o600)
    with pytest.raises(ToolConnectionIntegrityError, match="authority changed"):
        list_tool_connections("user-a", artifact_path=artifact)
    assert len(list_credentials(artifact_path=artifact)) == 1


def test_unknown_pending_id_is_cleared_without_delete(paths, monkeypatch) -> None:
    registry, artifact = paths
    pending = {
        "cred_id": "cred-x-0123456789abcdef",
        "owner_user_id": "user-a",
        "vendor": "youtube",
        "pipeline_kind": "connector_youtube",
        "account_handle": "tool-owner-youtube",
        "credential_fingerprint": "a" * 64,
    }
    Path(registry).write_text(
        json.dumps({"__pending_deletions__": [pending]}), encoding="utf-8"
    )
    os.chmod(registry, 0o600)
    monkeypatch.setattr(
        "runtime.connectors.registry.delete_credential",
        lambda *args, **kwargs: pytest.fail("unknown credential must never be deleted"),
    )
    list_tool_connections("user-a", artifact_path=artifact)
    assert json.loads(Path(registry).read_text(encoding="utf-8"))["__pending_deletions__"] == []


@pytest.mark.parametrize(
    ("vendor", "value"),
    [("youtube", "wrong-prefix-value-long-enough"), ("polygon", "short"), ("edgar", "not-email")],
)
def test_shape_errors_are_value_free(paths, vendor: str, value: str) -> None:
    _, artifact = paths
    with pytest.raises(ValueError) as exc:
        connect_tool(
            "user-a", vendor, value,
            artifact_path=artifact, key_bytes=KEY_BYTES,
        )
    assert value not in str(exc.value)
