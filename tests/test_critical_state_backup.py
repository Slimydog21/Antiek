"""Real WAL, credential and offline restore controls; no production resources."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import io
import json
import os
import sqlite3
import tarfile
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from nacl.public import PrivateKey

from runtime.byok.store import load_credential, store_credential
from substrate.auth import accounts, passkeys
from tools import critical_state_backup as backup
from tools.critical_backup_crypto import MAGIC, encrypt_file


def private_file(path: Path, body: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(body)
    path.chmod(0o600)
    return path


@pytest.fixture
def sources(tmp_path: Path) -> backup.SnapshotSources:
    state = tmp_path / "state"
    key, artifact = state / "byok/byok_master.key", state / "byok/credentials.enc"
    credential = store_credential("synthetic-owner", "synthetic-BYOK-secret", owner_user_id="acct_a",
                                  artifact_path=str(artifact), key_file=str(key))
    private_file(tmp_path / "credential-id", credential.encode())
    accounts = private_file(state / "auth/accounts.json", b'{"acct_a":{"role":"user","subject":"acct_a"}}')
    passkeys = private_file(state / "auth/passkeys.json", b'{"synthetic-credential":{"user_id":"acct_a"}}')
    private_file(state / "auth/pending-claims.json", b'{"do-not-restore":"ephemeral-claim"}')
    settings = state / "settings"
    private_file(settings / "lineup.json", b'{"owner":"acct_a"}')
    pointer = state / "turbopuffer-shadow"
    private_file(pointer / "promote-pointer.json", b'{"namespace":"synthetic-only"}')
    system = {name: private_file(tmp_path / "system" / name, b"synthetic-recovery-config-" + name.encode())
              for name in ("secrets.env", "rclone.conf", "tunnel.json")}
    return backup.SnapshotSources(state, key, artifact, accounts, passkeys, (settings,), pointer, system)


def keys(tmp_path: Path) -> tuple[Path, Path]:
    identity = PrivateKey.generate()
    return (private_file(tmp_path / "recipient.hex", bytes(identity.public_key).hex().encode()),
            private_file(tmp_path / "identity.hex", bytes(identity).hex().encode()))


def bundle(tmp_path: Path, sources: backup.SnapshotSources) -> tuple[Path, Path, Path]:
    recipient, identity = keys(tmp_path)
    staging = tmp_path / "antiek-backup.synthetic"
    staging.mkdir(mode=0o700)
    escrow = tmp_path / "byok-key"
    backup.prepare(sources, staging / "critical-state", escrow, recipient)
    archive = tmp_path / "data.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(staging, arcname=staging.name)
    archive.chmod(0o600)
    encrypted = tmp_path / "data.enc"
    encrypt_file(archive, encrypted, recipient)
    return encrypted, Path(str(escrow) + ".enc"), identity


def test_snapshot_includes_committed_wal_without_uncommitted_rows_and_live_copy(
    tmp_path: Path, sources: backup.SnapshotSources,
) -> None:
    path = sources.state / "accounting.sqlite3"
    writer = sqlite3.connect(path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE ledger(owner TEXT, cents INTEGER)")
        writer.execute("INSERT INTO ledger VALUES ('acct_a', 27)")
        writer.commit()
        path.chmod(0o600)
        assert Path(str(path) + "-wal").stat().st_size > 0
        writer.execute("INSERT INTO ledger VALUES ('acct_a', 999)")
        destination, escrow = tmp_path / "snapshot", tmp_path / "key"
        manifest = backup.snapshot(sources, destination, escrow)
        assert not list(destination.rglob("*-wal"))
        with closing(sqlite3.connect(destination / "state/accounting.sqlite3")) as restored:
            assert restored.execute("SELECT * FROM ledger").fetchall() == [("acct_a", 27)]
            assert restored.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        assert writer.execute("SELECT * FROM ledger").fetchall() == [("acct_a", 27), ("acct_a", 999)]
        assert writer.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert manifest["snapshot_consistency"].startswith("per-store;")
        assert any(row["kind"] == "sqlite-online-backup" for row in manifest["files"])
        assert not list(destination.rglob("*-wal"))
        assert not (destination / "state/auth/pending-claims.json").exists()
    finally:
        writer.rollback()
        writer.close()


def test_encrypt_restore_preserves_accounts_passkeys_and_real_owned_byok(
    tmp_path: Path, sources: backup.SnapshotSources, capsys: pytest.CaptureFixture[str],
) -> None:
    data, encrypted_key, identity = bundle(tmp_path, sources)
    assert data.read_bytes().startswith(MAGIC) and encrypted_key.read_bytes().startswith(MAGIC)
    assert b"synthetic-BYOK-secret" not in data.read_bytes() + encrypted_key.read_bytes()
    assert not (tmp_path / "byok-key").exists()
    recovered = tmp_path / "offline-recovery"
    backup.restore(data, encrypted_key, identity, recovered)
    critical = recovered / "critical-state"
    assert (critical / "state/auth/accounts.json").read_bytes() == sources.accounts.read_bytes()
    assert (critical / "state/auth/passkeys.json").read_bytes() == sources.passkeys.read_bytes()
    assert (critical / "system/secrets.env").read_bytes() == sources.system_files["secrets.env"].read_bytes()
    credential_id = (tmp_path / "credential-id").read_text()
    credential = load_credential(credential_id, artifact_path=str(critical / "state/byok/credentials.enc"),
                                 key_file=str(recovered / "separate-byok-key/byok_master.key"))
    assert credential.reveal() == "synthetic-BYOK-secret"
    assert not list(critical.rglob("*.key"))
    assert not list(recovered.rglob("pending-claims.json"))
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in recovered.rglob("*") if path.is_file())
    assert capsys.readouterr() == ("", "")


def test_full_encrypted_restore_recovers_actual_committed_wal_ledger(
    tmp_path: Path, sources: backup.SnapshotSources,
) -> None:
    ledger = sources.state / "spend.sqlite3"
    writer = sqlite3.connect(ledger)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE spend(owner TEXT, cents INTEGER)")
        writer.execute("INSERT INTO spend VALUES ('acct_a', 42)")
        writer.commit()
        ledger.chmod(0o600)
        assert Path(str(ledger) + "-wal").stat().st_size > 0
        data, encrypted_key, identity = bundle(tmp_path, sources)
        recovered = tmp_path / "offline-recovery"
        backup.restore(data, encrypted_key, identity, recovered)
        with sqlite3.connect(recovered / "critical-state/state/spend.sqlite3") as restored:
            assert restored.execute("SELECT * FROM spend").fetchall() == [("acct_a", 42)]
            assert restored.execute("PRAGMA quick_check").fetchall() == [("ok",)]
    finally:
        writer.close()


def test_offline_restored_accounts_and_public_passkey_retain_actual_auth_contract(
    tmp_path: Path, sources: backup.SnapshotSources, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_ACCOUNT_STORE", str(sources.accounts))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(sources.passkeys))
    sources.accounts.unlink()  # Replace the opaque byte-copy fixture with actual app stores.
    original = accounts.account_for_verified_email(
        "original@example.test", legacy_operator_email="original@example.test",
    )
    alice = accounts.account_for_verified_email("alice@example.test")
    private = ec.generate_private_key(ec.SECP256R1())
    numbers = private.public_key().public_numbers()
    public = cbor2.dumps({
        1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big"),
    })

    def b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    credential = passkeys.PasskeyCredential(
        credential_id=b64(b"isolated-recovery-key"), public_key=b64(public), sign_count=5,
        transports=("internal",), device_type="single_device", backed_up=False,
        label="Isolated recovery authenticator", created_at=1, user_id=alice.user_id, email=alice.email,
    )
    with passkeys._store_lock:
        passkeys._write_credentials_unlocked([credential])
    data, encrypted_key, identity = bundle(tmp_path, sources)
    recovered = tmp_path / "offline-auth-recovery"
    backup.restore(data, encrypted_key, identity, recovered)
    monkeypatch.setenv("ANTIEK_ACCOUNT_STORE", str(recovered / "critical-state/state/auth/accounts.json"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(recovered / "critical-state/state/auth/passkeys.json"))
    assert accounts.account_for_session(original.user_id, original.email) == original
    assert accounts.legacy_account_for_session(original.email) is None
    monkeypatch.setenv("ANTIEK_LEGACY_OPERATOR_EMAIL", original.email)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", original.email)
    assert accounts.legacy_account_for_session(original.email) == original
    assert accounts.account_for_session(alice.user_id, alice.email) == alice
    assert alice.legacy_owner is None and original.legacy_owner == "__operator__"
    assert passkeys.list_credentials() == [credential]
    monkeypatch.setenv("ANTIEK_WEBAUTHN_RP_ID", "recovery.test")
    monkeypatch.setenv("ANTIEK_WEBAUTHN_ORIGINS", "https://recovery.test")
    options = passkeys.authentication_options()
    client_data = json.dumps({
        "type": "webauthn.get", "challenge": options["challenge"],
        "origin": "https://recovery.test", "crossOrigin": False,
    }, separators=(",", ":")).encode()
    auth_data = hashlib.sha256(b"recovery.test").digest() + b"\x05" + (6).to_bytes(4, "big")
    signature = private.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
    assertion = {
        "id": credential.credential_id, "rawId": credential.credential_id, "type": "public-key",
        "response": {"clientDataJSON": b64(client_data), "authenticatorData": b64(auth_data),
                     "signature": b64(signature), "userHandle": None}, "clientExtensionResults": {},
    }
    verified = passkeys.complete_authentication(ceremony_id=options["ceremony_id"], credential=assertion)
    assert verified.user_id == alice.user_id and verified.email == alice.email and verified.sign_count == 6
    assert passkeys.list_credentials() == [verified]
    with pytest.raises(passkeys.PasskeyError):
        passkeys.complete_authentication(ceremony_id=options["ceremony_id"], credential=assertion)


@pytest.mark.parametrize("collision", ["accounts-passkeys", "accounts-byok", "system-config"])
def test_duplicate_required_source_cannot_certify_missing_critical_coverage(
    tmp_path: Path, sources: backup.SnapshotSources, collision: str,
) -> None:
    if collision == "accounts-passkeys":
        sources = replace(sources, accounts=sources.passkeys)
    elif collision == "accounts-byok":
        sources = replace(sources, accounts=sources.byok_artifact)
    else:
        sources = replace(sources, system_files={
            **sources.system_files, "secrets.env": sources.system_files["rclone.conf"],
        })
    destination, escrow = tmp_path / "snapshot", tmp_path / "key"
    with pytest.raises(backup.SnapshotError, match="distinct paths"):
        backup.snapshot(sources, destination, escrow)
    assert not destination.exists() and not escrow.exists()


@pytest.mark.parametrize("failure", ["wrong_identity", "tampered_data", "tampered_key", "foreign_key"])
def test_failed_authentication_or_pairing_never_leaves_recovered_state(
    tmp_path: Path, sources: backup.SnapshotSources, failure: str,
) -> None:
    data, encrypted_key, identity = bundle(tmp_path, sources)
    if failure == "wrong_identity":
        identity = private_file(tmp_path / "wrong.hex", bytes(PrivateKey.generate()).hex().encode())
    elif failure in {"tampered_data", "tampered_key"}:
        target = data if failure == "tampered_data" else encrypted_key
        raw = bytearray(target.read_bytes())
        raw[-9] ^= 1
        target.write_bytes(raw)
    else:
        other = tmp_path / "other"
        other.mkdir(mode=0o700)
        recipient = private_file(other / "public.hex",
                                 bytes(PrivateKey(bytes.fromhex(identity.read_text())).public_key).hex().encode())
        # Use the same real recipient with different key plaintext to exercise
        # the archive/object pairing, rather than only wrong-key decryption.
        plaintext = private_file(other / "key", b"x" * 32)
        encrypted_key = other / "key.enc"
        encrypt_file(plaintext, encrypted_key, recipient)
    destination = tmp_path / "refused"
    with pytest.raises(backup.SnapshotError):
        backup.restore(data, encrypted_key, identity, destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".critical-restore-*"))


@pytest.mark.parametrize("failure", ["missing_key", "wrong_pair", "symlink", "permissions", "invalid_sqlite",
                                     "missing_system", "master_in_settings", "existing_escrow"])
def test_snapshot_refuses_unsafe_missing_or_incoherent_state_and_cleans_only_own_files(
    tmp_path: Path, sources: backup.SnapshotSources, failure: str,
) -> None:
    escrow = tmp_path / "key"
    if failure == "missing_key":
        sources.byok_key.unlink()
    elif failure == "wrong_pair":
        sources.byok_key.write_bytes(b"x" * 32)
    elif failure == "symlink":
        (sources.settings[0] / "alias").symlink_to(sources.accounts)
    elif failure == "permissions":
        sources.accounts.chmod(0o644)
    elif failure == "invalid_sqlite":
        private_file(sources.state / "accounting.sqlite3", b"not-sqlite")
    elif failure == "missing_system":
        sources.system_files["secrets.env"].unlink()
    elif failure == "master_in_settings":
        sources = replace(sources, settings=(sources.byok_key.parent,))
    else:
        private_file(escrow, b"do-not-delete-foreign-data")
    destination = tmp_path / "snapshot"
    with pytest.raises((backup.SnapshotError, FileNotFoundError)):
        backup.snapshot(sources, destination, escrow)
    assert not destination.exists()
    if failure == "existing_escrow":
        assert escrow.read_bytes() == b"do-not-delete-foreign-data"
    else:
        assert not escrow.exists()


def test_held_actual_byok_artifact_lock_refuses_without_replacing_lock_inode(
    tmp_path: Path, sources: backup.SnapshotSources, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backup, "LOCK_TIMEOUT_SECONDS", 0.03)
    lock = Path(str(sources.byok_artifact) + ".lock")
    before = lock.stat().st_ino
    descriptor = os.open(lock, os.O_RDWR)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(backup.SnapshotError, match="deadline"):
            backup.snapshot(sources, tmp_path / "snapshot", tmp_path / "key")
    finally:
        os.close(descriptor)
    assert lock.stat().st_ino == before
    assert not (tmp_path / "snapshot").exists()


@pytest.mark.parametrize("member", ["../escape", "/absolute", "antiek-backup.x/../../escape", "symlink", "hardlink"])
def test_restore_refuses_archive_traversal_and_links(tmp_path: Path, member: str) -> None:
    recipient, identity = keys(tmp_path)
    archive = tmp_path / "malicious.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        row = tarfile.TarInfo(member if member not in {"symlink", "hardlink"} else "antiek-backup.x/link")
        if member in {"symlink", "hardlink"}:
            row.type = tarfile.SYMTYPE if member == "symlink" else tarfile.LNKTYPE
            row.linkname = "../outside"
            tar.addfile(row)
        else:
            row.size = 1
            tar.addfile(row, io.BytesIO(b"x"))
    archive.chmod(0o600)
    encrypted = tmp_path / "data.enc"
    encrypt_file(archive, encrypted, recipient)
    key = private_file(tmp_path / "key", b"x" * 32)
    encrypted_key = tmp_path / "key.enc"
    encrypt_file(key, encrypted_key, recipient)
    with pytest.raises(backup.SnapshotError):
        backup.restore(encrypted, encrypted_key, identity, tmp_path / "refused")
    assert not (tmp_path / "refused").exists()
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize("filename", ["external-accounting.sqlite3", "nonstandard-accounting.ledger"])
def test_explicit_external_ledger_is_snapshotted(
    tmp_path: Path, sources: backup.SnapshotSources, filename: str,
) -> None:
    path = tmp_path / filename
    with sqlite3.connect(path) as writer:
        writer.execute("CREATE TABLE spend(value INTEGER)")
        writer.execute("INSERT INTO spend VALUES (31)")
    path.chmod(0o600)
    sources = replace(sources, extra_sqlite=(path,))
    destination = tmp_path / "snapshot"
    backup.snapshot(sources, destination, tmp_path / "key")
    with sqlite3.connect(destination / "external-sqlite/0" / filename) as restored:
        assert restored.execute("SELECT value FROM spend").fetchone() == (31,)


def test_inventory_matches_actual_deployed_state_and_strict_raw_types(
    tmp_path: Path, sources: backup.SnapshotSources,
) -> None:
    raw = {"version": 1, "state": str(sources.state), "byok_key": str(sources.byok_key),
           "byok_artifact": str(sources.byok_artifact), "accounts": str(sources.accounts),
           "passkeys": str(sources.passkeys), "settings": [str(path) for path in sources.settings],
           "turbopuffer": str(sources.turbopuffer),
           "system_files": {name: str(path) for name, path in sources.system_files.items()}, "extra_sqlite": []}
    configuration = private_file(tmp_path / "sources.json", json.dumps(raw).encode())
    assert backup.load_sources(configuration, sources.state) == sources
    raw["version"] = True
    configuration.write_text(json.dumps(raw))
    with pytest.raises(backup.SnapshotError):
        backup.load_sources(configuration, sources.state)


def test_missing_recipient_retires_owned_snapshot_and_raw_key(
    tmp_path: Path, sources: backup.SnapshotSources,
) -> None:
    destination, escrow = tmp_path / "snapshot", tmp_path / "key"
    with pytest.raises(backup.SnapshotError):
        backup.prepare(sources, destination, escrow, tmp_path / "missing-public.hex")
    assert not destination.exists() and not escrow.exists()
    assert not Path(str(escrow) + ".enc").exists()


def test_preexisting_encrypted_escrow_is_never_overwritten_or_deleted(
    tmp_path: Path, sources: backup.SnapshotSources,
) -> None:
    recipient, _ = keys(tmp_path)
    escrow = tmp_path / "key"
    encrypted = private_file(Path(str(escrow) + ".enc"), b"foreign-owned-object")
    with pytest.raises(backup.SnapshotError):
        backup.prepare(sources, tmp_path / "snapshot", escrow, recipient)
    assert encrypted.read_bytes() == b"foreign-owned-object"
    assert not escrow.exists() and not (tmp_path / "snapshot").exists()


@pytest.mark.parametrize("bound", ["MAX_FILES", "MAX_TOTAL_BYTES"])
def test_snapshot_limits_refuse_without_partial_coverage_or_key_debris(
    tmp_path: Path, sources: backup.SnapshotSources, monkeypatch: pytest.MonkeyPatch, bound: str,
) -> None:
    monkeypatch.setattr(backup, bound, 0)
    with pytest.raises(backup.SnapshotError, match="limit"):
        backup.snapshot(sources, tmp_path / "snapshot", tmp_path / "key")
    assert not (tmp_path / "snapshot").exists()
    assert not (tmp_path / "key").exists()
