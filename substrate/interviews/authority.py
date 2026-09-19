"""Strict composite authority for consent-sensitive interview state."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

INTERVIEW_AUTHORITY_VERSION = 1
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


def interview_account_digest(account_id: str) -> str:
    account_id = _valid(account_id, "account_id")
    return hashlib.sha256(
        f"antiek-interview-authority-v1\0account\0{account_id}".encode()
    ).hexdigest()


@dataclass(frozen=True)
class InterviewAccountAuthority:
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
        object.__setattr__(self, "account_digest", interview_account_digest(account_id))

    def project(self, project_id: str) -> InterviewProjectAuthority:
        return InterviewProjectAuthority(self, project_id)

    def interview(self, interview_id: str) -> InterviewAuthority:
        return InterviewAuthority(self, interview_id)

    def owns_digest(self, candidate: object) -> bool:
        return isinstance(candidate, str) and hmac.compare_digest(
            candidate, self.account_digest
        )


@dataclass(frozen=True)
class InterviewProjectAuthority:
    account: InterviewAccountAuthority
    project_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.account, InterviewAccountAuthority):
            raise ValueError("interview account authority is invalid")
        object.__setattr__(self, "project_id", _valid(self.project_id, "project_id"))

    @property
    def account_id(self) -> str:
        return self.account.account_id

    @property
    def account_digest(self) -> str:
        return self.account.account_digest


@dataclass(frozen=True)
class InterviewAuthority:
    account: InterviewAccountAuthority
    interview_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.account, InterviewAccountAuthority):
            raise ValueError("interview account authority is invalid")
        object.__setattr__(self, "interview_id", _valid(self.interview_id, "interview_id"))

    @property
    def account_id(self) -> str:
        return self.account.account_id

    @property
    def account_digest(self) -> str:
        return self.account.account_digest

    @property
    def recovery_scope(self) -> str:
        return hashlib.sha256(
            f"antiek-interview-margin-recovery-v1\0{self.account_digest}\0{self.interview_id}".encode()
        ).hexdigest()


def operator_interview_account_authority() -> InterviewAccountAuthority:
    return InterviewAccountAuthority(
        LOCAL_OPERATOR_ACCOUNT, local_operator_compatibility=True
    )


__all__ = [
    "INTERVIEW_AUTHORITY_VERSION",
    "LOCAL_OPERATOR_ACCOUNT",
    "InterviewAccountAuthority",
    "InterviewAuthority",
    "InterviewProjectAuthority",
    "interview_account_digest",
    "operator_interview_account_authority",
]
