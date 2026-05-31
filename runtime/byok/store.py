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

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import nacl.secret
import nacl.utils

from runtime.byok.secret_str import SecretStr

_DEFAULT_ARTIFACT_NAME = "credentials.enc"
_KEY_SIZE = nacl.secret.SecretBox.KEY_SIZE  # 32
_KEY_FILE_MODE = 0o600

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
    pipeline_kind: Optional[str] = None


def _load_master_key(key_bytes: Optional[bytes], key_file: Optional[str]) -> bytes:
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
    pipeline_kind: Optional[str] = None,
    artifact_path: Optional[str] = None,
    key_bytes: Optional[bytes] = None,
    key_file: Optional[str] = None,
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
    box = nacl.secret.SecretBox(master)
    sealed = box.encrypt(secret.encode("utf-8"))
    cred_id = f"cred-x-{uuid.uuid4().hex[:16]}"

    data = _read_artifact(artifact)
    data[cred_id] = {
        "cred_id": cred_id,
        "account_handle": handle,
        "pipeline_kind": pipeline_kind,
        "ciphertext_hex": bytes(sealed).hex(),
    }
    _write_artifact(artifact, data)
    return cred_id


def load_credential(
    cred_id: str,
    *,
    artifact_path: Optional[str] = None,
    key_bytes: Optional[bytes] = None,
    key_file: Optional[str] = None,
) -> SecretStr:
    """Decrypt the credential for ``cred_id`` and return it as a redacting
    :class:`SecretStr` (the plaintext is reachable only via ``.reveal()``).

    Raises ``KeyError`` if ``cred_id`` is unknown. The decrypted plaintext is
    NEVER logged / emitted by this function — it is handed back wrapped.
    """
    artifact = artifact_path or _default_artifact_path()
    data = _read_artifact(artifact)
    rec = data.get(cred_id)
    if rec is None:
        raise KeyError(f"unknown cred_id: {cred_id}")
    master = _load_master_key(key_bytes, key_file)
    box = nacl.secret.SecretBox(master)
    sealed = bytes.fromhex(rec["ciphertext_hex"])
    plaintext = box.decrypt(sealed).decode("utf-8")
    return SecretStr(plaintext)


def list_credentials(
    *,
    artifact_path: Optional[str] = None,
) -> list[CredentialMetadata]:
    """List the NON-SECRET metadata for every stored credential. Never decrypts,
    never touches the key — safe to call from a config/listing surface."""
    artifact = artifact_path or _default_artifact_path()
    data = _read_artifact(artifact)
    out: list[CredentialMetadata] = []
    for rec in data.values():
        out.append(
            CredentialMetadata(
                cred_id=rec["cred_id"],
                account_handle=rec["account_handle"],
                pipeline_kind=rec.get("pipeline_kind"),
            )
        )
    out.sort(key=lambda m: m.cred_id)
    return out


__all__ = [
    "CredentialMetadata",
    "store_credential",
    "load_credential",
    "list_credentials",
]
