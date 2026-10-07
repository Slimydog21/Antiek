"""Persist verified account subjects without changing existing graph owners.

The acct_ namespace matches account-memory/BYOT's existing email derivation.
Only successful email or stored-passkey proof may call account creation.
Roles are resolved separately from deployment policy, never from this store.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import stat
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .passkeys import PasskeyCredential

_MAX_STORE_BYTES = 8 * 1024 * 1024


class AccountStoreError(RuntimeError):
    """Value-free account storage failure; not an authentication success."""


@dataclass(frozen=True)
class Account:
    user_id: str
    email: str
    legacy_owner: str | None = None


def open_signup_enabled() -> bool:
    """Rollout is explicit; an unset flag retains the operator-only service."""
    return os.environ.get("ANTIEK_OPEN_SIGNUP", "").strip() == "1"


def legacy_operator_email() -> str | None:
    """Only an explicit deployment binding may retain the shared legacy owner."""
    value = os.environ.get("ANTIEK_LEGACY_OPERATOR_EMAIL", "").strip().casefold()
    return value or None


def _normalized_email(email: str) -> str:
    if not email.isascii():
        raise AccountStoreError("account identity unavailable")
    value = email.strip().casefold()
    local, separator, domain = value.partition("@")
    if not local or not separator or not domain or "@" in domain or len(value) > 320:
        raise AccountStoreError("account identity unavailable")
    return value


def _subject(email: str) -> str:
    return "acct_" + hashlib.sha256(email.encode("utf-8")).hexdigest()[:32]


def account_store_path() -> Path:
    configured = os.environ.get("ANTIEK_ACCOUNT_STORE", "").strip()
    if configured:
        return Path(configured).expanduser()
    # The hardened service admits writes in ANTIEK_STATE_DIR, not its home.
    base = os.environ.get("ANTIEK_STATE_DIR", "").strip() or os.environ.get("ANTIEK_HOME", "").strip()
    return (Path(base).expanduser() if base else Path.home() / ".antiek") / "auth/accounts.json"


def account_registry_active() -> bool:
    """Closing signup does not erase existing subjects or downgrade their roles."""
    if open_signup_enabled():
        return True
    try:
        account_store_path().lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True  # An inaccessible store is not the legacy local escape.
    return True


@contextmanager
def _locked_store() -> Iterator[Path]:
    path = account_store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield path
        finally:
            os.close(fd)
    except OSError as exc:
        raise AccountStoreError("account storage unavailable") from exc


def _read(path: Path) -> list[Account]:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return []
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_STORE_BYTES:
            raise AccountStoreError("account storage unavailable")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            raw = handle.read(_MAX_STORE_BYTES + 1)
        if len(raw) > _MAX_STORE_BYTES:
            raise AccountStoreError("account storage unavailable")
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or type(payload.get("version")) is not int
            or payload["version"] != 1
        ):
            raise AccountStoreError("account storage unavailable")
        rows = payload.get("accounts")
        if not isinstance(rows, list):
            raise AccountStoreError("account storage unavailable")
        accounts = []
        emails: set[str] = set()
        subjects: set[str] = set()
        legacy_assigned = False
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"user_id", "email", "legacy_owner"}:
                raise AccountStoreError("account storage unavailable")
            email, subject, legacy = row["email"], row["user_id"], row["legacy_owner"]
            if not isinstance(email, str) or not isinstance(subject, str):
                raise AccountStoreError("account storage unavailable")
            if email != _normalized_email(email) or subject != _subject(email):
                raise AccountStoreError("account storage unavailable")
            if email in emails or subject in subjects or legacy not in (None, "__operator__"):
                raise AccountStoreError("account storage unavailable")
            if legacy is not None:
                if legacy_assigned:
                    raise AccountStoreError("account storage unavailable")
                legacy_assigned = True
            emails.add(email)
            subjects.add(subject)
            accounts.append(Account(subject, email, legacy))
        return accounts
    except (ValueError, TypeError) as exc:
        raise AccountStoreError("account storage unavailable") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def _write(path: Path, accounts: list[Account]) -> None:
    raw = (
        json.dumps({"version": 1, "accounts": [asdict(a) for a in accounts]}, separators=(",", ":"))
        + "\n"
    ).encode()
    if len(raw) > _MAX_STORE_BYTES:
        raise AccountStoreError("account storage unavailable")
    temporary = path.with_name(path.name + ".tmp-" + secrets.token_hex(12))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def account_for_verified_email(email: str, *, legacy_operator_email: str | None = None) -> Account:
    """Create after proof, preserving the sole explicitly verified legacy operator.

    The alias can be assigned once. A later allowlist change cannot transfer it
    to a second person. No document rows or passkeys are migrated here.
    """
    normalized = _normalized_email(email)
    with _locked_store() as path:
        accounts = _read(path)
        existing = next((a for a in accounts if a.email == normalized), None)
        if existing is not None:
            return existing
        legacy = None
        if (
            legacy_operator_email is not None
            and normalized == _normalized_email(legacy_operator_email)
            and not any(a.legacy_owner is not None for a in accounts)
        ):
            legacy = "__operator__"
        account = Account(_subject(normalized), normalized, legacy)
        if any(a.user_id == account.user_id for a in accounts):
            raise AccountStoreError("account identity unavailable")
        _write(path, [*accounts, account])
        return account


def account_for_session(user_id: str, email: str) -> Account | None:
    normalized = _normalized_email(email)
    with _locked_store() as path:
        return next(
            (a for a in _read(path) if a.user_id == user_id and a.email == normalized), None
        )


def account_for_email(email: str) -> Account | None:
    """Existing-account lookup for sign-in eligibility; never creates a subject."""
    normalized = _normalized_email(email)
    with _locked_store() as path:
        return next((a for a in _read(path) if a.email == normalized), None)


def account_for_verified_legacy_passkey(
    credential: PasskeyCredential, *, operator_emails: Collection[str],
) -> Account | None:
    """Retain the original owner after stored-key WebAuthn verification.

    The caller must first complete authentication against the stored public
    credential. Configuration and client-supplied email are not proof. A
    retained credential email, when present, must match current original
    operator policy. Existing subjects and aliases are never rebound.
    """
    if credential.user_id != "__operator__":
        return None
    retained = legacy_operator_email()
    if retained is None:
        return None
    email = _normalized_email(retained)
    if email not in operator_emails:
        return None
    if credential.email is not None and (
        not isinstance(credential.email, str) or _normalized_email(credential.email) != email
    ):
        return None
    with _locked_store() as path:
        accounts = _read(path)
        existing = next((a for a in accounts if a.email == email), None)
        if existing is not None:
            return existing if existing.legacy_owner == "__operator__" else None
        if any(a.legacy_owner is not None for a in accounts):
            return None
        account = Account(_subject(email), email, "__operator__")
        if any(a.user_id == account.user_id for a in accounts):
            raise AccountStoreError("account identity unavailable")
        _write(path, [*accounts, account])
        return account


def legacy_account_for_session(email: str) -> Account | None:
    """Resolve an old operator session only after an explicit persisted binding.

    This lookup never creates an account or migrates a credential. Email proof
    must have established the alias first, and current deployment policy must
    still name that exact retained email.
    """
    normalized = _normalized_email(email)
    if normalized != legacy_operator_email():
        return None
    with _locked_store() as path:
        return next(
            (a for a in _read(path) if a.email == normalized and a.legacy_owner == "__operator__"),
            None,
        )
