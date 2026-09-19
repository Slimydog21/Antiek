from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.engagement_spine.authority import EngagementAuthority
from substrate.engagement_spine.migration import migrate_legacy_engagement
from substrate.engagement_spine.store import FileEngagementStore, authorized_store
from substrate.floating_session.store import FileSessionStore, authorized_session_store


def _seed_legacy(engagement_root: Path, session_root: Path) -> None:
    engagement = FileEngagementStore(engagement_root)
    engagement.put_spawn(
        {
            "spawn_id": "spn_legacy",
            "parent_asset_id": "book",
            "status": "complete",
            "output_text": "legacy evidence",
        }
    )
    engagement.put_twin(
        {
            "note_id": "twin_legacy",
            "asset_id": "book",
            "kind": "insight",
            "text": "legacy insight",
        }
    )
    engagement.put_document(
        "draft",
        {"document_id": "draft", "parent_asset_id": "book", "body": "legacy draft"},
    )
    FileSessionStore(session_root).put_session(
        {"session_id": "ses_legacy", "parent_asset_id": "book", "status": "open"}
    )


def _files(root: Path) -> set[str]:
    return {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}


def test_dry_run_is_read_only_and_apply_requires_explicit_account(tmp_path: Path) -> None:
    engagement_root = tmp_path / "engagement"
    session_root = tmp_path / "sessions"
    _seed_legacy(engagement_root, session_root)
    before = (_files(engagement_root), _files(session_root))

    report = migrate_legacy_engagement(
        engagement_root=engagement_root,
        session_root=session_root,
        account_id="alice",
        mode="dry-run",
    )
    assert report["inventory"]["total"] == 4
    assert (_files(engagement_root), _files(session_root)) == before


def test_apply_scopes_rows_and_rollback_removes_only_scoped_copies(tmp_path: Path) -> None:
    engagement_root = tmp_path / "engagement"
    session_root = tmp_path / "sessions"
    _seed_legacy(engagement_root, session_root)
    legacy_before = (_files(engagement_root), _files(session_root))

    applied = migrate_legacy_engagement(
        engagement_root=engagement_root,
        session_root=session_root,
        account_id="alice",
        mode="apply",
        migration_id="test-assignment",
    )
    assert applied["applied"] == {
        "spawns": 1,
        "twins": 1,
        "documents": 1,
        "sessions": 1,
    }
    alice_authority = EngagementAuthority("alice")
    bob_authority = EngagementAuthority("bob")
    alice = authorized_store(FileEngagementStore(engagement_root), alice_authority)
    bob = authorized_store(FileEngagementStore(engagement_root), bob_authority)
    assert alice.get_spawn("spn_legacy")["output_text"] == "legacy evidence"
    assert bob.get_spawn("spn_legacy") is None
    assert alice.list_twins("book")[0]["text"] == "legacy insight"
    assert alice.get_document("draft")["body"] == "legacy draft"
    alice_sessions = authorized_session_store(FileSessionStore(session_root), alice_authority)
    assert alice_sessions.get_session("ses_legacy")["status"] == "open"

    rolled_back = migrate_legacy_engagement(
        engagement_root=engagement_root,
        session_root=session_root,
        account_id="alice",
        mode="rollback",
        migration_id="test-assignment",
    )
    assert rolled_back["state"] == "rolled_back"
    assert alice.get_spawn("spn_legacy") is None
    after = (_files(engagement_root), _files(session_root))
    assert legacy_before[1] == after[1]
    assert legacy_before[0].issubset(after[0])
    assert "migrations/test-assignment.json" in after[0]


def test_malformed_and_symlink_rows_are_quarantined(tmp_path: Path) -> None:
    engagement_root = tmp_path / "engagement"
    (engagement_root / "spawns").mkdir(parents=True)
    (engagement_root / "spawns" / "broken.json").write_text("{", encoding="utf-8")
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"spawn_id": "outside"}), encoding="utf-8")
    (engagement_root / "spawns" / "linked.json").symlink_to(outside)

    report = migrate_legacy_engagement(
        engagement_root=engagement_root,
        account_id="alice",
        mode="dry-run",
    )
    reasons = [row["reason"] for row in report["inventory"]["quarantined"]]
    assert any("JSONDecodeError" in reason for reason in reasons)
    assert any("symlink" in reason for reason in reasons)


def test_migration_id_traversal_and_operator_assignment_are_rejected(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="migration_id"):
        migrate_legacy_engagement(
            engagement_root=tmp_path / "engagement",
            account_id="alice",
            mode="dry-run",
            migration_id="../../escape",
        )
    with pytest.raises(ValueError, match="named authenticated account"):
        migrate_legacy_engagement(
            engagement_root=tmp_path / "engagement",
            account_id="__operator__",
            mode="dry-run",
        )


def test_interrupted_apply_leaves_a_rollback_manifest(tmp_path: Path, monkeypatch) -> None:
    engagement_root = tmp_path / "engagement"
    session_root = tmp_path / "sessions"
    _seed_legacy(engagement_root, session_root)
    original = FileEngagementStore.put_twin

    def fail_twin(self, note):
        if note.get("engagement_authority_version"):
            raise RuntimeError("simulated interruption")
        return original(self, note)

    monkeypatch.setattr(FileEngagementStore, "put_twin", fail_twin)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        migrate_legacy_engagement(
            engagement_root=engagement_root,
            session_root=session_root,
            account_id="alice",
            mode="apply",
            migration_id="interrupted",
        )
    manifest = json.loads(
        (engagement_root / "migrations" / "interrupted.json").read_text()
    )
    assert manifest["state"] == "applying"
    monkeypatch.setattr(FileEngagementStore, "put_twin", original)
    rolled_back = migrate_legacy_engagement(
        engagement_root=engagement_root,
        session_root=session_root,
        account_id="alice",
        mode="rollback",
        migration_id="interrupted",
    )
    assert rolled_back["state"] == "rolled_back"
    alice = authorized_store(
        FileEngagementStore(engagement_root), EngagementAuthority("alice")
    )
    assert alice.get_spawn("spn_legacy") is None
