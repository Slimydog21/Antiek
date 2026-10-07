"""Real offline encryption and publication-denial controls for recovery."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from nacl.public import PrivateKey

from tools.critical_backup_crypto import (
    CHUNK_BYTES,
    MAGIC,
    BackupCryptoError,
    decrypt_file,
    encrypt_file,
)


def _write(path: Path, body: bytes) -> Path:
    path.write_bytes(body)
    path.chmod(0o600)
    return path


def _keys(root: Path) -> tuple[Path, Path]:
    identity = PrivateKey.generate()
    return (
        _write(root / "recovery-public.hex", bytes(identity.public_key).hex().encode()),
        _write(root / "recovery-private.hex", bytes(identity).hex().encode()),
    )


@pytest.mark.parametrize("size", [0, 1, CHUNK_BYTES, CHUNK_BYTES * 3 + 53])
def test_real_stream_roundtrip_keeps_plaintext_out_of_object(tmp_path: Path, size: int) -> None:
    recipient, identity = _keys(tmp_path)
    secret = b"synthetic-private-BYOK-and-account-state"
    body = (secret * (size // len(secret) + 1))[:size]
    source = _write(tmp_path / "plain.tar.gz", body)
    encrypted, restored = tmp_path / "object.enc", tmp_path / "restored.tar.gz"

    receipt = encrypt_file(source, encrypted, recipient)
    assert encrypted.read_bytes().startswith(MAGIC)
    assert secret not in encrypted.read_bytes()
    assert receipt.sha256 == hashlib.sha256(encrypted.read_bytes()).hexdigest()
    assert receipt.bytes == encrypted.stat().st_size
    assert encrypted.stat().st_mode & 0o777 == 0o600
    decrypt_file(encrypted, restored, identity)
    assert restored.read_bytes() == body
    assert restored.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".backup-*"))


@pytest.mark.parametrize("mutation", ["wrapped_key", "header", "body", "truncated", "appended", "oversize_frame"])
def test_tampered_or_incomplete_object_never_publishes_plaintext(tmp_path: Path, mutation: str) -> None:
    recipient, identity = _keys(tmp_path)
    source = _write(tmp_path / "plain", b"private-synthetic-data" * 10000)
    encrypted, restored = tmp_path / "object.enc", tmp_path / "restore"
    encrypt_file(source, encrypted, recipient)
    raw = bytearray(encrypted.read_bytes())
    if mutation == "wrapped_key":
        raw[len(MAGIC) + 3] ^= 1
    elif mutation == "header":
        raw[len(MAGIC) + 81] ^= 1
    elif mutation == "body":
        raw[len(MAGIC) + 120] ^= 1
    elif mutation == "truncated":
        del raw[-1:]
    elif mutation == "appended":
        raw += b"untrusted tail"
    else:
        raw[len(MAGIC) + 104:len(MAGIC) + 108] = b"\xff" * 4
    encrypted.write_bytes(raw)

    with pytest.raises(BackupCryptoError):
        decrypt_file(encrypted, restored, identity)
    assert not restored.exists()
    assert not list(tmp_path.glob(".backup-*"))


def test_wrong_recovery_identity_refuses_and_keeps_existing_target(tmp_path: Path) -> None:
    recipient, _ = _keys(tmp_path)
    source = _write(tmp_path / "plain", b"synthetic-secret")
    encrypted = tmp_path / "object.enc"
    encrypt_file(source, encrypted, recipient)
    wrong = _write(tmp_path / "wrong.hex", bytes(PrivateKey.generate()).hex().encode())
    target = _write(tmp_path / "restored", b"existing protected data")

    with pytest.raises(BackupCryptoError):
        decrypt_file(encrypted, target, wrong)
    assert target.read_bytes() == b"existing protected data"
    assert not list(tmp_path.glob(".backup-*"))


@pytest.mark.parametrize("kind", ["source_symlink", "source_hardlink", "source_permission", "recipient_symlink", "destination_symlink", "parent_symlink", "parent_permission", "traversal"])
def test_unsafe_paths_refuse_without_overwrite(tmp_path: Path, kind: str) -> None:
    recipient, identity = _keys(tmp_path)
    source = _write(tmp_path / "plain", b"private synthetic key")
    protected = _write(tmp_path / "protected", b"unchanged")
    destination = tmp_path / "object.enc"
    if kind == "source_symlink":
        alias = tmp_path / "source-alias"
        alias.symlink_to(source)
        source = alias
    elif kind == "source_hardlink":
        (tmp_path / "hardlink").hardlink_to(source)
    elif kind == "source_permission":
        source.chmod(0o644)
    elif kind == "recipient_symlink":
        alias = tmp_path / "recipient-alias"
        alias.symlink_to(recipient)
        recipient = alias
    elif kind == "destination_symlink":
        destination.symlink_to(protected)
    elif kind == "parent_symlink":
        alias = tmp_path / "directory-alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        destination = alias / "object.enc"
    elif kind == "parent_permission":
        parent = tmp_path / "unsafe"
        parent.mkdir(mode=0o777)
        parent.chmod(0o777)
        destination = parent / "object.enc"
    else:
        destination = tmp_path / ".." / "object.enc"

    with pytest.raises(BackupCryptoError):
        encrypt_file(source, destination, recipient)
    assert protected.read_bytes() == b"unchanged"
    assert not list(tmp_path.glob(".backup-*"))
    assert identity.read_bytes()


def test_missing_and_invalid_recipient_are_value_free_refusals(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _write(tmp_path / "plain", b"synthetic-secret-not-for-logs")
    destination = tmp_path / "object.enc"
    with pytest.raises(BackupCryptoError):
        encrypt_file(source, destination, tmp_path / "absent.hex")
    invalid = _write(tmp_path / "invalid.hex", b"invalid-secret-shape")
    with pytest.raises(BackupCryptoError, match="exactly 32 hex-encoded bytes"):
        encrypt_file(source, destination, invalid)
    assert not destination.exists()
    assert capsys.readouterr() == ("", "")
