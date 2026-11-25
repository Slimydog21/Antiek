"""Authenticated streaming backups to an independently held recovery key.

Only the public Curve25519 recipient is needed on the source host. Libsodium
SealedBox wraps a fresh secretstream key; XChaCha20-Poly1305 authenticates the
ordered frames and final boundary. Failed publication retires only owned output.
This format is versioned separately from the existing DuckDB bundle contract.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
import struct
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from nacl import bindings, exceptions, public

MAGIC = b"ANTIEK-CRITICAL-BACKUP\x00v1\n"
CHUNK_BYTES = 64 * 1024
MAX_PLAINTEXT_BYTES = 64 * 1024**3
_WRAPPED_KEY_BYTES = (
    bindings.crypto_secretstream_xchacha20poly1305_KEYBYTES + bindings.crypto_box_SEALBYTES
)
_HEADER_BYTES = bindings.crypto_secretstream_xchacha20poly1305_HEADERBYTES
_OVERHEAD = bindings.crypto_secretstream_xchacha20poly1305_ABYTES


class BackupCryptoError(ValueError):
    """A value-free refusal suitable for an operational log."""


@dataclass(frozen=True)
class EncryptedObject:
    sha256: str
    bytes: int
    recipient_sha256: str


def _safe_parent(path: Path) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise BackupCryptoError("backup path must be absolute without traversal")
    for parent in reversed(path.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, os.getuid()}:
            raise BackupCryptoError("backup path parent is unsafe")
        if info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
            raise BackupCryptoError("backup path parent is writable by others")
    if path.parent.stat().st_mode & 0o022:
        raise BackupCryptoError("backup destination parent is writable by others")


@contextmanager
def _input(path: Path, *, secret: bool) -> Iterator[BinaryIO]:
    _safe_parent(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid not in {0, os.getuid()}
            or info.st_mode & (0o077 if secret else 0o022)
        ):
            raise BackupCryptoError("backup input is not a private owned regular file")
        yield stream


@contextmanager
def _output(path: Path) -> Iterator[BinaryIO]:
    """Publish once after authentication/fsync; never overwrite a recovery file."""
    _safe_parent(path)
    temporary = path.with_name(".backup-" + secrets.token_hex(16))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    owned = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        temporary.unlink()
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        # A link may be acquired even when its native call never returns.
        # Retire only our inode, including post-link sync/close failures.
        cleanup_failed = False
        for target in (path, temporary):
            try:
                current = target.lstat()
                if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                    target.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                cleanup_failed = True
        if cleanup_failed:
            raise BackupCryptoError("backup publication failed; owned output cleanup is incomplete") from None
        raise


def _key(path: Path, *, private: bool) -> bytes:
    with _input(path, secret=private) as stream:
        raw = stream.read(66)
    try:
        if len(raw) not in (64, 65) or (len(raw) == 65 and raw[-1:] != b"\n"):
            raise ValueError
        value = bytes.fromhex(raw.decode("ascii").strip())
        if len(value) != 32:
            raise ValueError
        return value
    except (UnicodeError, ValueError):
        raise BackupCryptoError("recovery key must contain exactly 32 hex-encoded bytes") from None


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    raw = stream.read(size)
    if len(raw) != size:
        raise BackupCryptoError("encrypted backup is truncated")
    return raw


def encrypt_file(source: Path, destination: Path, recipient_file: Path) -> EncryptedObject:
    """Seal a private file without loading its complete plaintext into memory."""
    try:
        recipient = public.PublicKey(_key(recipient_file, private=False))
        key = bindings.crypto_secretstream_xchacha20poly1305_keygen()
        wrapped = public.SealedBox(recipient).encrypt(key)
        state = bindings.crypto_secretstream_xchacha20poly1305_state()
        header = bindings.crypto_secretstream_xchacha20poly1305_init_push(state, key)
        envelope = MAGIC + wrapped + header
        digest = hashlib.sha256()
        written = total = 0
        with _input(source, secret=True) as plain, _output(destination) as encrypted:
            encrypted.write(envelope)
            digest.update(envelope)
            written += len(envelope)
            while chunk := plain.read(CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_PLAINTEXT_BYTES:
                    raise BackupCryptoError("backup plaintext exceeds its size limit")
                frame = bindings.crypto_secretstream_xchacha20poly1305_push(state, chunk, envelope)
                record = struct.pack(">I", len(frame)) + frame
                encrypted.write(record)
                digest.update(record)
                written += len(record)
            final = bindings.crypto_secretstream_xchacha20poly1305_push(
                state, b"", envelope, bindings.crypto_secretstream_xchacha20poly1305_TAG_FINAL,
            )
            record = struct.pack(">I", len(final)) + final
            encrypted.write(record)
            digest.update(record)
            written += len(record)
        return EncryptedObject(digest.hexdigest(), written, hashlib.sha256(bytes(recipient)).hexdigest())
    except (OSError, exceptions.CryptoError):
        raise BackupCryptoError("encrypted backup could not be created") from None


def decrypt_file(source: Path, destination: Path, identity_file: Path) -> None:
    """Authenticate the entire stream before publishing a private restore file."""
    try:
        identity = public.PrivateKey(_key(identity_file, private=True))
        with _input(source, secret=False) as encrypted, _output(destination) as plain:
            envelope = _read_exact(encrypted, len(MAGIC) + _WRAPPED_KEY_BYTES + _HEADER_BYTES)
            if not envelope.startswith(MAGIC):
                raise BackupCryptoError("encrypted backup version is unsupported")
            wrapped = envelope[len(MAGIC):len(MAGIC) + _WRAPPED_KEY_BYTES]
            key = public.SealedBox(identity).decrypt(wrapped)
            state = bindings.crypto_secretstream_xchacha20poly1305_state()
            bindings.crypto_secretstream_xchacha20poly1305_init_pull(state, envelope[-_HEADER_BYTES:], key)
            total = 0
            while True:
                size = struct.unpack(">I", _read_exact(encrypted, 4))[0]
                if not _OVERHEAD <= size <= CHUNK_BYTES + _OVERHEAD:
                    raise BackupCryptoError("encrypted backup frame size is invalid")
                chunk, tag = bindings.crypto_secretstream_xchacha20poly1305_pull(
                    state, _read_exact(encrypted, size), envelope,
                )
                if tag == bindings.crypto_secretstream_xchacha20poly1305_TAG_FINAL:
                    if chunk or encrypted.read(1):
                        raise BackupCryptoError("encrypted backup final boundary is invalid")
                    break
                if tag != bindings.crypto_secretstream_xchacha20poly1305_TAG_MESSAGE:
                    raise BackupCryptoError("encrypted backup frame tag is unsupported")
                total += len(chunk)
                if total > MAX_PLAINTEXT_BYTES:
                    raise BackupCryptoError("restored plaintext exceeds its size limit")
                plain.write(chunk)
    except (OSError, exceptions.CryptoError):
        raise BackupCryptoError("encrypted backup authentication failed") from None
