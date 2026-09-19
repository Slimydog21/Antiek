from __future__ import annotations

import json
import os

import pytest

from substrate.investigation_tenancy import (
    InvestigationAuthority,
    InvestigationOwnershipConflict,
    assert_legacy_stream_owner,
    bind_child_stream_lease,
    bind_legacy_stream_lease,
)


def test_authority_is_owner_bound_opaque_and_deterministic(tmp_path):
    alice = InvestigationAuthority("alice", "same", root=tmp_path)
    alice_again = InvestigationAuthority("alice", "same", root=tmp_path)
    bob = InvestigationAuthority("bob", "same", root=tmp_path)
    assert alice.stream_key == alice_again.stream_key
    assert alice.stream_key != bob.stream_key
    assert "alice" not in alice.stream_key
    assert "same" not in alice.stream_key


@pytest.mark.parametrize("investigation_id", ["../escape", "dir/stream", "dir\\stream"])
def test_legacy_bridge_rejects_path_separators(tmp_path, investigation_id):
    with pytest.raises(ValueError, match="investigation_id is invalid"):
        InvestigationAuthority("alice", investigation_id, root=tmp_path)


def test_global_stream_lease_is_idempotent_but_rejects_second_owner(tmp_path):
    alice = InvestigationAuthority("alice", "same", root=tmp_path)
    bob = InvestigationAuthority("bob", "same", root=tmp_path)
    first = bind_legacy_stream_lease(alice)
    assert bind_legacy_stream_lease(alice) == first
    assert_legacy_stream_owner(alice)
    with pytest.raises(InvestigationOwnershipConflict, match="another account"):
        bind_legacy_stream_lease(bob)
    with pytest.raises(InvestigationOwnershipConflict, match="another account"):
        assert_legacy_stream_owner(bob)


def test_background_child_inherits_opaque_parent_owner(tmp_path):
    parent = InvestigationAuthority("alice", "parent", root=tmp_path)
    bob_child = InvestigationAuthority("bob", "child", root=tmp_path)
    bind_legacy_stream_lease(parent)
    child_path = bind_child_stream_lease(
        "parent",
        "child",
        root=tmp_path,
        expected_account_digest=parent.account_digest,
    )
    child = json.loads(child_path.read_text(encoding="utf-8"))
    assert child["account_digest"] == parent.account_digest
    assert "alice" not in child_path.read_text(encoding="utf-8")
    with pytest.raises(InvestigationOwnershipConflict, match="another account"):
        bind_legacy_stream_lease(bob_child)


def test_background_child_requires_valid_bound_parent(tmp_path):
    with pytest.raises(InvestigationOwnershipConflict, match="parent"):
        bind_child_stream_lease(
            "missing",
            "child",
            root=tmp_path,
            expected_account_digest=InvestigationAuthority(
                "alice", "missing", root=tmp_path
            ).account_digest,
        )


def test_registry_receipt_is_private_and_redacted(tmp_path):
    authority = InvestigationAuthority("private@example.test", "secret-question", root=tmp_path)
    path = bind_legacy_stream_lease(authority, provenance="operator_migration")
    text = path.read_text(encoding="utf-8")
    assert "private@example.test" not in text
    assert "secret-question" not in text
    assert json.loads(text)["provenance"] == "operator_migration"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_symlinked_registry_lock_fails_closed(tmp_path):
    tenancy = tmp_path / ".tenancy"
    tenancy.mkdir()
    target = tmp_path / "foreign"
    target.write_text("unchanged", encoding="utf-8")
    os.symlink(target, tenancy / "registry.lock")
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    with pytest.raises(RuntimeError, match="lock is unsafe"):
        bind_legacy_stream_lease(authority)
    assert target.read_text(encoding="utf-8") == "unchanged"


def test_key_change_fails_closed_instead_of_orphaning_namespace(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_INVESTIGATION_TENANCY_KEY_SECRET", "a" * 32)
    first = InvestigationAuthority("alice", "inv", root=tmp_path)
    monkeypatch.setenv("ANTIEK_INVESTIGATION_TENANCY_KEY_SECRET", "b" * 32)
    with pytest.raises(RuntimeError, match="rotation requires migration"):
        InvestigationAuthority("alice", "inv", root=tmp_path)
    assert first.account_id == "alice"


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", 99),
        ("account_digest", "wrong"),
        ("investigation_digest", "wrong"),
        ("future_stream_key", "wrong"),
    ],
)
def test_assert_rejects_tampered_identity_fields(tmp_path, field, value):
    authority = InvestigationAuthority("alice", "inv", root=tmp_path)
    path = bind_legacy_stream_lease(authority)
    record = json.loads(path.read_text(encoding="utf-8"))
    record[field] = value
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(InvestigationOwnershipConflict, match="invalid binding"):
        assert_legacy_stream_owner(authority)
