"""ANT-AHT restartable, operator-only legacy migration."""

from __future__ import annotations

import json
import os

import pytest

from substrate.research_artifact.authority import ArtifactAuthority, operator_authority
from substrate.research_artifact.migration import (
    CorruptMigrationJournal,
    MigrationRefused,
    _append_journal,
    legacy_inventory,
    legacy_inventory_report,
    migrate_legacy_artifact,
    shadow_resolution,
)
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody
from substrate.research_artifact.storage import FilesystemArtifactStore


@pytest.fixture(autouse=True)
def isolated_authority_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path))


def _legacy(root, investigation_id="legacy-inv"):
    path = root / f"{investigation_id}.html"
    path.write_text(
        render_html(
            ResearchArtifactBody(
                investigation_id=investigation_id,
                problem_question="Private historical question",
                agent_notes=["Private historical note"],
            )
        ),
        encoding="utf-8",
    )
    return path


def test_inventory_accounts_without_logging_content(tmp_path):
    _legacy(tmp_path)
    (tmp_path / "bad.html").write_text("not an artifact", encoding="utf-8")
    (tmp_path / "compose-a.html").write_text("index", encoding="utf-8")
    os.symlink(tmp_path / "missing", tmp_path / "link.html")
    (tmp_path / "orphan.meta.json").write_text("{}", encoding="utf-8")

    inventory = legacy_inventory(tmp_path)
    assert inventory.total == 4
    assert inventory.valid == 1
    assert inventory.corrupt == 1
    assert inventory.composed == 1
    assert inventory.excluded == 1
    assert inventory.symlinked == 1
    assert inventory.v1 == 1
    assert inventory.v2 == 0
    assert inventory.orphan_sidecar == 1
    assert "Private historical" not in repr(inventory)
    report = legacy_inventory_report(tmp_path)
    assert len(report.entries) == 5
    assert {entry.disposition for entry in report.entries} == {
        "migrate_v1",
        "quarantine_corrupt",
        "excluded_composed",
        "quarantine_symlink",
        "quarantine_orphan_sidecar",
    }
    assert "Private historical" not in repr(report)


def test_apply_requires_exact_operator_and_explicit_approval(tmp_path):
    source = _legacy(tmp_path)
    with pytest.raises(MigrationRefused, match="canonical operator"):
        migrate_legacy_artifact(
            source, account_id="alice", approved=True, root=tmp_path
        )
    with pytest.raises(MigrationRefused, match="explicit operator approval"):
        migrate_legacy_artifact(
            source, account_id="__operator__", approved=False, root=tmp_path
        )
    assert source.exists()


@pytest.mark.parametrize(
    "crash_phase", ["locked", "published_verified", "receipt_prepared", "tombstoned"]
)
def test_crash_restart_finishes_without_loss_or_duplicate_ownership(tmp_path, crash_phase):
    source = _legacy(tmp_path)

    def crash(phase):
        if phase == crash_phase:
            raise RuntimeError("injected crash")

    with pytest.raises(RuntimeError, match="injected crash"):
        migrate_legacy_artifact(
            source,
            account_id="__operator__",
            approved=True,
            root=tmp_path,
            crash_after=crash,
        )

    receipt = migrate_legacy_artifact(
        source, account_id="__operator__", approved=True, root=tmp_path
    )
    authority = operator_authority("legacy-inv")
    html = FilesystemArtifactStore(tmp_path).read(authority)
    assert "Private historical note" in html
    assert receipt.verdict == "migrated"
    assert receipt.tombstone_retention_days == 90
    assert not source.exists()
    assert len(list((tmp_path / ".migration" / "tombstones").glob("*.html"))) == 1
    receipt_json = next((tmp_path / ".migration" / "receipts").glob("*.json")).read_text()
    assert "Private historical" not in receipt_json
    assert "legacy-inv" not in receipt_json


def test_corrupt_journal_is_quarantined_not_truncated(tmp_path):
    source = _legacy(tmp_path)
    authority = operator_authority("legacy-inv")
    journal_dir = tmp_path / ".migration" / "journals"
    journal_dir.mkdir(parents=True)
    journal = journal_dir / f"{authority.investigation_digest}.jsonl"
    journal.write_text(json.dumps({"version": 1}) + "\n", encoding="utf-8")
    original = journal.read_bytes()

    with pytest.raises(CorruptMigrationJournal):
        migrate_legacy_artifact(
            source, account_id="__operator__", approved=True, root=tmp_path
        )
    assert journal.read_bytes() == original
    markers = list((tmp_path / ".migration" / "quarantine").glob("*.json"))
    assert len(markers) == 1
    assert source.exists()


def test_validly_checksummed_but_reordered_journal_is_quarantined(tmp_path):
    source = _legacy(tmp_path)
    authority = operator_authority("legacy-inv")
    journal = (
        tmp_path / ".migration" / "journals" / f"{authority.investigation_digest}.jsonl"
    )
    journal.parent.mkdir(parents=True)
    _append_journal(journal, "published_verified", {})
    original = journal.read_bytes()

    with pytest.raises(CorruptMigrationJournal, match="phase"):
        migrate_legacy_artifact(
            source, account_id="__operator__", approved=True, root=tmp_path
        )
    assert journal.read_bytes() == original
    assert source.exists()


