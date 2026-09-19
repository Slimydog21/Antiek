from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from substrate.research_artifact.authority import ArtifactAuthority, operator_authority
from substrate.research_artifact.rollout import (
    ArtifactRolloutMode,
    build_activation_receipt,
    read_canonical_artifact,
)
from substrate.research_artifact.storage import FilesystemArtifactStore, UnsafeArtifactState


@pytest.fixture(autouse=True)
def isolated_authority_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path))


def test_shadow_compares_operator_metadata_but_serves_scoped_bytes(tmp_path):
    authority = operator_authority("shared")
    scoped = "<p>scoped canonical</p>"
    FilesystemArtifactStore(tmp_path).write(authority, scoped)
    (tmp_path / "shared.html").write_text(scoped, encoding="utf-8")

    html, resolution = read_canonical_artifact(
        authority, root=tmp_path, mode=ArtifactRolloutMode.SHADOW
    )
    assert html == scoped
    assert resolution is not None and resolution.hashes_match is True


def test_shadow_never_falls_back_to_legacy_bytes(tmp_path):
    authority = operator_authority("legacy-only")
    (tmp_path / "legacy-only.html").write_text("private legacy", encoding="utf-8")
    with pytest.raises(UnsafeArtifactState):
        read_canonical_artifact(authority, root=tmp_path, mode=ArtifactRolloutMode.SHADOW)


def test_non_operator_shadow_does_not_probe_legacy(tmp_path):
    authority = ArtifactAuthority("alice", "shared")
    FilesystemArtifactStore(tmp_path).write(authority, "alice scoped")
    (tmp_path / "shared.html").write_text("operator legacy", encoding="utf-8")
    html, resolution = read_canonical_artifact(
        authority, root=tmp_path, mode=ArtifactRolloutMode.SHADOW
    )
    assert html == "alice scoped"
    assert resolution is None


@pytest.mark.parametrize("mode", [ArtifactRolloutMode.SCOPED, ArtifactRolloutMode.ENFORCED])
def test_activation_modes_fail_closed_without_terminal_green_receipt(tmp_path, mode):
    authority = operator_authority("ready")
    FilesystemArtifactStore(tmp_path).write(authority, "scoped")
    with pytest.raises(RuntimeError, match="requires a verified receipt"):
        read_canonical_artifact(authority, root=tmp_path, mode=mode)


def test_account_scoped_backup_restore_survives_restart_without_crossing_owners(tmp_path):
    live = tmp_path / "live"
    backup = tmp_path / "backup"
    restored = tmp_path / "restored"
    alice = ArtifactAuthority("alice", "same-display-id")
    bob = ArtifactAuthority("bob", "same-display-id")
    store = FilesystemArtifactStore(live)
    store.write(alice, "alice private bytes")
    store.write(bob, "bob private bytes")

    shutil.copytree(live, backup, copy_function=shutil.copy2)
    shutil.copytree(backup, restored, copy_function=shutil.copy2)
    restarted_store = FilesystemArtifactStore(restored)

    assert restarted_store.read(alice) == "alice private bytes"
    assert restarted_store.read(bob) == "bob private bytes"
    assert alice.artifact_path(restored) != bob.artifact_path(restored)
    assert alice.sidecar_path(restored).read_bytes() != bob.sidecar_path(restored).read_bytes()


def _green_evidence(root) -> dict[str, dict[str, str]]:
    names = (
        "real_http_canary",
        "backup_restore",
        "artifact_outbox_reconcile",
        "frontend_private_window",
        "tenancy_ratchets",
        "browser_visual_canary",
        "security_gate",
    )
    evidence_dir = root / ".migration" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence = {}
    for index, name in enumerate(names, start=1):
        raw = json.dumps(
            {"gate": name, "run": index, "status": "pass", "exit_code": 0},
            sort_keys=True,
        ).encode()
        (evidence_dir / f"{name}.json").write_bytes(raw)
        evidence[name] = {"status": "pass", "digest": hashlib.sha256(raw).hexdigest()}
    return evidence


@pytest.mark.parametrize("mode", [ArtifactRolloutMode.SCOPED, ArtifactRolloutMode.ENFORCED])
def test_activation_receipt_is_exact_root_bound_and_tamper_evident(tmp_path, mode):
    authority = operator_authority("ready")
    FilesystemArtifactStore(tmp_path).write(authority, "scoped")
    receipt = build_activation_receipt(tmp_path, mode, _green_evidence(tmp_path))
    migration = tmp_path / ".migration"
    path = migration / f"rollout-{mode.value}.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")

    html, _ = read_canonical_artifact(authority, root=tmp_path, mode=mode)
    assert html == "scoped"

    receipt["evidence"]["security_gate"]["digest"] = "f" * 64
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(RuntimeError, match="not terminal-green"):
        read_canonical_artifact(authority, root=tmp_path, mode=mode)


def test_activation_receipt_cannot_be_replayed_at_another_root(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    authority = operator_authority("ready")
    FilesystemArtifactStore(source).write(authority, "scoped")
    receipt = build_activation_receipt(source, ArtifactRolloutMode.SCOPED, _green_evidence(source))
    migration = source / ".migration"
    (migration / "rollout-scoped.json").write_text(json.dumps(receipt), encoding="utf-8")
    shutil.copytree(source, destination)
    with pytest.raises(RuntimeError, match="not terminal-green"):
        read_canonical_artifact(authority, root=destination, mode=ArtifactRolloutMode.SCOPED)


def test_activation_receipt_rejects_fabricated_or_changed_evidence(tmp_path):
    evidence = _green_evidence(tmp_path)
    evidence["security_gate"]["digest"] = "f" * 64
    with pytest.raises(ValueError, match="does not match"):
        build_activation_receipt(tmp_path, ArtifactRolloutMode.SCOPED, evidence)

    evidence = _green_evidence(tmp_path)
    receipt = build_activation_receipt(tmp_path, ArtifactRolloutMode.SCOPED, evidence)
    path = tmp_path / ".migration" / "rollout-scoped.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    (tmp_path / ".migration" / "evidence" / "security_gate.json").write_text("changed")
    authority = operator_authority("ready")
    FilesystemArtifactStore(tmp_path).write(authority, "scoped")
    with pytest.raises(RuntimeError, match="not terminal-green"):
        read_canonical_artifact(authority, root=tmp_path, mode=ArtifactRolloutMode.SCOPED)


def test_activation_receipt_rejects_hashed_failed_evidence(tmp_path):
    evidence = _green_evidence(tmp_path)
    path = tmp_path / ".migration" / "evidence" / "security_gate.json"
    raw = json.dumps(
        {"gate": "security_gate", "status": "fail", "exit_code": 1},
        sort_keys=True,
    ).encode()
    path.write_bytes(raw)
    evidence["security_gate"]["digest"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="unavailable"):
        build_activation_receipt(tmp_path, ArtifactRolloutMode.SCOPED, evidence)
