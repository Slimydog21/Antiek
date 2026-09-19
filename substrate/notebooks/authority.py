"""Account-qualified authority for private authored notebooks."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

NOTEBOOK_AUTHORITY_VERSION = 1
LOCAL_OPERATOR_ACCOUNT = "__operator__"
MAX_ID_BYTES = 512


def _valid(value: str, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\x00" in value
        or len(value.encode("utf-8")) > MAX_ID_BYTES
    ):
        raise ValueError(f"{field_name} is invalid")
    return value


def notebook_account_digest(account_id: str) -> str:
    """Return the stable opaque storage partition for one account."""

    account_id = _valid(account_id, "account_id")
    message = f"antiek-notebook-authority-v1\0account\0{account_id}".encode()
    return hashlib.sha256(message).hexdigest()


@dataclass(frozen=True)
class NotebookAccountAuthority:
    """Request-derived authority over one account's notebook collection."""

    account_id: str
    local_operator_compatibility: bool = field(default=False, repr=False)
    account_digest: str = field(init=False)

    def __post_init__(self) -> None:
        account_id = _valid(self.account_id, "account_id")
        if not isinstance(self.local_operator_compatibility, bool):
            raise ValueError("local operator compatibility is invalid")
        if self.local_operator_compatibility and account_id != LOCAL_OPERATOR_ACCOUNT:
            raise ValueError("local operator compatibility account is invalid")
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "account_digest", notebook_account_digest(account_id))

    def notebook(self, notebook_id: str) -> NotebookAuthority:
        return NotebookAuthority(self, notebook_id)

    def owns_digest(self, candidate: object) -> bool:
        return isinstance(candidate, str) and hmac.compare_digest(
            candidate, self.account_digest
        )


@dataclass(frozen=True)
class NotebookAuthority:
    """Composite authority and storage identity for one display notebook ID."""

    account: NotebookAccountAuthority
    notebook_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.account, NotebookAccountAuthority):
            raise ValueError("notebook account authority is invalid")
        object.__setattr__(self, "notebook_id", _valid(self.notebook_id, "notebook_id"))

    @property
    def account_id(self) -> str:
        return self.account.account_id

    @property
    def account_digest(self) -> str:
        return self.account.account_digest

    @property
    def storage_identity(self) -> tuple[str, str]:
        return self.account_digest, self.notebook_id

    @property
    def recovery_scope(self) -> str:
        payload = (
            f"antiek-notebook-recovery-v1\0{self.account_digest}\0{self.notebook_id}"
        ).encode()
        return hashlib.sha256(payload).hexdigest()


def operator_notebook_account_authority() -> NotebookAccountAuthority:
    """Named compatibility adapter for unauthenticated trusted-local operation."""

    return NotebookAccountAuthority(
        LOCAL_OPERATOR_ACCOUNT,
        local_operator_compatibility=True,
    )


def operator_notebook_authority(notebook_id: str) -> NotebookAuthority:
    return operator_notebook_account_authority().notebook(notebook_id)


__all__ = [
    "LOCAL_OPERATOR_ACCOUNT",
    "NOTEBOOK_AUTHORITY_VERSION",
    "NotebookAccountAuthority",
    "NotebookAuthority",
    "notebook_account_digest",
    "operator_notebook_account_authority",
    "operator_notebook_authority",
]
