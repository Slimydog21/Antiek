"""Encrypted-at-rest BYOK credential store (Personal-Reading Lane SPR-08, M1).

The operator brings their OWN X / Twitter API key (BYOK). This module stores that
key ENCRYPTED AT REST and decrypts it ONLY in-process, at ingest time, behind an
explicit :class:`~runtime.byok.secret_str.SecretStr`. The on-disk artifact holds
only ciphertext + non-secret metadata (a ``cred_id``, the ``account_handle``, the
``pipeline_kind``); the plaintext key is never written to the DB, the repo, the
event log, or any logger.

────────────────────────────────────────────────────────────────────────────────
MECHANISM — libsodium ``SecretBox`` (PyNaCl), authenticated symmetric encryption
────────────────────────────────────────────────────────────────────────────────
Each credential is sealed with ``nacl.secret.SecretBox`` (XSalsa20-Poly1305): a
fresh 24-byte nonce per credential, prepended to the ciphertext; the box is keyed
off a 32-byte master key read from a key FILE at mode ``0600`` (the key never
sits in the repo or the DB — it lives outside the encrypted artifact, e.g. under
``$ANTIEK_BYOK_KEY_FILE`` on the box). Tests inject the key bytes directly, so the
whole path runs OFFLINE, deterministically, with NO network and NO OS keychain
daemon.

WHY SecretBox over the alternatives ON THIS HOST (rigor #2, steelmen recorded):
  * OS keyring — strongest case: keeps the key out of OUR files entirely and is
    the platform-blessed store. What tipped AGAINST it here: this is a headless,
    single-writer Linux box where a keyring daemon (gnome-keyring / SecretService
    / macOS Keychain) may be absent, and the CI unit tests MUST run offline and
    deterministically with no live keychain. SecretBox needs no daemon and is
    fully test-injectable. (Not "keyring is bad" — keyring is wrong for a
    headless box + offline tests.)
  * age-encrypted file — strong, but adds an external binary / an extra Python
    dependency and a CLI shell-out; SecretBox is already satisfied by PyNaCl,
    which the venv ships (1.5.0), and is dependency-light + in-process.
  * a single SHARED platform key for all X access — operationally simpler (one
    key), but it SOCIALISES one identity's rate-limit + quota + ToS liability and
    BREAKS the BYOK legitimacy premise: the whole point is that the fetch is
    authorized under the *operator's own* developer agreement. Rejected.

────────────────────────────────────────────────────────────────────────────────
THREAT MODEL (stated plainly — what this defends, and the one it does NOT)
────────────────────────────────────────────────────────────────────────────────
  * DEFENDS disk theft of ``antiek.duckdb`` / the repo / a backup: the key never
    sits in the DB or the tree in plaintext — only the SecretBox ciphertext does,
    and the master key lives in a separate ``0600`` file. A stolen disk WITHOUT
    the key file yields ciphertext only. (A test asserts the plaintext key
    substring is ABSENT from the raw artifact bytes.)
  * DEFENDS log / event-log leakage: the decrypted value is returned only as a
    redacting :class:`SecretStr`, and this module never passes the plaintext to a
    logger, ``print``, or ``emit_typed``.
  * DOES NOT DEFEND root on the live box at decrypt time: a process that has
    loaded the master key and called ``.reveal()`` holds the plaintext in memory,
    which root can read. This store raises the bar against disk theft and
    accidental logging, NOT against an adversary already root on the running box.
    Stated honestly; not overclaimed.

Metadata is non-secret by design (cred_id / handle / pipeline_kind) and is stored
alongside the ciphertext so :mod:`runtime.byok.pipelines` can list credentials
without ever touching the key.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import nacl.exceptions
import nacl.secret
import nacl.utils

from runtime.byok.secret_str import SecretStr

_DEFAULT_ARTIFACT_NAME = "credentials.enc"
_KEY_SIZE = nacl.secret.SecretBox.KEY_SIZE  # 32
_KEY_FILE_MODE = 0o600
_BOUND_CREDENTIAL_VERSION = 2
_BINDING_PERSON = b"antiek-byok-v2"

_ENV_ARTIFACT = "ANTIEK_BYOK_ARTIFACT"
_ENV_KEY_FILE = "ANTIEK_BYOK_KEY_FILE"


def _byok_dir() -> Path:
    return Path(__file__).resolve().parent


def _default_artifact_path() -> str:
    env = os.environ.get(_ENV_ARTIFACT)
    if env:
        return os.path.expanduser(env)
    return str(_byok_dir() / _DEFAULT_ARTIFACT_NAME)


def _default_key_file() -> str:
    env = os.environ.get(_ENV_KEY_FILE)
    if env:
        return os.path.expanduser(env)
    return str(_byok_dir() / "byok_master.key")


@dataclass(frozen=True)
class CredentialMetadata:
    """The NON-SECRET record for one stored credential. Never carries the key."""

    cred_id: str
    account_handle: str
    pipeline_kind: str | None = None
    binding_version: int = 1
    artifact_fingerprint: str = ""


class CredentialIntegrityError(ValueError):
    """Stored credential bytes no longer match their authenticated identity."""


def _bound_key(
    master: bytes,
    *,
    cred_id: str,
    account_handle: str,
    pipeline_kind: str | None,
) -> bytes:
    """Derive a SecretBox key bound to one immutable credential identity."""
    identity = json.dumps(
        {
            "account_handle": account_handle,
            "cred_id": cred_id,
            "pipeline_kind": pipeline_kind,
            "version": _BOUND_CREDENTIAL_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.blake2b(
        identity,
        key=master,
        digest_size=nacl.secret.SecretBox.KEY_SIZE,
        person=_BINDING_PERSON,
    ).digest()


def _artifact_fingerprint(record: dict[str, object]) -> str:
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _load_master_key(key_bytes: bytes | None, key_file: str | None) -> bytes:
    """Resolve the 32-byte master key.

    Precedence: an explicitly injected ``key_bytes`` (tests) wins; otherwise read
    the ``0600`` key file, creating it (with a fresh random key) on first use. The
    key is NEVER stored in the encrypted artifact or the DB.
    """
    if key_bytes is not None:
        if len(key_bytes) != _KEY_SIZE:
            raise ValueError(f"master key must be {_KEY_SIZE} bytes")
        return key_bytes
    kf = key_file or _default_key_file()
    path = Path(kf)
    if path.exists():
        data = path.read_bytes()
        if len(data) != _KEY_SIZE:
            raise ValueError(f"key file {kf} is not {_KEY_SIZE} bytes")
        return data
    key = nacl.utils.random(_KEY_SIZE)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _KEY_FILE_MODE)
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    os.chmod(str(path), _KEY_FILE_MODE)
    return key


def _read_artifact(artifact_path: str) -> dict:
    p = Path(artifact_path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def _write_artifact(artifact_path: str, data: dict) -> None:
    p = Path(artifact_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def store_credential(
    account_handle: str,
    secret: str,
    *,
    pipeline_kind: str | None = None,
    artifact_path: str | None = None,
    key_bytes: bytes | None = None,
    key_file: str | None = None,
) -> str:
    """Encrypt ``secret`` at rest and return a non-secret ``cred_id``.

    ``secret`` is the operator's own X API key / bearer token (a plaintext str).
    It is sealed with SecretBox (fresh nonce) and only the ciphertext + the
    non-secret metadata land on disk. The plaintext is never logged, never
    emitted, never written to the artifact.
    """
    if not isinstance(secret, str) or secret == "":
        raise ValueError("secret must be a non-empty str")
    handle = account_handle.lstrip("@")
    artifact = artifact_path or _default_artifact_path()
    master = _load_master_key(key_bytes, key_file)
    cred_id = f"cred-x-{uuid.uuid4().hex[:16]}"
    box = nacl.secret.SecretBox(
        _bound_key(
            master,
            cred_id=cred_id,
            account_handle=handle,
            pipeline_kind=pipeline_kind,
        )
    )
    sealed = box.encrypt(secret.encode("utf-8"))

    data = _read_artifact(artifact)
    data[cred_id] = {
        "cred_id": cred_id,
        "account_handle": handle,
        "pipeline_kind": pipeline_kind,
        "binding_version": _BOUND_CREDENTIAL_VERSION,
        "ciphertext_hex": bytes(sealed).hex(),
    }
    _write_artifact(artifact, data)
    return cred_id


def load_credential(
    cred_id: str,
    *,
    artifact_path: str | None = None,
    key_bytes: bytes | None = None,
    key_file: str | None = None,
) -> SecretStr:
    """Decrypt the credential for ``cred_id`` and return it as a redacting
    :class:`SecretStr` (the plaintext is reachable only via ``.reveal()``).

    Raises ``KeyError`` if ``cred_id`` is unknown. The decrypted plaintext is
    NEVER logged / emitted by this function — it is handed back wrapped.
    """
    artifact = artifact_path or _default_artifact_path()
    data = _read_artifact(artifact)
    rec = data.get(cred_id)
    if not isinstance(rec, dict) or rec.get("cred_id") != cred_id:
        raise KeyError(f"unknown cred_id: {cred_id}")
    try:
        account_handle = rec["account_handle"]
        pipeline_kind = rec.get("pipeline_kind")
        binding_version = rec.get("binding_version", 1)
        if not isinstance(account_handle, str) or (
            pipeline_kind is not None and not isinstance(pipeline_kind, str)
        ):
            raise CredentialIntegrityError("credential metadata is invalid")
        if not isinstance(binding_version, int) or isinstance(binding_version, bool):
            raise CredentialIntegrityError("credential binding version is invalid")
        master = _load_master_key(key_bytes, key_file)
        if binding_version == _BOUND_CREDENTIAL_VERSION:
            key = _bound_key(
                master,
                cred_id=cred_id,
                account_handle=account_handle,
                pipeline_kind=pipeline_kind,
            )
        elif binding_version == 1:
            # Legacy credentials remain readable for non-routing consumers.
            # New user-model route authority requires v2 below its own seam.
            key = master
        else:
            raise CredentialIntegrityError("credential binding version is unsupported")
        sealed = bytes.fromhex(rec["ciphertext_hex"])
        plaintext = nacl.secret.SecretBox(key).decrypt(sealed).decode("utf-8")
    except (KeyError, TypeError, ValueError, nacl.exceptions.CryptoError) as exc:
        if isinstance(exc, CredentialIntegrityError):
            raise
        raise CredentialIntegrityError("credential integrity check failed") from exc
    return SecretStr(plaintext)


def list_credentials(
    *,
    artifact_path: str | None = None,
) -> list[CredentialMetadata]:
    """List the NON-SECRET metadata for every stored credential. Never decrypts,
    never touches the key — safe to call from a config/listing surface."""
    artifact = artifact_path or _default_artifact_path()
    data = _read_artifact(artifact)
    out: list[CredentialMetadata] = []
    for cred_id, rec in data.items():
        if (
            not isinstance(rec, dict)
            or rec.get("cred_id") != cred_id
            or not isinstance(rec.get("account_handle"), str)
            or (
                rec.get("pipeline_kind") is not None
                and not isinstance(rec.get("pipeline_kind"), str)
            )
        ):
            continue
        binding_version = rec.get("binding_version", 1)
        if not isinstance(binding_version, int) or isinstance(binding_version, bool):
            continue
        out.append(
            CredentialMetadata(
                cred_id=cred_id,
                account_handle=rec["account_handle"],
                pipeline_kind=rec.get("pipeline_kind"),
                binding_version=binding_version,
                artifact_fingerprint=_artifact_fingerprint(rec),
            )
        )
    out.sort(key=lambda m: m.cred_id)
    return out


__all__ = [
    "CredentialMetadata",
    "CredentialIntegrityError",
    "store_credential",
    "load_credential",
    "list_credentials",
]