def test_validly_checksummed_later_identity_conflict_is_quarantined(tmp_path):
    source = _legacy(tmp_path)
    authority = operator_authority("legacy-inv")
    journal = (
        tmp_path / ".migration" / "journals" / f"{authority.investigation_digest}.jsonl"
    )
    journal.parent.mkdir(parents=True)
    _append_journal(journal, "locked", {"content_hash": "a"})
    _append_journal(journal, "published_verified", {"content_hash": "b"})
    original = journal.read_bytes()
    with pytest.raises(CorruptMigrationJournal, match="facts mismatch"):
        migrate_legacy_artifact(
            source, account_id="__operator__", approved=True, root=tmp_path
        )
    assert journal.read_bytes() == original
    assert source.exists()


def test_symlinked_migration_lock_fails_closed_without_touching_target(tmp_path):
    source = _legacy(tmp_path)
    migration_dir = tmp_path / ".migration"
    migration_dir.mkdir()
    target = tmp_path / "foreign-lock-target"
    target.write_text("do not touch", encoding="utf-8")
    os.symlink(target, migration_dir / "migration.lock")
    with pytest.raises(MigrationRefused, match="lock is unsafe"):
        migrate_legacy_artifact(
            source, account_id="__operator__", approved=True, root=tmp_path
        )
    assert target.read_text(encoding="utf-8") == "do not touch"
    assert source.exists()


def test_scoped_content_conflict_quarantines_legacy(tmp_path):
    source = _legacy(tmp_path)
    authority = operator_authority("legacy-inv")
    FilesystemArtifactStore(tmp_path).write(authority, "different scoped bytes")
    with pytest.raises(MigrationRefused, match="conflicts"):
        migrate_legacy_artifact(
            source, account_id="__operator__", approved=True, root=tmp_path
        )
    assert source.exists()


def test_renamed_legacy_file_is_quarantined_as_ambiguous(tmp_path):
    source = _legacy(tmp_path)
    renamed = source.with_name("wrong-name.html")
    source.rename(renamed)
    with pytest.raises(MigrationRefused, match="embedded identity conflict"):
        migrate_legacy_artifact(
            renamed, account_id="__operator__", approved=True, root=tmp_path
        )
    assert renamed.exists()


def test_path_substitution_during_tombstone_fails_closed(tmp_path, monkeypatch):
    from substrate.research_artifact import migration as migration_module

    source = _legacy(tmp_path)
    original_rename = migration_module.os.rename

    def substitute_then_rename(src, dst, *, src_dir_fd, dst_dir_fd):
        original_rename(source, tmp_path / "original-moved-by-attacker.html")
        source.write_text("hostile replacement", encoding="utf-8")
        original_rename(
            src,
            dst,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(migration_module.os, "rename", substitute_then_rename)
    with pytest.raises(MigrationRefused, match="changed during tombstoning"):
        migrate_legacy_artifact(
            source, account_id="__operator__", approved=True, root=tmp_path
        )


def test_substitution_after_descriptor_read_fails_identity_check(tmp_path, monkeypatch):
    from substrate.research_artifact import migration as migration_module

    source = _legacy(tmp_path)
    original_read = migration_module._read_regular_with_identity

    def read_then_substitute(path):
        result = original_read(path)
        source.rename(tmp_path / "original-after-read.html")
        source.write_text("hostile replacement", encoding="utf-8")
        return result

    monkeypatch.setattr(
        migration_module, "_read_regular_with_identity", read_then_substitute
    )
    with pytest.raises(MigrationRefused, match="changed during migration"):
        migrate_legacy_artifact(
            source, account_id="__operator__", approved=True, root=tmp_path
        )


def test_retry_rejects_tampered_tombstone(tmp_path):
    source = _legacy(tmp_path)

    def crash_after_tombstone(phase):
        if phase == "tombstoned":
            raise RuntimeError("injected crash")

    with pytest.raises(RuntimeError, match="injected crash"):
        migrate_legacy_artifact(
            source,
            account_id="__operator__",
            approved=True,
            root=tmp_path,
            crash_after=crash_after_tombstone,
        )
    tombstone = next((tmp_path / ".migration" / "tombstones").glob("*.html"))
    tombstone.write_text("tampered", encoding="utf-8")
    with pytest.raises(MigrationRefused, match="quarantined|conflict"):
        migrate_legacy_artifact(
            source, account_id="__operator__", approved=True, root=tmp_path
        )


def test_shadow_resolution_never_exposes_legacy_to_non_operator(tmp_path):
    source = _legacy(tmp_path)
    alice = shadow_resolution(
        ArtifactAuthority("alice", "legacy-inv"), root=tmp_path, legacy_source=source
    )
    assert alice.legacy_exists is False
    assert alice.scoped_exists is False
    assert alice.hashes_match is None
    assert alice.enforcement_ready is False

    operator = operator_authority("legacy-inv")
    before = shadow_resolution(operator, root=tmp_path, legacy_source=source)
    assert before.legacy_exists is True
    assert before.scoped_exists is False
    assert before.enforcement_ready is False
    FilesystemArtifactStore(tmp_path).write(operator, source.read_text(encoding="utf-8"))
    after = shadow_resolution(operator, root=tmp_path, legacy_source=source)
    assert after.hashes_match is True
    assert after.enforcement_ready is True
